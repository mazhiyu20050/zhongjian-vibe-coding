import base64
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

from conversations import ConversationStore
from discovery_jobs import DiscoveryJobs
from people_discovery import discover_skill,search_people,validate_url,rank_people
from test_web import WebTests

PERSON={'person':'张雪峰','wikidata_id':'Q47691464','verified_human':True,'aliases':['Zhang Xuefeng'],
        'identity_url':'https://www.wikidata.org/wiki/Q47691464','description':'教育咨询人物'}
DOWNLOADED={'status':'downloaded_pending_review','active':False,'repository':'https://github.com/example/person'}


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lookup=lambda q:[PERSON]
        self.download=lambda p,f:DOWNLOADED

    def make(self):
        jobs=DiscoveryJobs(self.tmp.name,self.lookup,self.download,retry_delays=());self.addCleanup(jobs.close);return jobs

    def finish(self,jobs,jid):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            job=next(j for j in jobs.list() if j['id']==jid)
            if job['status'] not in ('queued','searching','downloading'):return job
            time.sleep(.01)
        self.fail('background job did not finish')

    def test_start_returns_immediately_and_survives_client_detach(self):
        release=threading.Event();self.addCleanup(release.set)
        self.lookup=lambda q:(release.wait(2),[PERSON])[1]
        jobs=self.make();t=time.monotonic();job=jobs.start('张雪峰')
        self.assertLess(time.monotonic()-t,.5)
        self.assertEqual(jobs.start('张雪峰')['id'],job['id'])
        release.set();self.assertEqual(self.finish(jobs,job['id'])['status'],'completed')
        self.assertEqual(DiscoveryJobs(self.tmp.name,self.lookup,self.download).list()[0]['status'],'completed')

    def test_multiple_identities_auto_download_best_match(self):
        self.lookup=lambda q:[{**PERSON,'wikidata_id':'Q2','sitelink_count':1}, {**PERSON,'sitelink_count':30}]
        downloaded=[]
        self.download=lambda p,f:(downloaded.append(p['wikidata_id']),DOWNLOADED)[1]
        jobs=self.make();job=self.finish(jobs,jobs.start('张雪峰')['id'])
        self.assertEqual(job['status'],'completed');self.assertTrue(job['auto_matched'])
        self.assertEqual(downloaded,[PERSON['wikidata_id']]);self.assertEqual(len(job['people']),1)
        with self.assertRaises(ValueError):jobs.choose(job['id'],'Q9')

    def test_download_stages_profile_without_activating_skill(self):
        person={**PERSON,'lifespan':'近现代','portrait_file':'Example portrait.jpg'}
        self.lookup=lambda q:[person]
        with patch('person_profiles.prepare_portrait', return_value=('张雪峰', {'url':'/portraits/Q47691464.jpg'})) as picture:
            job=self.finish((jobs:=self.make()),jobs.start('张雪峰')['id'])
        self.assertEqual(job['status'],'completed')
        self.assertFalse(job['result']['active'])
        self.assertEqual(job['result']['profile']['biography'],'教育咨询人物')
        profile=Path(self.tmp.name)/'person-profiles'/PERSON['wikidata_id']/'profile.json'
        self.assertEqual(json.loads(profile.read_text(encoding='utf-8'))['wikidata_id'],PERSON['wikidata_id'])
        picture.assert_called_once()

    def test_old_choice_tasks_resume_automatically(self):
        path=Path(self.tmp.name)/'discovery-jobs.json'
        path.write_text(json.dumps([{'id':'test','status':'awaiting_choice','query':'张雪峰','updated_at':1,'people':[PERSON]}]))
        jobs=self.make();self.assertEqual(self.finish(jobs,'test')['status'],'completed')

    def test_exact_name_beats_famous_partial_match_and_nonhuman(self):
        people=[{**PERSON,'person':'张雪峰研究所','aliases':[],'sitelink_count':999},
                {**PERSON,'wikidata_id':'Q2','verified_human':False,'sitelink_count':9999},PERSON]
        self.assertEqual(rank_people(people,'張雪峰')[0]['wikidata_id'],PERSON['wikidata_id'])

    def test_download_icon_spinner_and_indeterminate_top_progress(self):
        root=Path(__file__).parent
        js=(root/'web/people.js').read_text(encoding='utf-8')
        css=(root/'web/people.css').read_text(encoding='utf-8')
        self.assertNotIn('选这位',js);self.assertNotIn('同名人物需确认',js)
        self.assertIn('aria-label="查找并下载 Skill"',js)
        self.assertIn("progress.setAttribute('role','progressbar')",js)
        self.assertNotIn('aria-valuenow',js)
        self.assertIn('download-spin',css);self.assertIn('height:2px',css)

    def test_missing_skill_and_network_error_are_different(self):
        self.download=lambda p,f:{'status':'not_found','active':False}
        jobs=self.make();self.assertEqual(self.finish(jobs,jobs.start('甲')['id'])['status'],'no_skill')
        jobs.download=lambda p,f:(_ for _ in ()).throw(ConnectionError())
        self.assertEqual(self.finish(jobs,jobs.start('乙')['id'])['status'],'network_error')

    def test_explicit_retry_and_cache(self):
        jobs=self.make();first=self.finish(jobs,jobs.start('张雪峰')['id'])
        self.assertEqual(jobs.start('张雪峰')['id'],first['id'])
        self.assertNotEqual(jobs.start('张雪峰',True)['id'],first['id'])
        jobs.tasks.join()

    def test_restart_marks_incomplete_tasks_retryable(self):
        path=Path(self.tmp.name)/'discovery-jobs.json'
        path.write_text(json.dumps([{'id':'test','status':'searching','query':'张雪峰','updated_at':1}]))
        self.assertEqual(self.make().list()[0]['status'],'interrupted')

    def test_invalid_input_and_external_redirect_rejected(self):
        jobs=self.make()
        for q in ('',None,'a'*81):
            with self.assertRaises(ValueError):jobs.start(q)
        for url in ('https://api.github.com:8443/x','https://user@api.github.com/x','https://localhost/x'):
            with self.assertRaises(ValueError):validate_url(url)


class SearchExpansionTests(unittest.TestCase):
    def test_bilingual_name_and_batched_human_verification(self):
        entity={'claims':{'P31':[{'mainsnak':{'datavalue':{'value':{'id':'Q5'}}}}]},
                'labels':{'zh':{'value':'张雪峰'},'en':{'value':'Zhang Xuefeng'}}}
        with patch('people_discovery.wikidata',side_effect=[{'search':[{'id':'Q47691464'}]}, {'entities':{'Q47691464':entity}}]) as call:
            found=search_people('張雪峰')
        self.assertIn('Zhang Xuefeng',found[0]['aliases']);self.assertEqual(call.call_count,2)
        self.assertEqual(call.call_args[0][0]['action'],'wbgetentities')

    def test_nested_skill_matches_english_slug(self):
        raw='张雪峰思想框架'.encode()
        def network(url,maximum=0):
            if '/search/repositories' in url:return {'items':[{'full_name':'example/people','license':{'spdx_id':'MIT'},'default_branch':'main'}]}
            if '/git/trees/' in url:return {'tree':[{'path':'skills/zhangxuefeng/SKILL.md','type':'blob','mode':'100644'}]}
            if url.endswith('/contents/SKILL.md'):raise urllib.error.HTTPError(url,404,'missing',{},None)
            return {'encoding':'base64','size':len(raw),'content':base64.b64encode(raw).decode(),'sha':'test-sha'}
        with tempfile.TemporaryDirectory() as tmp,patch('people_discovery.public_json',side_effect=network):
            result=discover_skill(PERSON,tmp)
            self.assertEqual(result['path'],'skills/zhangxuefeng/SKILL.md');self.assertFalse(result['active'])
            self.assertEqual(next(Path(tmp).rglob('SKILL.md')).read_bytes(),raw)


class ConversationTests(unittest.TestCase):
    def test_append_restore_title_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ConversationStore(Path(tmp)/'db.sqlite3')
            cid=store.append(None,'我被人骂了，很难过',{'question_title':'被骂后的难过','cards':[]},'session-one')
            store.append(cid,'怎么做？',{'cards':[]},'session-two')
            other=store.append(None,'另一件事',{'cards':[]})
            saved=ConversationStore(store.path).get(cid)
            self.assertEqual(saved['title'],'被骂后的难过');self.assertEqual(len(saved['turns']),2)
            self.assertEqual(saved['session_id'],'session-two');self.assertNotEqual(other,cid)
            self.assertIsNone(store.get('../private'))

    def test_agent_resume_restores_messages_but_not_action_authority(self):
        from agent import AgentService
        from collections_store import CollectionStore
        from test_query import source
        with tempfile.TemporaryDirectory() as tmp:
            agent=AgentService([source('朋友有信。')],CollectionStore(Path(tmp)/'db.sqlite3'),lambda *a:None)
            sid=agent.resume_history('expired',[{'question':'我被人骂了','result':{'synthesis':'核实事实','cards':[],'pending_confirmation':True}}])
            state=agent.session(sid)
            self.assertEqual(state.turns[0][0]['role'],'user');self.assertIsNone(state.pending)
            self.assertEqual(agent.resume_history(sid,[]),sid)


class NavigationAPITests(WebTests):
    # Inherit existing HTTP security coverage as well as exercise new endpoints.
    def test_history_api_requires_auth_and_query_saves_to_correct_thread(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/conversations')
        self.assertEqual(error.exception.code,403);error.exception.close()
        headers={'X-Zhongjian-Token':self.server.nonce}
        with self.request('/api/query',{'question':'导航接口测试'},**headers) as response:first=json.load(response)
        cid=first['conversation_id']
        with self.request('/api/query',{'question':'继续测试','conversation_id':cid},**headers) as response:self.assertEqual(json.load(response)['conversation_id'],cid)
        with self.request('/api/conversations?id='+cid,**headers) as response:self.assertEqual(len(json.load(response)['turns']),2)

    def test_jobs_return_202_and_are_pollable(self):
        with patch('web_server.search_people',return_value=[PERSON]),patch('web_server.discover_skill',return_value=DOWNLOADED):
            headers={'X-Zhongjian-Token':self.server.nonce}
            with self.request('/api/people/jobs',{'query':'张雪峰','retry':True},**headers) as response:
                self.assertEqual(response.status,202);job=json.load(response)['job']
            self.server.discovery_jobs.tasks.join()
            with self.request('/api/people/jobs',**headers) as response:
                result=next(j for j in json.load(response)['jobs'] if j['id']==job['id'])
            self.assertEqual(result['status'],'completed')

    def test_shell_assets_are_served(self):
        for path in ('/shell.js','/shell.css'):
            with self.request(path) as response:self.assertEqual(response.status,200)


if __name__=='__main__':unittest.main()
