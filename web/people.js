/* Jobs live on the local backend and outlive this modal. */
(() => {
  const opener=document.createElement('button');opener.id='people-open';opener.type='button';opener.textContent='人物偏好';opener.setAttribute('aria-label','选择感兴趣的人物');
  const dialog=document.createElement('dialog');dialog.id='people-dialog';
  const progress=document.createElement('div');progress.className='people-progress';progress.hidden=true;
  progress.setAttribute('role','progressbar');progress.setAttribute('aria-label','后台查找与下载中');
  document.body.append(progress);
  dialog.innerHTML='<form id="people-form"><div class="people-head"><h2>想听谁的观点？</h2><button type="button" id="people-close" aria-label="关闭人物选择">×</button></div><p class="people-caption">可多选，建议至少选择两人。</p><div class="people-search"><input id="people-search" type="search" maxlength="80" placeholder="搜索姓名、别名或思想主题" aria-label="搜索人物"><button type="button" id="people-discover" aria-label="查找并下载 Skill" title="查找并下载"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m-4-4 4 4 4-4M5 17v3h14v-3"/></svg></button></div><div id="people-list" class="people-grid"></div><section id="people-remote" aria-label="后台查找任务" aria-live="polite"></section><p id="people-status" role="status"></p><div class="people-bottom"><span id="people-count"></span><button type="submit" id="people-save">保存选择</button></div><p class="people-footnote">后台自动匹配并下载。下载后校验资料，再参与回答。<br>四张卡片按五轮累计分配：兴趣 40% · 推荐 40% · 相似 20%。</p></form>';
  (document.getElementById('menu-actions')||document.body).append(opener);dialog.append(progress.cloneNode(true));document.body.append(dialog);
  const el=id=>document.getElementById(id);
  let all=[],selected=new Set(),nonce='',jobs=[],timer=null,polling=false;
  const running=new Set(['queued','searching','downloading','retry_wait']);
  const text=(tag,value,className)=>{const x=document.createElement(tag);x.textContent=value;if(className)x.className=className;return x;};
  async function api(path,data){
    if(!nonce){const s=await fetch('/api/session').then(r=>r.json());nonce=s.token;}
    const response=await fetch(path,{method:data?'POST':'GET',headers:{'X-Zhongjian-Token':nonce,...(data?{'Content-Type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{})});
    const result=await response.json();if(!response.ok)throw Error(result.message||'操作未完成，请重试。');return result;
  }
  function render(){
    const q=el('people-search').value.trim().toLocaleLowerCase();el('people-list').replaceChildren();
    for(const p of all){
      if(q&&!([p.person,...p.aliases,...p.tags].join(' ').toLocaleLowerCase().includes(q)))continue;
      const label=document.createElement('label');label.className='person-choice';
      const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(p.person);check.value=p.person;
      check.addEventListener('change',()=>{if(check.checked)selected.add(p.person);else selected.delete(p.person);updateCount();});
      const words=document.createElement('span');words.append(text('strong',p.person),text('small',p.tags.slice(0,2).join(' · ')));
      label.title=p.description+(p.ready?'':'；原著资料仍在整理，暂不参与推荐');label.append(check,words);el('people-list').append(label);
    }
    if(!el('people-list').children.length)el('people-list').append(text('p','本地未找到，点下载箭头自动查找。','people-empty'));
    updateCount();
  }
  function updateCount(){el('people-count').textContent='已选 '+selected.size+' 人';}
  function renderJobs(){
    const area=el('people-remote');area.replaceChildren();
    const active=jobs.filter(j=>['queued','searching','downloading'].includes(j.status)).length;
    const waiting=jobs.some(j=>j.status==='retry_wait');
    el('people-discover').classList.toggle('is-loading',active>0);
    el('people-discover').setAttribute('aria-busy',String(active>0));
    progress.hidden=active===0;
    const modalProgress=dialog.querySelector('.people-progress');if(modalProgress)modalProgress.hidden=active===0;
    opener.textContent='人物偏好'+(active?' · 查找中':waiting?' · 等待重试':selected.size?' · '+selected.size:'');
    opener.setAttribute('aria-label','选择感兴趣的人物'+(active?'，'+active+' 个后台任务':''));
    const seen=new Set();
    const latest=jobs.filter(job=>{const key=job.query.toLocaleLowerCase();if(seen.has(key))return false;seen.add(key);return true;});
    for(const job of latest.slice(0,8)){
      const row=text('div','','people-job');
      let message=job.message;
      if(job.status==='retry_wait'&&job.next_retry_at){const seconds=Math.max(0,Math.ceil(job.next_retry_at-Date.now()/1000));const wait=seconds>=60?Math.ceil(seconds/60)+'分钟':seconds+'秒';message=(job.error_code==='rate_limited'?'来源请求次数超限':'等待恢复')+'，'+wait+'后自动重试。';}
      row.append(text('strong',job.query),text('small',message));
      if(['queued','searching','downloading'].includes(job.status)){const dots=text('span','···','job-running');dots.setAttribute('aria-label','后台处理中');row.append(dots);}
      for(const person of (job.people||[]).slice(0,1)){
        const info=text('div','','people-remote-row');info.append(text('span',person.person),text('small',person.description));
        const source=text('a','来源 ↗');source.href=person.identity_url;source.target='_blank';source.rel='noopener';info.append(source);
        row.append(info);
      }
      if(['network_error','interrupted','not_found','no_skill'].includes(job.status)){
        const retry=text('button','重试');retry.type='button';retry.addEventListener('click',()=>start(job.query,true));row.append(retry);
      }
      if(job.result?.repository){const source=text('a','Skill 来源 ↗');source.href=job.result.repository;source.target='_blank';source.rel='noopener';row.append(source);}
      if(job.result?.profile?.biography||job.result?.profile?.portrait_ready){
        row.append(text('small',job.result.profile.portrait_ready?'肖像已准备 · 审核接入后显示':'简介已准备 · 肖像暂缺'));
      }
      area.append(row);
    }
  }
  function schedule(){clearTimeout(timer);if(jobs.some(j=>running.has(j.status)))timer=setTimeout(refresh,1400);}
  async function refresh(){
    if(polling)return;polling=true;
    try{jobs=(await api('/api/people/jobs')).jobs;renderJobs();}
    catch(e){el('people-status').textContent='后台状态暂未连上；重新打开人物偏好可恢复。';}
    finally{polling=false;schedule();}
  }
  async function start(query,retry=false){
    if(!query){el('people-status').textContent='先输入人名。';return;}
    el('people-discover').disabled=true;
    el('people-discover').classList.add('is-loading');progress.hidden=false;
    const modalProgress=dialog.querySelector('.people-progress');if(modalProgress)modalProgress.hidden=false;
    try{await api('/api/people/jobs',{query,retry});el('people-status').textContent='已在后台查找，可以关闭窗口继续提问。';await refresh();}
    catch(e){el('people-status').textContent=e.message;}
    finally{el('people-discover').disabled=false;renderJobs();}
  }
  opener.addEventListener('click',async()=>{
    document.getElementById('app-menu')?.close();el('people-status').textContent='';el('people-search').value='';
    try{const [catalog,prefs]=await Promise.all([api('/api/people'),api('/api/preferences')]);all=catalog.people;selected=new Set(prefs.selected);render();renderJobs();if(!dialog.open)dialog.showModal();await refresh();}
    catch(e){el('people-status').textContent=e.message;if(!dialog.open)dialog.showModal();}
  });
  el('people-close').addEventListener('click',()=>dialog.close());
  el('people-search').addEventListener('input',()=>{el('people-status').textContent='';render();});
  el('people-search').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();start(el('people-search').value.trim());}});
  el('people-form').addEventListener('submit',async e=>{e.preventDefault();el('people-save').disabled=true;try{await api('/api/preferences',{selected:[...selected]});renderJobs();dialog.close();}catch(error){el('people-status').textContent=error.message;}finally{el('people-save').disabled=false;}});
  el('people-discover').addEventListener('click',()=>start(el('people-search').value.trim()));
  document.addEventListener('zhongjian:people-job-started',refresh);
  refresh();
})();
