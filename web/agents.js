/* A discreet top-edge entrance; only reviewed, answer-capable people appear. */
(() => {
  const dock=document.createElement('section');dock.id='agent-dock';dock.setAttribute('aria-label','人物智能体选择');
  dock.innerHTML='<button id="agent-trigger" type="button" aria-label="选择专属智能体" aria-expanded="false" aria-controls="agent-panel"></button><div id="agent-panel" role="region" aria-label="人物卡牌" inert><div class="agent-panel-head"><h2>和谁聊聊？</h2><button type="button" id="agent-default">众见 · 多人观点</button></div><div id="agent-cards"></div><input id="agent-scroll" type="range" min="0" max="0" step="1" value="0" aria-label="人物轮盘位置" disabled><p id="agent-note"></p></div>';
  const current=node('button','','agent-current');current.type='button';current.hidden=true;current.title='切换智能体';document.body.append(dock,current);
  const trigger=$('agent-trigger'),panel=$('agent-panel');let loaded=false,loading=false;
  const close=node('button','×');close.id='agent-panel-close';close.type='button';close.setAttribute('aria-label','关闭人物轮盘');panel.append(close);
  const stage=$('agent-cards'),slider=$('agent-scroll');stage.tabIndex=0;stage.setAttribute('aria-label','人物轮盘，滚轮或左右方向键切换');
  let cardNodes=[],position=0,target=0,frame=null,snapTimer=null;
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  function paint(){
    const count=cardNodes.length;if(!count)return;
    slider.value=String(((Math.round(target)%count)+count)%count);
    const step=Math.min(window.innerWidth*.16,155);
    for(let index=0;index<count;index++){
      const card=cardNodes[index];const distance=((index-position+count/2)%count+count)%count-count/2;
      const d=Math.abs(distance),visible=d<3.25;
      card.hidden=!visible;card.inert=!visible;card.tabIndex=visible?0:-1;
      card.setAttribute('aria-hidden',String(!visible));
      card.style.setProperty('--wheel-transform','translate(-50%,-50%) translate3d('+(distance*step).toFixed(2)+'px,'+(d*4).toFixed(2)+'px,'+(-d*90).toFixed(2)+'px) rotateY('+(-distance*11).toFixed(2)+'deg) scale('+Math.max(.42,1-d*.18).toFixed(3)+')');
      card.style.zIndex=String(100-Math.round(d*15));card.style.opacity=String(Math.max(.28,1-d*.17));
      card.style.filter='brightness('+Math.max(.65,1-d*.12).toFixed(2)+')';card.classList.toggle('is-center',d<.5);
    }
  }
  function animate(){
    frame=null;if(reduced.matches)position=target;else position+=(target-position)*.16;
    if(Math.abs(target-position)<.002)position=target;paint();
    if(position!==target)frame=requestAnimationFrame(animate);
  }
  function move(delta){target+=delta;if(frame===null)frame=requestAnimationFrame(animate);}
  function centerSelected(){
    const selected=cardNodes.findIndex(card=>card.dataset.person===agentPerson);
    position=target=selected<0?0:selected;paint();
  }
  function hide(){dock.classList.remove('open');trigger.setAttribute('aria-expanded','false');panel.inert=true;clearTimeout(snapTimer);if(frame!==null)cancelAnimationFrame(frame);frame=null;}
  async function show(){
    dock.classList.add('open');trigger.setAttribute('aria-expanded','true');panel.inert=false;
    if(loaded){paint();return;}if(loading)return;loading=true;
    try{
      const result=await getJSON('/api/agents');const cards=$('agent-cards');cards.replaceChildren();
      for(const person of result.agents){
        const card=node('button',undefined,'agent-card');card.type='button';card.dataset.person=person.person;card.setAttribute('aria-label','与'+person.person+'对话');
        if(person.portrait){
          const img=document.createElement('img');img.src=person.portrait.url;img.alt=person.person+'肖像';img.loading='lazy';
          img.addEventListener('error',()=>{img.remove();card.prepend(node('span',person.person.slice(0,1),'portrait-placeholder'));});
          card.append(img);card.title=[person.portrait.artist,person.portrait.license,person.portrait.source].filter(Boolean).join(' · ');
        }else card.append(node('span',person.person.slice(0,1),'portrait-placeholder'));
        card.append(node('strong',person.person),node('small',person.tags.slice(0,2).join(' · ')));
        card.addEventListener('click',()=>choose(person.person));cards.append(card);
      }
      cardNodes=Array.from(cards.children);slider.max=String(Math.max(0,cardNodes.length-1));slider.disabled=cardNodes.length<2;loaded=true;update();centerSelected();
    }catch(e){$('agent-note').textContent='人物卡牌暂未加载，移开后重试。';}
    finally{loading=false;}
  }
  panel.addEventListener('wheel',event=>{
    if(!loaded||!dock.classList.contains('open')||event.ctrlKey)return;
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
    current.textContent=agentPerson||'';current.hidden=!agentPerson;
    for(const card of dock.querySelectorAll('.agent-card'))card.setAttribute('aria-pressed',String(card.dataset.person===agentPerson));
  }
  trigger.addEventListener('pointerenter',show);trigger.addEventListener('focus',show);trigger.addEventListener('click',show);
  current.addEventListener('click',show);
  slider.addEventListener('input',()=>{
    clearTimeout(snapTimer);
    if(frame!==null)cancelAnimationFrame(frame);
    frame=null;position=target=Number(slider.value);paint();
  });
  let dragging=false;
  slider.addEventListener('pointerdown',event=>{dragging=event.pointerType==='mouse';});
  panel.addEventListener('pointerleave',event=>{if(event.pointerType==='mouse'&&!dragging)hide();});
  function endDrag(event){
    if(!dragging)return;
    dragging=false;
    const box=panel.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>=box.right||event.clientY<box.top||event.clientY>=box.bottom)hide();
  }
  window.addEventListener('pointerup',endDrag);
  window.addEventListener('pointercancel',endDrag);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
  document.addEventListener('zhongjian:hide-agents',hide);
  document.addEventListener('zhongjian:agent',update);$('agent-default').addEventListener('click',()=>choose(null));
})();
