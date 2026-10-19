import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from query import make_passages, finalize_answer
from test_query import source
from test_agent import tool, final
from agent import AgentService
from collections_store import CollectionStore


class AnswerFormatTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{**source('立志而行。'), 'id':f'unit{i}'} for i in range(4)]
        self.passages = make_passages(self.rows)
        self.aliases = {f'P{i}':p['id'] for i,p in enumerate(self.passages,1)}
        self.card = {'passage_id':'P1','quote_id':'Q1','explanation':'你可以在具体事情中立志。'}

    def test_single_card_object_is_normalized(self):
        result = finalize_answer({'cards':self.card,'synthesis':'你可以认真做眼前的事。'},self.passages,self.aliases)
        self.assertEqual(result['cards'][0]['quote'],'立志而行。')

    def test_empty_cards_null_is_normalized(self):
        result = finalize_answer({'cards':None,'synthesis':'你指的是事业目标，还是生活态度？'},self.passages,self.aliases)
        self.assertEqual(result['cards'],[])

    def test_sentence_array_is_joined_not_reinvented(self):
        result = finalize_answer({'cards':[],'synthesis':['你不必急着二选一。','先看自己愿担起什么。']},[],{})
        self.assertEqual(result['synthesis'],'你不必急着二选一。\n先看自己愿担起什么。')

    def test_four_proposals_are_checked_then_grouped_by_author(self):
        cards = [{**self.card,'passage_id':f'P{i}'} for i in range(1,5)]
        result = finalize_answer({'cards':cards,'synthesis':'你可以这样看。'},self.passages,self.aliases)
        self.assertEqual(len(result['cards']),1)
        self.assertEqual(result['author_cards_removed'],3)
        cards[-1]['quote_id']='Q999'
        with self.assertRaises(ValueError):
            finalize_answer({'cards':cards,'synthesis':'你可以这样看。'},self.passages,self.aliases)

    def test_structured_prose_is_not_silently_stringified(self):
        with self.assertRaises(ValueError):
            finalize_answer({'cards':[],'synthesis':{'invented':'内容'}},[],{})

    def test_two_repairs_work_and_diagnostics_do_not_store_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock(side_effect=[tool('search_sources',{'terms':['立志']}),
                {'role':'assistant','content':'{"cards":['},
                {'role':'assistant','content':json.dumps({'cards':[],'synthesis':{'private':'私人内容'}})},
                final([self.card],text='你可以从认真做一件小事开始。')])
            service = AgentService(self.rows,CollectionStore(Path(tmp)/'db.sqlite3'),client,Path(tmp)/'tools.jsonl')
            result = service.ask('私人问题：该立大志还是平安随心？')['result']
            self.assertEqual(len(result['cards']),1)
            self.assertEqual(client.call_count,4)
            diagnostic=(Path(tmp)/'answer_validation.jsonl').read_text(encoding='utf-8')
            self.assertNotIn('私人',diagnostic)
            self.assertIn('synthesis_type',diagnostic)


if __name__ == '__main__':
    unittest.main()
