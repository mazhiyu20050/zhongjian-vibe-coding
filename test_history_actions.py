from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from conversations import ConversationStore

class HistoryActions(unittest.TestCase):
    def test_metadata_and_restore(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'db'
            store=ConversationStore(path)
            cid=store.append(None,'问题',{})
            store.manage(cid,'title',' 新名字 ')
            store.manage(cid,'section','资料')
            store.manage(cid,'unread',True)
            store.manage(cid,'archived',True)
            row=ConversationStore(path).list()[0]
            self.assertEqual((row['title'],row['section'],row['unread'],row['archived']),('新名字','资料',1,1))
            store.manage(cid,'archived',False)
            self.assertFalse(store.get(cid)['archived'])
            with self.assertRaises(ValueError):store.manage(cid,'title',' ')

    def test_branch_is_independent(self):
        with TemporaryDirectory() as folder:
            store=ConversationStore(Path(folder)/'db')
            pid=store.create_project('项目')['id']
            cid=store.append(None,'第一问',{'text':'回答'},'original','孔子',pid)
            store.manage(cid,'section','资料')
            branch=store.branch(cid)
            row=store.get(branch)
            self.assertNotEqual(branch,cid)
            self.assertIsNone(row['session_id'])
            self.assertEqual((row['turns'],row['agent_person'],row['project_id'],row['section']),(store.get(cid)['turns'],'孔子',pid,'资料'))
            store.append(branch,'继续',{})
            self.assertEqual(len(store.get(cid)['turns']),1)

    def test_history_http_actions(self):
        import json
        import threading
        from urllib.request import Request, build_opener, ProxyHandler
        from web_server import LocalServer
        with TemporaryDirectory() as folder:
            server=LocalServer(('127.0.0.1',0),[],collection_path=Path(folder)/'db')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                cid=server.conversations.append(None,'问题',{'cards':[]})
                opened=[]
                server.open_conversation_window=opened.append
                base=f'http://127.0.0.1:{server.server_port}'
                def request(path,data=None):
                    req=Request(base+'/api/conversations'+path,json.dumps(data).encode() if data is not None else None,
                                {'X-Zhongjian-Token':server.nonce,'Content-Type':'application/json'})
                    with build_opener(ProxyHandler({})).open(req,timeout=5) as res:return json.load(res)
                self.assertTrue(request('/manage',{'id':cid,'field':'title','value':'新标题'})['ok'])
                branch=request('/branch',{'id':cid})['id']
                self.assertEqual(request('?id='+branch)['title'],'新标题（分支）')
                self.assertTrue(request('/window',{'id':branch})['ok'])
                self.assertEqual(opened,[branch])
            finally:
                server.shutdown();server.server_close();thread.join()
