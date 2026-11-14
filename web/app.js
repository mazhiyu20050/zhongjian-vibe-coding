'use strict';
const $ = id => document.getElementById(id);
let token = '', busy = false, sessionId = null, conversationId = null, agentPerson = null;
function resizeQuestion(){const q=$('question');q.style.height='auto';q.style.height=Math.max(24,q.scrollHeight)+'px';}
$('question').addEventListener('input',resizeQuestion);
$('question').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();if(!busy)$('query-form').requestSubmit();}});
function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
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
  if (data.session_id) sessionId = data.session_id;
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
  article.addEventListener('toggle', async () => {
    if (!article.open || loaded || loading) return;
    loading = true;
    const dots = node('div', undefined, 'inline-thinking'); dots.setAttribute('role', 'status'); dots.setAttribute('aria-label', '正在整理');
    for (let i = 0; i < 3; i++) dots.append(node('span'));
    panel.replaceChildren(dots); panel.setAttribute('aria-busy', 'true');
    try { const data = await getJSON('/api/source/details', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({passage_id:card.id,highlight_start:card.highlight_start,highlight_end:card.highlight_end,question:card.reader_question || ''})}); fillDetails(panel, data, depth, card.reader_question || ''); loaded = true; }
    catch (e) { panel.replaceChildren(node('p', e.message, 'detail-note error')); }
    finally { loading = false; panel.removeAttribute('aria-busy'); }
  });
}
let viewpointMenu;
function attachViewpointMenu(card, summary, person){
  summary.setAttribute('aria-haspopup','menu');
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
    action.addEventListener('click',()=>{close();if(!busy)document.dispatchEvent(new CustomEvent('zhongjian:choose-agent',{detail:person}));});
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
  question = result.question_context || question;
  panel.replaceChildren();
  const cards = result.cards || [];
  const title = node('h2', undefined, 'question-title');
  title.append(node('mark', result.question_title || question.slice(0,18)));
  if (result.clarification?.awaiting_answer || result.pending_confirmation) panel.append(node('p', result.display_reply || '', 'reply'));
  else if (!cards.length) panel.append(node('p', '未找到贴切原文。', 'empty-result'));
  const grid=node('div',undefined,'cards-grid');
  if(cards.length) panel.append(grid);
  for (const card of cards.slice(0,4)) {
    const d = card.display; if (!d) continue;
    const article = node('details', undefined, 'card'); const summary = node('summary', undefined, 'card-summary'); const top = node('div', undefined, 'card-top');
    const person = node('span', d.person, 'person');
    person.title = '基于原著与Skill的AI人物视角；讲解非历史原话';
    top.append(person);
    summary.append(top);
    const heading=node('div',undefined,'card-heading');
    heading.append(node('h3', d.viewpoint_title || '观点与建议', 'viewpoint-title'));
    if(d.tendency_applicable){
      const weights=node('span',undefined,'advice-tendency');
      weights.title='AI估计的建议侧重，不是概率、正确率或历史本人意见。'+(d.tendency_reason ? '依据：'+d.tendency_reason : '');
      weights.setAttribute('aria-label',weights.title);
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
    article.append(summary);
    attachViewpointMenu(article,summary,d.person);attachDetails(article, {...card,reader_question:question}); grid.append(article);
  }
  if(cards.length) panel.append(title);
  panel.hidden = false;
}
function makeTurn(question){
  const section=node('section',undefined,'history-turn');
  const answer=node('div',undefined,'turn-answer');
  section.append(node('p',question,'history-question'),answer);
  return {section,answer};
}
function showConversation(history){
  conversationId=history.id;sessionId=history.session_id||null;
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
  document.dispatchEvent(new Event('zhongjian:history'));
}
$('query-form').addEventListener('submit', async event => {
  event.preventDefault(); const question = $('question').value.trim(); if (busy || !question) return;
  document.querySelector('main').classList.add('has-started','has-answer');
  $('new-chat').disabled=true;
  busy=true; $('submit').disabled=true; $('question').disabled=true;
  $('query-form').setAttribute('aria-busy','true');
  const {section,answer}=makeTurn(question);
  $('results').append(section);$('results').hidden=false;
  answer.append(node('p','正在思考…','turn-pending'));answer.setAttribute('aria-busy','true');
  $('question').value='';$('question').placeholder='继续说说你的想法';resizeQuestion();
  section.scrollIntoView({block:'start'});
  try{
    const data=await getJSON('/api/query',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,session_id:sessionId,conversation_id:conversationId,agent_person:agentPerson,project_id:window.currentProjectId||null})});
    conversationId=data.conversation_id||conversationId;
    render(data.result,question,answer);
    if(data.history_warning)answer.append(node('p',data.history_warning,'detail-note'));
    document.dispatchEvent(new Event('zhongjian:history'));
  }catch(e){
    answer.replaceChildren(node('p',e.message,'query-error'));
    $('question').value=question;
  }finally{
    answer.removeAttribute('aria-busy');busy=false;
    $('submit').disabled=false;$('question').disabled=false;$('new-chat').disabled=false;
    $('query-form').removeAttribute('aria-busy');resizeQuestion();
  }
});

getJSON('/api/session').then(data => { token = data.token; document.dispatchEvent(new Event('zhongjian:session-ready')); $('submit').disabled = !data.ready; if (!data.ready) reply('服务尚未就绪，请启动已配置密钥的本机服务。'); }).catch(() => reply('本机服务尚未连接。', true));

resizeQuestion();
