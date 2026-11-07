import argparse, json, os, sqlite3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from core import run
ROOT = Path(__file__).resolve().parent
DB = os.environ.get('PROJECT_DB', str(ROOT / '.data' / 'app.sqlite3'))

class Handler(BaseHTTPRequestHandler):

    def valid_host(self):
        host = self.headers.get('Host', '')
        return host in ['127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port), 'queue-api:' + str(self.server.server_port)]

    def send(self, status, body, kind='application/json'):
        data = json.dumps(body, allow_nan=False).encode() if kind == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Untrusted Host'})
        path = urlsplit(self.path).path
        if path == '/health':
            return self.send(200, {'status': 'ok'})
        if path == '/api':
            return self.send(200, run({'action': 'list'}, DB))
        files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'application/javascript'), '/styles.css': ('styles.css', 'text/css')}
        if path not in files:
            return self.send(404, {'error': 'Not found'})
        name, kind = files[path]
        p = ROOT / name
        if not p.is_file():
            return self.send(404, {'error': 'No browser client for this service'})
        return self.send(200, p.read_bytes(), kind)

    def do_POST(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Untrusted Host'})
        if urlsplit(self.path).path != '/api':
            return self.send(404, {'error': 'Not found'})
        origin = self.headers.get('Origin')
        expected = 'http://' + self.headers.get('Host', '')
        if self.headers.get('X-Local-Client') != '1' or (origin and origin != expected):
            return self.send(403, {'error': 'Same-origin local client required'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'JSON required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send(400, {'error': 'Invalid Content-Length'})
        if not 0 < length <= 1000000:
            return self.send(413, {'error': 'Body must be 1 byte–1 MB'})
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('JSON object required')
            if payload.get('action') == 'demo':
                raise ValueError('Demo seeding is disabled through the HTTP API')
            self.send(200, run(payload, DB))
        except (ValueError, TypeError, KeyError) as e:
            self.send(400, {'error': str(e)})
        except sqlite3.Error:
            self.send(503, {'error': 'Database unavailable; try again'})

    def log_message(self, *args):
        pass
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--container', action='store_true')
    a = p.parse_args()
    if not 1024 <= a.port <= 65535:
        raise SystemExit('Port must be 1024–65535')
    host = '0.0.0.0' if a.container else '127.0.0.1'
    print('Local reference service listening on port', a.port, flush=True)
    ThreadingHTTPServer((host, a.port), Handler).serve_forever()
