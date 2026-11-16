/* Rank only the reviewed roster; a weak match must not send the wheel to someone else. */
const matchAgentPerson = (() => {
  const normalize = value => String(value ?? '').normalize('NFKD').toLowerCase()
    .replace(/u\u0308/g,'v').replace(/\p{M}/gu,'').replace(/[^\p{L}\p{N}]/gu,'');
  function edits(a,b){
    const rows=[Array.from({length:b.length+1},(_,index)=>index)];
    for(let i=1;i<=a.length;i++){
      const row=[i],prev=rows[i-1];
      for(let j=1;j<=b.length;j++){
        row[j]=Math.min(row[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]!==b[j-1]));
        if(i>1&&j>1&&a[i-1]===b[j-2]&&a[i-2]===b[j-1])row[j]=Math.min(row[j],rows[i-2][j-2]+1);
      }
      rows.push(row);
    }
    return rows[a.length][b.length];
  }
  function score(query,field){
    if(query===field)return 1;
    if(query.length<2||field.length<2)return 0;
    const han=/\p{Script=Han}/u.test(query), fieldHan=/\p{Script=Han}/u.test(field);
    if(han!==fieldHan)return 0;
    const ratio=query.length/field.length;
    if(field.startsWith(query)&&(han?ratio>=.45:query.length>=3))return .88+.09*ratio;
    if(field.includes(query)&&(han?ratio>=.5:query.length>=4&&ratio>=.55))return .82+.08*ratio;
    const n=Math.min(query.length,field.length);
    if(n<(han?3:5)||Math.abs(query.length-field.length)>2)return 0;
    const distance=edits(query,field);
    if(distance<=1)return .78+.02*n/Math.max(query.length,field.length);
    if(distance===2&&((han&&n>=4&&query[0]===field[0])||(!han&&n>=7&&query.slice(0,2)===field.slice(0,2))))return .70;
    return 0;
  }
  return (value,people)=>{
    const query=normalize(value);if(!query||query.length>80)return null;
    const ranked=people.map(person=>{
      const fields=[person.person,...(person.aliases||[]),person.pinyin].map(normalize).filter(Boolean);
      const soundAlike=(person.search_aliases||[]).some(alias=>normalize(alias)===query)? .89 : 0;
      return {person,score:Math.max(soundAlike,...fields.map(field=>score(query,field)))};
    }).filter(entry=>entry.score>=.70).sort((a,b)=>b.score-a.score);
    if(!ranked.length||(ranked.length>1&&ranked[0].score<ranked[1].score+.035&&
      (ranked[0].score<1||ranked[1].score===1)))return null;
    return ranked[0].person;
  };
})();
if(typeof module!=='undefined')module.exports=matchAgentPerson;

/* A discreet top-edge entrance; only reviewed, answer-capable people appear. */
if(typeof document!=='undefined')(() => {
  const dock=document.createElement('section');dock.id='agent-dock';dock.setAttribute('aria-label','人物智能体选择');
  dock.innerHTML='<button id="agent-trigger" type="button" aria-label="选择专属智能体" aria-expanded="false" aria-controls="agent-panel"></button><div id="agent-panel" role="region" aria-label="人物卡牌" inert><div class="agent-panel-head"><h2>和谁聊聊？</h2><button type="button" id="agent-default">众见 · 多人观点</button></div><div id="agent-cards"></div><input id="agent-scroll" type="range" min="0" max="0" step="1" value="0" aria-label="人物轮盘位置" disabled><p id="agent-note"></p></div>';
  const current=node('button','','agent-current');current.type='button';current.hidden=true;current.title='切换智能体';document.body.append(dock,current);
  const trigger=$('agent-trigger'),panel=$('agent-panel');let loaded=false,loading=false,roster='';
  const close=node('button','×');close.id='agent-panel-close';close.type='button';close.setAttribute('aria-label','关闭人物轮盘');panel.append(close);
  const stage=$('agent-cards'),slider=$('agent-scroll');stage.tabIndex=0;stage.setAttribute('aria-label','人物轮盘，滚轮或左右方向键切换');
  const group=node('div',undefined,'agent-search-group');
  group.innerHTML='<button id="agent-search-toggle" type="button" aria-label="搜索人物" aria-expanded="false" aria-controls="agent-search-form" title="搜索人物"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="5.6"/><path d="m15 15 4.2 4.2"/></svg></button><form id="agent-search-form" role="search" aria-label="搜索人物" hidden><input id="agent-search" aria-label="姓名、别名或拼音" placeholder="姓名、别名或拼音" maxlength="80" autocomplete="off" spellcheck="false"><button id="agent-search-go" type="submit" hidden></button><button id="agent-search-download" type="button" aria-label="查找并下载人物 Skill" title="查找并下载人物 Skill" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v10m-4-4 4 4 4-4M5 15v4h14v-4"/></svg></button></form><p id="agent-search-status" role="status" hidden></p>';
  panel.querySelector('h2').after(group);
  const searchToggle=$('agent-search-toggle'),searchForm=$('agent-search-form'),searchInput=$('agent-search');
  const searchGo=$('agent-search-go'),searchDownload=$('agent-search-download'),searchStatus=$('agent-search-status');
  let people=[],searchMatch=null,composing=false,shake=null,markedCard=null,markTimer=null,jobRequest='',jobPoll=null;
  const searchJobs=new Map(), runningJobs=new Set(['queued','searching','downloading','retry_wait']);
  const retryJobs=new Set(['network_error','interrupted','not_found','no_skill']);
  const searchValue=()=>searchInput.value.trim();
  const jobKey=value=>value.normalize('NFKC').toLowerCase();
  function refreshSearch(){
    const value=searchValue();
    searchMatch=value&&!composing?matchAgentPerson(value,people):null;
    const job=searchJobs.get(jobKey(value));
    const pending=jobRequest===jobKey(value)||runningJobs.has(job?.status);
    searchGo.hidden=!searchMatch;
    searchGo.textContent=searchMatch?searchMatch.person+' ↗':'';
    searchDownload.hidden=!loaded||!value||composing||Boolean(searchMatch);
    searchDownload.disabled=pending||job?.status==='completed';
    searchDownload.classList.toggle('is-loading',pending);
    searchStatus.textContent=job?.message||(!loaded&&value?'正在加载人物…':'');
    searchStatus.hidden=!searchStatus.textContent||searchForm.hidden||Boolean(searchMatch);
  }
  function closeSearch(){
    searchForm.hidden=true;searchStatus.hidden=true;searchToggle.setAttribute('aria-expanded','false');
    searchInput.value='';searchMatch=null;composing=false;
  }
  searchToggle.addEventListener('click',()=>{
    if(!searchForm.hidden){closeSearch();return;}
    searchForm.hidden=false;searchToggle.setAttribute('aria-expanded','true');refreshSearch();
    searchInput.focus({preventScroll:true});
  });
  searchInput.addEventListener('compositionstart',()=>{composing=true;refreshSearch();});
  searchInput.addEventListener('compositionend',()=>{composing=false;refreshSearch();});
  searchInput.addEventListener('input',refreshSearch);
  searchInput.addEventListener('keydown',event=>{
    if(event.key==='Enter'&&(event.isComposing||event.keyCode===229))event.preventDefault();
  });
  searchForm.addEventListener('submit',event=>{
    event.preventDefault();if(composing||!searchMatch)return;
    const index=cardNodes.findIndex(card=>card.dataset.person===searchMatch.person);
    if(index<0)return;
    jumpTo(index);
  });
  async function monitorJob(id,key){
    try{
      const result=await getJSON('/api/people/jobs');
      const job=result.jobs.find(item=>item.id===id);
      if(!job){
        searchJobs.set(key,{status:'network_error',message:'未找到这次任务，可点图标重试。'});
        refreshSearch();return;
      }
      searchJobs.set(key,job);refreshSearch();
    }catch{
      searchJobs.set(key,{status:'network_error',message:'暂未查到下载进度，可点图标重试。'});
      refreshSearch();
    }finally{
      scheduleJobs();
    }
  }
  function scheduleJobs(){
    if(jobPoll!==null)return;
    const item=[...searchJobs].find(([,job])=>job.id&&runningJobs.has(job.status));
    if(item)jobPoll=setTimeout(()=>{
      jobPoll=null;monitorJob(item[1].id,item[0]);
    },1000);
  }
  searchDownload.addEventListener('click',async()=>{
    const value=searchValue(),key=jobKey(value);
    if(!value||searchMatch||jobRequest||!loaded)return;
    const retry=retryJobs.has(searchJobs.get(key)?.status);
    jobRequest=key;
    searchJobs.set(key,{status:'queued',message:'正在提交后台查找…'});refreshSearch();
    if(!reduced.matches&&searchForm.animate){
      shake?.cancel();
      shake=searchForm.animate(
        [0,-6,5,-4,3,-2,0].map(x=>({transform:'translate3d('+x+'px,0,0)'})),
        {duration:290,easing:'ease-out'}
      );
    }
    try{
      const result=await getJSON('/api/people/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:value,retry})});
      searchJobs.set(key,result.job);scheduleJobs();
      document.dispatchEvent(new Event('zhongjian:people-job-started'));
    }catch(error){
      searchJobs.set(key,{status:'network_error',message:error.message||'提交暂未成功，请重试。'});
    }finally{jobRequest='';refreshSearch();}
  });
  const bio=document.createElement('dialog');bio.id='agent-bio';
  bio.setAttribute('aria-labelledby','agent-bio-name');bio.setAttribute('aria-describedby','agent-bio-text');
  bio.innerHTML='<button type="button" class="agent-bio-close" aria-label="关闭生平简介" autofocus>×</button><p class="agent-bio-label">人物生平</p><h2 id="agent-bio-name"></h2><p id="agent-bio-meta"></p><p id="agent-bio-text"></p><a id="agent-bio-source" target="_blank" rel="noopener noreferrer">查看人物资料 ↗</a> <a id="agent-bio-portrait" target="_blank" rel="noopener noreferrer">肖像来源 ↗</a>';
  document.body.append(bio);
  let bioCard=null;
  function showBio(person,card){
    if(bio.open)return;
    bioCard=card;
    $('agent-bio-name').textContent=person.person;
    $('agent-bio-meta').textContent=[person.lifespan,person.description].filter(Boolean).join(' · ');
    $('agent-bio-text').textContent=person.biography||'暂未收录详细生平。';
    function link(id, value){
      const source=$(id);let url=null;
      try{url=new URL(value);}catch{}
      source.hidden=url?.protocol!=='https:';
      if(source.hidden)source.removeAttribute('href');else source.href=url.href;
    }
    link('agent-bio-source',person.biography_url||person.identity_url);
    link('agent-bio-portrait',person.portrait?.source);
    bio.showModal();
  }
  bio.querySelector('.agent-bio-close').addEventListener('click',()=>bio.close());
  let backdropPress=false;
  function onBackdrop(event){
    if(event.target!==bio)return false;
    const box=bio.getBoundingClientRect();
    return event.clientX<box.left||event.clientX>=box.right||event.clientY<box.top||event.clientY>=box.bottom;
  }
  bio.addEventListener('pointerdown',event=>{backdropPress=onBackdrop(event);});
  bio.addEventListener('click',event=>{if(backdropPress&&onBackdrop(event))bio.close();backdropPress=false;});
  bio.addEventListener('close',()=>{
    backdropPress=false;
    if(dock.classList.contains('open')&&!bioCard?.hidden)bioCard?.focus({preventScroll:true});
    bioCard=null;
  });
  let cardNodes=[],position=0,target=0,frame=null,snapTimer=null,flight=null;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  function paint(){
    const count=cardNodes.length;if(!count)return;
    slider.value=String(((Math.round(target)%count)+count)%count);
    const step=Math.min(window.innerWidth*.16,155);
    for(let index=0;index<count;index++){
      const card=cardNodes[index];const distance=((index-position+count/2)%count+count)%count-count/2;
      const d=Math.abs(distance),visible=d<3.25;
      if(card.hidden===visible||!card.hasAttribute('aria-hidden')){
        card.hidden=!visible;card.inert=!visible;card.tabIndex=visible?0:-1;
        card.setAttribute('aria-hidden',String(!visible));
      }
      if(!visible)continue;
      card.style.setProperty('--wheel-transform','translate(-50%,-50%) translate3d('+(distance*step).toFixed(2)+'px,'+(d*4).toFixed(2)+'px,'+(-d*90).toFixed(2)+'px) rotateY('+(-distance*11).toFixed(2)+'deg) scale('+Math.max(.42,1-d*.18).toFixed(3)+')');
      card.style.zIndex=String(100-Math.round(d*15));card.style.opacity=String(Math.max(.28,1-d*.17));
      card.style.filter='brightness('+Math.max(.65,1-d*.12).toFixed(2)+')';card.classList.toggle('is-center',d<.5);
    }
  }
  function animate(now){
    frame=null;
    if(reduced.matches){position=target;if(flight)highlightCard();flight=null;}
    else if(flight){
      const t=Math.max(0,Math.min(1,(now-flight.start)/flight.duration));
      position=flight.origin+(target-flight.origin)*(1-Math.pow(1-t,3));
      if(t===1){position=target;flight=null;highlightCard();}
    }else position+=(target-position)*.16;
    if(!flight&&Math.abs(target-position)<.002)position=target;paint();
    if(flight||position!==target)frame=requestAnimationFrame(animate);
  }
  function move(delta){flight=null;target+=delta;if(frame===null)frame=requestAnimationFrame(animate);}
  function highlightCard(){
    const count=cardNodes.length;if(!count)return;
    clearTimeout(markTimer);markedCard?.classList.remove('is-found');
    markedCard=cardNodes[((Math.round(target)%count)+count)%count];
    markedCard.classList.add('is-found');
    markTimer=setTimeout(()=>markedCard?.classList.remove('is-found'),850);
  }
  function jumpTo(index){
    const count=cardNodes.length;
    const offset=((index-position+count/2)%count+count)%count-count/2;
    clearTimeout(snapTimer);
    target=Math.abs(offset)<.002?Math.round(position):position+offset;
    if(reduced.matches||Math.abs(offset)<.002){
      if(frame!==null)cancelAnimationFrame(frame);
      frame=null;flight=null;position=target;paint();highlightCard();return;
    }
    flight={origin:position,start:performance.now(),duration:Math.min(490,300+Math.abs(offset)*20)};
    if(frame===null)frame=requestAnimationFrame(animate);
  }
  function centerSelected(){
    const selected=cardNodes.findIndex(card=>card.dataset.person===agentPerson);
    flight=null;position=target=selected<0?0:selected;paint();
  }
  function hide(){if(bio.open)return;closeSearch();dock.classList.remove('open');trigger.setAttribute('aria-expanded','false');panel.inert=true;clearTimeout(snapTimer);if(frame!==null)cancelAnimationFrame(frame);frame=null;flight=null;}
  async function show(){
    const wasOpen=dock.classList.contains('open');
    dock.classList.add('open');trigger.setAttribute('aria-expanded','true');panel.inert=false;
    if(loaded)paint();if(loading||(loaded&&wasOpen))return;loading=true;
    try{
      const result=await getJSON('/api/agents');const signature=JSON.stringify(result.agents);
      if(signature===roster||bio.open)return;
      const cards=$('agent-cards');cards.replaceChildren();roster=signature;
      people=result.agents;
      for(const person of people){
        const card=node('button',undefined,'agent-card');card.type='button';card.dataset.person=person.person;card.setAttribute('aria-label','与'+person.person+'对话');
        if(person.portrait){
          const img=document.createElement('img');img.src=person.portrait.url;img.alt=person.person+'肖像';img.loading='lazy';
          img.addEventListener('error',()=>{img.remove();card.prepend(node('span',person.person.slice(0,1),'portrait-placeholder'));});
          card.append(img);card.title=[person.portrait.artist,person.portrait.license,person.portrait.source].filter(Boolean).join(' · ');
        }else card.append(node('span',person.person.slice(0,1),'portrait-placeholder'));
        card.append(node('strong',person.person),node('small',person.tags.slice(0,2).join(' · ')));
        card.setAttribute('aria-description','右键或 Shift+F10 查看生平简介');
        card.addEventListener('contextmenu',event=>{event.preventDefault();event.stopPropagation();showBio(person,card);});
        card.addEventListener('keydown',event=>{
          if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){
            event.preventDefault();event.stopPropagation();showBio(person,card);
          }
        });
        card.addEventListener('click',()=>choose(person.person));cards.append(card);
      }
      cardNodes=Array.from(cards.children);slider.max=String(Math.max(0,cardNodes.length-1));slider.disabled=cardNodes.length<2;loaded=true;update();centerSelected();refreshSearch();
    }catch(e){$('agent-note').textContent='人物卡牌暂未加载，移开后重试。';}
    finally{loading=false;}
  }
  panel.addEventListener('wheel',event=>{
    if(!loaded||!dock.classList.contains('open')||event.ctrlKey||group.contains(event.target))return;
    event.preventDefault();const delta=event.deltaY||event.deltaX;
    // Scrolling down moves the floating portraits from left to right.
    const units=event.deltaMode===1?delta*18:event.deltaMode===2?delta*window.innerHeight:delta;
    move(-Math.max(-1.5,Math.min(1.5,units/95)));
    clearTimeout(snapTimer);snapTimer=setTimeout(()=>{target=Math.round(target);if(frame===null)frame=requestAnimationFrame(animate);},130);
  },{passive:false});
  stage.addEventListener('keydown',event=>{if(event.key==='ArrowRight'||event.key==='ArrowLeft'){event.preventDefault();target=Math.round(target);move(event.key==='ArrowRight'?1:-1);}if(event.key==='Enter'&&event.target===stage&&cardNodes.length){const index=((Math.round(position)%cardNodes.length)+cardNodes.length)%cardNodes.length;choose(cardNodes[index].dataset.person);}});
  let touchX=null,suppressClickUntil=0;
  stage.addEventListener('pointerdown',event=>{if(event.pointerType==='touch')touchX=event.clientX;});
  stage.addEventListener('pointerup',event=>{if(touchX!==null&&Math.abs(event.clientX-touchX)>30){move(-(event.clientX-touchX)/140);suppressClickUntil=Date.now()+400;}touchX=null;});
  stage.addEventListener('pointercancel',()=>{touchX=null;});
  window.addEventListener('resize',()=>{if(dock.classList.contains('open'))paint();});
  close.addEventListener('click',hide);panel.addEventListener('click',event=>{if(event.target===panel||event.target===stage)hide();});
  function choose(person){if(busy||Date.now()<suppressClickUntil)return;document.dispatchEvent(new CustomEvent('zhongjian:choose-agent',{detail:person}));hide();}
  function update(){
    document.querySelector('main').classList.toggle('single-agent',Boolean(agentPerson));
    const changed=current.textContent!==(agentPerson||'');
    current.textContent=agentPerson||'';current.hidden=!agentPerson;
    if(changed&&agentPerson&&!reduced.matches){
      current.getAnimations().forEach(animation=>animation.cancel());
      current.animate([{opacity:0,scale:'.9',translate:'0 -7px'},{opacity:1,scale:'1.04',translate:'0 0',offset:.68},
        {opacity:1,scale:'1',translate:'0 0'}],{duration:350,easing:'cubic-bezier(.2,.76,.24,1)'});
    }
    for(const card of dock.querySelectorAll('.agent-card'))card.setAttribute('aria-pressed',String(card.dataset.person===agentPerson));
  }
  trigger.addEventListener('pointerenter',show);trigger.addEventListener('focus',show);trigger.addEventListener('click',show);
  current.addEventListener('click',show);
  slider.addEventListener('input',()=>{
    clearTimeout(snapTimer);
    if(frame!==null)cancelAnimationFrame(frame);
    frame=null;flight=null;position=target=Number(slider.value);paint();
  });
  let dragging=false;
  slider.addEventListener('pointerdown',event=>{dragging=event.pointerType==='mouse';});
  panel.addEventListener('pointerleave',event=>{if(event.pointerType==='mouse'&&!dragging&&searchForm.hidden)hide();});
  function endDrag(event){
    if(!dragging)return;
    dragging=false;
    const box=panel.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>=box.right||event.clientY<box.top||event.clientY>=box.bottom)hide();
  }
  window.addEventListener('pointerup',endDrag);
  window.addEventListener('pointercancel',endDrag);
  document.addEventListener('pointerdown',event=>{
    if(dock.classList.contains('open')&&!searchForm.hidden&&!dock.contains(event.target)&&!current.contains(event.target))hide();
  });
  document.addEventListener('keydown',e=>{
    if(e.key!=='Escape'||e.isComposing||!dock.classList.contains('open')||bio.open)return;
    if(!searchForm.hidden){closeSearch();searchToggle.focus({preventScroll:true});}else hide();
  });
  document.addEventListener('zhongjian:session-ready',()=>{if(!loaded&&dock.classList.contains('open'))show();});
  document.addEventListener('zhongjian:hide-agents',hide);
  document.addEventListener('zhongjian:agent',update);$('agent-default').addEventListener('click',()=>choose(null));
})();
