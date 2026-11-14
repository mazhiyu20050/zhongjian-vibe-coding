"""Explicit synthetic UI fixture; uses real preferences endpoints, no paid model."""
from pathlib import Path
import tempfile
import threading
from corpus import load_library
from query import make_passages
from web_server import LocalServer
from recommendations import LABELS
import argparse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18767);args=parser.parse_args()
    rows=load_library();passages=make_passages(rows)
    server=None
    def engine(question):
        plan=server.recommendations.plan({p['person'] for p in passages})
        people=[p for g,n in plan['quotas'].items() for p in [p for p in sorted(plan['groups']) if plan['groups'][p]==g][:n]]
        cards=[]
        for person in people:
            p=next(p for p in passages if p['person']==person)
            cards.append({**p,'paragraph':p['text'],'quote':'','highlight_start':0,'highlight_end':0,
                          'viewpoint_title':'界面测试 · 非实际回答','explanation':'这是用于检查推荐分组与排版的模拟内容，不代表人物的真实观点。',
                          'recommendation_group':plan['groups'][person], 'recommendation_label':LABELS[plan['groups'][person]]})
        return {'question_title':'推荐界面回归测试','cards':cards,'recommendation':server.recommendations.commit(plan,cards)}
    with tempfile.TemporaryDirectory() as tmp:
        server=LocalServer(('127.0.0.1',args.port),rows,engine,Path(tmp)/'db.sqlite3')
        timer=threading.Timer(900,server.shutdown);timer.daemon=True;timer.start()
        try:server.serve_forever()
        finally:timer.cancel();server.server_close()


if __name__=='__main__':main()
