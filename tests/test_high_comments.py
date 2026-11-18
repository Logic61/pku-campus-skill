import unittest
from unittest.mock import Mock,patch
from campus.treehole import Treehole


class HighCommentTests(unittest.TestCase):
    def response(self,rows,total=1):
        response=Mock()
        response.json.return_value={'code':20000,'data':{'list':rows,'total':total}}
        return response

    def test_threshold_and_real_count_not_preview_count(self):
        client=Treehole({'enabled':True,'token':'TEST-ONLY'})
        responses=[self.response([
            {'pid':1,'text':'测试高楼','comment_total':1001,'comment_list':[]},
            {'pid':2,'text':'边界','comment_total':100}]),
            self.response([{'pid':3,'text':'第二页','comment_total':500}])]
        with patch.object(client,'_request',side_effect=responses) as request:
            result=client.scan_high_comments(min_comments=100,pages=2)
        self.assertEqual([d['sourceId'] for d in result['items']],['1','3'])
        self.assertEqual(result['scannedUniquePosts'],3)
        self.assertEqual(request.call_count,2) # Do not stop at an unreliable total=1.
        self.assertNotIn('keyword',request.call_args.kwargs['params'])
        self.assertEqual(request.call_args.kwargs['params']['comment_limit'],0)

    def test_repeated_page_and_empty_page_terminate(self):
        for last,reason in [([{'pid':1,'text':'重复','reply':200}],'repeated_page'),([], 'empty_page')]:
            client=Treehole({'enabled':True,'token':'TEST-ONLY'})
            with patch.object(client,'_request',side_effect=[self.response([{'pid':1,'text':'测试','reply':200}]),self.response(last)]):
                result=client.scan_high_comments(pages=3)
            self.assertEqual(result['stopReason'],reason)
            self.assertEqual(result['matchedCount'],1)
