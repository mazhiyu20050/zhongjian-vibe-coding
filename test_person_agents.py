import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
from agent import AgentService
from collections_store import CollectionStore
from conversations import ConversationStore
from corpus import load_library
from query import make_passages,QueryStageError
from presentation import with_display
from thinkers import build_profiles
from test_agent import tool,final


class PersonAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=load_library();cls.profiles=build_profiles(make_passages(cls.rows))

    def test_selected_agent_is_exclusive_even_if_question_names_another_person(self):
        calls=[];person='王阳明'
        def model(messages,**options):
            calls.append(messages)
            if len(calls)==1:
                self.assertIn('专属人物对话',messages[0]['content'])
                self.assertIn('专属人物长答',messages[0]['content'])
                self.assertIn('今晚要交小组作业',messages[0]['content'])
                self.assertNotIn('save_favorite',{tool['function']['name'] for tool in options['tools']})
                return tool('select_thinkers',{'question_focus':'面对困惑作出行动','user_facts':[],
                    'selections':[{'person':person,'concept_id':self.profiles[person]['concepts'][0]['id'],'reason':'从此人的框架审视问题'}]})
            if len(calls)==2:return tool('search_sources',{'terms':['行动','判断']})
            sources=json.loads([m['content'] for m in messages if m.get('role')=='tool'][-1])['sources']
            self.assertTrue(all(s['person']==person for s in sources))
            hit=next(s for s in sources if s['sentences'])
            return final([{'passage_id':hit['id'],'quote_id':hit['sentences'][0]['id'],'viewpoint_title':'先检验眼前这一念',
                           'explanation':'你先检查眼前的判断，再做一件具体的事，不必拿他人的评价代替自己的省察。'}])
        with tempfile.TemporaryDirectory() as tmp:
            service=AgentService(self.rows,CollectionStore(Path(tmp)/'db.sqlite3'),model,skill_routing=True)
            response=service.ask('毛泽东会怎样看待我的困惑？',agent_person=person,
                                 branch_entry=True,branch_context='今晚要交小组作业。')
            self.assertEqual([c['person'] for c in response['result']['cards']],[person])
            self.assertEqual(service.session(response['session_id']).agent_person,person)
            with self.assertRaises(QueryStageError):service.ask('继续',response['session_id'],agent_person='毛泽东')

    def test_history_preserves_selected_agent_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db.sqlite3';store=ConversationStore(path)
            cid=store.append(None,'怎样行动',{'cards':[]},'expired',agent_person='王阳明')
            history=ConversationStore(path).get(cid)
            service=AgentService(self.rows,CollectionStore(path),Mock(),skill_routing=True)
            sid=service.resume_history(history['session_id'],history['turns'],history['agent_person'])
            self.assertEqual(service.session(sid).agent_person,'王阳明')

    def test_single_person_analysis_is_not_cut_to_a_brief_summary(self):
        analysis='先把心里的顾虑和已经发生的事分开。\n别等到一点也不怕再动身。\n在现场先做一步，回来按实情复盘。'
        result={'agent_person':'王阳明','synthesis':analysis,'cards':[]}
        self.assertEqual(with_display({'result':result})['result']['display_reply'],analysis)
        result.pop('agent_person')
        self.assertNotEqual(with_display({'result':result})['result']['display_reply'],analysis)

    def test_existing_database_is_migrated_without_losing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db.sqlite3'
            db=sqlite3.connect(path)
            with db:
                db.execute('CREATE TABLE conversations (id TEXT PRIMARY KEY,title TEXT NOT NULL,updated_at REAL NOT NULL,session_id TEXT)')
                db.execute('INSERT INTO conversations VALUES (?,?,?,?)',('a'*24,'旧对话',1,None))
            db.close()
            store=ConversationStore(path)
            self.assertEqual(store.get('a'*24)['title'],'旧对话');self.assertIsNone(store.get('a'*24)['agent_person'])

    def test_unreviewed_person_is_not_silently_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=AgentService(self.rows,CollectionStore(Path(tmp)/'db.sqlite3'),Mock(),skill_routing=True)
            with self.assertRaises(QueryStageError):service.ask('你好',agent_person='未接入人物')

    def test_hover_dock_accessible_touch_and_keyboard_and_no_remote_images(self):
        root=Path(__file__).parent
        js=(root/'web/agents.js').read_text(encoding='utf-8');css=(root/'web/agents.css').read_text(encoding='utf-8')
        self.assertIn("'pointerenter',show",js);self.assertIn("'focus',show",js);self.assertIn("'click',show",js)
        self.assertIn("new CustomEvent('zhongjian:choose-agent'",js)
        self.assertIn('translateY(-30px)',css);self.assertIn('object-fit:cover',css)
        self.assertIn('perspective:1400px',css);self.assertIn('height:min(70dvh,660px)',css)
        self.assertIn('index-position+count/2',js);self.assertIn('move(-Math.max',js)
        self.assertIn("'关闭人物轮盘'",js);self.assertIn('scale(1.12)',css)

    def test_twenty_portraits_have_matching_identity_attribution_and_hash(self):
        from recommendations import people_catalog
        folder=Path(__file__).parent/'web/portraits'
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(set(manifest),{p['person'] for p in people_catalog()})
        for person in people_catalog():
            item=manifest[person['person']]
            self.assertIn(person['wikidata_id'],item['url'])
            self.assertTrue(item['source'].startswith('https://commons.wikimedia.org/'))
            self.assertTrue(item['license'])
            self.assertEqual(hashlib.sha256((folder/Path(item['url']).name).read_bytes()).hexdigest(),item['sha256'])

    def test_every_catalog_person_has_a_short_biography(self):
        from recommendations import people_catalog
        for person in people_catalog():
            with self.subTest(person=person['person']):
                self.assertGreater(len(person['biography']), 35)
                self.assertNotEqual(person['biography'], person['description'])
                self.assertTrue(person.get('biography_url', person['identity_url']).startswith('https://'))


if __name__=='__main__':unittest.main()
