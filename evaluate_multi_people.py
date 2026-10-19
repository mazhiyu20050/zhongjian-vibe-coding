"""Live smoke test with synthetic questions; uses local nonce, never reads provider keys."""
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent

def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = 'http://127.0.0.1:8765'
    with opener.open(base + '/api/session', timeout=10) as response:
        session = json.load(response)
    cases = [('mao', '毛泽东的观点里，我面对朋友的批评，怎样先弄清事实，再决定改什么？', '毛泽东'),
             ('wang', '王阳明怎么看朋友相处总争高低？你能告诉我先怎么做吗？', '王阳明')]
    results = []
    for name, question, expected in cases:
        request = urllib.request.Request(base + '/api/query',
            data=json.dumps({'question': question}, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json', 'X-Zhongjian-Token': session['token']})
        with opener.open(request, timeout=180) as response:
            data = json.load(response)
        cards = data['result']['cards']
        persons = [c['person'] for c in cards]
        checks = {'has_cards': bool(cards), 'named_author_only': bool(cards) and set(persons) == {expected},
                  'one_card_per_author': len(persons) == len(set(persons)),
                  'literal_quotes': all(c['paragraph'][c['highlight_start']:c['highlight_end']] == c['quote'] for c in cards),
                  'second_person': all('你' in c['explanation'] for c in cards) and bool(cards)}
        results.append({'case': name, 'checks': checks, 'cards': [
            {k: c[k] for k in ('person', 'work', 'volume', 'section', 'quote', 'explanation')} for c in cards]})
        print(name, json.dumps(checks, ensure_ascii=False), flush=True)
    path = ROOT / 'reports' / '多人物真实查询测试.json'
    path.write_text(json.dumps({'corpus_records': session['records'], 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    if not all(all(r['checks'].values()) for r in results):
        raise SystemExit(1)

if __name__ == '__main__': main()
