from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from server import Handler


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.server.api_token='TEST-TOKEN'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,path,headers=None,method='GET'):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request(method,path,headers=headers or {})
        response=conn.getresponse()
        data=response.read()
        conn.close()
        return response.status,data

    def test_private_api_requires_bearer(self):
        self.assertEqual(self.request('/api/v1/status')[0],403)
        status,data=self.request('/api/v1/status',{'Authorization':'Bearer TEST-TOKEN'})
        self.assertEqual(status,200)
        self.assertEqual(len(json.loads(data)['sources']),3)
        self.assertNotIn(b'TEST-TOKEN',data)

    def test_origin_and_host_restricted(self):
        headers={'Authorization':'Bearer TEST-TOKEN','Origin':'https://untrusted.example'}
        self.assertEqual(self.request('/api/v1/status',headers)[0],403)
        self.assertEqual(self.request('/',{'Host':'untrusted.example'})[0],403)

    def test_html_bootstraps_local_token_and_files_not_exposed(self):
        status,data=self.request('/')
        self.assertEqual(status,200)
        self.assertIn(b'name="awe-api-token" content="TEST-TOKEN"',data)
        self.assertEqual(self.request('/private/config.toml')[0],404)

    def test_real_search_and_invalid_source(self):
        headers={'Authorization':'Bearer TEST-TOKEN'}
        status,data=self.request('/api/v1/search?q=%E7%BD%91%E7%90%83&sources=activities',headers)
        self.assertEqual(status,200)
        self.assertTrue(json.loads(data)['items'])
        self.assertEqual(self.request('/api/v1/search?sources=not-valid',headers)[0],400)
