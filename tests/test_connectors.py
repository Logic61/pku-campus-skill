import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from campus.blackboard import parse_list, parse_timetable, Blackboard
from campus.config import CampusError, ROOT
from campus.service import Campus
from campus.store import Store, now
from campus.treehole import Treehole, normalize_post
from mcp_server import dispatch


def test_directory():
    parent = (ROOT / 'private').resolve()
    parent.mkdir(exist_ok=True)
    temp = tempfile.TemporaryDirectory(dir=parent,prefix='test-')
    assert Path(temp.name).resolve().is_relative_to(parent)
    return temp


class ParserTests(unittest.TestCase):
    def test_assignment_body_and_relative_deadline(self):
        text = '\x1b[1m> 所有作业 (包括已完成) (2) <\x1b[0m\n\n测试课程 > 作业 1 (3 天) a012\n\n要求：实现检索\n[附件] spec.pdf\n\n测试课程 > 作业 2 (已完成: 2026-10-01) b123\n正文\n'
        docs = parse_list(text,'assignment')
        self.assertEqual(len(docs),2)
        self.assertEqual(docs[0]['title'],'作业 1')
        self.assertIn('实现检索',docs[0]['text'])
        self.assertIsNone(docs[0]['dueAt'])
        self.assertEqual(docs[0]['deadlineText'],'3 天')
        self.assertTrue(docs[1]['completed'])

    def test_announcement_list_and_zero(self):
        docs = parse_list('> 课程公告 (1) <\n[ 1] 测试课程 > 实验安排 (2 个附件) ab12\n','announcement')
        self.assertEqual(docs[0]['sourceId'],'ab12')
        self.assertFalse(docs[0]['detailLoaded'])
        self.assertEqual(parse_list('> 未完成作业 (0) <\n','assignment'),[])

    def test_bad_output_is_not_an_empty_success(self):
        for text in ('登录失败','> 未完成作业 (1) <\n无法识别','> 未完成作业 (0) <\n测试 > 标题 ab12'):
            with self.assertRaises(CampusError):
                parse_list(text,'assignment')

    def test_raw_timetable(self):
        result = parse_timetable(json.dumps({'course':[{'mon':{'courseName':'测试课程(主)<br>教师：测试'}}]}))
        self.assertEqual(result[0]['weekday'],'mon')
        self.assertEqual(result[0]['slot'],1)
        self.assertNotIn('<br>',result[0]['text'])

    def test_bad_timetable(self):
        with self.assertRaises(CampusError):
            parse_timetable('{"error":"login required"}')

    def test_arbitrary_command_rejected_before_execution(self):
        with patch('campus.blackboard.subprocess.run') as run:
            with self.assertRaises(CampusError):
                Blackboard({}).run('submit')
            with self.assertRaises(CampusError):
                Blackboard({}).run('announcement_detail','ab;whoami')
            run.assert_not_called()


class TreeholeTests(unittest.TestCase):
    def test_normalization_preserves_source_and_bounded_comments(self):
        doc = normalize_post({'pid':123,'text':'测试正文','timestamp':1700000000,
                              'comment_list':[{'text':'测试评论'}]*60,'comment_total':60})
        self.assertEqual(doc['id'],'treehole:post:123')
        self.assertEqual(len(doc['comments']),30)
        self.assertFalse(doc['commentsComplete'])
        self.assertEqual(doc['visibility'],'private')

    def test_blank_credentials_never_make_a_network_request(self):
        client = Treehole({'enabled':True,'session_file':'private/no-such-test-session.json'})
        with patch.object(client,'_request') as request:
            with self.assertRaises(CampusError):
                client.search('课程')
            request.assert_not_called()

    def test_remote_search_contract(self):
        client = Treehole({'enabled':True,'token':'TEST-ONLY'})
        response = Mock()
        response.json.return_value = {'code':20000,'data':{'list':[{'pid':123,'text':'正文'}],'total':17}}
        with patch.object(client,'_request',return_value=response) as request:
            docs,total = client.search('测试',limit=3,page=2)
        self.assertEqual(total,17)
        self.assertEqual(docs[0]['sourceId'],'123')
        self.assertEqual(request.call_args.kwargs['params'],{'keyword':'测试','page':2,'limit':3,'comment_limit':5})

    def test_rejected_search_is_not_zero_results(self):
        client = Treehole({'enabled':True,'token':'TEST-ONLY'})
        response = Mock()
        response.json.return_value = {'code':401,'message':'secret token response'}
        with patch.object(client,'_request',return_value=response):
            with self.assertRaises(CampusError) as caught:
                client.search('测试')
        self.assertNotIn('secret',str(caught.exception))

    def test_live_empty_comments_shape_for_zero_reply_post(self):
        client=Treehole({'enabled':True,'token':'TEST-ONLY'})
        post=Mock();post.json.return_value={'success':True,'data':{'pid':123,'text':'测试','reply':0}}
        comments=Mock();comments.json.return_value={'success':True,'data':{}}
        with patch.object(client,'_request',side_effect=[post,comments]):
            doc=client.detail('123')
        self.assertEqual(doc['comments'],[])
        self.assertTrue(doc['commentsComplete'])
        post.json.return_value['data']['reply']=3
        with patch.object(client,'_request',side_effect=[post,comments]):
            with self.assertRaises(CampusError):
                client.detail('123')

    def test_non_pku_or_http_destination_rejected(self):
        client = Treehole({'enabled':True,'token':'TEST-ONLY'})
        with patch.object(client,'_session',return_value=Mock()) as session:
            for url in ('http://treehole.pku.edu.cn/','https://example.com/'):
                with self.assertRaises(CampusError):
                    client._request('GET',url)
            session.return_value.request.assert_not_called()

    def test_https_login_and_mobile_challenge(self):
        with test_directory() as directory:
            client = Treehole({'enabled':True,'session_file':str(Path(directory)/'session.json')})
            oauth = Mock(); oauth.json.return_value={'success':True,'token':'IAAA-TEST'}
            redirect = Mock(); redirect.status_code=302;redirect.url='https://treehole.pku.edu.cn/cas_iaaa_login'
            redirect.headers={'Location':'https://treehole.pku.edu.cn/web/#/login?token=TREE-TEST'}
            challenge=Mock();challenge.json.return_value={'success':False,'message':'请进行令牌验证'}
            with patch.object(client,'_request',side_effect=[oauth,redirect,challenge]) as request:
                self.assertEqual(client.login('test-user','test-password')['state'],'needs_mobile_token')
                self.assertTrue(all(call.args[1].startswith('https://') for call in request.call_args_list))
            verified=Mock();verified.json.return_value={'success':True,'token':'VERIFIED-TEST'}
            ready=Mock();ready.json.return_value={'success':True}
            with patch.object(client,'_request',side_effect=[verified,ready]) as request:
                self.assertEqual(client.verify_mobile('123456')['state'],'ready')
                self.assertEqual(request.call_args_list[0].kwargs['data'],{'code':'123456'})
            self.assertTrue(client.session_path.exists())


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = test_directory()
        self.store = Store(Path(self.temp.name)/'test.sqlite3')
        self.config={'blackboard':{'enabled':True},'treehole':{'enabled':True},'agent':{'allow_private':True}}
        self.service=Campus(config=self.config,store=self.store)

    def tearDown(self):
        self.temp.cleanup()

    def doc(self,identity='blackboard:assignment:abc',text='测试课程 内容'):
        return {'id':identity,'source':'blackboard','kind':'assignment','title':'测试作业','text':text,'fetchedAt':now()}

    def test_bound_parameter_search_and_chinese(self):
        self.store.put([self.doc()])
        self.assertEqual(self.store.search('测试课程',['blackboard'],10)[1],1)
        self.assertEqual(self.store.search("' OR 1=1 --",['blackboard'],10)[1],0)

    def test_disabled_source_never_exposes_cached_private_data(self):
        self.store.put([self.doc()])
        self.config['agent']['allow_private']=False
        result=self.service.search('',sources=['blackboard'],live_treehole=False)
        self.assertEqual(result['items'],[])
        with self.assertRaises(CampusError):
            self.service.get_document('blackboard:assignment:abc',live=False)

    def test_sync_failure_retains_previous_kind(self):
        self.store.put([self.doc()])
        with patch.object(self.service.blackboard,'status',return_value={'state':'configured'}), \
             patch.object(self.service.blackboard,'fetch',side_effect=CampusError('timeout','测试超时')):
            result=self.service.sync_blackboard()
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['results']),3)
        self.assertIsNotNone(self.store.get('blackboard:assignment:abc'))

    def test_remote_comment_match_is_not_lost_to_local_filter(self):
        doc={'id':'treehole:post:123','source':'treehole','kind':'post','title':'正文','text':'正文','fetchedAt':now()}
        with patch.object(self.service.treehole,'search',return_value=([doc],5)):
            result=self.service.search('只存在未预览评论中的词',sources=['treehole'])
        self.assertEqual(result['items'][0]['id'],'treehole:post:123')
        self.assertEqual(result['treeholeRemoteTotal'],5)

    def test_invalid_arguments(self):
        for kwargs in ({'limit':0},{'limit':True},{'offset':-1},{'sources':['unknown']},{'live_treehole':'false'}):
            with self.assertRaises(CampusError):
                self.service.search(**kwargs)


class MCPTests(unittest.TestCase):
    def test_stdio_roundtrip_real_process(self):
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'campus_search','arguments':{'query':'网球','sources':['activities']}}}]
        process=subprocess.run([sys.executable,str(ROOT/'mcp_server.py')],
            input=('\n'.join(json.dumps(m) for m in messages)+'\n').encode(),capture_output=True,timeout=15)
        self.assertEqual(process.returncode,0,process.stderr.decode(errors='replace'))
        responses=[json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses),3)
        self.assertIn('campus_find_high_comments',{tool['name'] for tool in responses[1]['result']['tools']})
        result=responses[2]['result']
        self.assertFalse(result['isError'])
        self.assertGreater(len(result['structuredContent']['items']),0)

    def test_argument_and_method_errors(self):
        response=dispatch({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'campus_status','arguments':{'password':'NO-LEAK'}}})
        self.assertTrue(response['result']['isError'])
        self.assertNotIn('NO-LEAK',json.dumps(response))
        self.assertEqual(dispatch({'jsonrpc':'2.0','id':2,'method':'missing'})['error']['code'],-32601)
