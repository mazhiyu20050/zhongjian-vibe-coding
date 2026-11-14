"""Loopback-only reviewer preview: fixed commentary and real local source passages."""
import argparse
from html import escape
from urllib.parse import urlparse

from corpus import load_library
from query import QueryStageError
from web_server import Handler, LocalServer, ROOT

DEMO_QUESTION = "小组作业里队友拖延，我要不要直接接手？"
SAMPLE = (
    ("wym-8842abc3c1261fb5", "人須在事上磨，方立得住", "先处理具体卡点",
     "先弄清具体卡在哪里。与其在聊天里争谁更负责，不如请队友一起完成一小段任务，看看是缺材料、缺方法，还是赶不上时间。"),
    ("confucius-0016", "不患人之不己知，患不知人也", "先弄清对方情况",
     "暂时别把延期解释成不上心。单独问对方进度和困难，把事实问清后，再谈哪一部分需要换人。"),
    ("laozi-0063", "天下難事，必作于易，天下大事，必作于細", "把交付缩成小一步",
     "别一下子接手整份任务。先把下一次交付缩成一个能检查的小成果；到点仍没进展，再把关键部分重新分配。"),
)
NEXT_STEP = "今天先问对方卡在哪里，并约定今晚交一段可检查的草稿；若到点仍未收到，只补上影响整体交付的部分。"


class ReviewerHandler(Handler):
    allowed_posts = frozenset({
        "/api/query", "/api/source/details", "/api/session/reset",
        "/api/collections/add", "/api/collections/cancel", "/api/preferences",
        "/api/projects", "/api/projects/rename", "/api/projects/status", "/api/projects/manage",
        "/api/conversations/move", "/api/conversations/pin", "/api/conversations/manage",
        "/api/conversations/branch",
    })
    allowed_gets = frozenset({
        "/api/session", "/api/agents", "/api/collections", "/api/people",
        "/api/people/jobs", "/api/preferences", "/api/projects", "/api/conversations", "/api/context",
    })

    def do_GET(self):
        if not self.trusted_host():
            return self.send(403, {"error": "host_rejected"})
        path = urlparse(self.path).path
        if path == "/":
            html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
            html = html.replace("</head>", '<link rel="stylesheet" href="/reviewer.css"></head>')
            html = html.replace("<body>", '<body><aside id="reviewer-notice"><strong>离线评审演示</strong>'
                                ' · 固定示例，非实时生成 · 只在本机临时保存<br>示例问题：'
                                + escape(DEMO_QUESTION) + '</aside>', 1)
            html = html.replace('aria-label="输入你的困惑"></textarea>',
                                'aria-label="输入你的困惑">' + escape(DEMO_QUESTION) + '</textarea>', 1)
            return self.send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/reviewer.css":
            return self.send(200, b'#reviewer-notice{margin:10px auto 6px;padding:9px 12px;text-align:center;'
                             b'font:13px/1.55 system-ui,sans-serif;max-width:calc(100% - 124px);width:max-content;'
                             b'color:#354227;background:#edf1e4;border-radius:9px} @media(max-width:500px){'
                             b'#reviewer-notice{margin-top:56px;max-width:calc(100% - 30px)}}',
                             "text/css; charset=utf-8")
        if path.startswith("/api/") and path not in self.allowed_gets:
            return self.send(404, {"error": "demo_route_disabled", "message": "离线评审演示未启用此功能。"})
        return super().do_GET()

    def authorized(self):
        if not super().authorized():
            return False
        if self.command == "POST" and self.path not in self.allowed_posts:
            self.send(403, {"error": "demo_route_disabled",
                            "message": "离线评审演示未启用联网、文件夹或外部窗口操作。"})
            return False
        return True

    def send(self, status, value, content_type="application/json; charset=utf-8"):
        if status == 200 and content_type.startswith("application/json") and isinstance(value, dict):
            if "result" in value or urlparse(self.path).path == "/api/session":
                value = {**value, "mode": "reviewer_demo"}
        if status == 503 and isinstance(value, dict):
            value = {**value, "message": "此功能仅在正式模式可用；离线评审演示只提供固定案例。"}
        return super().send(status, value, content_type)

    def source_details(self, data):
        pid = data.get("passage_id")
        if not isinstance(pid, str) or pid not in self.server.demo_cards:
            return self.send(404, {"error": "source_not_found", "message": "这段原文不在离线评审演示案例中。"})
        card = self.server.demo_cards[pid]
        reference = " · ".join(str(card[key]) for key in ("person", "work", "volume", "section", "entry") if card.get(key))
        return self.send(200, {"reading": card["paragraph"], "reference": reference,
                               "reading_emphasis": [], "related": [], "original_language": "zh"})


def create_demo(port=0):
    wanted = {entry[0] for entry in SAMPLE}
    rows = [row for row in load_library() if row["id"] in wanted]
    cards = {}

    def fixed_answer(question):
        if question.rstrip("？?") != DEMO_QUESTION.rstrip("？?"):
            raise QueryStageError("评审演示", "demo_example_only", "离线评审演示仅支持示例问题：" + DEMO_QUESTION)
        return {"question_title": "别急着接手整份作业", "synthesis": NEXT_STEP,
                "cards": list(cards.values())}

    server = LocalServer(("127.0.0.1", port), rows, fixed_answer)
    server.RequestHandlerClass = ReviewerHandler
    try:
        for unit, quote, title, commentary in SAMPLE:
            passage = next((p for p in server.passages.values() if p["unit_id"] == unit and quote in p["text"]), None)
            if passage is None:
                raise RuntimeError(f"评审示例无法核对本地原文：{unit}")
            start = passage["text"].index(quote)
            cards[passage["id"]] = {
                **passage, "paragraph": passage["text"], "quote": quote,
                "highlight_start": start, "highlight_end": start + len(quote),
                "viewpoint_title": title, "explanation": commentary,
            }
        server.demo_cards = cards
        return server
    except BaseException:
        server.server_close()
        raise


def main():
    parser = argparse.ArgumentParser(description="众见离线评审演示，不读密钥，不调用模型")
    parser.add_argument("--port", type=int, default=8765, help="本机端口；设为 0 分配空闲端口")
    args = parser.parse_args()
    with create_demo(args.port) as server:
        print(f"众见离线评审演示：http://127.0.0.1:{server.server_port}/", flush=True)
        print("打开网址，发送输入框中预填的问题。按 Ctrl+C 关闭。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
