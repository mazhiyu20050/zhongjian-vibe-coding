import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from corpus import load_library
from query import make_passages, quote_candidates, search_normalized, finalize_answer, ordinary_freud_quote
from thinkers import build_profiles
from agent import AgentService
from collections_store import CollectionStore
from presentation import display_card
from test_agent import tool, final


class FreudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[r for r in load_library() if r['person']=='弗洛伊德']
        cls.passages=make_passages(cls.rows)

    def test_three_books_are_real_source_not_skill_text(self):
        self.assertEqual({r['work'] for r in self.rows},{'自我与本我','超越快乐原则','文明及其不满'})
        self.assertEqual(len(self.rows),303)
        for r in self.rows:
            self.assertEqual(r['language'],'en')
            self.assertEqual(r['kind'],'source')
            self.assertIn('gutenberg.org/ebooks/',r['source_url'])
            self.assertNotIn('PROJECT GUTENBERG LICENSE',r['text'])

    def test_ordinary_confusion_does_not_get_a_patient_diagnosis_quote(self):
        self.assertFalse(ordinary_freud_quote('In two very familiar maladies the sense of guilt is over-strongly conscious.','我总是自责'))
        self.assertTrue(ordinary_freud_quote('An explanation of the normal conscious sense of guilt presents no difficulties.','我总是自责'))
        self.assertTrue(ordinary_freud_quote('In two very familiar maladies the sense of guilt is over-strongly conscious.','这段临床医学史讲什么？'))

    def test_six_concepts_have_literal_english_anchors(self):
        concepts=build_profiles(self.passages)['弗洛伊德']['concepts']
        self.assertEqual(len(concepts),6)
        lookup={p['id']:p for p in self.passages}
        for c in concepts:
            a=c['primary_anchor'];p=lookup[a['passage_id']]
            self.assertEqual(p['text'][a['start']:a['end']],a['quote'])

    def test_english_sentence_spans_and_case_insensitive_search(self):
        text='We are never so defenceless against suffering as when we love, never so forlornly unhappy as when we have lost our love-object or its love.'
        candidates=quote_candidates(text)
        self.assertEqual(candidates[0]['text'],text)
        self.assertEqual(search_normalized('Repression'),search_normalized('repression'))
        for q in quote_candidates('Word '*100):
            self.assertEqual(('Word '*100)[q['start']:q['end']],q['text'])
            self.assertLessEqual(len(q['text']),480)

    def test_chinese_translation_is_separate_from_verified_original(self):
        p=self.passages[0];raw=quote_candidates(p['text'])[0]
        translated='心里存在追求快乐的倾向，但并非所有结果都带来快乐。'
        result=finalize_answer({'cards':[{'passage_id':'P1','quote_id':raw['id'],
            'translation':translated,'explanation':'先承认愿望，再考虑现实。'}],'synthesis':''},[p],{'P1':p['id']})
        card=result['cards'][0];display=display_card(card)
        self.assertEqual(card['quote'],raw['text'])
        self.assertEqual(display['excerpt'],translated)
        self.assertTrue(display['is_translation'])

    def test_named_freud_routes_only_to_freud_and_requires_translation(self):
        args={'question_focus':'无故自责与过错的区别','user_facts':['我总在自责'],
            'question_title':'自责是否等于有错','selections':[{'person':'弗洛伊德','concept_id':'freud-guilt','reason':'分清内疚与实际过错'}]}
        card={'passage_id':'P1','quote_id':'Q1','explanation':'先分清具体责任与过度自责。'}
        client=Mock(side_effect=[tool('select_thinkers',args),tool('search_sources',{'terms':['内疚','guilt']}),
            final([card]),final([{**card,'translation':'内疚感与自我的批评作用有关。'}])])
        with tempfile.TemporaryDirectory() as d:
            service=AgentService(load_library(),CollectionStore(Path(d)/'c.sqlite3'),client,skill_routing=True)
            result=service.ask('弗洛伊德，我总在自责')['result']
        self.assertEqual({c['person'] for c in result['cards']},{'弗洛伊德'})
        self.assertTrue(result['cards'][0]['translation'])
        self.assertEqual(client.call_count,4)


if __name__=='__main__':unittest.main()
