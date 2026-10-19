"""Opt-in UI fixture: no provider/API key, one synthetic answer then a JSON error."""
from pathlib import Path
import tempfile
import threading
from query import QueryStageError
from web_server import LocalServer


def main():
    calls=0
    def engine(question):
        nonlocal calls
        calls+=1
        if calls>1:raise QueryStageError('fixture','invalid_json','模型返回的文本不是完整有效的 JSON')
        return {'question_title':'界面回归测试','cards':[{'id':'fixture-only',
            'person':'测试人物','viewpoint_title':'已成功的测试答复','explanation':'这是模拟内容，仅用于验证失败后保留已展示的结果。',
            'paragraph':'模拟片段，非历史原文。','highlight_start':0,'highlight_end':0}]}
    with tempfile.TemporaryDirectory() as tmp:
        server=LocalServer(('127.0.0.1',0),[],engine,Path(tmp)/'fixture.sqlite3')
        timer=threading.Timer(180,server.shutdown);timer.daemon=True;timer.start()
        print('http://127.0.0.1:'+str(server.server_port)+'/',flush=True)
        try:server.serve_forever()
        finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
