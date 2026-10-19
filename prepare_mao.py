"""Import existing local Mao primary texts, never persona/AI summaries as quotations."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
from corpus import OUTPUT, ROOT

DEFAULT_SOURCE = Path.home() / '.codex/skills/mao/knowledge/mao-source-library'

def extract_body(raw, title):
    marker = re.search(r'(?m)^正文[：:]\s*\n', raw)
    if not marker:
        raise ValueError('missing_body_marker')
    lines = raw[marker.end():].splitlines()
    # Headers/navigation/footnotes are metadata, never quote candidates.
    body, notes = [], []
    in_notes = False
    for line in lines:
        line = line.strip()
        if not line or line == '>' or re.match(r'^\|?\s*上一页\s', line):
            continue
        if re.match(r'^(?:注释|注　释|注　　释|注释：|〔\d+〕|\[\d+\])', line):
            in_notes = True
        if in_notes:
            notes.append(line)
            continue
        if not body and (line == title or re.sub(r'\[\d+\]|〔\d+〕', '', line) == title):
            continue
        if not body and re.fullmatch(r'[（(]一九[^）)]{3,25}[）)]', line):
            continue
        if line.startswith(('（这是毛泽东', '(这是毛泽东', '根据中央档案馆保存的', '根据毛泽东手稿刊印')):
            notes.append(line)
            continue
        body.append(line)
    return '\n\n'.join(body).strip(), '\n'.join(notes)

def build(source=DEFAULT_SOURCE):
    q = json.loads((source / 'qstheory-index.json').read_text(encoding='utf-8'))
    w = json.loads((source / 'mzdbl-text-index.json').read_text(encoding='utf-8'))
    records, skipped, seen = [], [], set()
    snapshots = ROOT / 'data' / 'raw' / 'mao'
    guides = json.loads((ROOT / 'data' / 'mao_frameworks.json').read_text(encoding='utf-8'))['frameworks']
    for index, family in ((q, 'selected'), (w, 'collected')):
        for item in index:
            if family == 'collected' and not re.fullmatch(r'wenji-[1-8]', item.get('collection', '')):
                continue
            if not item.get('has_text') or item['title'] in ('出版说明', '目录', '题解'):
                skipped.append({'file': item['file'], 'reason': 'editorial_or_empty'})
                continue
            origin = source / item['file']
            raw = origin.read_text(encoding='utf-8')
            text, notes = extract_body(raw, item['title'])
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            if len(text) < 30 or digest in seen:
                skipped.append({'file': item['file'], 'reason': 'short_or_duplicate'})
                continue
            seen.add(digest)
            target = snapshots / item['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            collection = item.get('volume') or item['collection_name']
            volume = re.search(r'第[一二三四五六七八]卷', collection).group()
            sid = hashlib.sha256(item['source_url'].encode()).hexdigest()[:16]
            records.append({'id': 'mao-' + sid, 'person': '毛泽东',
                'work': '毛泽东选集' if family == 'selected' else '毛泽东文集',
                'volume': volume, 'section': item['title'], 'entry': '', 'kind': 'source',
                'frameworks': [g['name'] for g in guides if any(title in item['title'] for title in g['articles'])],
                'text': text, 'notes_text': notes, 'source_url': item['source_url'],
                'source_name': item['source'], 'source_file': str(target.relative_to(ROOT)),
                'source_sha256': hashlib.sha256(origin.read_bytes()).hexdigest(), 'text_sha256': digest,
                'source_page': item.get('page'), 'text_reviewed': False,
                'speaker_note': '历史文章、讲话或书信，包含引文；区分作者论述与所引用的他人话语。',
                'quality_warning': '从本机已有文本导入，尚未逐字对照印本；保留历史语境，不把政治军事语汇直接套到私人关系。'})
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('duplicate_source_ids')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / 'mao.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
    report = {'source_directory': str(source), 'records': len(records),
              'volumes': dict(Counter(r['work'] + r['volume'] for r in records)),
              'characters': sum(len(r['text']) for r in records), 'skipped': skipped,
              'status': 'local_import_not_full_manual_proofreading',
              'scope': '毛泽东选集一至四卷的本地网页分页文本、毛泽东文集一至八卷的本地篇目文本',
              'cleaning': '剥离文件元信息、网页翻页、可辨识的注释与编辑说明；保留原文，不用AI改写正文。'}
    (OUTPUT / 'mao_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    report = build(args.source)
    print(json.dumps({k: report[k] for k in ('records', 'volumes', 'characters')}, ensure_ascii=False))
