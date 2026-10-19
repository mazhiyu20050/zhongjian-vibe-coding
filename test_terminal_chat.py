import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from terminal_chat import LocalAPI,TerminalChat,ChatError,ensure_backend
from web_server import LocalServer

CARD={'id':'source-1','person':'测试人物','highlight_start':0,'highlight_end':3,
      'display':{'person':'测试人物','viewpoint_title':'先辨事实','explanation':'先看具体发生了什么。','excerpt':'测试原文','advice_tendency':[{'option':'核实','percent':60},{'option':'调整','percent':40}]}}
RESULT={'question_title':'面对批评','question_context':'合成问题','cards':[CARD]}
DETAIL={'person':'测试人物','reading':'这是详解，先分清具体事实与人格评价。','original':'测试原文','reference':'测试作品',
        'related':[{'id':'source-2','reference':'相关文章'}]}

class TerminalChatTests(unittest.TestCase):
    def setUp(self):
        self.api=Mock();self.api.query.return_value=RESULT;self.api.details.return_value=DETAIL
        self.lines=[];self.app=TerminalChat(self.api,self.lines.append)

    def test_plain_question_number_and_return_need_no_code(self):
        self.app.handle('合成问题');self.app.handle('1');self.app.handle('返回')
        self.api.query.assert_called_once_with('合成问题')
        self.api.details.assert_called_once_with(CARD,'合成问题')
        text='\n'.join(self.lines)
        self.assertIn('[1] 测试人物',text);self.assertIn('核实 ≈60%',text);self.assertIn('这是详解',text)
        self.assertNotIn('passage_id',text);self.assertFalse(self.app.stack)

    def test_detail_is_cached_and_related_can_be_opened(self):
        self.app.handle('合成问题');self.app.handle('1');self.app.handle('1')
        self.assertEqual(self.api.details.call_count,1)
        self.app.handle('更多1');self.assertEqual(self.api.details.call_count,2)
        self.app.handle('原文');self.assertIn('测试原文','\n'.join(self.lines))

    def test_query_failure_keeps_previous_answer_and_can_retry(self):
        self.app.handle('第一个问题');self.api.query.side_effect=[ChatError('测试错误'),RESULT]
        with self.assertRaises(ChatError):self.app.handle('第二个问题')
        self.assertEqual(self.app.result,RESULT);self.assertEqual(self.app.failed,'第二个问题')
        self.app.handle('重试');self.assertIsNone(self.app.failed)
        self.assertEqual(self.api.query.call_args.args[0],'第二个问题')

    def test_new_topic_resets_backend_and_terminal_memory(self):
        self.app.handle('合成问题');self.app.handle('1');self.app.handle('新问题')
        self.api.reset.assert_called_once();self.assertIsNone(self.app.result);self.assertEqual(self.app.cache,{})

    def test_invalid_numbers_do_not_call_paid_api(self):
        self.app.handle('4');self.app.handle('更多1');self.app.handle('原文')
        self.api.query.assert_not_called();self.api.details.assert_not_called()

    def test_interactive_loop_accepts_natural_text_and_exit(self):
        self.app.run(Mock(side_effect=['合成问题','1','返回','退出']))
        self.assertIn('已退出终端对话','\n'.join(self.lines))

    def test_existing_backend_does_not_start_another_process(self):
        self.api.connect.return_value={'ready':True,'model':'deepseek-flash'}
        with patch('terminal_chat.subprocess.Popen') as start:
            ensure_backend(self.api,8765,'deepseek-flash');start.assert_not_called()

    def test_model_mismatch_is_not_silently_ignored(self):
        self.api.connect.return_value={'ready':True,'model':'different'}
        with self.assertRaises(ChatError):ensure_backend(self.api,8765,'requested')

    def test_missing_backend_starts_hidden_with_requested_model(self):
        self.api.connect.side_effect=[ChatError('not started'),{'ready':True,'model':'requested'}]
        with patch('socket.socket') as sock,patch('terminal_chat.subprocess.Popen') as start,patch.dict('os.environ',{'DEEPSEEK_API_KEY':'synthetic-test-key'}):
            sock.return_value.__enter__.return_value.connect_ex.return_value=1
            start.return_value.poll.return_value=None
            ensure_backend(self.api,18765,'requested',out=self.lines.append)
            options=start.call_args.kwargs
            self.assertEqual(options['env']['DEEPSEEK_MODEL'],'requested')
            self.assertEqual(options['env']['DEEPSEEK_API_KEY'],'synthetic-test-key')
            self.assertEqual(start.call_args.args[0][-2:],['--port','18765'])
            self.assertNotIn('synthetic-test-key','\n'.join(self.lines))

    def test_remote_destinations_are_not_allowed(self):
        for url in ('https://example.com','http://example.com','http://user:pass@127.0.0.1:8765'):
            with self.assertRaises(ChatError):LocalAPI(url)

    def test_real_local_http_preserves_utf8_and_conversation_session(self):
        class Agent:
            def __init__(self):self.calls=[]
            def ask(self,q,sid):self.calls.append((q,sid));return {'session_id':'session-test','result':RESULT}
            def reset(self,sid):self.reset_id=sid
        with tempfile.TemporaryDirectory() as tmp:
            server=LocalServer(('127.0.0.1',0),[],lambda q:RESULT,Path(tmp)/'db.sqlite3');server.agent=Agent()
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                api=LocalAPI('http://127.0.0.1:'+str(server.server_port));self.assertTrue(api.connect()['ready'])
                self.assertEqual(api.query('中文合成问题')['question_title'],'面对批评')
                api.query('继续追问');self.assertEqual(server.agent.calls,[('中文合成问题',None),('继续追问','session-test')])
                api.reset();self.assertEqual(server.agent.reset_id,'session-test');self.assertIsNone(api.session_id)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
