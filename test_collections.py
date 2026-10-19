import tempfile
from pathlib import Path
import unittest

from collections_store import CollectionStore


def snapshot():
    return {'passage_id': 'p1', 'highlight_start': 0, 'highlight_end': 4,
            'quote': '朋友有信', 'paragraph': '朋友有信。', 'unit_id': 'u1',
            'person': '王阳明', 'work': '传习录', 'volume': '卷下', 'entry': '214',
            'section': '门人记录', 'source_url': 'https://zh.wikisource.org/wiki/test',
            'speaker_note': '归属待核对', 'quality_warning': '待核对'}


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'collections.sqlite3'
        self.store = CollectionStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_reopen(self):
        saved = self.store.add(snapshot())
        self.assertTrue(saved['created'])
        self.assertEqual(CollectionStore(self.path).list()[0]['quote'], '朋友有信')

    def test_duplicate_is_idempotent(self):
        first = self.store.add(snapshot())
        second = self.store.add(snapshot())
        self.assertEqual(first['item']['collection_id'], second['item']['collection_id'])
        self.assertFalse(second['created'])
        self.assertEqual(len(self.store.list()), 1)

    def test_cancel_and_restore(self):
        saved = self.store.add(snapshot())['item']
        self.assertTrue(self.store.cancel(saved['collection_id']))
        self.assertEqual(self.store.list(), [])
        restored = self.store.add(snapshot())
        self.assertEqual(restored['item']['collection_id'], saved['collection_id'])
        self.assertTrue(restored['created'])

    def test_unknown_cancel(self):
        self.assertFalse(self.store.cancel(999))

    def test_personal_input_not_saved(self):
        data = snapshot()
        data.update(question='PRIVATE_QUESTION', api_key='PRIVATE_KEY', explanation='PRIVATE_INTERPRETATION')
        self.store.add(data)
        item = self.store.list()[0]
        self.assertNotIn('question', item)
        self.assertNotIn('api_key', item)
        self.assertNotIn('explanation', item)
        self.assertNotIn(b'PRIVATE_', self.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
