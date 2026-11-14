import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch
from people_discovery import PublicAPIError,http_failure,discover_skill
from discovery_jobs import DiscoveryJobs

PERSON={'person':'雷军','wikidata_id':'Q9000717','verified_human':True,'verified_at':time.time(),'aliases':['Lei Jun']}
DONE={'status':'downloaded_pending_review','active':False}


class ReliabilityTests(unittest.TestCase):
    def test_http_rate_limit_respects_reset(self):
        error=urllib.error.HTTPError('https://api.github.com/test',403,'rate limit exceeded',
                  {'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(time.time()+120),'Retry-After':'90'},io.BytesIO())
        result=http_failure(error,error.url);error.close()
        self.assertEqual(result.kind,'rate_limited');self.assertGreater(result.retry_after,115)

    def test_forbidden_is_not_always_rate_limit(self):
        error=urllib.error.HTTPError('https://api.github.com/test',403,'Forbidden',{},io.BytesIO())
        result=http_failure(error,error.url);error.close()
        self.assertEqual(result.kind,'access_denied');self.assertFalse(result.retryable)

    def test_rate_limit_stops_repeated_repository_requests(self):
        with tempfile.TemporaryDirectory() as tmp,patch('people_discovery.registered_skill',return_value=None),patch('people_discovery.public_json',side_effect=PublicAPIError('rate_limited','GitHub',120)) as network:
            with self.assertRaises(PublicAPIError):discover_skill(PERSON,tmp)
            self.assertEqual(network.call_count,1)

    def test_registered_source_skips_search_quota(self):
        with tempfile.TemporaryDirectory() as tmp,patch('people_discovery.registered_skill',return_value=DONE),patch('people_discovery.public_json') as network:
            self.assertEqual(discover_skill(PERSON,tmp),DONE)
            network.assert_not_called()

    def test_automatic_retry_reuses_verified_person_then_succeeds(self):
        calls=[]
        def download(p,f):
            calls.append(p['wikidata_id'])
            if len(calls)==1:raise PublicAPIError('connection_error')
            return DONE
        with tempfile.TemporaryDirectory() as tmp:
            jobs=DiscoveryJobs(tmp,lambda q:[PERSON],download,retry_delays=(.03,))
            try:
                jid=jobs.start('雷军')['id'];deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    result=next(j for j in jobs.list() if j['id']==jid)
                    if result['status']=='completed':break
                    time.sleep(.01)
                self.assertEqual(result['status'],'completed');self.assertEqual(len(calls),2)
            finally:jobs.close()

    def test_rate_limit_is_persisted_as_waiting_not_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs=DiscoveryJobs(tmp,lambda q:[PERSON],lambda *a:(_ for _ in ()).throw(PublicAPIError('rate_limited','GitHub',120)))
            try:
                jobs.start('雷军');jobs.tasks.join();job=jobs.list()[0]
                self.assertEqual(job['status'],'retry_wait');self.assertEqual(job['error_code'],'rate_limited')
                self.assertIsNone(job['result']);self.assertIn('GitHub',job['message'])
                self.assertGreater(job['next_retry_at']-time.time(),115)
                reopened=DiscoveryJobs(tmp,lambda q:[],lambda *a:DONE)
                try:self.assertEqual(reopened.list()[0]['status'],'retry_wait')
                finally:reopened.close()
            finally:jobs.close()

    def test_prior_verified_identity_is_reused_on_user_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs=DiscoveryJobs(tmp,lambda q:[PERSON],lambda *a:DONE)
            try:
                jobs.start('雷军');jobs.tasks.join()
                jobs.lookup=lambda q:(_ for _ in ()).throw(AssertionError('duplicate lookup'))
                jobs.start('雷军',retry=True);jobs.tasks.join()
                self.assertEqual(jobs.list()[0]['status'],'completed')
            finally:jobs.close()

    def test_typography_is_consistent_without_removing_emphasis(self):
        css=(Path(__file__).parent/'web/shell.css').read_text(encoding='utf-8')
        self.assertIn('Microsoft YaHei UI',css);self.assertIn('body,body *{font-family:',css)
        self.assertNotIn('body *{font-weight:400',css)


if __name__=='__main__':unittest.main()
