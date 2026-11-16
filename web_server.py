"""Loopback-only UI for the existing query pipeline; no public deployment."""
import argparse
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
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
from recommendations import RecommendationStore, people_catalog
from people_discovery import search_people, discover_skill
from discovery_jobs import DiscoveryJobs
from conversations import ConversationStore
from conversation_outline import outline_events, outline
from person_profiles import read_profile, portrait_bytes, stage_profile

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
        self.outline_cache = {}
        self.outline_lock = threading.Lock()
        self.outline_pending = set()
        self.slots = threading.BoundedSemaphore(2)
        self.recommendations = RecommendationStore(self.collections.path)
        self.conversations = ConversationStore(self.collections.path)
        self.discovery_lock = threading.Lock()
        self.discovered_people = {}; self.project_folder_selections = {}
        self.discovery_jobs = DiscoveryJobs(self.collections.path.parent,lambda q:search_people(q),lambda p,f:discover_skill(p,f))

    def server_close(self):
        self.discovery_jobs.close()
        super().server_close()
        if self.collection_tmp:
            self.collection_tmp.cleanup()


class Handler(BaseHTTPRequestHandler):
    allow_fixed_person_preview = False

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
                  '/style.css': ('style.css', 'text/css; charset=utf-8'),
                  '/people.js': ('people.js', 'text/javascript; charset=utf-8'),
                  '/shell.js': ('shell.js', 'text/javascript; charset=utf-8'),
                  '/shell.css': ('shell.css', 'text/css; charset=utf-8'),
                  '/agents.js': ('agents.js', 'text/javascript; charset=utf-8'),
                  '/agents.css': ('agents.css', 'text/css; charset=utf-8'),
                  '/outline.js': ('outline.js', 'text/javascript; charset=utf-8'),
                  '/outline.css': ('outline.css', 'text/css; charset=utf-8'),
                  '/portrait-credits': ('portraits/credits.html', 'text/html; charset=utf-8'),
                  '/people.css': ('people.css', 'text/css; charset=utf-8')}
        if parsed.path in assets:
            filename, mime = assets[parsed.path]
            return self.send(200, (ROOT / 'web' / filename).read_bytes(), mime)
        if parsed.path.startswith('/portraits/'):
            name=parsed.path[len('/portraits/'):]
            if '/' in name or '\\' in name or not name.endswith(('.jpg','.png','.webp')):
                return self.send(404,{'error':'not_found'})
            path=ROOT/'web'/'portraits'/name
            if not path.is_file():return self.send(404,{'error':'not_found'})
            mime='image/png' if name.endswith('.png') else 'image/webp' if name.endswith('.webp') else 'image/jpeg'
            return self.send(200,path.read_bytes(),mime)
        if parsed.path.startswith('/person-portraits/'):
            name=parsed.path[len('/person-portraits/'):]
            match=re.fullmatch(r'(Q[1-9][0-9]{0,12})\.(jpg|png|webp)',name)
            if not match or not any(p['wikidata_id']==match[1] for p in self.active_people()):
                return self.send(404,{'error':'not_found'})
            raw=portrait_bytes(self.server.collections.path.parent,name)
            if raw is None:return self.send(404,{'error':'not_found'})
            return self.send(200,raw,{'jpg':'image/jpeg','png':'image/png','webp':'image/webp'}[match[2]])
        if parsed.path=='/api/agents':
            if not self.authorized():return
            manifest=ROOT/'web'/'portraits'/'manifest.json'
            portraits=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
            agents=[]
            for p in self.active_people():
                profile=read_profile(self.server.collections.path.parent,p['wikidata_id'])
                # Curated text and image beat a freshly fetched candidate.
                bio=({k:v for k,v in profile.items() if v and k!='portrait'}
                     if not p.get('biography') else {})
                bundled=portraits.get(p['person'])
                if bundled and Path(bundled.get('url','')).stem!=p['wikidata_id']:
                    bundled=None
                agents.append({**p,**bio,'portrait':bundled or profile.get('portrait')})
            return self.send(200,{'agents':agents})
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
        if parsed.path=='/api/people/jobs':
            if not self.authorized():return
            return self.send(200,{'jobs':self.server.discovery_jobs.list()})
        if parsed.path=='/api/projects':
            if not self.authorized():return
            return self.send(200,{'projects':self.server.conversations.projects()})
        if parsed.path=='/api/conversations':
            if not self.authorized():return
            cid=parse_qs(parsed.query).get('id',[None])[0]
            if cid:
                conversation=self.server.conversations.get(cid)
                if not conversation:return self.send(404,{'message':'这条对话尚未找到。'})
                conversation['turns']=[{**t,'result':with_display({'result':t['result']})['result']} for t in conversation['turns']]
                return self.send(200,conversation)
            return self.send(200,{'items':self.server.conversations.list()})
        if parsed.path in ('/api/people','/api/preferences'):
            if not self.authorized():return
            if parsed.path=='/api/preferences':return self.send(200,self.server.recommendations.read())
            people=people_catalog()
            available={r['person'] for r in self.server.rows}
            q=parse_qs(parsed.query).get('q',[''])[0][:80].casefold()
            return self.send(200,{'people':[{**p,'ready':p['person'] in available} for p in people
                if not q or q in ' '.join([p['person'],*p.get('aliases',[]),*p.get('tags',[])]).casefold()]})
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
        if self.path not in ('/api/query', '/api/source/details', '/api/conversations/outline', '/api/collections/add', '/api/collections/cancel', '/api/session/reset', '/api/preferences', '/api/people/discover', '/api/people/skill', '/api/people/jobs', '/api/people/jobs/select', '/api/projects', '/api/conversations/move', '/api/projects/rename', '/api/projects/reveal', '/api/conversations/pin', '/api/projects/folder', '/api/projects/status','/api/conversations/manage','/api/conversations/branch','/api/conversations/window','/api/projects/manage'):
            return self.send(404, {'error': 'not_found'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'json_required'})
        try:
            data = json.loads(raw_body)
            if not isinstance(data, dict):
                return self.send(400, {'error': 'invalid_body'})
            if self.path=='/api/conversations/outline':
                return self.conversation_outline(data)
            if self.path=='/api/conversations/window':
                opener=getattr(self.server,'open_conversation_window',None)
                cid=data.get('id')
                if opener is None:return self.send(404,{'message':'此入口仅在桌面版可用。'})
                if not self.server.conversations.get(cid):return self.send(404,{'message':'对话不存在。'})
                opener(cid)
                return self.send(200,{'ok':True})
            if self.path in ('/api/conversations/manage','/api/conversations/branch'):
                try:
                    store=self.server.conversations
                    if self.path.endswith('/branch'):
                        return self.send(201,{'id':store.branch(data.get('id'))})
                    store.manage(data.get('id'),data.get('field'),data.get('value'))
                    return self.send(200,{'ok':True})
                except ValueError:return self.send(400,{'message':'请检查对话或输入内容。'})
            if self.path=='/api/projects/folder':
                try:
                    from project_folders import choose_folder
                    folder=choose_folder()
                    if not folder:return self.send(200,{'cancelled':True})
                    folder=str(Path(folder).resolve());selection=secrets.token_hex(16)
                    selections=self.server.project_folder_selections
                    if len(selections)>=8:selections.pop(next(iter(selections)))
                    selections[selection]=folder
                    return self.send(200,{'selection_id':selection,'path':folder,'name':Path(folder).name[:40]})
                except Exception:return self.send(500,{'message':'文件夹选择窗口打开失败，请重试。'})
            if self.path=='/api/projects/manage':
                try:
                    changed=self.server.conversations.manage_project(data.get('id'),data.get('action'),data.get('value'))
                    return self.send(200,{'ok':True,'changed':changed})
                except ValueError:return self.send(400,{'message':'请检查项目或操作。'})
            if self.path=='/api/projects/status':
                try:
                    self.server.conversations.project_status(data.get('id'),data.get('status'))
                    return self.send(200,{'ok':True})
                except ValueError:return self.send(400,{'message':'请检查项目状态。'})
            if self.path in ('/api/projects/rename','/api/projects/reveal','/api/conversations/pin', '/api/projects/folder', '/api/projects/status'):
                try:
                    store=self.server.conversations
                    if self.path.endswith('/rename'):store.rename_project(data.get('id'),data.get('name'))
                    elif self.path.endswith('/pin'):store.pin(data.get('id'),data.get('pinned'))
                    else:
                        folder=store.project_folder(data.get('id'))
                        if os.name!='nt':return self.send(400,{'message':'此入口适用于 Windows 资源管理器。'})
                        os.startfile(str(folder))
                    return self.send(200,{'ok':True})
                except ValueError:return self.send(400,{'message':'请检查项目或对话。'})
                except OSError:return self.send(500,{'message':'打开目录时出错，请稍后重试。'})
            if self.path in ('/api/projects','/api/conversations/move'):
                try:
                    if self.path=='/api/projects':
                        selection=data.get('selection_id');folder=None
                        if selection is not None:
                            if not isinstance(selection,str) or selection not in self.server.project_folder_selections:raise ValueError('invalid_selection')
                            folder=self.server.project_folder_selections[selection]
                        result=self.server.conversations.create_project(data.get('name'),folder)
                        if selection:self.server.project_folder_selections.pop(selection,None)
                        return self.send(201,result)
                    self.server.conversations.move(data.get('conversation_id'),data.get('project_id'))
                    return self.send(200,{'moved':True})
                except ValueError:return self.send(400,{'message':'请检查项目名称或对话。'})
            if self.path=='/api/preferences':
                try:return self.send(200,self.server.recommendations.save(data.get('selected')))
                except ValueError:return self.send(400,{'message':'请选择人物列表中的人物。'})
            if self.path in ('/api/people/jobs','/api/people/jobs/select'):
                try:
                    manager=self.server.discovery_jobs
                    job=manager.choose(data.get('id'),data.get('wikidata_id')) if self.path.endswith('/select') else manager.start(data.get('query'),data.get('retry') is True)
                    return self.send(202,{'job':job})
                except ValueError:return self.send(400,{'message':'请填写姓名，或选择已核验的人物。'})
                except RuntimeError:return self.send(429,{'message':'后台任务较多，请稍后再试。'})
            if self.path in ('/api/people/discover','/api/people/skill'):
                if not self.server.discovery_lock.acquire(blocking=False):
                    return self.send(429,{'message':'正在查询人物资料，请稍后。'})
                try:
                    if self.path.endswith('/discover'):
                        items=search_people(data.get('query'))
                        if len(self.server.discovered_people)>128:self.server.discovered_people.clear()
                        for p in items:self.server.discovered_people[p['wikidata_id']]=p
                        return self.send(200,{'people':items,'note':'人物存在不表示一定有可用Skill；请选择正确的同名人物。'})
                    person=self.server.discovered_people.get(data.get('wikidata_id'))
                    if not person:return self.send(400,{'message':'请先联网检验人物并选择身份。'})
                    storage=self.server.collections.path.parent
                    result=discover_skill(person,storage/'skills-incoming')
                    if result['status']=='downloaded_pending_review':
                        try:result={**result,'profile':stage_profile(person,storage)}
                        except (OSError,ValueError):pass
                    return self.send(200,result)
                except ValueError:
                    return self.send(400,{'message':'请输入1至80字的人名。'})
                except Exception:
                    return self.send(502,{'message':'人物库或Skill来源暂时连接异常，请稍后重试。'})
                finally:self.server.discovery_lock.release()
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
            cid=data.get('conversation_id')
            self.server.conversations.validate_project(data.get('project_id'))
            conversation=self.server.conversations.get(cid) if cid else None
            if cid and not conversation:return self.send(404,{'message':'请重新选择历史对话，或新建对话。'})
            agent_person=data.get('agent_person')
            if conversation:
                if agent_person is not None and agent_person!=conversation.get('agent_person'):
                    return self.send(409,{'message':'切换人物请新建对话。'})
                agent_person=conversation.get('agent_person')
            if agent_person is not None and (not isinstance(agent_person,str) or agent_person not in {p['person'] for p in people_catalog()}):
                return self.send(400,{'message':'请选择已接入的人物。'})
            branch_context=data.get('branch_context','')
            if not isinstance(branch_context,str) or len(branch_context)>2000:
                return self.send(400,{'message':'原对话背景过长或格式有误。'})
            branch_entry=bool(not cid and agent_person and data.get('branch_entry') is True)
            if not branch_entry:branch_context=''
        except (ValueError, UnicodeError):
            return self.send(400, {'error': 'invalid_json'})
        if self.server.engine is None:
            return self.send(503, {'error': 'key_not_configured', 'message': '后台尚未加载密钥，请通过启动脚本打开。'})
        if agent_person and not self.server.agent and not self.allow_fixed_person_preview:
            return self.send(503,{'message':'专属人物服务尚未就绪。'})
        if not self.server.slots.acquire(blocking=False):
            return self.send(429, {'error': 'busy', 'message': '当前查询较多，请稍后再试。'})
        try:
            if self.server.agent:
                sid=conversation.get('session_id') if conversation else data.get('session_id')
                if conversation:sid=self.server.agent.resume_history(sid,conversation['turns'],agent_person)
                person_options={'branch_entry':True,'branch_context':branch_context} if branch_entry else {}
                answer = self.server.agent.ask(question.strip(), sid, agent_person=agent_person, **person_options) if agent_person else self.server.agent.ask(question.strip(), sid)
                answer={**answer,'mode':'live_agent'}
            else:
                result = self.answer_from_engine(question.strip(),agent_person)
                answer={'result':result,'mode':'live'}
            try:
                answer['conversation_id']=self.server.conversations.append(cid,question.strip(),answer['result'],answer.get('session_id'),agent_person,data.get('project_id'))
            except (sqlite3.Error,OSError,ValueError):
                answer['history_warning']='回答已完成，本机历史暂未保存。'
            self.send(200,answer)
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

    def answer_from_engine(self, question, agent_person):
        return self.server.engine(question)

    def active_people(self):
        from person_skills import load_skills
        skills=load_skills()
        available={r['person'] for r in self.server.rows}
        return [p for p in people_catalog() if p['person'] in skills and p['person'] in available]

    def conversation_outline(self, data):
        conversation = self.server.conversations.get(data.get('id'))
        if not conversation:
            return self.send(404, {'message': '这段对话还没有保存的内容。'})
        events = outline_events(conversation['turns'])
        client = self.server.detail_client
        if not client or not events:
            return self.send(200, outline(events))
        cache_key = (conversation['id'], len(conversation['turns']), id(client))
        with self.server.outline_lock:
            cached = self.server.outline_cache.get(cache_key)
            pending = cache_key in self.server.outline_pending
            if cached is None and not pending:
                self.server.outline_pending.add(cache_key)
        if cached is not None:
            return self.send(200, cached)
        if pending:
            return self.send(429, {'message': '正在整理这段对话，请稍后重试。'})
        try:
            if not self.server.slots.acquire(blocking=False):
                return self.send(429, {'message': '服务正在回答其他问题，请稍后重试。'})
            try:
                result = outline(events, client)
            except Exception:
                result = outline(events)
            finally:
                self.server.slots.release()
            with self.server.outline_lock:
                if result['mode'] == 'ai' and self.server.detail_client is client:
                    if len(self.server.outline_cache) >= 32:
                        self.server.outline_cache.pop(next(iter(self.server.outline_cache)))
                    self.server.outline_cache[cache_key] = result
            return self.send(200, result)
        finally:
            with self.server.outline_lock:
                self.server.outline_pending.discard(cache_key)

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


def create_server(port=8765, key='', model='deepseek-flash', storage=None, server_class=LocalServer):
    """Shared web/desktop backend; desktop supplies its writable user directory."""
    storage = Path(storage) if storage else ROOT / '.local'
    rows = load_library()
    server = server_class(('127.0.0.1', port), rows, None, storage / 'collections.sqlite3')
    configure_server(server, key, model, storage)
    return server


def configure_server(server, key, model, storage):
    client = make_model_client(key, model) if key else None
    agent = None
    if key:
        def call_agent(messages, **options):
            return complete(key, model, messages, max_tokens=4096, thinking={'type': 'disabled'},
                            response_format={'type': 'json_object'}, **options)
        agent = AgentService(server.rows, server.collections, call_agent,
                             Path(storage) / 'logs' / 'agent_tools.jsonl',
                             skill_routing=True, advice_tendencies=True, recommendations=server.recommendations)
    server.engine = (lambda question: query(question, server.rows, client)) if key else None
    server.detail_client = client
    server.agent = agent
    server.model_name = model if key else None
    server.detail_cache.clear()
    with server.outline_lock:
        server.outline_cache.clear()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    server = create_server(args.port, key, os.environ.get('DEEPSEEK_MODEL') or 'deepseek-flash', ROOT / '.local')
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
