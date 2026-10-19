"""Regression coverage for all nine additions, without paid model calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from corpus import ROOT, load_library
from query import make_passages, quote_candidates
from thinkers import build_profiles
from person_skills import load_skills
from person_registry import EXPANSION, MODERN_SLUGS, named_people
from agent import AgentService
from collections_store import CollectionStore
from test_agent import tool, final


class ExpandedPeopleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=load_library()
        cls.passages=make_passages(cls.rows)
        cls.profiles=build_profiles(cls.passages)
        cls.skills=load_skills()

    def test_twelve_people_have_skills_and_local_sources(self):
        expected={'王阳明','毛泽东','弗洛伊德'}|{p for p,_ in EXPANSION.values()}
        self.assertEqual(set(self.skills),expected)
        self.assertEqual({r['person'] for r in self.rows},expected)
        self.assertEqual(set(self.profiles),expected)

    def test_every_addition_has_substantive_data_and_verified_concepts(self):
        passages={p['id']:p for p in self.passages}
        for slug,(person,_) in EXPANSION.items():
            with self.subTest(person=person):
                rows=[r for r in self.rows if r['person']==person]
                self.assertGreaterEqual(len(rows),3 if slug in MODERN_SLUGS else 15)
                self.assertGreaterEqual(len(self.profiles[person]['concepts']),3)
                for row in rows:
                    self.assertTrue(row['text'].strip())
                    self.assertTrue(row['source_url'].startswith('https://'))
                for c in self.profiles[person]['concepts']:
                    a=c['primary_anchor'];p=passages[a['passage_id']]
                    self.assertEqual(p['person'],person)
                    self.assertEqual(p['text'][a['start']:a['end']],a['quote'])

    def test_new_source_snapshots_have_portable_paths_and_matching_hashes(self):
        checked=set()
        for row in self.rows:
            if row['person'] not in {p for p,_ in EXPANSION.values()}:continue
            path=Path(row['source_file'])
            self.assertFalse(path.is_absolute())
            if path.as_posix() in checked:continue
            checked.add(path.as_posix())
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),row['source_sha256'])

    def test_new_aliases_and_named_author_limits(self):
        for alias,person in [('苏东坡','苏轼'),('周树人','鲁迅'),('孔夫子','孔子'),('莊子','庄子'),('NIETZSCHE','尼采'),('Schopenhauer','叔本华'),('老聃','老子'),('Justin Sun','孙宇晨'),('Elon Musk','马斯克')]:
            self.assertEqual(named_people('请用'+alias+'的视角回答',self.skills),(person,))
        self.assertEqual(named_people('用孔子和庄子的观点',self.skills),('孔子','庄子'))
        self.assertEqual(named_people('请问苏轼怎么看',{'王阳明'}),())

    def test_modern_quotations_are_short_and_not_full_article_copies(self):
        totals={}
        for row in self.rows:
            if row.get('source_kind')!='modern_short_quotation':continue
            totals[row['source_url']]=totals.get(row['source_url'],0)+len(row['text'].split())
            snapshot=json.loads((ROOT/row['source_file']).read_text(encoding='utf-8'))
            self.assertEqual(snapshot['excerpt'],row['text'])
            self.assertNotIn('full_text',snapshot)
            self.assertEqual(row['source_kind'],'modern_short_quotation')
        self.assertEqual(len(totals),6)
        self.assertTrue(all(0<n<=25 for n in totals.values()))

    def test_each_new_author_can_route_retrieve_generate_and_validate(self):
        for person,_ in EXPANSION.values():
            with self.subTest(person=person),tempfile.TemporaryDirectory() as tmp:
                question='请用'+person+'的视角，直接给我建议：我该如何面对别人的评价？'
                concept=self.profiles[person]['concepts'][0]
                args={'question_focus':'面对他人评价','user_facts':[],
                      'advice_options':['辨别','行动'],
                      'selections':[{'person':person,'concept_id':concept['id'],'reason':'依据此人核心观念判断'}]}
                calls=[]
                def client(messages,**options):
                    calls.append(messages)
                    if len(calls)==1:return tool('select_thinkers',args)
                    if len(calls)==2:return tool('search_sources',{'terms':[t for t in concept['topics'] if 2 <= len(t) <= 20][:2] or ['评价']})
                    data=json.loads([m for m in messages if m.get('role')=='tool'][-1]['content'])
                    hit=next(p for p in data['sources'] if p['sentences'])
                    card={'passage_id':hit['id'],'quote_id':hit['sentences'][0]['id'],
                          'explanation':'你先辨别评价是否对应具体事实，再决定要不要改变。',
                          'translation':'你可以考察自己的判断。',
                          'viewpoint_title':'辨清评价再行动',
                          'advice_tendency':[{'option':'辨别','percent':60},{'option':'行动','percent':40}],
                          'tendency_reason':'先辨别评价依据，再决定行动。'}
                    return final([card])
                service=AgentService(self.rows,CollectionStore(Path(tmp)/'db.sqlite3'),client,
                                     skill_routing=True,advice_tendencies=True)
                result=service.ask(question)['result']
                self.assertEqual([c['person'] for c in result['cards']],[person])
                self.assertTrue(result['cards'][0]['tendency_applicable'])
                self.assertEqual(result['skill_route']['skills'][0]['person'],person)
                self.assertEqual([e['tool'] for e in result['tool_trace']],['select_thinkers','search_sources'])
                system=calls[0][0]['content']
                self.assertIn('requested_people',system)
                from person_skills import catalog
                for other in self.skills:
                    if other!=person:
                        self.assertNotIn('\"person\": \"'+other+'\", \"id\":',system)

if __name__=='__main__':unittest.main()
