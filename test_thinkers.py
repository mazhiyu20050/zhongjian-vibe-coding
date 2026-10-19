import json
import unittest
from unittest.mock import Mock
from corpus import load_library
from query import make_passages, QueryStageError
from thinkers import build_profiles
from source_details import build_details
from test_query import source
from agent import AgentService, Session
from collections_store import CollectionStore
import tempfile
from pathlib import Path

class ThinkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.passages = make_passages(load_library())
        cls.profiles = build_profiles(cls.passages)

    def test_core_concepts_have_real_author_anchors(self):
        lookup = {p['id']:p for p in self.passages}
        self.assertEqual(len(self.profiles['王阳明']['concepts']), 6)
        self.assertEqual(len(self.profiles['毛泽东']['concepts']), 8)
        for person, profile in self.profiles.items():
            valid = {c['id'] for c in profile['concepts']}
            for c in profile['concepts']:
                a=c['primary_anchor']; p=lookup[a['passage_id']]
                self.assertEqual(p['person'],person)
                self.assertEqual(p['text'][a['start']:a['end']],a['quote'])
                self.assertTrue(set(c['related_concepts']) <= valid)

    def test_unavailable_concept_is_not_invented(self):
        self.assertEqual(build_profiles(make_passages([source('朋友之间相互尊重。')])), {})

    def test_core_idea_can_retrieve_anchor_without_literal_keyword(self):
        row={**source('是非之心，人皆有之。'),'work':'大学问','section':'正文'}
        with tempfile.TemporaryDirectory() as folder:
            service=AgentService([row],CollectionStore(Path(folder)/'c.sqlite3'),Mock())
            output=service._tool(Session('t'), 'search_sources', {'terms':['致良知']},None)
        self.assertEqual(len(output['sources']),1)
        self.assertIn('致良知',[c['name'] for c in output['thinker_profiles'][0]['concepts']])

    def test_detail_rejects_invented_user_facts(self):
        row=source('知是行之始，行是知之成。')
        ps=make_passages([row])
        response={'reading':'你可以从知行合一理解这件事。','concept_id':'wym-knowing-doing',
                  'recommendation_type':'reframe','user_facts':['你替朋友骂了人']}
        with self.assertRaises(QueryStageError):
            build_details(ps[0],row,ps,Mock(return_value={'content':json.dumps(response)}),question='我明白道理但不敢开口。')

    def test_detail_cannot_mix_another_authors_concept(self):
        row=source('知是行之始，行是知之成。'); ps=make_passages([row])
        response={'reading':'你可以从实践理解问题。','concept_id':'mao-practice',
                  'recommendation_type':'reframe','user_facts':[]}
        with self.assertRaises(QueryStageError):
            build_details(ps[0],row,ps,Mock(return_value={'content':json.dumps(response)}),question='我不敢开口。')

    def test_detail_connects_core_idea_and_validates_book(self):
        row=source('知是行之始，行是知之成。');ps=make_passages([row])
        response={'reading':'你不必再积累一个道理，知行合一把明白和践履放在同一件事里；可以重读《传习录》这一段。',
                  'concept_id':'wym-knowing-doing','recommendation_type':'reading','user_facts':['不敢开口']}
        result=build_details(ps[0],row,ps,Mock(return_value={'content':json.dumps(response)}),question='我明白道理但不敢开口。')
        self.assertEqual(result['thought_context']['concept_id'],'wym-knowing-doing')
        self.assertTrue(result['thought_context']['primary_anchors_verified'])
        response['reading']='你应该读《不存在的心学万能答案书》。'
        with self.assertRaises(QueryStageError):
            build_details(ps[0],row,ps,Mock(return_value={'content':json.dumps(response)}),question='我明白道理但不敢开口。')

if __name__ == '__main__': unittest.main()
