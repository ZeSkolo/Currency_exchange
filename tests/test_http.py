import unittest, tempfile, threading, urllib.request, urllib.error, json
from pathlib import Path
import server

class HTTPTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB = str(Path(cls.tmp.name) / 'test.db')
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, headers=None, body=b'{}'):
        return urllib.request.Request(self.url + '/api', data=body, headers=headers or {})

    def test_health(self):
        self.assertEqual(json.load(urllib.request.urlopen(self.url + '/health'))['status'], 'ok')

    def test_post_guard(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.request())
        self.assertEqual(e.exception.code, 403)

    def test_foreign_origin(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.request({'X-Local-Client': '1', 'Content-Type': 'application/json', 'Origin': 'https://untrusted.example'}))
        self.assertEqual(e.exception.code, 403)

    def test_private_files(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.url + '/.data/app.sqlite3')
        self.assertEqual(e.exception.code, 404)

    def test_malformed_json(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.request({'X-Local-Client': '1', 'Content-Type': 'application/json'}, b'{'))
        self.assertEqual(e.exception.code, 400)
