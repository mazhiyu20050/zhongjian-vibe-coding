"""Bounded local background jobs. Network work outlives a modal, not the app.

Persist public search terms and provenance, never model credentials or questions.
Downloaded Markdown remains quarantined and is never executed or auto-activated.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import time

from presentation import simplified
from people_discovery import rank_people,PublicAPIError

RUNNING={'queued','searching','downloading','retry_wait'}


class DiscoveryJobs:
    def __init__(self,folder,lookup,download,retry_delays=(5,20)):
        self.folder=Path(folder);self.path=self.folder/'discovery-jobs.json'
        self.lookup=lookup;self.download=download
        self.lock=threading.RLock();self.jobs={};self.tasks=queue.Queue(maxsize=6)
        self.closed=False;self.workers=[];self.timers={};self.retry_delays=retry_delays
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            for job in saved[-64:]:
                if job['status'] in RUNNING-{'retry_wait'}:
                    job.update(status='interrupted',message='上次任务被关闭，点重试继续。')
                self.jobs[job['id']]=job
        except (OSError,ValueError,KeyError,TypeError):self.jobs={}
        # Migrate older "choose a person" tasks to the new automatic workflow.
        for jid,job in self.jobs.items():
            if job['status']=='awaiting_choice':
                ranked=rank_people(job.get('people',[]),job['query'])
                if ranked and not self.tasks.full():
                    job.update(status='queued',people=[ranked[0]],message='已自动匹配，后台下载中。')
                    self.tasks.put_nowait((jid,ranked[0]))
                else:job.update(status='interrupted',message='可重试自动匹配。')
        if not self.tasks.empty():
            self._save();self._workers()
        for jid,job in self.jobs.items():
            if job['status']=='retry_wait':self._schedule(jid,max(0,job.get('next_retry_at',time.time())-time.time()))

    def _save(self):
        self.folder.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(list(self.jobs.values()),ensure_ascii=False),encoding='utf-8')
        os.replace(temp,self.path)

    def _update(self,jid,**values):
        with self.lock:
            self.jobs[jid].update(values,updated_at=time.time());self._save()

    def list(self):
        with self.lock:return deepcopy(list(self.jobs.values())[-30:][::-1])

    def start(self,query,retry=False):
        if not isinstance(query,str) or not 1<=len(query.strip())<=80:raise ValueError('invalid_query')
        query=simplified(query.strip())
        with self.lock:
            if self.closed:raise RuntimeError('jobs_closed')
            for job in reversed(list(self.jobs.values())):
                same=job['query'].casefold()==query.casefold()
                cached=job['status'] in ('completed','awaiting_choice') and time.time()-job['updated_at']<86400
                if same and (job['status'] in RUNNING or cached and not retry):return deepcopy(job)
            if sum(j['status'] in RUNNING for j in self.jobs.values())>=6:raise RuntimeError('queue_full')
            if len(self.jobs)>=64:
                old=next((k for k,j in self.jobs.items() if j['status'] not in RUNNING),None)
                if old is None:raise RuntimeError('queue_full')
                del self.jobs[old]
            jid=secrets.token_hex(12)
            # Retry known identities without paying for another identical lookup.
            cached=next((j.get('people',[]) for j in reversed(list(self.jobs.values()))
                         if j['query'].casefold()==query.casefold() and j.get('people')
                         and time.time()-j['people'][0].get('verified_at',0)<86400),[])
            cached=rank_people(cached,query)
            job={'id':jid,'query':query,'status':'queued','message':'已加入后台查找。','people':cached[:1],
                 'updated_at':time.time(),'result':None,'attempt':0}
            self.jobs[jid]=job;self._save();self._workers();self.tasks.put_nowait((jid,cached[0] if cached else None))
            return deepcopy(job)

    def _schedule(self,jid,delay):
        def wake():
            with self.lock:
                self.timers.pop(jid,None)
                if self.closed:return
                job=self.jobs[jid];people=rank_people(job.get('people',[]),job['query'])
                if self.tasks.full():self._schedule(jid,5);return
                self._update(jid,status='queued',message='正在自动重试…')
                self._workers();self.tasks.put_nowait((jid,people[0] if people else None))
        timer=threading.Timer(delay,wake);timer.daemon=True;self.timers[jid]=timer;timer.start()

    def _failed(self,jid,error):
        kind=getattr(error,'kind','connection_error' if isinstance(error,OSError) else 'internal_error')
        service=getattr(error,'service','')
        messages={'rate_limited':(service or '来源')+'请求次数超限', 'access_denied':'来源拒绝访问',
                  'certificate_error':'来源证书校验失败','timeout':'来源响应超时',
                  'connection_error':'网络连接中断','service_unavailable':'来源服务暂时异常',
                  'internal_error':'任务处理异常'}
        attempt=self.jobs[jid].get('attempt',0)
        retryable=getattr(error,'retryable',isinstance(error,OSError))
        if retryable and attempt<len(self.retry_delays):
            delay=max(self.retry_delays[attempt],getattr(error,'retry_after',0))
            wait=f'{int(delay+0.99)}秒' if delay<120 else f'{int(delay/60+0.99)}分钟'
            self._update(jid,status='retry_wait',error_code=kind,attempt=attempt+1,next_retry_at=time.time()+delay,
                         message=messages[kind]+'，'+wait+'后自动重试。')
            with self.lock:
                if not self.closed:self._schedule(jid,delay)
        else:self._update(jid,status='network_error',error_code=kind,message=messages[kind]+'；任务已保留，可稍后重试。')

    def choose(self,jid,qid):
        with self.lock:
            job=self.jobs.get(jid)
            if not job or job['status']!='awaiting_choice':raise ValueError('not_awaiting_choice')
            person=next((p for p in job['people'] if p['wikidata_id']==qid),None)
            if not person:raise ValueError('unverified_choice')
            if self.closed or self.tasks.full():raise RuntimeError('queue_full')
            self._update(jid,status='queued',message='已确认人物，后台下载中。')
            self._workers();self.tasks.put_nowait((jid,deepcopy(person)))
            return deepcopy(job)

    def _workers(self):
        if self.workers:return
        for _ in range(2):
            worker=threading.Thread(target=self._work,daemon=True,name='zhongjian-person-discovery')
            self.workers.append(worker);worker.start()

    def _work(self):
        while True:
            task=self.tasks.get()
            try:
                if task is None:return
                jid,person=task
                if self.closed:return
                if person is None:
                    self._update(jid,status='searching',message='正在检索人物、别名并核验身份…')
                    people=self.lookup(self.jobs[jid]['query'])
                    people=rank_people(people,self.jobs[jid]['query'])
                    if not people:
                        self._update(jid,status='not_found',message='暂未检索到已核验的人物，可换用全名或英文名。');continue
                    person=people[0]
                self._update(jid,status='downloading',people=[person],auto_matched=True,message='已自动匹配，正在查找并下载 Skill…')
                result=self.download(person,self.folder/'skills-incoming')
                if result['status']=='downloaded_pending_review':
                    self._update(jid,status='completed',result=result,message='Skill 已下载，待资料校验。')
                else:
                    self._update(jid,status='no_skill',result=result,message='人物已找到，暂未发现许可明确、姓名匹配的 Skill。')
            except Exception as error:
                if task is not None:
                    self._failed(task[0],error)
            finally:self.tasks.task_done()

    def close(self):
        with self.lock:
            self.closed=True
            for timer in self.timers.values():timer.cancel()
            # Never block desktop shutdown on a third-party timeout.
            for worker in self.workers:
                try:self.tasks.put_nowait(None)
                except queue.Full:break
