from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from campus.browser_login import rust_cookies,filter_cookies,save_session,BrowserLogins,verify_treehole_response
from campus.config import ROOT,CampusError


class BrowserSessionTests(unittest.TestCase):
    def cookie(self,domain='treehole.pku.edu.cn',**kwargs):
        return {'name':'test_cookie','value':'TEST-SESSION-ONLY','domain':domain,'path':'/',
                'secure':True,'httpOnly':True,'expires':-1,**kwargs}

    def test_cookie_scope_and_expiry(self):
        cookies=[self.cookie(),self.cookie('evil.example'),self.cookie('course.pku.edu.cn'),
                 self.cookie(expires=time.time()-20)]
        self.assertEqual(len(filter_cookies(cookies,'treehole')),1)

    def test_upstream_cookie_store_shape(self):
        result=rust_cookies([self.cookie(),self.cookie('.pku.edu.cn',expires=2000000000)])
        self.assertEqual(result[0]['domain'],{'HostOnly':'treehole.pku.edu.cn'})
        self.assertEqual(result[0]['expires'],'SessionEnd')
        self.assertEqual(result[0]['path'],['/',True])
        self.assertIn('HttpOnly',result[0]['raw_cookie'])
        self.assertEqual(result[1]['domain'],{'Suffix':'pku.edu.cn'})
        self.assertIn('AtUtc',result[1]['expires'])

    def test_treehole_export_requires_token_and_preserves_old_on_failure(self):
        parent=(ROOT/'private').resolve()
        with tempfile.TemporaryDirectory(dir=parent,prefix='test-browser-') as directory:
            assert Path(directory).resolve().is_relative_to(parent)
            target=Path(directory)/'session.json'
            config={'treehole':{'session_file':str(target)}}
            save_session('treehole',[self.cookie()],'TEST-TOKEN',config,device_uuid='TEST-DEVICE',user_agent='TEST-UA')
            saved=json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(saved['loginMethod'],'browser')
            self.assertEqual(saved['uuid'],'TEST-DEVICE')
            with self.assertRaises(CampusError):
                save_session('treehole',[self.cookie()],'',config)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),saved)

    def test_real_retrieval_contract_is_login_evidence(self):
        verify_treehole_response(200,{'code':20000,'data':{'list':[],'total':0}})
        for status,data in [(200,{'success':True}), (200,{'code':40002}), (401,{}), (200,{'code':20000,'data':None})]:
            with self.assertRaises(CampusError):
                verify_treehole_response(status,data)

    def test_saved_browser_device_is_reused_with_latest_token(self):
        from campus.treehole import Treehole
        parent=(ROOT/'private').resolve()
        with tempfile.TemporaryDirectory(dir=parent,prefix='test-device-') as directory:
            assert Path(directory).resolve().is_relative_to(parent)
            target=Path(directory)/'session.json'
            config={'treehole':{'session_file':str(target)}}
            save_session('treehole',[self.cookie()],'NEW-TEST-TOKEN',config,device_uuid='TEST-DEVICE',user_agent='TEST-UA')
            client=Treehole({'session_file':str(target),'token':'OLD-TEST-TOKEN'})
            headers=client._session().headers
            self.assertEqual(headers['Uuid'],'TEST-DEVICE')
            self.assertEqual(headers['User-Agent'],'TEST-UA')
            self.assertEqual(headers['Authorization'],'Bearer NEW-TEST-TOKEN')

    def test_http_status_cannot_return_credentials(self):
        manager=BrowserLogins()
        self.assertEqual(manager.status(),{'state':'idle'})
        with self.assertRaises(CampusError):
            manager.start('https://evil.example')
        with self.assertRaises(CampusError):
            manager.finish()
