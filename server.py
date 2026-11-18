"""AWE PKU: local-first campus information desk, Python 3.11+."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
import argparse
import json
import re
import threading
import secrets
import hmac
from urllib.parse import parse_qs
from campus.config import CampusError
from campus.service import Campus
from campus.browser_login import BROWSER_LOGINS


def api_token():
    path = ROOT / 'private/http-token'
    path.parent.mkdir(exist_ok=True)
    try:
        with path.open('x',encoding='ascii') as out:
            token = secrets.token_urlsafe(32)
            out.write(token)
            return token
    except FileExistsError:
        return path.read_text(encoding='ascii').strip()

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'activities.json'
LOCK = threading.Lock()
SHANGHAI = timezone(timedelta(hours=8))


def parse_pkuknow(html):
    """Read the public page's hydration payload, without executing scripts."""
    chunks = []
    for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)</script>', html, re.S):
        try:
            chunk = json.loads(match[1])
            if len(chunk) > 1 and isinstance(chunk[1], str):
                chunks.append(chunk[1])
        except (ValueError, TypeError):
            continue
    stream = ''.join(chunks)
    decoder = json.JSONDecoder()
    for match in re.finditer(r'"items"\s*:\s*\[', stream):
        try:
            items, _ = decoder.raw_decode(stream, match.end() - 1)
        except ValueError:
            continue
        result, seen = [], set()
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get('url', '')
            if not item.get('title') or urlparse(url).scheme not in ('https', 'http'):
                continue
            identity = str(item.get('id', url))
            if identity in seen:
                continue
            seen.add(identity)
            result.append({
                'id': identity, 'title': item['title'], 'url': url,
                'source': item.get('source_name', 'PKUKnow'),
                'category': item.get('category', '校园通知'),
                'publishedAt': item.get('published_at'),
                'registration': bool(item.get('requires_registration')),
            })
        if result:
            return result
    raise ValueError('公开页面数据结构已变化，保留上次快照。')


def read_feed():
    if not DATA.exists():
        return {'items': [], 'fetchedAt': None, 'mode': 'empty'}
    return json.loads(DATA.read_text(encoding='utf-8'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Search keywords and document IDs are private; omit request lines.
        pass

    def valid_host(self):
        port = self.server.server_address[1]
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def authorized(self):
        if not self.valid_host():
            return False
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            return False
        actual = self.headers.get('Authorization','')
        expected = 'Bearer ' + self.server.api_token
        return hmac.compare_digest(actual.encode('utf-8'),expected.encode('utf-8'))

    def api(self,path,query):
        if not self.authorized():
            return self.send(403,{'error':{'code':'unauthorized','message':'需要本机 API Bearer token；网页请刷新后重试。'}})
        try:
            service = Campus()
            if path == '/api/v1/status':
                result = service.status()
            elif path == '/api/v1/login/browser':
                result = BROWSER_LOGINS.status()
            elif path == '/api/v1/treehole/high-comments':
                result = service.high_comment_posts(query.get('q',[''])[0],
                    min_comments=query.get('min_comments',[100])[0],
                    start_page=query.get('start_page',[1])[0],pages=query.get('pages',[15])[0])
            elif path == '/api/v1/search':
                result = service.search(query.get('q',[''])[0],
                    sources=query.get('sources',[','.join(('activities','blackboard','treehole'))])[0].split(','),
                    limit=query.get('limit',[10])[0], offset=query.get('offset',[0])[0],
                    live_treehole=query.get('live_treehole',['true'])[0] == 'true',page=query.get('page',[1])[0])
            elif path == '/api/v1/document':
                result = service.get_document(query.get('id',[''])[0],live=query.get('live',['true'])[0] == 'true',
                    page=query.get('page',[1])[0],limit=query.get('limit',[20])[0])
            else:
                return self.send(404,{'error':{'code':'not_found','message':'接口不存在。'}})
            self.send(200,result)
        except CampusError as exc:
            self.send(400,{'error':exc.as_dict()})
        except Exception:
            self.send(500,{'error':{'code':'internal_error','message':'本机服务异常，请运行诊断。'}})

    def send(self, status, body, mime='application/json; charset=utf-8'):
        raw = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, dict) else body
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.valid_host():
            return self.send(403,{'error':'Invalid Host'})
        path = urlparse(self.path).path
        if path.startswith('/api/v1/'):
            return self.api(path,parse_qs(urlparse(self.path).query))
        if path == '/api/feed':
            return self.send(200, read_feed())
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in files:
            return self.send(404, {'error': 'Not found'})
        name, mime = files[path]
        raw = (ROOT / 'web' / name).read_bytes()
        if name == 'index.html':
            raw = raw.replace(b'</head>',f'<meta name="awe-api-token" content="{self.server.api_token}"></head>'.encode())
        self.send(200, raw, mime)

    def do_POST(self):
        path=urlparse(self.path).path
        if path.startswith('/api/v1/login/browser/'):
            if not self.authorized():
                return self.send(403,{'error':{'code':'unauthorized','message':'需要本机 API Bearer token。'}})
            try:
                action=path.rsplit('/',1)[-1]
                result=BROWSER_LOGINS.finish() if action=='finish' else BROWSER_LOGINS.start(action)
                return self.send(200,result)
            except CampusError as exc:
                return self.send(400,{'error':exc.as_dict()})
            except Exception:
                return self.send(500,{'error':{'code':'browser_failed','message':'无法启动本机登录窗口，请检查依赖。'}})
        if urlparse(self.path).path == '/api/v1/sync/blackboard':
            if not self.authorized():
                return self.send(403,{'error':{'code':'unauthorized','message':'需要本机 API Bearer token。'}})
            try:
                return self.send(200,Campus().sync_blackboard())
            except CampusError as exc:
                return self.send(400,{'error':exc.as_dict()})
            except Exception:
                return self.send(500,{'error':{'code':'internal_error','message':'本机同步失败。'}})
        # A local page can refresh only its own fixed public source. No credentials.
        if not self.valid_host() or self.headers.get('Origin') != f'http://{self.headers.get("Host")}':
            return self.send(403, {'error': '只接受本页面发起的同步。'})
        if urlparse(self.path).path != '/api/refresh':
            return self.send(404, {'error': 'Not found'})
        if not LOCK.acquire(blocking=False):
            return self.send(409, {'error': '正在同步，请稍候。'})
        try:
            req = Request('https://pkuknow.cn/', headers={'User-Agent': 'AWE-PKU/0.1 (personal campus reader)'})
            with urlopen(req, timeout=20) as response:
                html = response.read(5_000_001)
            if len(html) > 5_000_000:
                raise ValueError('来源响应过大，保留上次快照。')
            items = parse_pkuknow(html.decode('utf-8'))
            feed = {'items': items, 'fetchedAt': datetime.now(SHANGHAI).isoformat(),
                    'mode': 'live', 'source': 'https://pkuknow.cn/'}
            DATA.parent.mkdir(exist_ok=True)
            temp = DATA.with_suffix('.tmp')
            temp.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(DATA)
            self.send(200, feed)
        except Exception as exc:
            message = '同步失败，保留已有快照。请检查网络或来源服务。'
            if 'CERTIFICATE_VERIFY_FAILED' in str(exc):
                message = '来源站点证书校验失败，已保留快照；请待站点修复证书后重试。'
            self.send(502, {'error': message})
        finally:
            LOCK.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'AWE PKU: http://127.0.0.1:{args.port}', flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.api_token = api_token()
    server.serve_forever()
