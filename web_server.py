"""Loopback-only UI for the existing query pipeline; no public deployment."""
import argparse
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import urllib.error
from urllib.parse import urlparse, parse_qs
from query import query, make_model_client, QueryStageError, make_passages
from corpus import OUTPUT, load_library
from collections_store import CollectionStore
from agent import AgentService
from check_api import complete
from presentation import with_display
from source_details import build_details

ROOT = Path(__file__).resolve().parent


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, rows, engine=None, collection_path=None):
        super().__init__(address, Handler)
        self.rows = rows
        self.by_id = {r['id']: r for r in rows}
        self.passages = {p['id']: p for p in make_passages(rows)}
        self.collection_tmp = tempfile.TemporaryDirectory() if collection_path is None else None
        self.collections = CollectionStore(collection_path if collection_path is not None else
                                           Path(self.collection_tmp.name) / 'collections.sqlite3')
        self.nonce = secrets.token_urlsafe(32)
        self.engine = engine
        self.agent = None
        self.detail_client = None
        self.detail_cache = {}
        self.slots = threading.BoundedSemaphore(2)

    def server_close(self):
        super().server_close()
        if self.collection_tmp:
            self.collection_tmp.cleanup()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log personal queries or request bodies.

    def send(self, status, value, content_type='application/json; charset=utf-8'):
        if content_type.startswith('application/json'):
            value = with_display(value)
        body = json.dumps(value, ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        port = self.server.server_port
        return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

    def authorized(self):
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',
                                     f'http://localhost:{self.server.server_port}'):
            self.send(403, {'error': 'origin_rejected'})
            return False
        token = self.headers.get('X-Zhongjian-Token', '')
        if not token.isascii() or not hmac.compare_digest(token, self.server.nonce):
            self.send(403, {'error': 'token_rejected'})
            return False
        return True

    def do_GET(self):
        if not self.trusted_host():
            return self.send(403, {'error': 'host_rejected'})
        parsed = urlparse(self.path)
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if parsed.path in assets:
            filename, mime = assets[parsed.path]
            return self.send(200, (ROOT / 'web' / filename).read_bytes(), mime)
        if parsed.path == '/api/session':
            return self.send(200, {'token': self.server.nonce, 'ready': self.server.engine is not None,
                                  'person': '、'.join(sorted({r['person'] for r in self.server.rows})), 'records': len(self.server.rows),
                                  'app':'zhongjian','model':getattr(self.server,'model_name',None)})
        if parsed.path == '/api/collections':
            if not self.authorized():
                return
            try:
                return self.send(200, {'items': self.server.collections.list()})
            except sqlite3.Error:
                return self.send(503, {'error': 'storage_error', 'message': '收藏库暂时读取异常，请稍后再试。'})
        if parsed.path == '/api/context':
            rid = parse_qs(parsed.query).get('id', [''])[0]
            row = self.server.by_id.get(rid)
            if not row or row['kind'] != 'source':
                return self.send(404, {'error': 'source_not_found'})
            return self.send(200, {k: row[k] for k in ('id', 'text', 'work', 'volume', 'section', 'entry',
                                                       'source_url', 'speaker_note', 'quality_warning')})
        if parsed.path == '/api/example':
            path = ROOT / 'logs' / 'evaluation_live.json'
            if path.exists():
                report = json.loads(path.read_text(encoding='utf-8'))
                # Only the predefined synthetic case, never arbitrary personal query history.
                case = next((c for c in report['results'] if c['id'] == 'criticism' and c['status'] == 'completed'), None)
                if case:
                    return self.send(200, {'question': case['question'], 'result': case['answer'],
                                          'mode': 'saved_example'})
            return self.send(404, {'error': 'example_not_available'})
        self.send(404, {'error': 'not_found'})

    def do_POST(self):
        if not self.trusted_host():
            return self.send(403, {'error': 'host_rejected'})
        # Read bounded input before responding, including unauthorized requests.
        # Closing a Windows socket with an unread request body can reset the
        # connection and hide the intended 403 from the client.
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16000:
                return self.send(413, {'error': 'request_too_large'})
            self.connection.settimeout(10)
            raw_body = self.rfile.read(length)
        except (ValueError, TimeoutError, OSError):
            return self.send(400, {'error': 'invalid_request_body'})
        if not self.authorized():
            return
        if self.path not in ('/api/query', '/api/source/details', '/api/collections/add', '/api/collections/cancel', '/api/session/reset'):
            return self.send(404, {'error': 'not_found'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'json_required'})
        try:
            data = json.loads(raw_body)
            if not isinstance(data, dict):
                return self.send(400, {'error': 'invalid_body'})
            if self.path == '/api/source/details':
                return self.source_details(data)
            if self.path == '/api/session/reset':
                try:
                    if self.server.agent:
                        self.server.agent.reset(data.get('session_id'))
                    return self.send(200, {'reset': True})
                except QueryStageError as exc:
                    return self.send(409, {'error': exc.code, 'message': exc.reason})
            if self.path != '/api/query':
                return self.collection_action(data)
            question = data.get('question')
            if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
                return self.send(400, {'error': 'invalid_question', 'message': '请输入1至2000字的问题。'})
        except (ValueError, UnicodeError):
            return self.send(400, {'error': 'invalid_json'})
        if self.server.engine is None:
            return self.send(503, {'error': 'key_not_configured', 'message': '后台尚未加载密钥，请通过启动脚本打开。'})
        if not self.server.slots.acquire(blocking=False):
            return self.send(429, {'error': 'busy', 'message': '当前查询较多，请稍后再试。'})
        try:
            if self.server.agent:
                answer = self.server.agent.ask(question.strip(), data.get('session_id'))
                self.send(200, {**answer, 'mode': 'live_agent'})
            else:
                result = self.server.engine(question.strip())
                self.send(200, {'result': result, 'mode': 'live'})
        except QueryStageError as exc:
            self.send(422, {'error': exc.code, 'stage': exc.stage, 'message': exc.reason,
                            'session_id': getattr(exc, 'session_id', data.get('session_id'))})
        except urllib.error.HTTPError as exc:
            self.send(502, {'error': 'provider_http_' + str(exc.code), 'message': '模型接口返回错误，请检查账户或稍后再试。',
                            'session_id': getattr(exc, 'session_id', data.get('session_id'))})
        except (urllib.error.URLError, TimeoutError) as exc:
            self.send(504, {'error': 'network_timeout', 'message': '请求超时或网络异常，请稍后重试。',
                            'session_id': getattr(exc, 'session_id', data.get('session_id'))})
        except Exception:
            self.send(500, {'error': 'internal_error', 'message': '本次查询异常，个人输入未写入日志。'})
        finally:
            self.server.slots.release()

    def source_details(self, data):
        pid = data.get('passage_id')
        passage = self.server.passages.get(pid) if isinstance(pid, str) else None
        if not passage:
            return self.send(404, {'error': 'source_not_found', 'message': '这段原文尚未收录。'})
        a, b = data.get('highlight_start'), data.get('highlight_end')
        question = data.get('question', '')
        if not isinstance(question, str) or len(question) > 2000:
            return self.send(400, {'error': 'invalid_question'})
        focus = None
        if a is not None or b is not None:
            maximum = 480 if passage.get('language')=='en' else 180
            if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(passage['text']) or b - a > maximum:
                return self.send(400, {'error': 'invalid_source_span', 'message': '原文位置有误，请重新查询。'})
            focus = passage['text'][a:b]
        cache_key = (pid, a, b, hashlib.sha256(question.encode()).hexdigest())
        if cache_key in self.server.detail_cache:
            return self.send(200, self.server.detail_cache[cache_key])
        if not self.server.detail_client:
            return self.send(503, {'error': 'key_not_configured', 'message': '详读服务尚未就绪。'})
        if not self.server.slots.acquire(blocking=False):
            return self.send(429, {'error': 'busy', 'message': '正在处理其他查询，请稍后再试。'})
        try:
            result = build_details(passage, self.server.by_id[passage['unit_id']],
                                   list(self.server.passages.values()), self.server.detail_client, focus, question)
            if len(self.server.detail_cache) >= 64:
                self.server.detail_cache.pop(next(iter(self.server.detail_cache)))
            self.server.detail_cache[cache_key] = result
            return self.send(200, result)
        except QueryStageError:
            return self.send(422, {'error': 'detail_generation_failed', 'message': '本次讲解尚未整理完整，收起后可再次展开重试。'})
        except Exception:
            return self.send(502, {'error': 'detail_service_error', 'message': '详读暂时未完成，收起后可再次展开重试。'})
        finally:
            self.server.slots.release()

    def collection_action(self, data):
        try:
            if self.path == '/api/collections/cancel':
                cid = data.get('collection_id')
                if type(cid) is not int or not 1 <= cid < 2**63:
                    return self.send(400, {'error': 'invalid_collection_id'})
                changed = self.server.collections.cancel(cid)
                return self.send(200, {'cancelled': changed})
            pid, a, b = data.get('passage_id'), data.get('highlight_start'), data.get('highlight_end')
            p = self.server.passages.get(pid) if isinstance(pid, str) else None
            if not p or type(a) is not int or type(b) is not int or not 0 <= a < b <= len(p['text']) or b-a > 180:
                return self.send(400, {'error': 'invalid_source_span', 'message': '收藏的原文位置无效，请重新查询。'})
            snapshot = {k: p[k] for k in ('unit_id', 'person', 'work', 'volume', 'entry', 'section',
                                         'source_url', 'speaker_note', 'quality_warning')}
            snapshot.update(passage_id=pid, highlight_start=a, highlight_end=b,
                            quote=p['text'][a:b], paragraph=p['text'],
                            source_sha256=self.server.by_id[p['unit_id']].get('source_sha256', ''))
            return self.send(200, self.server.collections.add(snapshot))
        except OverflowError:
            return self.send(409, {'error': 'collection_limit', 'message': '收藏已达500条，请先整理。'})
        except sqlite3.Error:
            return self.send(503, {'error': 'storage_error', 'message': '本次收藏操作未完成，请稍后重试。'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    rows = load_library()
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    engine = None
    if key:
        client = make_model_client(key, os.environ.get('DEEPSEEK_MODEL') or 'deepseek-flash')
        engine = lambda question: query(question, rows, client)
    server = LocalServer(('127.0.0.1', args.port), rows, engine, ROOT / '.local' / 'collections.sqlite3')
    server.model_name = (os.environ.get('DEEPSEEK_MODEL') or 'deepseek-flash') if key else None
    if key:
        server.detail_client = client
    if key:
        model = os.environ.get('DEEPSEEK_MODEL') or 'deepseek-flash'
        def call_agent(messages, **options):
            return complete(key, model, messages, max_tokens=4096, thinking={'type': 'disabled'},
                            response_format={'type': 'json_object'}, **options)
        server.agent = AgentService(rows, server.collections, call_agent, ROOT / 'logs' / 'agent_tools.jsonl', skill_routing=True, advice_tendencies=True)
    print(f'众见已启动：http://127.0.0.1:{server.server_port}', flush=True)
    print('只监听本机；问题与结果不自动保存；按 Ctrl+C 结束。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
