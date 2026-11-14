from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

from recommendations import CYCLE, GROUPS, RecommendationStore, make_plan, people_catalog
from people_discovery import search_people, discover_skill, public_json
from corpus import load_library
from query import make_passages
from thinkers import build_profiles
from person_skills import load_skills
from agent import AgentService
from collections_store import CollectionStore
from test_agent import tool, final


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db.sqlite3';self.store=RecommendationStore(self.path)
        self.people=people_catalog();self.available={p['person'] for p in self.people}

    def test_twenty_real_person_directory_has_identity_sources(self):
        self.assertEqual(len(self.people),20)
        self.assertEqual(len(self.available),20)
        self.assertTrue(all(p['identity_url'].startswith('https://') and p['description'] and p['tags'] for p in self.people))

    def test_preferences_persist_and_reset_cycle(self):
        self.store.save(['王阳明','毛泽东'])
        self.assertEqual(RecommendationStore(self.path).read()['selected'],['王阳明','毛泽东'])
        plan=self.store.plan(self.available)
        cards=[{'person':p} for g,n in plan['quotas'].items() for p in [p for p in sorted(plan['groups']) if plan['groups'][p]==g][:n]]
        self.store.commit(plan,cards);self.assertEqual(self.store.read()['round_index'],1)
        self.store.save(['苏轼']);self.assertEqual(self.store.read()['round_index'],0)

    def test_five_rounds_exactly_eight_eight_four(self):
        self.store.save(['王阳明','毛泽东'])
        for i in range(5):
            plan=self.store.plan(self.available);self.assertEqual(sum(plan['quotas'].values()),4)
            cards=[{'person':p} for g,n in plan['quotas'].items() for p in [p for p in sorted(plan['groups']) if plan['groups'][p]==g][:n]]
            self.assertEqual(len({c['person'] for c in cards}),4)
            self.assertTrue(self.store.commit(plan,cards)['balanced'])
        self.assertEqual(self.store.read()['counts'],{'interest':8,'recommended':8,'similar':4})

    def test_no_interest_is_system_recommendation(self):
        plan=self.store.plan(self.available)
        self.assertEqual(plan['quotas'],{'interest':0,'recommended':4,'similar':0})

    def test_one_interest_is_not_duplicated_to_fake_forty_percent(self):
        plan=make_plan(['王阳明'],self.available)
        self.assertEqual(plan['quotas']['interest'],1)
        self.assertEqual(sum(plan['quotas'].values()),4)

    def test_explicit_request_overrides_mixture(self):
        self.store.save(['王阳明','毛泽东'])
        plan=self.store.plan(self.available,['乔布斯'])
        self.assertEqual(plan['groups'],{'乔布斯':'explicit'})
        self.assertEqual(plan['mode'],'explicit')

    def test_three_groups_are_disjoint_and_cover_available(self):
        plan=make_plan(['王阳明','毛泽东'],self.available)
        self.assertEqual(set(plan['groups']),self.available)
        self.assertEqual(plan['groups']['王阳明'],'interest')
        self.assertTrue(all(plan['similarity'][p]>0 for p,g in plan['groups'].items() if g=='similar'))

    def test_missing_or_all_interested_capacity_has_honest_fallback(self):
        for interests,available in [(['王阳明'],{'孔子'}),(list(self.available),self.available),(['不在库'],self.available)]:
            plan=make_plan(interests,available)
            self.assertEqual(sum(plan['quotas'].values()),min(4,len(available)))
            capacities=Counter(plan['groups'].values())
            self.assertTrue(all(n<=capacities[g] for g,n in plan['quotas'].items()))

    def test_invalid_preferences_rejected_without_overwrite(self):
        self.store.save(['王阳明'])
        for value in [None,'王阳明',['未知人物'],['王阳明','王阳明'],[{}]]:
            with self.assertRaises(ValueError):self.store.save(value)
        self.assertEqual(self.store.read()['selected'],['王阳明'])

    def test_stale_plan_does_not_charge_new_preferences(self):
        self.store.save(['王阳明','毛泽东']);plan=self.store.plan(self.available)
        self.store.save(['苏轼','庄子'])
        # Same round index alone cannot distinguish a preference edit; exercise revision in plan implementation.
        cards=[{'person':'王阳明'}]
        self.store.commit(plan,cards)
        self.assertEqual(self.store.read()['counts'],{})


class PersonDiscoveryTests(unittest.TestCase):
    def test_human_claim_required_not_just_search_hit(self):
        mock=Mock(side_effect=[{'search':[{'id':'Q1','label':'虚构角色'},{'id':'Q2','label':'真实人物'}]},
             {'entities':{'Q1':{'claims':{'P31':[{'mainsnak':{'datavalue':{'value':{'id':'Q95074'}}}}]}},
                          'Q2':{'claims':{'P31':[{'mainsnak':{'datavalue':{'value':{'id':'Q5'}}}}]}}}}])
        with patch('people_discovery.wikidata',mock):people=search_people('同名人物')
        self.assertEqual([p['wikidata_id'] for p in people],['Q2'])

    def test_no_arbitrary_remote_endpoints(self):
        for url in ['http://api.github.com/test','https://localhost/secret','https://api.github.com.evil.org/']:
            with self.assertRaises(ValueError):public_json(url)

    def test_unverified_person_skill_download_rejected(self):
        with self.assertRaises(ValueError):discover_skill({'wikidata_id':'Q1'},'.')

    def test_download_is_quarantined_and_not_executed(self):
        import base64,hashlib
        raw='---\nname: person\n---\n真实人物思想说明，引用需核对原著。'.encode()
        data=[{'items':[{'full_name':'example/person-skill','license':{'spdx_id':'MIT'}}]},
              {'encoding':'base64','size':len(raw),'content':base64.b64encode(raw).decode(),'sha':'blob'}]
        with tempfile.TemporaryDirectory() as tmp,patch('people_discovery.public_json',side_effect=data):
            result=discover_skill({'wikidata_id':'Q2','person':'真实人物','verified_human':True},tmp)
            self.assertFalse(result['active']);self.assertEqual(result['status'],'downloaded_pending_review')
            saved=next(Path(tmp).rglob('SKILL.md'));self.assertEqual(saved.read_bytes(),raw)

    def test_missing_license_not_activated(self):
        with tempfile.TemporaryDirectory() as tmp,patch('people_discovery.public_json',return_value={'items':[{'full_name':'a/b','license':None}]}):
            self.assertEqual(discover_skill({'wikidata_id':'Q2','person':'真实人物','verified_human':True},tmp)['status'],'not_found')


class RecommendationAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=load_library();cls.skills=load_skills();cls.profiles=build_profiles(make_passages(cls.rows))

    def test_twenty_people_have_reviewed_skill_and_literal_anchor(self):
        self.assertEqual(len(self.skills),20)
        self.assertEqual(set(self.profiles),{p['person'] for p in people_catalog()})
        self.assertTrue(all(p['concepts'] for p in self.profiles.values()))

    def test_mixture_drives_real_tools_and_returned_card_origins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CollectionStore(Path(tmp)/'db.sqlite3');prefs=RecommendationStore(store.path);prefs.save(['王阳明','毛泽东'])
            plan=prefs.plan(set(self.profiles));selected=[p for g,n in plan['quotas'].items() for p in [p for p in sorted(plan['groups']) if plan['groups'][p]==g][:n]]
            calls=[]
            def model(messages,**options):
                calls.append(messages)
                if len(calls)==1:return tool('select_thinkers',{'question_focus':'面对困惑如何判断','user_facts':[],
                  'selections':[{'person':p,'concept_id':self.profiles[p]['concepts'][0]['id'],'reason':'这一思想回应当前问题'} for p in selected]})
                if len(calls)==2:return tool('search_sources',{'terms':['判断','行动']})
                sources=json.loads([m['content'] for m in messages if m.get('role')=='tool'][-1])['sources']
                cards=[]
                for p in selected:
                    hit=next(s for s in sources if s['person']==p and s['sentences'])
                    card={'passage_id':hit['id'],'quote_id':hit['sentences'][0]['id'],'viewpoint_title':'核对理由再行动','explanation':'你可以先检验眼前判断的根据，再选一件具体的事去做。'}
                    if hit['language']=='en':card['translation']='这是一条测试译意，仅用于离线接口回归。'
                    cards.append(card)
                return final(cards)
            agent=AgentService(self.rows,store,model,skill_routing=True,recommendations=prefs)
            result=agent.ask('怎样面对困惑？')['result']
            self.assertEqual(len(result['cards']),4)
            self.assertEqual(result['recommendation']['actual'],{'interest':2,'recommended':1,'similar':1})
            self.assertTrue(all(c['recommendation_label'] for c in result['cards']))
            self.assertEqual(prefs.read()['round_index'],1)


if __name__=='__main__':unittest.main()
