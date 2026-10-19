"""Live multi-turn development scenario against the running local server.

Uses synthetic prompts only; never opens the credential file or restarts server.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8765'
SCENARIO = [
    ('批评资料', '我被朋友批评后很难过。请检索朋友相处与批评的原文，并核对相关上下文后解释。'),
    ('查上下文', '请查看刚展示的第一张卡片的上下文，区分是谁说的，别只重复高亮句。'),
    ('提出收藏', '请收藏刚展示的第一张卡片，先让我确认。'),
    ('确认收藏', '确认'),
    ('查看收藏', '请查询我的收藏，告诉我原文及收藏编号。'),
    ('切换主题', '换个问题：我想有人陪，不确定需要朋友还是只是不想独处。请查相关资料。'),
    ('陪伴语境', '请读取这次第一条材料的上下文，区分来书者的自述和王阳明的意见。'),
    ('情绪资料', '我难过时是不是必须压住情绪，变成完全理性的人？请重新检索相关资料。'),
    ('情绪语境', '请查看刚才第一条的原文上下文，它讨论的是正常情绪还是其他事情？'),
    ('改变资料', '别人希望我改变，我怎样区分改进具体行为和否定整个自己？请另查原文。'),
    ('改变语境', '请读取本次第一条原文的上下文，指出它与现代自我价值问题的边界。'),
    ('再次查收藏', '请重新查询我的收藏，给出当前活动收藏的编号。'),
    ('提出取消', '请取消你在本次对话帮我收藏的那条原文，先让我确认。'),
    ('确认取消', '确认'),
    ('异常恢复', '请先尝试读取来源编号P999的上下文；若编号不存在，就检索关于改过和省察的真实资料继续回答。'),
]


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path, token=None):
        request = urllib.request.Request(BASE+path, headers={'X-Zhongjian-Token': token} if token else {})
        with opener.open(request, timeout=10) as response:
            return json.load(response)
    session = get('/api/session')
    token = session['token']
    def post(path, data):
        request = urllib.request.Request(BASE+path, data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'X-Zhongjian-Token': token}, method='POST')
        with opener.open(request, timeout=360) as response:
            return json.load(response)
    before = {x['collection_id'] for x in get('/api/collections', token)['items']}
    sid, results = None, []
    print('开始真实多轮场景：15个有独立用途的任务，单会话，不重启、不人工修补状态。', flush=True)
    for purpose, question in SCENARIO:
        print('任务：' + purpose, flush=True)
        try:
            answer = post('/api/query', {'question': question, 'session_id': sid})
            sid = answer['session_id']
            results.append({'purpose': purpose, 'question': question, 'status': 'completed', **answer})
            print('  工具：' + ', '.join(e['tool']+':'+e['status'] for e in answer['result'].get('tool_trace', [])), flush=True)
        except urllib.error.HTTPError as exc:
            with exc:
                error = json.load(exc)
            sid = error.get('session_id') or sid
            results.append({'purpose': purpose, 'question': question, 'status': 'failed', **error})
            print('  本轮失败：' + error.get('error', 'http_error'), flush=True)
        except (urllib.error.URLError, TimeoutError):
            results.append({'purpose': purpose, 'question': question, 'status': 'failed', 'error': 'network_error'})
            print('  网络异常，保留失败案例', flush=True)
    after = get('/api/collections', token)['items']
    # Cleanup happens AFTER the complete scenario; never alters intermediate state.
    for item in after:
        if item['collection_id'] not in before:
            post('/api/collections/cancel', {'collection_id': item['collection_id']})
    events = []
    event_path = ROOT / 'logs' / 'agent_tools.jsonl'
    if event_path.exists() and sid:
        events = [e for line in event_path.read_text(encoding='utf-8').splitlines()
                  if (e := json.loads(line))['session_id'] == sid]
    effective = [e for e in events if e['effective']]
    report = {'created_utc': datetime.now(timezone.utc).isoformat(), 'session_id': sid,
              'server_unchanged': get('/api/session')['token'] == token,
              'unique_response_sessions': sorted({r.get('session_id') for r in results if r.get('session_id')}),
              'effective_calls': len(effective), 'tool_types': sorted({e['tool'] for e in effective}),
              'tool_errors': sum(e['status'] == 'error' for e in events),
              'pending_calls_excluded': sum(e['status'] == 'needs_confirmation' for e in events),
              'development_scenario_only': True, 'results': results, 'events': events,
              'code_sha256': hashlib.sha256((ROOT/'agent.py').read_bytes()).hexdigest()}
    folder = ROOT/'logs'; folder.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for name in ('agent_live_latest.json', f'agent_live_{stamp}.json'):
        (folder/name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('effective_calls', 'tool_types', 'tool_errors', 'server_unchanged')}, ensure_ascii=False), flush=True)
    print('报告：'+str(folder/'agent_live_latest.json'), flush=True)


if __name__ == '__main__':
    main()
