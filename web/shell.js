/* Local history and navigation, no third-party storage. */
(() => {
  const drawer=document.getElementById('app-menu'),open=document.getElementById('menu-open');
  window.currentProjectId=null;let projects=[],renaming=null;
  const actions=document.getElementById('menu-actions');drawer.append(actions);
  const menu=node('div',undefined,'sidebar-context-menu');menu.hidden=true;menu.setAttribute('role','menu');drawer.append(menu);
  function hideMenu(){menu.hidden=true;}
  function context(event,items){event.preventDefault();event.stopPropagation();menu.replaceChildren();
    for(const [label,action,shortcut,choices] of items){
      const button=node('button');button.type='button';button.setAttribute('role','menuitem');button.append(node('span',label));
      if(shortcut)button.append(node('kbd',shortcut));if(choices)button.setAttribute('aria-haspopup','menu');
      button.addEventListener('click',async e=>{
        if(choices){const box=menu.getBoundingClientRect();context({clientX:box.left,clientY:box.top,preventDefault(){},stopPropagation(){}},[['‹ 返回',()=>context(event,items)],...choices]);return;}
        hideMenu();try{await action();}catch(err){error.textContent=err.message;}
      });menu.append(button);}
    menu.hidden=false;const box=menu.getBoundingClientRect();
    menu.style.left=Math.max(4,Math.min(event.clientX,window.innerWidth-box.width-8))+'px';
    menu.style.top=Math.max(4,Math.min(event.clientY,window.innerHeight-box.height-8))+'px';menu.querySelector('button').focus();
  }
  const post=(path,data)=>getJSON(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  drawer.addEventListener('click',event=>{if(!menu.contains(event.target))hideMenu();});drawer.addEventListener('close',hideMenu);drawer.addEventListener('keydown',event=>{if(event.key==='Escape'&&!menu.hidden){event.preventDefault();event.stopPropagation();hideMenu();}});drawer.addEventListener('scroll',hideMenu);
  const projectArea=node('section',undefined,'project-area');projectArea.setAttribute('aria-label','项目');
  const projectHeader=node('div',undefined,'project-section-head');
  const projectToggle=node('button',undefined,'project-section-toggle');projectToggle.type='button';projectToggle.append(node('strong','项目'),node('span','⌄'));projectToggle.setAttribute('aria-expanded','true');
  const create=node('button','＋','project-create');create.type='button';create.title='新建项目';create.setAttribute('aria-label','新建项目');projectHeader.append(projectToggle,create);
  const modal=node('dialog',undefined,'project-dialog');modal.setAttribute('aria-label','创建项目');document.body.append(modal);
  const form=node('form',undefined,'project-form');
  const modalHead=node('div',undefined,'project-modal-head'),modalTitle=node('h2','创建项目'),modalClose=node('button','×','project-modal-close');modalClose.type='button';modalClose.setAttribute('aria-label','关闭创建项目');modalHead.append(modalTitle,modalClose);
  const name=document.createElement('input');name.placeholder='项目名称';name.maxLength=40;name.setAttribute('aria-label','项目名称');
  const save=node('button','创建项目');save.type='submit';const cancel=node('button','取消');cancel.type='button';
  const error=node('p','','project-error');error.setAttribute('role','status');
  const projectList=node('div',undefined,'project-list');projectList.id='project-list';
  const nameWrap=node('div',undefined,'project-name-wrap');nameWrap.append(node('span','▱'),name);
  const sourceLabel=node('h3','源文件夹'),sourceBox=node('div',undefined,'project-source-box'),sourceText=node('p','在此电脑上添加文件夹 ⌄'),addFolder=node('button','▱ 添加','project-add-folder');addFolder.type='button';addFolder.title='选择本地文件夹；文件留在本机，不上传';
  sourceBox.append(sourceText,addFolder);let selectionId=null;
  const modalError=node('p','','project-error');modalError.setAttribute('role','status');
  const footer=node('div',undefined,'project-modal-footer');footer.append(cancel,save);
  form.append(modalHead,nameWrap,sourceLabel,sourceBox,modalError,footer);modal.append(form);
  projectArea.append(projectHeader,error,projectList);drawer.insertBefore(projectArea,drawer.querySelector('.history-heading'));
  function openProjectDialog(project=null){renaming=project?.id||null;selectionId=null;modalTitle.textContent=project?'重命名项目':'创建项目';modal.setAttribute('aria-label',modalTitle.textContent);save.textContent=project?'保存':'创建项目';name.value=project?.name||'';sourceLabel.hidden=sourceBox.hidden=Boolean(project);sourceText.textContent='在此电脑上添加文件夹 ⌄';modalError.textContent='';modal.showModal();name.focus();}
  create.addEventListener('click',()=>openProjectDialog());cancel.addEventListener('click',()=>modal.close());modalClose.addEventListener('click',()=>modal.close());
  modal.addEventListener('click',event=>{if(event.target===modal){const r=modal.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)modal.close();}});
  projectToggle.addEventListener('click',()=>{projectList.hidden=!projectList.hidden;projectToggle.setAttribute('aria-expanded',String(!projectList.hidden));});
  addFolder.addEventListener('click',async()=>{addFolder.disabled=true;modalError.textContent='请选择本地文件夹…';try{const result=await post('/api/projects/folder',{});if(!result.cancelled){selectionId=result.selection_id;sourceText.textContent=result.path;if(!name.value.trim())name.value=result.name;}modalError.textContent='';}catch(e){modalError.textContent=e.message;}finally{addFolder.disabled=false;}});
  form.addEventListener('submit',async event=>{event.preventDefault();if(!name.value.trim())return;save.disabled=true;
    try{if(renaming){await post('/api/projects/rename',{id:renaming,name:name.value});renaming=null;}
      else{if(!canLeaveQuestionQueue())return;const p=await post('/api/projects',{name:name.value,selection_id:selectionId});if(newConversation(null,false,true))window.currentProjectId=p.id;}
      modal.close();name.value='';await refreshHistory();}
    catch(e){modalError.textContent=e.message;}finally{save.disabled=false;}});
  document.addEventListener('zhongjian:project',e=>{window.currentProjectId=e.detail;});
  open.addEventListener('click',()=>{drawer.showModal();open.setAttribute('aria-expanded','true');refreshHistory();});
  document.getElementById('menu-close').addEventListener('click',()=>drawer.close());
  drawer.addEventListener('click',e=>{if(e.target===drawer){const r=drawer.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)drawer.close();}});
  drawer.addEventListener('close',()=>open.setAttribute('aria-expanded','false'));
  const shortcuts={r:'Alt+Ctrl+R',p:'Alt+Ctrl+P',u:'Ctrl+Shift+U',a:'Ctrl+Shift+A'};
  const detail=id=>getJSON('/api/conversations?id='+encodeURIComponent(id));
  async function openHistory(item,closeDrawer=true){
    if(busy)return;
    const history=await detail(item.id);
    if(busy)return;
    if(history.unread)await post('/api/conversations/manage',{id:item.id,field:'unread',value:false});
    if(busy||!canLeaveQuestionQueue())return;
    showConversation(history);if(closeDrawer&&drawer.open)drawer.close();
  }
  async function transcript(item){
    const history=await detail(item.id);
    const lines=['# '+history.title];
    for(const turn of history.turns){
      const r=turn.result||{};
      lines.push('## 提问',turn.question,'## 回答',r.display_reply||r.reply||'');
      for(const card of r.cards||[]){
        const d=card.display||{};
        const text=d.explanation||card.text||card.commentary||card.insight;
        const excerpt=d.excerpt||(typeof card.quote==='string'?card.quote:'');
        lines.push([d.person||card.person||card.author,d.viewpoint_title,text].filter(Boolean).join('：'));
        if(excerpt)lines.push('> '+excerpt.replace(/\r?\n/g,'\n> '));
      }
    }
    return lines.filter(Boolean).join('\n\n');
  }
  async function copyText(text){
    if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return;}
    const field=document.createElement('textarea');field.value=text;field.readOnly=true;
    (drawer.open?drawer:document.body).append(field);field.select();
    try{if(!document.execCommand('copy'))throw Error('剪贴板暂不可用');}finally{field.remove();}
  }
  const manage=(item,field,value)=>post('/api/conversations/manage',{id:item.id,field,value}).then(refreshHistory);
  const historyActions={
    r:item=>{const value=window.prompt('重命名对话',item.title);if(value!==null&&value.trim())return manage(item,'title',value);},
    p:item=>post('/api/conversations/pin',{id:item.id,pinned:!item.pinned}).then(refreshHistory),
    u:item=>manage(item,'unread',!item.unread),
    a:item=>manage(item,'archived',!item.archived)
  };
  let historyItems=[],historyTarget=null;
  function historyMenu(event,item,activeProjects){
    historyTarget=item.id;
    const projectChoices=[{id:null,name:'移出项目'},...activeProjects].map(p=>[p.name,async()=>{
      await post('/api/conversations/move',{conversation_id:item.id,project_id:p.id});
      if(item.id===conversationId)window.currentProjectId=p.id;
      await refreshHistory();
    }]);
    const sectionChoices=[['取消分区',()=>manage(item,'section','')],...Array.from(new Set(historyItems.map(x=>x.section).filter(Boolean))).map(name=>[name,()=>manage(item,'section',name)]),['新建分区…',()=>{const name=window.prompt('分区名称');if(name?.trim())return manage(item,'section',name);}]];
    const submenu=(label,choices)=>[label+' ›',null,'',choices];
    context(event,[
      ['重命名',()=>historyActions.r(item),shortcuts.r],
      [item.pinned?'取消置顶':'置顶',()=>historyActions.p(item),shortcuts.p],
      [item.unread?'标记为已读':'标记为未读',()=>historyActions.u(item),shortcuts.u],
      submenu('项目',projectChoices),submenu('分区',sectionChoices),
      submenu('继续',[['继续原对话',()=>openHistory(item)],['创建分支并继续',async()=>{if(busy)return;const b=await post('/api/conversations/branch',{id:item.id});await openHistory(b);}]]),
      ['分享',async()=>{
        const blob=new Blob([await transcript(item)],{type:'text/markdown;charset=utf-8'}),url=URL.createObjectURL(blob);
        const link=node('a');link.href=url;link.download=(item.title.replace(/[\\/:*?"<>|]/g,'_')||'众见对话')+'.md';
        document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
      }],
      submenu('复制',[['复制标题',()=>copyText(item.title)],['复制整段对话',async()=>copyText(await transcript(item))]]),
      ['在新窗口中打开',()=>{
        const url=new URL('/',location.href);url.searchParams.set('conversation',item.id);
        if(window.zhongjianDesktop)return post('/api/conversations/window',{id:item.id});
        window.open(url.href,'_blank','noopener');
      }],
      [item.archived?'恢复对话':'归档',()=>historyActions.a(item),shortcuts.a]
    ]);
  }
  document.addEventListener('keydown',event=>{
    const key=event.key.toLowerCase();
    if(event.repeat||event.defaultPrevented||event.metaKey||!event.ctrlKey||!historyActions[key])return;
    if(event.target?.matches?.('input,textarea,select,[contenteditable=true]')||modal.open)return;
    if(!(['r','p'].includes(key)?event.altKey&&!event.shiftKey:event.shiftKey&&!event.altKey))return;
    const item=historyItems.find(x=>x.id===(drawer.open&&historyTarget?historyTarget:conversationId));
    if(!item)return;
    event.preventDefault();Promise.resolve().then(()=>historyActions[key](item)).catch(e=>{error.textContent=e.message;});
  });
  async function refreshHistory(){
    const list=document.getElementById('history-list');
    try{
      const [result,projectResult]=await Promise.all([getJSON('/api/conversations'),getJSON('/api/projects')]);list.replaceChildren();
      projects=projectResult.projects;
      const expanded=new Set(Array.from(projectList.querySelectorAll('details[open]')).map(x=>x.dataset.id));projectList.replaceChildren();
      const groups=new Map(),projectSections=new Map();const activeProjects=projects.filter(p=>p.status==='active');
      for(const p of activeProjects){const folder=node('details',undefined,'project-folder');folder.dataset.id=p.id;folder.open=expanded.has(p.id)||window.currentProjectId===p.id;
        const heading=node('summary','', 'project-heading');
        const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');
        const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d','M3 7V5h6l2 2h9v3M3 8h18l-3 11H3z');icon.append(path);
        heading.append(icon,node('span',p.name));folder.append(heading);
        const projectMenu=event=>context(event,[
          [p.pinned?'取消置顶':'置顶',()=>projectAction(p,'pinned',!p.pinned)],
          ['编辑',()=>openProjectDialog(p)],
          ['分区 ›',null,'',[['取消分区',()=>projectAction(p,'section','')],...Array.from(new Set(activeProjects.map(x=>x.section).filter(Boolean))).map(section=>[section,()=>projectAction(p,'section',section)]),['新建分区…',()=>{const value=window.prompt('分区名称');if(value?.trim())return projectAction(p,'section',value);}]]],
          ['在资源管理器中打开',()=>post('/api/projects/reveal',{id:p.id})],
          ['归档聊天',()=>projectAction(p,'archive_chats')],
          ['移除项目',()=>{if(window.confirm('移除项目？对话会回到历史列表，本地文件保持原样。'))return projectAction(p,'remove');}]
        ]);
        const controls=node('span',undefined,'project-row-actions');
        const more=node('button','···','project-row-action');more.type='button';more.setAttribute('aria-label','项目操作：'+p.name);more.setAttribute('aria-haspopup','menu');
        more.addEventListener('click',event=>{const r=more.getBoundingClientRect();projectMenu({clientX:r.left,clientY:r.bottom,preventDefault:()=>event.preventDefault(),stopPropagation:()=>event.stopPropagation()});});
        const fresh=node('button','✎','project-row-action');fresh.type='button';fresh.title='在项目中新建对话';fresh.setAttribute('aria-label','在项目中新建对话：'+p.name);
        fresh.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();if(newConversation(null)){window.currentProjectId=p.id;drawer.close();}});
        controls.append(more,fresh);heading.append(controls);
        heading.addEventListener('contextmenu',projectMenu);
        if(p.pinned)heading.classList.add('is-pinned');
        const entries=node('div');folder.append(entries);groups.set(p.id,entries);
        let parent=projectList;
        if(p.section&&!p.pinned){
          if(!projectSections.has(p.section)){
            const section=node('details',undefined,'history-section');section.open=true;
            section.append(node('summary',p.section));projectSections.set(p.section,section);projectList.append(section);
          }
          parent=projectSections.get(p.section);
        }
        parent.append(folder);

      }
      for(const [status,label] of [['archived','已归档项目'],['deleted','最近删除']]){const stored=projects.filter(p=>p.status===status);if(!stored.length)continue;const group=node('details',undefined,'project-storage');group.append(node('summary',label));
        for(const p of stored){const line=node('div',undefined,'project-storage-row');line.append(node('span',p.name));const restore=node('button','恢复');restore.type='button';restore.addEventListener('click',()=>changeProjectStatus(p.id,'active').catch(e=>{error.textContent=e.message;}));line.append(restore);group.append(line);}projectList.append(group);}
      historyItems=result.items;
      const visibleItems=result.items.filter(item=>!item.archived&&!projects.some(p=>p.id===item.project_id&&p.status==='archived'));
      const archived=result.items.filter(item=>item.archived);
      const sections=new Map();
      function destination(item){
        const parent=groups.get(item.project_id)||list;
        if(!item.section)return parent;
        if(!sections.has(parent))sections.set(parent,new Map());
        const names=sections.get(parent);
        if(!names.has(item.section)){
          const section=node('details',undefined,'history-section');section.open=true;
          section.append(node('summary',item.section));parent.append(section);names.set(item.section,section);
        }
        return names.get(item.section);
      }
      function historyRow(item){
        const button=node('button',item.title,'history-item');button.type='button';button.setAttribute('aria-current',String(item.id===conversationId));
        if(item.agent_person)button.append(node('span',' ——'+item.agent_person,'history-person'));
        if(item.pinned){button.classList.add('is-pinned');button.append(node('span','⌖','history-pin'));}
        if(item.unread){button.classList.add('is-unread');const dot=node('span','●','history-unread');dot.setAttribute('aria-label','未读');button.append(dot);}
        button.addEventListener('click',async()=>{if(busy)return;button.disabled=true;
          try{await openHistory(item);}catch(e){error.textContent=e.message;}finally{button.disabled=false;}
        });
        const row=node('div',undefined,'history-row');row.append(button);
        row.addEventListener('contextmenu',event=>historyMenu(event,item,activeProjects));
        button.addEventListener('keydown',event=>{
          if(event.key!=='ContextMenu'&&!(event.shiftKey&&event.key==='F10'))return;
          const r=button.getBoundingClientRect();
          historyMenu({clientX:r.left,clientY:r.bottom,preventDefault:()=>event.preventDefault(),stopPropagation:()=>event.stopPropagation()},item,activeProjects);
        });
        return row;
      }
      for(const item of visibleItems)destination(item).append(historyRow(item));
      if(!visibleItems.some(item=>!groups.has(item.project_id))&&!archived.length)list.append(node('p','还没有对话','history-empty'));
      if(archived.length){
        const group=node('details',undefined,'history-section');group.append(node('summary','已归档对话'));
        for(const item of archived)group.append(historyRow(item));list.append(group);
      }
    }catch(e){list.replaceChildren(node('p','历史暂未读到，重新打开可重试。','history-empty'));}
  }
  async function projectAction(p,action,value){
    await post('/api/projects/manage',{id:p.id,action,value});
    if(action==='remove'&&window.currentProjectId===p.id)window.currentProjectId=null;
    await refreshHistory();
  }
  async function changeProjectStatus(id,status){await post('/api/projects/status',{id,status});if(window.currentProjectId===id&&status!=='active')window.currentProjectId=null;await refreshHistory();}
  const personBack=node('button','‹ 返回','persona-back');
  personBack.type='button';personBack.hidden=true;
  personBack.setAttribute('aria-label','返回上一对话');
  document.body.append(personBack);
  let previousView=null;
  function setPersonBack(state){
    previousView=state;personBack.hidden=!state;
  }
  document.addEventListener('zhongjian:clear-person-back',()=>setPersonBack(null));
  function savePersonView(){
    const main=document.querySelector('main'),results=$('results');
    if(results.hidden||!results.childElementCount)return null;
    return {conversationId,sessionId,agentPerson,personBranch,personBranchContext,failedTurn,queue:pendingQuestions.slice(),
      projectId:window.currentProjectId||null,nodes:[...results.childNodes],previousView,
      hasAnswer:main.classList.contains('has-answer'),hasStarted:main.classList.contains('has-started'),
      draft:$('question').value,placeholder:$('question').placeholder,scroll:window.scrollY};
  }
  function keepPersonView(saved){
    if(!saved)return;
    const original=node('details',undefined,'persona-origin');
    original.open=true;
    original.append(node('summary','原对话'),...saved.nodes);
    $('results').append(original);$('results').hidden=false;
    document.querySelector('main').classList.add('has-answer','has-started');
    setPersonBack(saved);
  }
  personBack.addEventListener('click',()=>{
    const saved=previousView;if(!saved||!canLeaveQuestionQueue())return;
    cancelQueryView();
    ({conversationId,sessionId,agentPerson,personBranch,personBranchContext,failedTurn}=saved);
    setQuestionQueue(saved.queue);
    window.currentProjectId=saved.projectId;
    document.dispatchEvent(new CustomEvent('zhongjian:project',{detail:saved.projectId}));
    const main=document.querySelector('main');
    main.classList.toggle('has-answer',saved.hasAnswer);main.classList.toggle('has-started',saved.hasStarted);
    $('results').replaceChildren(...saved.nodes);$('results').hidden=false;
    $('question').value=saved.draft;$('question').placeholder=saved.placeholder;resizeQuestion();
    setPersonBack(saved.previousView);
    document.dispatchEvent(new Event('zhongjian:agent'));
    document.dispatchEvent(new Event('zhongjian:outline-change'));
    $('question').focus({preventScroll:true});
    requestAnimationFrame(()=>window.scrollTo({top:saved.scroll,behavior:'instant'}));
    refreshHistory();
  });
  function newConversation(person=null,preserveDraft=false,queueHandled=false){
    if(busy||(!queueHandled&&!canLeaveQuestionQueue()))return false;
    const draft=preserveDraft?$('question').value:'';
    failedTurn=null;setPersonBack(null);
    setQuestionQueue();
    agentPerson=person;
    personBranchContext='';
    personBranch=false;
    sessionId=null;conversationId=null;
    document.dispatchEvent(new Event('zhongjian:outline-change'));
    document.querySelector('main').classList.remove('has-answer','has-started');
    $('results').replaceChildren();$('results').hidden=true;$('thinking').hidden=true;
    $('query-form').hidden=false;$('question').value=draft;$('question').placeholder=person?'和'+person+'聊聊':'说说你的困惑';resizeQuestion();$('question').focus();
    document.dispatchEvent(new Event('zhongjian:agent'));
    refreshHistory();
    return true;
  }
  document.getElementById('new-chat').addEventListener('click',()=>{if(!newConversation(agentPerson))return;window.currentProjectId=null;if(drawer.open)drawer.close();document.dispatchEvent(new Event('zhongjian:hide-agents'));});
  document.addEventListener('zhongjian:choose-agent',event=>{
    if(busy)return;
    const choice=event.detail;
    if(!choice||typeof choice==='string'){
      if(choice&&choice===agentPerson)return;
      const saved=choice?savePersonView():null;
      if(newConversation(choice||null,true,Boolean(saved)))keepPersonView(saved);return;
    }
    if(typeof choice.person!=='string'||typeof choice.question!=='string')return;
    const saved=savePersonView();
    if(!newConversation(choice.person,false,Boolean(saved)))return;
    keepPersonView(saved);
    document.dispatchEvent(new Event('zhongjian:hide-agents'));
    const seed=choice.question.trim();
    const context=typeof choice.priorContext==='string'?choice.priorContext.trim():'';
    personBranchContext=context.endsWith('\n'+seed)?context.slice(0,-(seed.length+1)).trim().slice(-2000)
      : context&&context!==seed?context.slice(-2000):'';
    personBranch=true;
    $('question').value=seed;
    resizeQuestion();
    if(seed)$('query-form').requestSubmit();
  });
  document.addEventListener('zhongjian:history',refreshHistory);
  document.addEventListener('zhongjian:session-ready',()=>{
    const id=new URLSearchParams(location.search).get('conversation');
    if(id&&/^[a-f0-9]{24}$/.test(id))openHistory({id},false).catch(e=>{reply(e.message,true);});
  });
})();
