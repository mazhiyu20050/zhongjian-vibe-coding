"""Run the judge preview against the real HTTP stack without a model key."""
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from reviewer_demo import DEMO_FOLLOWUP, DEMO_QUESTION, create_demo


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

    def test_preview_with_classical_excerpt_anchors_and_local_history(self):
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
        self.assertEqual(len(self.server.rows), 3)
        self.assertTrue(answer["result"]["display_reply"])
        for card in cards:
            self.assertTrue(card["work"])
            start, end = (card["highlight_start"], card["highlight_end"])
            self.assertEqual(card["paragraph"][start:end], card["quote"])
            source = self.call("/api/context?id=" + card["unit_id"])
            self.assertIn(card["quote"], source["text"])
            self.assertTrue(source["source_url"].startswith("https://zh.wikisource.org/"))
            self.assertLess(len(source["text"]), 30)
            detail = self.call("/api/source/details", {
                "passage_id": card["id"], "highlight_start": start,
                "highlight_end": end, "question": DEMO_QUESTION,
            })
            self.assertIn(card["quote"], detail["reading"])
        self.assertEqual(self.call("/api/conversations?id=" + answer["conversation_id"])["turns"][0]["question"], DEMO_QUESTION)

    def test_agent_biographies_are_in_the_offline_catalog(self):
        people = {person["person"]: person for person in self.call("/api/agents")["agents"]}
        self.assertIn("王阳明", people)
        self.assertEqual(set(people), {"王阳明", "孔子", "老子"})
        self.assertTrue(all(not entry.get("portrait") for entry in people.values()))
        self.assertIn("未分发第三方肖像", self.call("/portrait-credits"))
        for person in people.values():
            with self.subTest(person=person["person"]):
                self.assertTrue(person["biography"])
                self.assertNotEqual(person["description"], person["biography"])
                self.assertTrue(person["identity_url"].startswith("https://"))
        self.assertIn("1472", people["王阳明"]["lifespan"])
        self.assertIn("争议", people["老子"]["biography"])
        self.assertNotIn("lifespan", people["老子"])

    def test_preview_person_followup_and_consensus_use_separate_history(self):
        original = self.call("/api/query", {"question": DEMO_QUESTION})
        parent = original["conversation_id"]
        summary = self.call("/api/conversations/outline", {"id": parent})
        self.assertEqual(summary["mode"], "reviewer_demo")
        self.assertEqual(len(summary["consensus"]["speakers"]), 3)
        selected = self.call("/api/query", {"question": DEMO_QUESTION, "agent_person": "孔子",
                                            "branch_entry": True})
        child = selected["conversation_id"]
        self.assertNotEqual(child, parent)
        self.assertEqual([card["person"] for card in selected["result"]["cards"]], ["孔子"])
        self.assertIn("\n", selected["result"]["display_reply"])
        followup = self.call("/api/query", {"question": DEMO_FOLLOWUP, "conversation_id": child})
        self.assertEqual(followup["conversation_id"], child)
        self.assertEqual(len(self.call("/api/conversations?id=" + child)["turns"]), 2)
        self.assertEqual(len(self.call("/api/conversations?id=" + parent)["turns"]), 1)
        self.assertIsNone(self.server.detail_client)

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
