import json
from pathlib import Path
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock
from web_server import LocalServer
from test_query import source


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Mock(return_value={'cards': [], 'terms': ['朋友'], 'synthesis': '测试响应'})
        cls.server = LocalServer(('127.0.0.1', 0), [source('朋友有信。')], cls.engine)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, path, data=None, **headers):
        if data is not None:
            headers.setdefault('Content-Type', 'application/json')
            data = json.dumps(data).encode()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(urllib.request.Request(self.url + path, data=data, headers=headers), timeout=5)

    def test_page_serves(self):
        with self.request('/') as r:
            self.assertEqual(r.status, 200)
            self.assertIn('众见', r.read().decode())

    def test_details_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/source/details', {'passage_id': 'fake'})
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_unknown_detail_source_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/source/details', {'passage_id': 'fake'}, **{'X-Zhongjian-Token': self.server.nonce})
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_detail_generation_cached(self):
        client = Mock(return_value={'content': json.dumps({'reading': '朋友要守信用。\n\n强调诚信。'})})
        self.server.detail_client = client
        self.server.detail_cache.clear()
        pid = next(iter(self.server.passages))
        try:
            for _ in range(2):
                with self.request('/api/source/details', {'passage_id': pid}, **{'X-Zhongjian-Token': self.server.nonce}) as response:
                    result = json.load(response)
                self.assertEqual(result['reading'], '朋友要守信用。\n\n强调诚信。')
                self.assertEqual(result['original'], '朋友有信。')
            self.assertEqual(client.call_count, 1)
            with self.request('/api/source/details', {'passage_id': pid, 'question': '另一个问题'}, **{'X-Zhongjian-Token': self.server.nonce}) as response:
                json.load(response)
            self.assertEqual(client.call_count, 2)
        finally:
            self.server.detail_client = None
            self.server.detail_cache.clear()

    def test_detail_rejects_invalid_span(self):
        pid = next(iter(self.server.passages))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/source/details', {'passage_id': pid, 'highlight_start': 0, 'highlight_end': 99999}, **{'X-Zhongjian-Token': self.server.nonce})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_long_english_sentence_can_open_without_relaxing_chinese_limit(self):
        row={**source(('An original English sentence with its context. '*10).strip()), 'person':'弗洛伊德','language':'en'}
        server=LocalServer(('127.0.0.1',0),[row],self.engine)
        server.detail_client=Mock(return_value={'content':json.dumps({'reading':'我不把情绪强度当成过错的证据。'})})
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            pid=next(iter(server.passages))
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/source/details',
                data=json.dumps({'passage_id':pid,'highlight_start':0,'highlight_end':230}).encode(),
                headers={'Content-Type':'application/json','X-Zhongjian-Token':server.nonce})
            with urllib.request.urlopen(req,timeout=5) as response:
                result=json.load(response)
            self.assertEqual(result['original_language'],'en')
            self.assertEqual(result['original_focus'],row['text'][:230])
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_session_contains_no_provider_key(self):
        with self.request('/api/session') as r:
            data = json.load(r)
        self.assertEqual(set(data), {'token', 'ready', 'person', 'records', 'app', 'model'})
        self.assertTrue(data['ready'])

    def test_secret_file_not_served(self):
        for path in ('/.local/deepseek-key.xml', '/logs/evaluation_live.json', '/../check_api.py'):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                self.request(path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_query_without_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/query', {'question': '问题'})
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_external_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/query', {'question': '问题'}, Origin='https://example.com',
                         **{'X-Zhongjian-Token': self.server.nonce})
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_live_endpoint_uses_engine(self):
        with self.request('/api/query', {'question': '测试问题'},
                          **{'X-Zhongjian-Token': self.server.nonce}) as r:
            data = json.load(r)
        self.assertEqual(data['mode'], 'live')
        self.engine.assert_called_with('测试问题')

    def test_agent_endpoint_keeps_conversation_id(self):
        agent = Mock()
        agent.ask.return_value = {'session_id': 'session-fixture', 'result': {'cards': [], 'synthesis': '回复'}}
        self.server.agent = agent
        try:
            with self.request('/api/query', {'question': '追问', 'session_id': 'session-fixture'},
                              **{'X-Zhongjian-Token': self.server.nonce}) as r:
                answer = json.load(r)
            self.assertEqual(answer['mode'], 'live_agent')
            self.assertEqual(answer['session_id'], 'session-fixture')
            agent.ask.assert_called_with('追问', 'session-fixture')
        finally:
            self.server.agent = None

    def test_agent_reset_endpoint(self):
        agent = Mock()
        self.server.agent = agent
        try:
            with self.request('/api/session/reset', {'session_id': 'old'},
                              **{'X-Zhongjian-Token': self.server.nonce}) as r:
                self.assertTrue(json.load(r)['reset'])
            agent.reset.assert_called_with('old')
        finally:
            self.server.agent = None

    def test_invalid_question_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/query', {'question': 'x' * 2001},
                         **{'X-Zhongjian-Token': self.server.nonce})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_foreign_host_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/session', Host='untrusted.example')
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_query_failure_then_next_request_works(self):
        from query import QueryStageError
        original = self.server.engine
        self.server.engine = Mock(side_effect=[QueryStageError('原文引用核验', 'invalid_quote_id', '引用编号异常'),
                                              {'cards': [], 'synthesis': '下一次正常'}])
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/query', {'question': '预设问题'}, **{'X-Zhongjian-Token': self.server.nonce})
            self.assertEqual(caught.exception.code, 422)
            caught.exception.close()
            with self.request('/api/query', {'question': '预设问题二'}, **{'X-Zhongjian-Token': self.server.nonce}) as r:
                self.assertEqual(json.load(r)['result']['synthesis'], '下一次正常')
        finally:
            self.server.engine = original

    def test_context_reads_local_source_only(self):
        with self.request('/api/context?id=unit1') as r:
            self.assertEqual(json.load(r)['text'], '朋友有信。')

    def test_collection_list_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/collections')
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_collection_roundtrip_and_server_reconstructs_quote(self):
        pid = next(iter(self.server.passages))
        body = {'passage_id': pid, 'highlight_start': 0, 'highlight_end': 4,
                'quote': '伪造原文', 'question': 'PRIVATE_QUESTION'}
        headers = {'X-Zhongjian-Token': self.server.nonce}
        with self.request('/api/collections/add', body, **headers) as r:
            saved = json.load(r)['item']
        self.assertEqual(saved['quote'], '朋友有信')
        self.assertNotIn('question', saved)
        try:
            with self.request('/api/collections/add', body, **headers) as r:
                duplicate = json.load(r)
            self.assertFalse(duplicate['created'])
            self.assertEqual(duplicate['item']['collection_id'], saved['collection_id'])
            with self.request('/api/collections', **headers) as r:
                self.assertTrue(any(x['collection_id'] == saved['collection_id'] for x in json.load(r)['items']))
        finally:
            with self.request('/api/collections/cancel', {'collection_id': saved['collection_id']}, **headers) as r:
                self.assertTrue(json.load(r)['cancelled'])

    def test_bad_collection_span_rejected(self):
        headers = {'X-Zhongjian-Token': self.server.nonce}
        for a, b in ((-1, 4), (0, 999), (True, 4)):
            with self.subTest(a=a, b=b), self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/collections/add', {'passage_id': next(iter(self.server.passages)),
                             'highlight_start': a, 'highlight_end': b}, **headers)
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()

    def test_unknown_collection_source_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/collections/add', {'passage_id': 'unknown', 'highlight_start': 0, 'highlight_end': 4},
                         **{'X-Zhongjian-Token': self.server.nonce})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_client_uses_text_not_model_html(self):
        js = (Path(__file__).parent / 'web/app.js').read_text(encoding='utf-8')
        self.assertNotIn('innerHTML', js)
        self.assertNotIn('DEEPSEEK_API_KEY', js)


if __name__ == '__main__':
    unittest.main()
