"""Small development-set evaluation; offline runs never call an API."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import urllib.error
from query import make_passages, retrieve, query, make_model_client, QueryStageError
from corpus import OUTPUT

ROOT = Path(__file__).resolve().parent


def evaluate_offline(rows, cases):
    passages = make_passages(rows)
    results = []
    for case in cases:
        hits = retrieve(passages, case['offline_terms'])
        expected = set(case['reference_entries'])
        returned = {h['entry'] for h in hits}
        results.append({
            'id': case['id'], 'topic': case['topic'], 'question': case['question'],
            'terms_origin': '人工指定，不是模型生成', 'terms': case['offline_terms'],
            'reference_entries': case['reference_entries'],
            'reference_entry_hit': bool(expected & returned) if expected else None,
            'evidence_scope': case['evidence_scope'], 'review_rule': case['review_rule'],
            'candidates': [{k: h[k] for k in ('id', 'work', 'volume', 'entry', 'text', 'source_url')}
                           for h in hits],
            'relevance_review': None, 'attribution_review': None,
        })
    return results


def evaluate_live(rows, cases, client):
    results = []
    for case in cases:
        print('正在测试：' + case['topic'])
        result = {'id': case['id'], 'question': case['question'], 'review_rule': case['review_rule'],
                  'evidence_scope': case['evidence_scope'], 'human_review': None}
        try:
            result.update(status='completed', answer=query(case['question'], rows, client))
        except QueryStageError as exc:
            result.update(status='failed', stage=exc.stage, error_code=exc.code)
        except urllib.error.HTTPError as exc:
            result.update(status='failed', error_code='http_' + str(exc.code))
        except (urllib.error.URLError, TimeoutError):
            result.update(status='failed', error_code='network_error')
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='真实模型测试，最多10次模型请求')
    parser.add_argument('--configured', action='store_true', help='使用已配置的进程密钥，执行预设批量测试')
    parser.add_argument('--case', nargs='+', help='仅执行指定的开发案例 ID')
    args = parser.parse_args()
    cases = json.loads((ROOT / 'evaluation_cases.json').read_text(encoding='utf-8'))['cases']
    if args.case:
        unknown = set(args.case) - {c['id'] for c in cases}
        if unknown:
            parser.error('存在未知的案例 ID')
        cases = [c for c in cases if c['id'] in args.case]
    rows = [json.loads(line) for line in (OUTPUT / 'wang_yangming.jsonl').read_text(encoding='utf-8').splitlines()]
    if args.live:
        print(f'将测试{len(cases)}个预设问题，最多{len(cases)*2}次API请求，有费用；问题、候选古籍片段发至DeepSeek。')
        print('本次将保存预设问题的答案与测试状态到本机logs；不保存密钥。')
        if not args.configured and input('输入 Y 继续：').strip().lower() != 'y':
            return
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if not key and not args.configured:
            key = getpass.getpass('输入新密钥（隐藏输入）：').strip()
        if not key:
            print('未输入密钥，测试取消。')
            return
        model = os.environ.get('DEEPSEEK_MODEL') or ('deepseek-flash' if args.configured else
                input('模型名称 [deepseek-flash]：').strip() or 'deepseek-flash')
        results = evaluate_live(rows, cases, make_model_client(key, model))
        mode = 'live'
        folder = ROOT / 'logs'
    else:
        results = evaluate_offline(rows, cases)
        mode = 'offline'
        folder = ROOT / 'reports'
    folder.mkdir(exist_ok=True)
    report = {'mode': mode, 'created_utc': datetime.now(timezone.utc).isoformat(),
              'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in ('query.py', 'corpus.py', 'check_api.py')},
              'limitations': '开发样本；人工参考条目不是唯一答案；离线命中不证明回答相关、引用归属或心理支持有效',
              'results': results}
    path = folder / f'evaluation_{mode}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.live:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        (folder / f'evaluation_live_{stamp}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('报告：' + str(path))
    if not args.live:
        for item in results:
            status = '参考条目已召回' if item['reference_entry_hit'] else '需检查参考条目'
            if item['reference_entry_hit'] is None:
                status = '资料不足边界案例，待检查模型是否承认局限'
            print(item['topic'] + '：' + status)
    else:
        print('已完成执行；completed只代表流程完成，回答质量需人工复核。')


if __name__ == '__main__':
    main()
