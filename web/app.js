'use strict';
const $ = id => document.getElementById(id);
let token = '', busy = false, sessionId = null, conversationId = null, agentPerson = null;
let personBranchContext = '', personBranch = false;
let activeQuery=null, failedTurn=null;
let pendingQuestions=[], queueEditor=null, serviceReady=false;
function cancelQueryView(){
  activeQuery?.abort();activeQuery=null;busy=false;
  $('submit').disabled=!serviceReady;$('new-chat').disabled=false;
}
function resizeQuestion(){const q=$('question');q.style.height='auto';q.style.height=Math.max(24,q.scrollHeight)+'px';}
$('question').addEventListener('input',resizeQuestion);
$('question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(serviceReady)$('query-form').requestSubmit();}});
function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
const queuePanel=node('section',undefined,'question-queue');
queuePanel.hidden=true;queuePanel.setAttribute('aria-label','问题队列');
$('query-form').before(queuePanel);
new ResizeObserver(()=>queuePanel.style.setProperty('--composer-height',$('query-form').getBoundingClientRect().height+'px')).observe($('query-form'));
function queueButton(text,label,action){
  const button=node('button',text,'queue-action');
  button.type='button';button.title=label;button.setAttribute('aria-label',label);button.addEventListener('click',action);
  return button;
}
function setQuestionQueue(items=[]){pendingQuestions=items.slice();queueEditor=null;renderQueue();}
function canLeaveQuestionQueue(){
  return !pendingQuestions.length||window.confirm('还有未发送的排队问题。切换会话会清空队列，继续吗？');
}
function renderQueue(){
  queuePanel.hidden=!pendingQuestions.length;
  queuePanel.replaceChildren();
  if(queuePanel.hidden)return;
  const header=node('div',undefined,'queue-header');
  const hint=failedTurn?'上一条失败，队列已暂停':queueEditor?'编辑完成后继续发送':'按顺序自动发送';
  header.append(node('strong','待发送 · '+pendingQuestions.length),node('span',hint));
  if(failedTurn)header.append(queueButton('跳过失败项','跳过失败项并继续发送',()=>{
    if(busy)return;
    const failed=failedTurn;failedTurn=null;
    if($('question').value.trim()===failed?.question)$('question').value='';
    resizeQuestion();renderQueue();drainQuestionQueue();
  }));
  const list=node('ol',undefined,'queue-items');
  pendingQuestions.forEach((item,index)=>{
    const row=node('li',undefined,'queue-item');
    if(queueEditor?.item===item){
      const editor=node('textarea');editor.value=queueEditor.draft;editor.rows=2;editor.maxLength=2000;
      editor.setAttribute('aria-label','编辑第 '+(index+1)+' 条排队问题');
      editor.addEventListener('input',()=>{queueEditor.draft=editor.value;});
      const finish=save=>{
        const draft=editor.value.trim();if(save&&!draft){editor.focus();return;}
        if(save)item.text=draft;queueEditor=null;renderQueue();drainQuestionQueue();
      };
      row.append(editor,queueButton('保存','保存修改',()=>finish(true)),queueButton('取消','取消编辑',()=>finish(false)));
    }else{
      const text=node('span',item.text,'queue-text');text.title=item.text;
      const move=delta=>{
        const to=index+delta;if(to<0||to>=pendingQuestions.length)return;
        [pendingQuestions[index],pendingQuestions[to]]=[pendingQuestions[to],pendingQuestions[index]];
        renderQueue();
      };
      const up=queueButton('↑','上移第 '+(index+1)+' 条',()=>move(-1));up.disabled=index===0;
      const down=queueButton('↓','下移第 '+(index+1)+' 条',()=>move(1));down.disabled=index===pendingQuestions.length-1;
      const edit=queueButton('✎','编辑第 '+(index+1)+' 条',()=>{
        queueEditor={item,draft:item.text};renderQueue();queuePanel.querySelector('textarea').focus();
      });
      const remove=queueButton('×','删除第 '+(index+1)+' 条',()=>{
        pendingQuestions.splice(index,1);renderQueue();drainQuestionQueue();
      });
      row.append(node('span',String(index+1),'queue-number'),text,up,down,edit,remove);
    }
    list.append(row);
  });
  queuePanel.append(header,list);
}
function drainQuestionQueue(){
  if(busy||failedTurn||queueEditor||!serviceReady||!pendingQuestions.length)return;
  const {text}=pendingQuestions.shift();renderQueue();runQuestion(text);
}
function emphasized(tag, text, fragments, className) {
  const el = node(tag, undefined, className), spans = [];
  for (const phrase of (Array.isArray(fragments) ? fragments : []).slice(0,2)) {
    if (typeof phrase !== 'string' || phrase.length < 2 || phrase.length > 20) continue;
    const start = text.indexOf(phrase); if (start >= 0) spans.push({start,end:start+phrase.length,phrase});
  }
  spans.sort((a,b)=>a.start-b.start); let cursor=0;
  for (const span of spans) {
    if (span.start < cursor) continue;
    el.append(document.createTextNode(text.slice(cursor,span.start)),node('mark',span.phrase,'insight-emphasis'));
    cursor=span.end;
  }
  el.append(document.createTextNode(text.slice(cursor))); return el;
}
async function getJSON(url, options = {}) {
  const headers = {...options.headers}; if (token) headers['X-Zhongjian-Token'] = token;
  const response = await fetch(url, {...options, headers}); const data = await response.json();
  if (data.session_id&&!options.signal?.aborted) sessionId = data.session_id;
  if (!response.ok){const friendly={invalid_json:'这次回答没整理完整，请再发送一次，输入的文字仍在。',output_truncated:'这次回答没整理完整，请再发送一次，输入的文字仍在。',invalid_explanation:'这次解读还没核验好，请再试一次，输入的文字仍在。',tool_budget:'这次检索没完成，请再试一次，输入的文字仍在。'};throw new Error(friendly[data.error]||data.message||'暂时没有查询成功，请再试一次。');}
  return data;
}
function reply(text, error = false) { $('results').append(node('p', text, error ? 'reply error' : 'reply')); $('results').hidden = false; }
function fillDetails(panel, data, depth, question) {
  panel.replaceChildren();
  const paragraphs = data.reading.split(/\n+/).map(text => text.trim()).filter(Boolean);
  paragraphs.forEach((text, i) => panel.append(emphasized('p', text, data.reading_emphasis, i === 0 ? 'reading-meaning' : 'reading-thought')));
  if (data.reference) panel.append(node('div', data.reference, 'reading-reference'));
  if (data.original_language === 'en' && data.original_focus) {
    const source = node('details', undefined, 'original-reading');
    source.append(node('summary','英文原句'),node('p',data.original_focus));
    if(data.edition_note) source.append(node('div',data.edition_note,'reading-reference'));
    panel.append(source);
  }
  if (depth > 0) return;
  for (const item of data.related || []) {
    const entry = node('details', undefined, 'related-reading');
    const summary = node('summary', item.language === 'en' ? item.reference : '“' + item.excerpt + '”');
    entry.append(summary); attachDetails(entry, {id:item.id,reader_question:question}, depth + 1); panel.append(entry);
  }
}
function attachDetails(article, card, depth = 0) {
  const panel = node('div', undefined, 'reading-panel'); article.append(panel);
  let loaded = false, loading = false;
  async function loadDetails() {
    if (!article.open || loaded || loading) return;
    loading = true;
    const dots = node('div', undefined, 'inline-thinking'); dots.setAttribute('role', 'status'); dots.setAttribute('aria-label', '正在整理');
    for (let i = 0; i < 3; i++) dots.append(node('span'));
    panel.replaceChildren(dots); panel.setAttribute('aria-busy', 'true');
    try { const data = await getJSON('/api/source/details', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({passage_id:card.id,highlight_start:card.highlight_start,highlight_end:card.highlight_end,question:card.reader_question || ''})}); fillDetails(panel, data, depth, card.reader_question || ''); loaded = true; }
    catch (e) {
      const retry=node('button','刷新重试','query-retry');
      retry.type='button';retry.addEventListener('click',loadDetails);
      const failure=node('div',undefined,'query-error-row');
      failure.append(node('p',e.message,'query-error'),retry);panel.replaceChildren(failure);
    }
    finally { loading = false; panel.removeAttribute('aria-busy'); }
  }
  article.addEventListener('toggle',loadDetails);
}
let viewpointMenu;
function attachViewpointMenu(card, summary, person, question, priorContext){
  if(agentPerson)return;
  summary.setAttribute('aria-haspopup','menu');
  const switchPerson = () => {
    if (busy||agentPerson) return;
    document.dispatchEvent(new CustomEvent('zhongjian:choose-agent',{detail:{person,question,priorContext}}));
  };
  card.classList.add('persona-entry');
  const read = node('button','详读原文','persona-source-toggle');
  read.type='button';read.setAttribute('aria-expanded','false');
  read.addEventListener('click',event=>{
    event.preventDefault();event.stopPropagation();card.open=!card.open;
  });
  card.addEventListener('toggle',()=>read.setAttribute('aria-expanded',String(card.open)));
  summary.querySelector('.card-top').append(read);
  summary.title='点击进入'+person+'的专属对话';
  summary.addEventListener('click',event=>{
    if(event.target.closest('button,a'))return;
    event.preventDefault();
    const selection=window.getSelection();
    if(selection&&!selection.isCollapsed&&summary.contains(selection.anchorNode))return;
    switchPerson();
  });
  function open(event,x,y){
    event.preventDefault();
    if(viewpointMenu)viewpointMenu.close();
    const menu=node('div',undefined,'viewpoint-context-menu');
    menu.setAttribute('role','menu');
    const action=node('button','与'+person+'对话');
    action.type='button';action.setAttribute('role','menuitem');action.disabled=busy;
    const controller=new AbortController(), options={signal:controller.signal};
    function close(restore=false){
      controller.abort();menu.remove();viewpointMenu=null;
      if(restore)summary.focus({preventScroll:true});
    }
    viewpointMenu={close};
    menu.append(action);document.body.append(menu);
    const box=menu.getBoundingClientRect();
    menu.style.left=Math.max(8,Math.min(x,window.innerWidth-box.width-8))+'px';
    menu.style.top=Math.max(8,Math.min(y,window.innerHeight-box.height-8))+'px';
    menu.tabIndex=-1;(action.disabled?menu:action).focus({preventScroll:true});
    action.addEventListener('click',()=>{close();switchPerson();});
    document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))close();},options);
    document.addEventListener('contextmenu',e=>{if(!menu.contains(e.target)&&!card.contains(e.target))close();},options);
    document.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true);}else if(e.key==='Tab')close(true);},options);
    window.addEventListener('resize',()=>close(),options);
    document.addEventListener('scroll',()=>close(),{...options,capture:true});
  }
  card.addEventListener('contextmenu',e=>open(e,e.clientX,e.clientY));
  summary.addEventListener('keydown',e=>{
    if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){
      const box=summary.getBoundingClientRect();open(e,box.left,box.bottom);
    }
  });
}

function render(result, question, panel) {
  const originalQuestion=question;
  question = result.question_context || question;
  panel.replaceChildren();
  const cards = result.cards || [];
  const title = node('h2', undefined, 'question-title');
  title.append(node('mark', result.question_title || question.slice(0,18)));
  const awaitingInput = result.clarification?.awaiting_answer || result.pending_confirmation;
  const analysis=typeof result.display_reply==='string' ? result.display_reply.trim() : '';
  if (awaitingInput) panel.append(node('p', result.display_reply || '', 'reply'));
  else if(agentPerson&&analysis){
    const focused=node('section',undefined,'persona-analysis');
    focused.append(node('h3',agentPerson+'的分析'),node('p',analysis));
    panel.append(focused);
  }
  else if (!cards.length) panel.append(node('p', '未找到贴切原文。', 'empty-result'));
  const grid=node('div',undefined,'cards-grid');
  if(cards.length) panel.append(grid);
  for (const card of cards.slice(0,4)) {
    const d = card.display; if (!d) continue;
    const article = node('details', undefined, 'card'); const summary = node('summary', undefined, 'card-summary'); const top = node('div', undefined, 'card-top');
    const person = node('span', d.person, 'person');
    top.append(person);
    summary.append(top);
    const heading=node('div',undefined,'card-heading');
    heading.append(node('h3', d.viewpoint_title || '观点与建议', 'viewpoint-title'));
    if(d.tendency_applicable){
      const weights=node('span',undefined,'advice-tendency');
      if(d.tendency_reason)weights.title='依据：'+d.tendency_reason;
      if(Array.isArray(d.advice_tendency)){
        for(const item of d.advice_tendency){
          if(!item || typeof item.option !== 'string' || !Number.isInteger(item.percent)) continue;
          const option=node('span',undefined,'tendency-option');
          option.append(document.createTextNode(item.option+' '),node('b','≈'+item.percent+'%'));
          weights.append(option);
        }
      }else weights.append(node('span','待定'));
      heading.append(weights);
    }
    summary.append(heading);
    if (d.explanation) summary.append(emphasized('p', d.explanation, d.emphasis, 'card-insight'));
    const paragraph = node('p', undefined, 'excerpt'); const chars = Array.from(d.excerpt);
    if (d.highlight_end > d.highlight_start) paragraph.append(document.createTextNode(chars.slice(0,d.highlight_start).join('')), node('mark', chars.slice(d.highlight_start,d.highlight_end).join('')), document.createTextNode(chars.slice(d.highlight_end).join('')));
    else paragraph.textContent = d.excerpt;
    if(d.is_translation){paragraph.title='所选英文原句的AI译意；展开可核对英文';paragraph.append(node('span','（译）','translation-note'));}
    summary.append(paragraph);
    const entry = Number.isInteger(d.entry) && d.entry > 0 ? '第'+d.entry+'条' : '';
    const source = [d.work ? '《'+d.work+'》' : '', d.volume, d.section, entry].filter(Boolean).join(' · ');
    if (source) summary.append(node('p', '出处：'+source, 'card-reference'));
    article.append(summary);
    attachViewpointMenu(article,summary,d.person,originalQuestion,result.question_context);
    attachDetails(article, {...card,reader_question:question}); grid.append(article);
  }
  if(cards.length) {
    panel.append(title);
    const suggestion = typeof result.display_reply === 'string' ? result.display_reply.trim() : '';
    if (!agentPerson && !awaitingInput && suggestion) {
      const step = node('section', undefined, 'answer-next-step');
      step.append(node('h3', '可先试一步'), node('p', suggestion));
      panel.append(step);
    }
  }
  panel.hidden = false;
}
function makeTurn(question){
  const section=node('section',undefined,'history-turn');
  const answer=node('div',undefined,'turn-answer');
  section.append(node('p',question,'history-question'),answer);
  return {section,answer};
}
function showConversation(history){
  document.dispatchEvent(new Event('zhongjian:clear-person-back'));
  failedTurn=null;
  setQuestionQueue();
  conversationId=history.id;sessionId=history.session_id||null;
  personBranchContext='';
  personBranch=false;
  document.dispatchEvent(new CustomEvent('zhongjian:project',{detail:history.project_id||null}));
  agentPerson=history.agent_person||null;document.dispatchEvent(new Event('zhongjian:agent'));
  const sections=history.turns.map(turn=>{
    const {section,answer}=makeTurn(turn.question);
    render(turn.result,turn.question,answer);
    return section;
  });
  $('results').replaceChildren(...sections);$('results').hidden=false;
  document.querySelector('main').classList.add('has-answer','has-started');
  $('query-form').hidden=false;$('question').value='';$('question').placeholder='继续说说你的想法';resizeQuestion();
  sections.at(-1)?.scrollIntoView({block:'start'});
  document.dispatchEvent(new Event('zhongjian:outline-change'));
  document.dispatchEvent(new Event('zhongjian:history'));
}
async function runQuestion(question, turn=makeTurn(question)){
  if(busy||!question)return;
  const controller=new AbortController();activeQuery=controller;
  const {section,answer}=turn;
  failedTurn=null;
  document.querySelector('main').classList.add('has-started','has-answer');
  $('new-chat').disabled=true;
  busy=true;
  if(!section.isConnected)$('results').append(section);
  $('results').hidden=false;
  answer.replaceChildren(node('p',agentPerson ? agentPerson+'正在分析…' : '正在思考…','turn-pending'));answer.setAttribute('aria-busy','true');
  $('question').placeholder='还可以输入下一条问题';resizeQuestion();
  section.scrollIntoView({block:'start'});
  try{
    const branchContext=agentPerson&&!conversationId&&personBranch ? {branch_entry:true,branch_context:personBranchContext} : {};
    const data=await getJSON('/api/query',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({question,session_id:sessionId,conversation_id:conversationId,agent_person:agentPerson,project_id:window.currentProjectId||null,...branchContext})});
    if(activeQuery!==controller)return;
    conversationId=data.conversation_id||conversationId;
    if(data.conversation_id){personBranchContext='';personBranch=false;}
    render(data.result,question,answer);
    if(data.history_warning)answer.append(node('p',data.history_warning,'detail-note'));
    if(data.conversation_id)document.dispatchEvent(new Event('zhongjian:outline-change'));
    document.dispatchEvent(new Event('zhongjian:history'));
  }catch(e){
    if(activeQuery!==controller)return;
    const retry=node('button','刷新重试','query-retry');
    retry.type='button';
    retry.addEventListener('click',()=>{
      if(busy||section.parentNode!==$('results')||(failedTurn&&failedTurn.turn!==turn))return;
      if($('question').value.trim()===question)$('question').value='';
      $('results').append(section);
      runQuestion(question,turn);
    });
    const error=node('div',undefined,'query-error-row');
    error.append(node('p',e.message,'query-error'),retry);answer.replaceChildren(error);
    failedTurn={question,turn};
    if(!pendingQuestions.length&&!$('question').value)$('question').value=question;
  }finally{
    answer.removeAttribute('aria-busy');
    if(activeQuery===controller){
      cancelQueryView();resizeQuestion();
      $('question').placeholder='继续说说你的想法';
      renderQueue();drainQuestionQueue();
    }
  }
}
$('query-form').addEventListener('submit',event=>{
  event.preventDefault();
  const question=$('question').value.trim();
  if(!serviceReady||!question)return;
  $('question').value='';resizeQuestion();$('question').focus({preventScroll:true});
  const retry=failedTurn?.question===question&&failedTurn.turn.section.parentNode===$('results');
  if(!busy&&retry){runQuestion(question,failedTurn.turn);return;}
  if(busy||pendingQuestions.length||failedTurn){
    pendingQuestions.push({text:question});renderQueue();drainQuestionQueue();return;
  }
  runQuestion(question);
});

getJSON('/api/session').then(data => { token = data.token; serviceReady=Boolean(data.ready); $('submit').disabled = !serviceReady; document.dispatchEvent(new Event('zhongjian:session-ready')); if (!data.ready) reply('服务尚未就绪，请启动已配置密钥的本机服务。'); }).catch(() => reply('本机服务尚未连接。', true));

resizeQuestion();
