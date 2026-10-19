'use strict';
const $ = id => document.getElementById(id);
let token = '', busy = false, sessionId = null;
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
  if (!response.ok) throw new Error(data.message || '暂时没有查询成功，请再试一次。');
  return data;
}
function reply(text, error = false) { $('results').replaceChildren(node('p', text, error ? 'reply error' : 'reply')); $('results').hidden = false; }
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
function render(result, question) {
  question = result.question_context || question;
  const panel = $('results'); panel.replaceChildren();
  const cards = result.cards || [];
  const title = node('h2', undefined, 'question-title');
  title.append(node('mark', result.question_title || question.slice(0,18)));
  panel.append(title);
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
    article.append(summary); attachDetails(article, {...card,reader_question:question}); grid.append(article);
  }
  panel.hidden = false;
}
function motion(element, frames, duration, easing = 'cubic-bezier(.22,1,.36,1)') {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve();
  const animation = element.animate(frames, {duration, easing, fill:'both'});
  return animation.finished.catch(() => {}).finally(() => animation.cancel());
}
async function foldSearch() {
  const form = $('query-form'), results = $('results');
  const fading = results.hidden ? Promise.resolve() : motion(results, [{opacity:1},{opacity:0,transform:'translateY(-6px)'}], 220);
  await Promise.all([fading, motion(form, [{opacity:1,transform:'scale(1)',filter:'blur(0)'},{opacity:0,transform:'scale(.04,.72)',filter:'blur(3px)'}], 340, 'cubic-bezier(.55,0,.3,1)')]);
  form.hidden = true; results.hidden = true; results.replaceChildren();
  document.querySelector('main').classList.remove('has-answer');
  $('thinking').hidden = false;
}
async function revealSearch() {
  $('thinking').hidden = true;
  document.querySelector('main').classList.add('has-answer');
  $('query-form').hidden = false;
  await Promise.all([
    motion($('results'), [{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}], 360),
    motion($('query-form'), [{opacity:0,transform:'translateY(24px) scale(.98)'},{opacity:1,transform:'translateY(0) scale(1)'}], 480)
  ]);
}
$('query-form').addEventListener('submit', async event => {
  event.preventDefault(); const question = $('question').value.trim(); if (busy || !question) return;
  busy = true; $('submit').disabled = true; $('question').disabled = true;
  $('query-form').setAttribute('aria-busy', 'true');
  const response = getJSON('/api/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,session_id:sessionId})}).then(data => ({data}), error => ({error}));
  try {
    await foldSearch();
    const outcome = await response;
    if (outcome.error) throw outcome.error;
    render(outcome.data.result, question);
    $('question').value = ''; $('question').placeholder = '继续说说你的想法';
  } catch (e) { reply(e.message, true); }
  finally {
    await revealSearch();
    busy = false; $('submit').disabled = false; $('question').disabled = false;
    $('query-form').removeAttribute('aria-busy');
  }
});
getJSON('/api/session').then(data => { token = data.token; $('submit').disabled = !data.ready; if (!data.ready) reply('服务尚未就绪，请启动已配置密钥的本机服务。'); }).catch(() => reply('本机服务尚未连接。', true));
