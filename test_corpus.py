import unittest
from corpus import clean_wikitext, split_records, search_records


class CorpusTests(unittest.TestCase):
    def test_markup(self):
        text, notes = clean_wikitext('{{header|notes={{Textquality|25%}}}}\n<u>先生</u>曰：[[心學|心学]]。<ref>现代注释</ref>')
        self.assertEqual(text, '先生曰：心学。')
        self.assertEqual(notes, ['现代注释'])

    def test_variants(self):
        self.assertEqual(clean_wikitext('答-{云}-。')[0], '答云。')

    def test_numbered_units_and_offsets(self):
        raw = '{{header}}\n==徐愛引言==\n序文\n==以下門人徐愛錄==\n===1===\n先生曰：知行。\n===2===\n問學。\n==註釋==\n{{reflist}}'
        records = split_records(raw, '传习录', '卷上')
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]['kind'], 'editorial')
        self.assertEqual(records[1]['entry'], '1')
        for record in records:
            self.assertEqual(raw[record['raw_start']:record['raw_end']], record['raw_text'])
            self.assertNotIn('reflist', record['text'])

    def test_daxuewen_afterword(self):
        records = split_records('{{header}}\n陽明子曰：一體。\n\n曰：何也？\n\n德洪曰：教典也。', '大学问', '')
        self.assertEqual(records[-1]['kind'], 'editorial')
        self.assertEqual(records[-1]['speaker_note'], '钱德洪跋语，非王阳明直接发言')
        self.assertNotIn('德洪曰', records[0]['text'])

    def test_no_noise_as_content(self):
        self.assertEqual(clean_wikitext('<!--说明-->{{明朝作品}}[[Category:作品]]')[0], '')

    def test_search_excludes_editorial(self):
        rows = [{'text': '省察', 'kind': 'editorial'}, {'text': '省察克治', 'kind': 'source'}]
        self.assertEqual(len(search_records(rows, ['省察'])), 1)

    def test_empty_query(self):
        self.assertEqual(search_records([], []), [])


if __name__ == '__main__':
    unittest.main()
