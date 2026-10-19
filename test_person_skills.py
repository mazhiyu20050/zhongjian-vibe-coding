import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from person_skills import load_skills, catalog
from agent import AgentService
from corpus import load_library
from collections_store import CollectionStore
from test_agent import tool, final
from source_details import build_details
from query import QueryStageError


class PersonSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_library()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CollectionStore(Path(self.tmp.name)/'collections.sqlite3')
        self.service = AgentService(self.rows, self.store, Mock(), skill_routing=True)
        self.state = self.service.session(None)
        self.state.topic_messages = ['我总是想得多却迟迟不行动']
        self.args = {'question_focus':'懂得却未践行','user_facts':['迟迟不行动'],
                     'selections':[{'person':'王阳明','concept_id':'wym-knowing-doing','reason':'知行合一回应懂得与行动脱节'}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_installed_skills_and_catalog_are_separate(self):
        skills = load_skills()
        self.assertTrue({'王阳明','毛泽东','弗洛伊德'} <= set(skills))
        self.assertNotIn('instructions',catalog(skills,{'王阳明'})[0])
        self.assertIn('专属解答方法',skills['王阳明']['instructions'])

    def test_personal_reflection_cannot_silently_omit_weights(self):
        self.service.advice_tendencies=True
        self.state.topic_messages=['我爱猫，但猫尿床时我狠狠打了它，事后很后悔']
        args={**self.args,'user_facts':['我爱猫'],'question_focus':'冲动伤害后的反思'}
        self.assertEqual(self.service._tool(self.state,'select_thinkers',args,None)['error'],'advice_options_required')
        args['advice_options']=['止怒','查因','补救']
        self.assertTrue(self.service._tool(self.state,'select_thinkers',args,None)['ok'])

    def test_pure_information_can_explicitly_omit_weights(self):
        self.service.advice_tendencies=True
        args={**self.args,'no_advice_reason':'只查询知行合一的概念含义，不涉及个人行动选择。'}
        self.assertTrue(self.service._tool(self.state,'select_thinkers',args,None)['ok'])

    def test_route_required_and_author_filtered(self):
        self.assertEqual(self.service._tool(self.state,'search_sources',{'terms':['行动']},None)['error'],'select_skill_first')
        selected = self.service._tool(self.state,'select_thinkers',self.args,None)
        self.assertTrue(selected['ok'])
        self.assertEqual(selected['skills'][0]['person'],'王阳明')
        hits = self.service._tool(self.state,'search_sources',{'terms':['知行']},None)
        self.assertTrue(hits['sources'])
        self.assertEqual({p['person'] for p in hits['sources']},{'王阳明'})
        self.assertEqual(len(hits['person_skills']),1)
        for hit in hits['sources']:
            passage = self.state.evidence[self.state.aliases[hit['id']]]
            for sentence in hit['sentences']:
                self.assertIn(sentence['text'],passage['text'])

    def test_invented_facts_and_cross_author_concept_rejected(self):
        bad = {**self.args,'user_facts':['你骂了朋友']}
        self.assertFalse(self.service._tool(self.state,'select_thinkers',bad,None)['ok'])
        bad = {**self.args,'selections':[{'person':'毛泽东','concept_id':'wym-knowing-doing','reason':'不匹配'}]}
        self.assertFalse(self.service._tool(self.state,'select_thinkers',bad,None)['ok'])

    def test_actual_turn_routes_before_search(self):
        client = Mock(side_effect=[tool('select_thinkers',self.args),tool('search_sources',{'terms':['知行']}),final(text='你可以从今天最小的一步开始，把明白落实到行动。')])
        self.service.call_model = client
        result = self.service.ask(self.state.topic_messages[0])['result']
        self.assertEqual([e['tool'] for e in result['tool_trace']],['select_thinkers','search_sources'])
        self.assertEqual(client.call_args_list[0].kwargs['tool_choice']['function']['name'],'select_thinkers')
        self.assertIn('知行合一',client.call_args_list[0].args[0][0]['content'])
        self.assertEqual(result['skill_route']['skills'][0]['id'],'zhongjian-wang-yangming')

    def test_model_cannot_skip_production_routing(self):
        self.service.call_model = Mock(return_value=final(text='你可以先试试。'))
        with self.assertRaises(QueryStageError) as exc:
            self.service.ask('我总是想得多却迟迟不行动')
        self.assertEqual(exc.exception.code,'skill_route_required')

    def test_short_title_is_returned(self):
        args = {**self.args, 'question_title':'懂得却迟迟不行动'}
        self.service.call_model = Mock(side_effect=[tool('select_thinkers',args),
            tool('search_sources',{'terms':['知行']}),final(text='从小事开始。')])
        result = self.service.ask(self.state.topic_messages[0])['result']
        self.assertEqual(result['question_title'],'懂得却迟迟不行动')

    def test_overlong_title_rejected(self):
        result = self.service._tool(self.state,'select_thinkers',
            {**self.args,'question_title':'很长的标题'*10},None)
        self.assertEqual(result['error'],'invalid_question_title')

    def test_long_caption_is_rewritten_before_display(self):
        card={'passage_id':'P1','quote_id':'Q1','explanation':'长篇重复解释。'*12}
        short={**card,'explanation':'准备是在行动中完成的，不是等来的。'}
        self.service.call_model=Mock(side_effect=[tool('select_thinkers',self.args),
            tool('search_sources',{'terms':['知行']}),final([card]),final([short])])
        result=self.service.ask(self.state.topic_messages[0])['result']
        self.assertEqual(result['cards'][0]['explanation'],short['explanation'])

    def test_three_relevant_authors_are_not_collapsed_to_one_or_two(self):
        args={'question_focus':'被朋友批评后的判断','user_facts':[], 'selections':[
            {'person':'王阳明','concept_id':'wym-reflection','reason':'看自身具体责任'},
            {'person':'毛泽东','concept_id':'mao-criticism','reason':'核对事实与改进'},
            {'person':'弗洛伊德','concept_id':'freud-guilt','reason':'分清过错与自我苛责'}]}
        args['advice_options']=['沟通核实','调整自己','保持距离']
        self.service.advice_tendencies=True
        calls=[]
        def client(messages,**options):
            calls.append(1)
            if len(calls)==1:return tool('select_thinkers',args)
            if len(calls)==2:return tool('search_sources',{'terms':['批评','自责']})
            output=json.loads(messages[-1]['content']);cards=[]
            for person in ('王阳明','毛泽东','弗洛伊德'):
                hit=next(s for s in output['sources'] if s['person']==person and s['sentences'])
                cards.append({'passage_id':hit['id'],'quote_id':hit['sentences'][0]['id'],
                    'explanation':'先分清事实、责任与情绪，不把批评当成人格定论。',
                    'advice_tendency':[{'option':s,'percent':p} for s,p in zip(args['advice_options'],[60,30,10])],
                    'tendency_reason':'先澄清具体事实，再辨明可以调整的部分。',
                    'translation':'内疚感与自我批评有关。'})
            return final(cards)
        self.service.call_model=client
        result=self.service.ask('朋友批评我太敏感，我该改变还是离开？')['result']
        self.assertEqual({c['person'] for c in result['cards']},{'王阳明','毛泽东','弗洛伊德'})
        self.assertEqual(len(result['cards']),3)
        for card in result['cards']:
            self.assertEqual(sum(x['percent'] for x in card['advice_tendency']),100)
            self.assertEqual([x['option'] for x in card['advice_tendency']],args['advice_options'])
            self.assertTrue(card['tendency_applicable'])

    def test_invalid_tendency_gets_specific_bounded_repair(self):
        self.service.advice_tendencies=True
        options=['继续准备','开始尝试','暂缓决定']
        args={**self.args,'advice_options':options}
        card={'passage_id':'P1','quote_id':'Q1','explanation':'先做能做到的一步，再从实际中补足认识。',
              'advice_tendency':[{'option':s,'percent':p} for s,p in zip(options,[25,65,10])],
              'tendency_reason':'原文强调知行应落到具体行为。'}
        corrected={**card,'advice_tendency':[{'option':s,'percent':p} for s,p in zip(options,[20,70,10])]}
        client=Mock(side_effect=[tool('select_thinkers',args),tool('search_sources',{'terms':['知行']}),final([card]),final([corrected])])
        self.service.call_model=client
        result=self.service.ask(self.state.topic_messages[0])['result']
        self.assertEqual([i['percent'] for i in result['cards'][0]['advice_tendency']],[20,70,10])
        self.assertEqual(client.call_count,4)
        self.assertTrue(any('percent必须是JSON整数' in m.get('content','') for m in client.call_args.args[0] if isinstance(m.get('content'),str)))

    def test_detail_loads_only_current_authors_skill(self):
        concept = self.service.thinker_profiles['毛泽东']['concepts'][0]
        pid = concept['primary_anchor']['passage_id']
        passage = next(p for p in self.service.passages if p['id']==pid)
        client = Mock(return_value={'content':json.dumps({'concept_id':concept['id'],'reading':'你可以先了解事情实际发生的经过，再判断该采纳谁的意见。','user_facts':[]})})
        result = build_details(passage,self.service.rows[passage['unit_id']],self.service.passages,client,question='我不知道该听谁的')
        system = client.call_args.args[0][0]['content']
        self.assertIn('毛泽东 · 众见专属 Skill',system)
        self.assertNotIn('王阳明 · 众见专属 Skill',system)
        self.assertEqual(result['thought_context']['skill']['person'],'毛泽东')


if __name__ == '__main__':
    unittest.main()
