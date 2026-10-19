"""Interactive terminal frontend for the same loopback API as the webpage."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent

class ChatError(Exception):
    pass

class LocalAPI:
    def __init__(self,url):
        parsed=urlparse(url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password:
            raise ChatError('终端版只连接本机众见后台。')
        self.url=url.rstrip('/');self.token='';self.session_id=None
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self,path,data=None,timeout=240):
        headers={'X-Zhongjian-Token':self.token}
        body=None
        if data is not None:
            headers['Content-Type']='application/json; charset=utf-8'
            body=json.dumps(data,ensure_ascii=False).encode('utf-8')
        try:
            with self.opener.open(urllib.request.Request(self.url+path,data=body,headers=headers),timeout=timeout) as r:
                answer=json.load(r)
        except urllib.error.HTTPError as error:
            try:payload=json.loads(error.read().decode('utf-8'))
            except (ValueError,UnicodeError):payload={}
            finally:error.close()
            if payload.get('session_id'):self.session_id=payload['session_id']
            code=payload.get('error')
            friendly={'invalid_json':'这次回答没整理完整，输入“重试”再试一次。',
                      'output_truncated':'这次回答没整理完整，输入“重试”再试一次。',
                      'token_rejected':'后台已重启，请退出后重新打开终端版。',
                      'detail_generation_failed':'详解暂未整理好，可以重新输入人物编号。'}
            raise ChatError(friendly.get(code,payload.get('message','本次请求未完成，请稍后重试。'))) from None
        except (urllib.error.URLError,TimeoutError,ConnectionError,OSError):
            raise ChatError('本机后台暂时未连接，或请求超时。可重新打开终端版。') from None
        except (ValueError,UnicodeError):
            raise ChatError('后台返回格式异常，输入“重试”再试一次。') from None
        if not isinstance(answer,dict):raise ChatError('后台返回格式异常。')
        if answer.get('session_id'):self.session_id=answer['session_id']
        return answer

    def connect(self):
        data=self.request('/api/session',timeout=2)
        if not isinstance(data.get('token'),str) or not isinstance(data.get('ready'),bool):
            raise ChatError('这个端口不是可识别的众见后台。')
        self.token=data['token'];return data

    def query(self,question):
        return self.request('/api/query',{'question':question,'session_id':self.session_id})['result']

    def details(self,card,question):
        payload={'passage_id':card.get('id',card.get('passage_id')),'question':question}
        if isinstance(card.get('highlight_start'),int) and isinstance(card.get('highlight_end'),int):
            payload.update(highlight_start=card['highlight_start'],highlight_end=card['highlight_end'])
        return self.request('/api/source/details',payload)

    def reset(self):
        self.request('/api/session/reset',{'session_id':self.session_id});self.session_id=None


def ensure_backend(api,port,model=None,no_start=False,out=print):
    try:status=api.connect()
    except ChatError:
        # Never start over an occupied port or an unrecognized HTTP service.
        import socket
        with socket.socket() as s:
            occupied=s.connect_ex(('127.0.0.1',port))==0
        if occupied:raise ChatError('端口已被占用但连接未完成，请稍候重开终端版，或检查后台。')
        if no_start:raise
        key=os.environ.get('DEEPSEEK_API_KEY','').strip() or getpass.getpass('输入 DeepSeek 密钥（隐藏输入，仅本次使用）：').strip()
        if not key:raise ChatError('尚未配置密钥。可先运行“配置密钥.ps1”。')
        env=os.environ.copy();env['DEEPSEEK_API_KEY']=key;env['PYTHONUTF8']='1'
        if model:env['DEEPSEEK_MODEL']=model
        options={'cwd':str(ROOT),'env':env,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
        if os.name=='nt':options['creationflags']=subprocess.CREATE_NO_WINDOW
        else:options['start_new_session']=True
        out('正在启动本机后台……')
        process=subprocess.Popen([sys.executable,'-u',str(ROOT/'web_server.py'),'--port',str(port)],**options)
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if process.poll() is not None:raise ChatError('后台启动失败，请用“启动网页.ps1”查看启动情况。')
            try:
                status=api.connect()
                if status.get('ready'):break
            except ChatError:pass
            time.sleep(.25)
        else:
            process.terminate();raise ChatError('后台启动等待超时，请用“启动网页.ps1”检查。')
    if not status.get('ready'):raise ChatError('后台尚未加载密钥，请先关闭它，再运行已配置密钥的启动脚本。')
    if model and status.get('model')!=model:
        raise ChatError('现有后台的模型与指定模型不一致或版本未报告模型。请先关闭旧后台，再用 -Model 指定模型启动。')
    return status


HELP='直接输入问题；1～4 看人物详解；返回上层；摘要 看人物概览；更多1 看相关文章；原文 看原句；新问题 另起话题；重试；退出。'

class TerminalChat:
    def __init__(self,api,out=print):
        self.api=api;self.out=out;self.result=None;self.question='';self.stack=[];self.cache={};self.failed=None

    def summary(self):
        if not self.result:self.out('先直接输入你的问题。');return
        r=self.result
        if r.get('question_title'):self.out('\n'+r['question_title'])
        reply=r.get('display_reply') or r.get('synthesis','')
        if reply and (not r.get('cards') or r.get('pending_confirmation') or r.get('clarification',{}).get('awaiting_answer')):self.out(reply)
        for i,c in enumerate(r.get('cards',[]),1):
            d=c.get('display',c)
            self.out('\n['+str(i)+'] '+d.get('person',c.get('person',''))+' · '+d.get('viewpoint_title',''))
            self.out(d.get('explanation',c.get('explanation','')))
            weights=d.get('advice_tendency',c.get('advice_tendency'))
            if weights:self.out('  '.join(str(w['option'])+' ≈'+str(w['percent'])+'%' for w in weights))
            quote=d.get('excerpt') or c.get('quote','')
            if quote:self.out('「'+quote+'」'+('（译意）' if d.get('is_translation') else ''))
        if r.get('cards'):self.out('\n输入人物编号展开，或直接继续聊。')

    def detail(self,d):
        self.out('\n'+d.get('person','')+'\n')
        self.out(d.get('reading','本次详解尚未整理完成。'))
        if d.get('reference'):self.out('\n'+d['reference'])
        for i,p in enumerate(d.get('related',[]),1):self.out('更多'+str(i)+' · '+p.get('reference','相关文章'))
        self.out('\n返回 · 原文 · 或直接继续聊')

    def open_detail(self,card,replace=False):
        q=(self.result or {}).get('question_context') or self.question
        key=(card.get('id',card.get('passage_id')),card.get('highlight_start'),card.get('highlight_end'),q)
        if key not in self.cache:
            self.out('正在整理详解……');self.cache[key]=self.api.details(card,q)
        if replace:self.stack=[]
        self.stack.append(self.cache[key]);self.detail(self.stack[-1])

    def handle(self,text):
        text=text.strip()
        if not text:return True
        if text in ('退出','exit','quit','/exit'):return False
        if text in ('帮助','help','/help'):self.out(HELP);return True
        if text in ('返回','摘要'):
            if text=='返回' and len(self.stack)>1:self.stack.pop();self.detail(self.stack[-1])
            else:self.stack=[];self.summary()
            return True
        if text in ('新问题','新话题','/new'):
            self.api.reset();self.result=None;self.question='';self.stack=[];self.cache={};self.failed=None
            self.out('已另起话题，直接输入新问题。');return True
        if text=='原文':
            if not self.stack:self.out('先输入人物编号，再看原文。')
            else:
                d=self.stack[-1];self.out('\n'+(d.get('original_focus') or d.get('original','')))
                if d.get('edition_note'):self.out(d['edition_note'])
            return True
        if text.isdigit():
            cards=(self.result or {}).get('cards',[]);n=int(text) if len(text)<=2 else 0
            if not 1<=n<=len(cards):self.out('请输入当前人物的编号。');return True
            self.open_detail(cards[n-1],replace=True);return True
        match=re.fullmatch(r'更多\s*([1-9])',text)
        if match:
            items=self.stack[-1].get('related',[]) if self.stack else [];n=int(match[1])
            if not 1<=n<=len(items):self.out('这份详解没有这个相关文章编号。');return True
            self.open_detail(items[n-1]);return True
        if text=='重试':
            if not self.failed:self.out('当前没有待重试的问题。');return True
            text=self.failed
        if len(text)>2000:self.out('问题请控制在2000字以内。');return True
        self.failed=text;self.out('正在思考……')
        answer=self.api.query(text)
        self.result=answer;self.question=text;self.stack=[];self.cache={};self.failed=None
        if text.startswith(('收藏','确认','取消')):
            message=answer.get('display_reply') or answer.get('synthesis','')
            if message:self.out(message)
        self.summary();return True

    def run(self,input_fn=input):
        self.out('众见终端版 · 与网页共用后台，对话独立\n'+HELP)
        while True:
            try:
                if not self.handle(input_fn('\n你 > ')):break
            except EOFError:break
            except KeyboardInterrupt:self.out('\n已结束本次等待。可继续输入，或输入“退出”。')
            except ChatError as error:self.out(str(error)+'\n原有内容仍保留。')
        self.out('已退出终端对话；后台仍可供网页使用。')


def main():
    parser=argparse.ArgumentParser(description='众见交互终端：直接聊、输入编号看详解。')
    parser.add_argument('--port',type=int,default=8765);parser.add_argument('--model');parser.add_argument('--no-start',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('port must be between 1 and 65535')
    api=LocalAPI('http://127.0.0.1:'+str(args.port))
    try:
        ensure_backend(api,args.port,args.model,args.no_start)
        TerminalChat(api).run();return 0
    except (ChatError,KeyboardInterrupt,EOFError) as error:
        print(str(error) or '已结束。');return 1

if __name__=='__main__':raise SystemExit(main())
