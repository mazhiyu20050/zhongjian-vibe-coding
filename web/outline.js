/* A compact outline of the visible conversation, generated on demand. */
(() => {
  const edge = node('div'); edge.id = 'outline-edge'; edge.hidden = true;
  const open = node('button', '‹'); open.type = 'button';
  open.title = '对话脉络'; open.setAttribute('aria-label', '打开对话脉络');
  open.setAttribute('aria-controls', 'outline-drawer'); open.setAttribute('aria-expanded', 'false');
  edge.append(open);
  const panel = node('aside'); panel.id = 'outline-drawer'; panel.hidden = true;
  panel.setAttribute('aria-labelledby', 'outline-title');
  const header = node('header');
  const title = node('h2', '对话脉络'); title.id = 'outline-title';
  const close = node('button', '×'); close.type = 'button'; close.setAttribute('aria-label', '关闭对话脉络');
  header.append(title, close);
  const status = node('p', '', 'outline-status'); status.setAttribute('role', 'status');
  const consensus = node('section', undefined, 'outline-consensus'); consensus.hidden = true;
  const consensusText = node('strong');
  const consensusNames = node('p', '', 'outline-names');
  consensus.append(node('h3', '共同点'), consensusText, consensusNames);
  const list = node('ol', undefined, 'outline-list');
  const retry = node('button', '重试 AI 总结', 'outline-retry'); retry.type = 'button'; retry.hidden = true;
  panel.append(header, status, consensus, list, retry);
  document.body.append(edge, panel);

  let activeId = null, request = null, memo = null;
  function render(data) {
    const fixed = data.mode === 'reviewer_demo';
    status.textContent = fixed ? '离线演示 · 固定归纳' : data.mode === 'ai' ? 'AI 总结 · 只提炼本段对话' : '本地摘录 · AI 总结暂未生成';
    retry.hidden = fixed || data.mode === 'ai';
    consensus.hidden = !data.consensus?.text;
    consensusText.textContent = data.consensus?.text || '';
    consensusNames.textContent = data.consensus?.speakers?.join(' · ') || '';
    list.replaceChildren(...data.nodes.map(item => {
      const step = node('li'); step.dataset.kind = item.kind;
      const who = item.kind === 'question' ? '你问' : item.kind === 'followup' ? '你追问'
        : item.speakers?.length > 1 ? item.speakers.join(' · ') : item.speaker + '回应';
      step.append(node('span', who, 'outline-speaker'), node('strong', item.text));
      return step;
    }));
    if (!data.nodes.length) status.textContent = '这段对话还没有可整理的内容。';
  }
  async function load() {
    if (!activeId || request) return;
    if (memo) { render(memo); return; }
    const controller = new AbortController(); request = controller; const id = activeId;
    list.replaceChildren(); consensus.hidden = true; retry.hidden = true; status.textContent = '正在提炼关键节点…';
    panel.setAttribute('aria-busy', 'true');
    try {
      const data = await getJSON('/api/conversations/outline', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id}), signal: controller.signal
      });
      if (request === controller && activeId === id) {
        if (data.mode === 'ai' || data.mode === 'reviewer_demo') memo = data;
        render(data);
      }
    } catch (error) {
      if (controller.signal.aborted || request !== controller) return;
      status.textContent = error.message || '暂未整理成功，请重试。';
      retry.hidden = false;
    } finally {
      if (request === controller) { request = null; panel.removeAttribute('aria-busy'); }
    }
  }
  function hide(restoreFocus = false) {
    panel.hidden = true; open.setAttribute('aria-expanded', 'false');
    if (restoreFocus) open.focus({preventScroll: true});
  }
  function change() {
    const switched = activeId !== conversationId;
    request?.abort(); request = null; memo = null; panel.removeAttribute('aria-busy');
    activeId = conversationId;
    edge.hidden = !activeId;
    if (switched || !activeId) hide();
    else if (!panel.hidden) load();
  }
  open.addEventListener('click', () => {
    if (!panel.hidden) { hide(true); return; }
    panel.hidden = false; open.setAttribute('aria-expanded', 'true'); close.focus({preventScroll: true});
    load();
  });
  close.addEventListener('click', () => hide(true));
  retry.addEventListener('click', load);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden && !document.querySelector('dialog[open]')) hide(panel.contains(document.activeElement));
  });
  document.addEventListener('zhongjian:outline-change', change);
  change();
})();
