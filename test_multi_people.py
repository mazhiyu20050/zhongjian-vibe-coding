import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from agent import AgentService, Session
from collections_store import CollectionStore
from corpus import load_library, ROOT
from prepare_mao import extract_body
from query import make_passages, retrieve, finalize_answer, address_reader
from test_query import source

class MultiPeopleTests(unittest.TestCase):
    def test_second_person_style_guard(self):
        self.assertEqual(address_reader('先把事实列出来。'), '你先把事实列出来。')
        self.assertEqual(address_reader('你可以先观察。'), '你可以先观察。')
        self.assertEqual(address_reader('注意力容易被输赢占满。'), '注意力容易被输赢占满。')
    def test_import_cleans_headers_notes_navigation(self):
        raw = '标题：实践论\n正文：\n实践论\n（一九三七年七月）\n你要知道，须在实践中检验。\n〔1〕这是注释。\n上一页 1 2 下一页\n'
        body, notes = extract_body(raw, '实践论')
        self.assertEqual(body, '你要知道，须在实践中检验。')
        self.assertIn('注释', notes)
        self.assertNotIn('上一页', notes)

    def test_real_library_has_twelve_mao_volumes_and_primary_titles(self):
        rows = [r for r in load_library() if r['person'] == '毛泽东']
        self.assertEqual(len(rows), 965)
        self.assertEqual(len({(r['work'], r['volume']) for r in rows}), 12)
        for title in ('实践论', '矛盾论', '反对本本主义', '论持久战', '新民主主义论', '论十大关系', '关于正确处理人民内部矛盾的问题'):
            self.assertTrue(any(title in r['section'] for r in rows), title)
        for row in rows:
            self.assertTrue(row['text'].strip())
            self.assertEqual(hashlib.sha256((ROOT / row['source_file']).read_bytes()).hexdigest(), row['source_sha256'])
            self.assertNotIn('上一页 1 2', row['text'])
        self.assertTrue(any('矛盾分析' in r['frameworks'] for r in rows))

    def test_both_scripts_and_people_retrievable(self):
        a = source('朋友之間當謙下，批評亦須反己。')
        b = {**a, 'id': 'mao-test', 'person': '毛泽东', 'text': '批评和自我批评，要从实际调查入手。', 'work': '毛泽东选集'}
        hits = retrieve(make_passages([a, b]), ['批评', '調查'])
        self.assertEqual({p['person'] for p in hits}, {'王阳明', '毛泽东'})
        self.assertIn('批评', next(p for p in hits if p['person'] == '王阳明')['matched_terms'])

    def test_one_card_per_author_keeps_people_separate(self):
        a = source('朋友当谦下。')
        b = {**a, 'id': 'unit2', 'text': '朋友须互相学习。'}
        c = {**a, 'id': 'mao-test', 'person': '毛泽东', 'text': '你要调查。'}
        ps = make_passages([a, b, c])
        aliases = {f'P{i}': p['id'] for i, p in enumerate(ps, 1)}
        answer = finalize_answer({'cards': [{'passage_id': k, 'quote_id': 'Q1', 'explanation': '你先了解具体情况。'} for k in aliases], 'synthesis': '你可以这样试。'}, ps, aliases)
        self.assertEqual([c['person'] for c in answer['cards']], ['王阳明', '毛泽东'])
        self.assertEqual(answer['author_cards_removed'], 1)

    def test_named_person_filter_and_person_metadata(self):
        a = source('朋友需要批评。')
        b = {**a, 'id': 'mao-test', 'person': '毛泽东', 'text': '批评要有根据。'}
        with tempfile.TemporaryDirectory() as folder:
            service = AgentService([a, b], CollectionStore(Path(folder) / 'c.sqlite3'), Mock())
            state = Session('test', requested_people=('毛泽东',))
            result = service._tool(state, 'search_sources', {'terms': ['批评']}, None)
        self.assertEqual({s['person'] for s in result['sources']}, {'毛泽东'})

if __name__ == '__main__': unittest.main()
