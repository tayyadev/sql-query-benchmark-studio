import json
import threading
import unittest
from http.client import HTTPConnection
from sqlbench.server import ThreadingHTTPServer, make_handler


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler())
        cls.server.daemon_threads = True
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def fetch(self, method, route, data=None, headers=None):
        conn = HTTPConnection('127.0.0.1', self.port, timeout=15)
        body = json.dumps(data) if data is not None else None
        extra = {'Content-Type': 'application/json', 'X-SqlBench-Request': '1'}
        if headers:
            extra.update(headers)
        conn.request(method, route, body=body, headers=extra)
        res = conn.getresponse()
        raw = res.read()
        outcome = (res.status, dict(res.getheaders()), raw)
        conn.close()
        return outcome

    def test_pages_and_health(self):
        for route in ('/', '/app.js', '/styles.css', '/logo.svg'):
            status, headers, raw = self.fetch('GET', route)
            self.assertEqual(status, 200)
            self.assertGreater(len(raw), 10)
            self.assertEqual(headers['X-Frame-Options'], 'DENY')
        status, _, raw = self.fetch('GET', '/api/health')
        self.assertTrue(json.loads(raw)['ok'])

    def test_demo_dataset_endpoint(self):
        status, _, raw = self.fetch('GET', '/api/demo')
        report = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertIn('ShowPlanXML', report['plan_before'])
        self.assertIn('SELECT', report['before'])

    def test_benchmark_api(self):
        status, _, raw = self.fetch('POST','/api/benchmark',
            {'sql':'SELECT COUNT(*) FROM customers', 'iterations':3, 'warmups':0})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['result']['row_count'], 1)

    def test_blocked_mutation(self):
        status, _, raw = self.fetch('POST','/api/benchmark',
            {'sql':'DELETE FROM customers', 'iterations':3})
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(raw)['error']['code'], 'input_error')

    def test_plan_comparison_api(self):
        _,_,body=self.fetch('GET','/api/demo')
        doc=json.loads(body)
        status,_,raw=self.fetch('POST','/api/plan/compare',
            {'before':doc['plan_before'], 'after':doc['plan_after']})
        self.assertEqual(status, 200)
        result=json.loads(raw)['result']
        self.assertLess(result['comparison']['estimated_cost_delta_percent'], 0)

    def test_rejects_cross_origin_and_invalid_host(self):
        for hdr in ({'Origin':'https://attacker.example'}, {'Host':'evil.example'}):
            status, _, _ = self.fetch('POST','/api/benchmark',
               {'sql':'SELECT 1', 'iterations':3},headers=hdr)
            self.assertEqual(status,403)

    def test_requires_csrf_header_and_json(self):
        status,_,_ = self.fetch('POST','/api/benchmark',
             {'sql':'SELECT 1'},headers={'X-SqlBench-Request':'0'})
        self.assertEqual(status,403)
        status,_,_ = self.fetch('POST','/api/benchmark',
             {'sql':'SELECT 1'},headers={'Content-Type':'text/plain'})
        self.assertEqual(status,415)

    def test_does_not_expose_arbitrary_files(self):
        for route in ('/sqlbench/benchmark.py', '/../../etc/passwd',
                      '/docs/SECURITY.md','/.github/workflows/ci.yml'):
            status,_,_=self.fetch('GET',route)
            self.assertEqual(status,404)

    def test_malformed_input_is_handled(self):
        status,_,raw=self.fetch('POST','/api/plan',{'xml':23})
        self.assertEqual(status,422)
        self.assertFalse(json.loads(raw)['ok'])


if __name__ == '__main__':
    unittest.main()
