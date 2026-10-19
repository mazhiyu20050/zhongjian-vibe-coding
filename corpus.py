"""Local-only source preparation. No model calls or invented translations."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote
from person_registry import EXPANSION

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'data' / 'processed'

def load_library():
    """Explicit corpus allowlist: persona skills never become quote sources."""
    rows = []
    for filename in ('wang_yangming.jsonl', 'mao.jsonl', 'freud.jsonl',
                     *(f'additions_{slug}.jsonl' for slug in EXPANSION)):
        path = OUTPUT / filename
        if path.exists():
            rows.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate_corpus_ids')
    return rows


def clean_wikitext(raw):
    notes = re.findall(r'<ref\b[^>]*>(.*?)</ref\s*>', raw, re.S | re.I)
    text = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
    text = re.sub(r'<ref\b[^>]*>.*?</ref\s*>|<ref\b[^>]*/\s*>', '', text, flags=re.S | re.I)
    # Nested templates removed innermost first; intended for the inspected files.
    while re.search(r'\{\{[^{}]*\}\}', text):
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    text = re.sub(r'\[\[(?:Category|分類|分类):[^\]]*\]\]', '', text, flags=re.I)
    text = re.sub(r'\[\[([^\[\]]+)\]\]', lambda m: m[1].split('|')[-1], text)
    text = re.sub(r'-\{([^{}]+)\}-', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace("'''", '').replace("''", '')
    text = html.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text, notes


def split_records(raw, work, volume):
    sections = []
    # Keep entry boundaries from the original, rather than inventing page numbers.
    matches = list(re.finditer(r'(?m)^(={2,3})([^=\n]+)\1\s*$', raw))
    if work == '大学问':
        afterword = re.search(r'(?m)^德洪曰[：:]', raw)
        boundaries = [0] + ([afterword.start()] if afterword else []) + [len(raw)]
        for a, b in zip(boundaries, boundaries[1:]):
            sections.append((a, b, '正文' if a == 0 else '钱德洪跋语', '', a != 0))
    else:
        heading = ''
        for i, match in enumerate(matches):
            title = match[2].strip()
            if title in ('註釋', '注释'):
                break
            if len(match[1]) == 2:
                heading = title
            entry = title if len(match[1]) == 3 else ''
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            editorial = not entry or '引言' in heading or '序' in heading
            sections.append((match.end(), end, heading, entry, editorial))
    records = []
    for start, end, section, entry, editorial in sections:
        original = raw[start:end]
        text, notes = clean_wikitext(original)
        if not text:
            continue
        sid = hashlib.sha256(f'{work}|{volume}|{section}|{entry}|{text}'.encode()).hexdigest()[:16]
        section_text, section_notes = clean_wikitext(section)
        records.append({
            'id': 'wym-' + sid, 'person': '王阳明', 'work': work, 'volume': volume,
            'section': section_text, 'section_notes_wikitext': section_notes,
            'entry': entry, 'kind': 'editorial' if editorial else 'source',
            'speaker_note': ('钱德洪跋语，非王阳明直接发言' if work == '大学问' and editorial else
                             '序言或编者文字，非王阳明直接发言' if editorial else
                             '问答或书信原文，含提问者及引文，逐句归属待复核'),
            'text': text, 'notes_wikitext': notes, 'raw_start': start, 'raw_end': end,
            'raw_text': original, 'text_reviewed': False,
            'quality_warning': '源文件含 Textquality 25% 标记，待校对' if work == '大学问' else '转录与逐句说话人待抽查',
        })
    return records


def search_records(records, terms, limit=5):
    terms = [t.strip() for t in terms if t.strip()]
    if not terms:
        return []
    hits = []
    for row in records:
        if row['kind'] != 'source':
            continue
        matched = [term for term in terms if term in row['text']]
        if matched:
            # Keyword baseline only; explicitly not an answer-correctness score.
            score = len(matched) + sum(min(row['text'].count(t), 3) for t in matched) / 10
            hits.append({**row, 'matched_terms': matched, 'keyword_score': score})
    return sorted(hits, key=lambda r: (-r['keyword_score'], len(r['text'])))[:limit]


def build(source):
    specs = [('01-传习录', f'传习录-{v}-维基文库原文.txt', '传习录', v,
              'https://zh.wikisource.org/wiki/' + quote(f'傳習錄/{v}')) for v in ['卷上', '卷中', '卷下']]
    specs.append(('02-大学问', '大学问-维基文库原文.txt', '大学问', '',
                  'https://zh.wikisource.org/wiki/' + quote('大學問')))
    all_rows, manifest = [], []
    for folder, filename, work, volume, url in specs:
        path = source / folder / filename
        content = path.read_bytes()
        raw = content.decode('utf-8-sig')
        sha = hashlib.sha256(content).hexdigest()
        rows = split_records(raw, work, volume)
        for row in rows:
            row.update(source_file=str(path), source_sha256=sha, source_url=url,
                       attribution='王守仁及相关记录者；维基文库贡献者；见原页面历史',
                       license_url='https://creativecommons.org/licenses/by-sa/4.0/',
                       rights_note='古籍正文与维基贡献分别记录；依来源署名并保留修改说明；发布前复核具体页面',
                       license_review='site_policy_and_saved_html_checked; individual_revision_pending')
        all_rows.extend(rows)
        manifest.append({'file': filename, 'sha256': sha, 'source_url': url,
                         'records': len(rows), 'raw_characters': len(raw),
                         'revision_id': None, 'revision_status': '本地文件未记录固定修订号，暂不猜测'})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    corpus = OUTPUT / 'wang_yangming.jsonl'
    corpus.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in all_rows), encoding='utf-8')
    report = {'source_files': manifest, 'total_records': len(all_rows),
              'source_records': sum(r['kind'] == 'source' for r in all_rows),
              'editorial_records': sum(r['kind'] == 'editorial' for r in all_rows),
              'unique_ids': len({r['id'] for r in all_rows}),
              'cleaning': '移除模板、链接与展示标记；注释独立保存；原文繁体不转换；不生成译文',
              'excluded': '全书索引、作者页、HTML、人物 Skill 不作正文入库',
              'status': '清洗候选库，未完成全量校对或语义检索'}
    (OUTPUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report['unique_ids'] == report['total_records']
    for row in all_rows:
        assert not any(mark in row['text'] for mark in ('{{', '[[', '<ref', '<pages'))
        assert row['text'].strip()
    print(json.dumps({k: report[k] for k in ('total_records', 'source_records', 'editorial_records')}, ensure_ascii=False))
    return all_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--terms', nargs='+')
    args = parser.parse_args()
    if args.source:
        rows = build(args.source)
    else:
        rows = [json.loads(line) for line in (OUTPUT / 'wang_yangming.jsonl').read_text(encoding='utf-8').splitlines()]
    if args.terms:
        hits = search_records(rows, args.terms)
        report = {'method': '人工指定古文关键词的本地基线，非自动理解问题或语义 RAG',
                  'terms': args.terms, 'results': hits}
        (OUTPUT / 'search_smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for hit in hits:
            print(hit['work'], hit['volume'], hit['section'], hit['entry'], hit['matched_terms'])
            print(hit['text'][:240])


if __name__ == '__main__':
    main()
