"""Run the judge preview against the real HTTP stack without a model key."""
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from reviewer_demo import DEMO_QUESTION, create_demo


class ReviewerDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_demo(0)
        cls.folder = Path(cls.server.collection_tmp.name)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = build_opener(ProxyHandler({}))
        cls.token = cls.call("/api/session")["token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()
        if cls.folder.exists():
            raise AssertionError("temporary demo store was not cleaned up")

    @classmethod
    def call(cls, path, payload=None):
        headers = {"X-Zhongjian-Token": getattr(cls, "token", "")}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        with cls.opener.open(Request(cls.url + path, body, headers), timeout=5) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if response.headers.get_content_type() == "application/json" else text

    def test_named_preview_with_real_corpus_anchors_and_local_history(self):
        self.assertIn("离线评审演示", self.call("/"))
        self.assertIn("固定示例", self.call("/"))
        self.assertIn(DEMO_QUESTION + "</textarea>", self.call("/"))
        self.assertIsNone(self.server.agent)
        self.assertIsNone(self.server.detail_client)
        self.assertEqual(self.call("/api/session")["mode"], "reviewer_demo")
        answer = self.call("/api/query", {"question": DEMO_QUESTION})
        self.assertEqual(answer["mode"], "reviewer_demo")
        cards = answer["result"]["cards"]
        self.assertGreaterEqual(len({card["person"] for card in cards}), 3)
        self.assertTrue(answer["result"]["display_reply"])
        for card in cards:
            self.assertTrue(card["work"])
            start, end = (card["highlight_start"], card["highlight_end"])
            self.assertEqual(card["paragraph"][start:end], card["quote"])
            source = self.call("/api/context?id=" + card["unit_id"])
            self.assertIn(card["quote"], source["text"])
            detail = self.call("/api/source/details", {
                "passage_id": card["id"], "highlight_start": start,
                "highlight_end": end, "question": DEMO_QUESTION,
            })
            self.assertIn(card["quote"], detail["reading"])
        self.assertEqual(self.call("/api/conversations?id=" + answer["conversation_id"])["turns"][0]["question"], DEMO_QUESTION)

    def test_unsupported_queries_and_external_work_are_blocked(self):
        for path, payload, code in [
            ("/api/query", {"question": "一个新的问题"}, 422),
            ("/api/people/jobs", {"query": "新人物"}, 403),
            ("/api/projects/reveal", {"id": "other"}, 403),
        ]:
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as failure:
                    self.call(path, payload)
                self.assertEqual(failure.exception.code, code)
                self.assertIn("演示", json.loads(failure.exception.read().decode("utf-8"))["message"])


if __name__ == "__main__":
    unittest.main()
