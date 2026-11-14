/* Desktop-only settings. No privileged JS bridge or credential read-back. */
(() => {
  const gear=document.getElementById('desktop-settings')||document.createElement('button');
  gear.id='desktop-settings';gear.type='button';gear.textContent='设置';gear.title='设置';gear.setAttribute('aria-label','设置');gear.disabled=false;
  const dialog=document.createElement('dialog');dialog.id='desktop-dialog';
  dialog.innerHTML='<form id="desktop-form"><h2>众见</h2><p class="desktop-intro">填写密钥，即可开始。</p><label for="desktop-key">API</label><input id="desktop-key" type="password" autocomplete="off" spellcheck="false" maxlength="256" placeholder="sk-…"><label for="desktop-model">模型</label><input id="desktop-model" value="deepseek-flash" maxlength="80" spellcheck="false"><p class="desktop-note">密钥由 Windows 加密保存在本机。提问和相关原文会发送至 DeepSeek，按接口计费。</p><p id="desktop-status" role="status"></p><div class="desktop-actions"><button type="button" id="desktop-close">返回</button><button type="submit" id="desktop-save">保存</button></div><small>桌面版 0.2.0</small></form>';
  (document.getElementById('menu-actions')||document.body).append(gear);document.body.append(dialog);
  const field=id=>document.getElementById(id);
  let nonce='';
  async function open(){
    document.getElementById('app-menu')?.close();
    field('desktop-status').textContent='';field('desktop-key').value='';
    try{
      const s=await fetch('/api/session').then(r=>r.json());nonce=s.token;
      const response=await fetch('/api/desktop/settings',{headers:{'X-Zhongjian-Token':nonce}});
      if(!response.ok)throw Error();
      const c=await response.json();field('desktop-model').value=c.model;
      field('desktop-key').placeholder=c.configured?'已保存；留空保留原密钥':'sk-…';
      field('desktop-status').textContent=c.warning||'';
      if(!dialog.open)dialog.showModal();
      field('desktop-key').focus();
    }catch(e){field('desktop-status').textContent='设置读取失败，请重新打开。';if(!dialog.open)dialog.showModal();}
  }
  gear.addEventListener('click',open);
  field('desktop-close').addEventListener('click',()=>{field('desktop-key').value='';dialog.close();});
  dialog.addEventListener('close',()=>{field('desktop-key').value='';});
  field('desktop-form').addEventListener('submit',async e=>{
    e.preventDefault();field('desktop-save').disabled=true;field('desktop-status').textContent='正在保存…';
    try{
      const r=await fetch('/api/desktop/settings',{method:'POST',headers:{'Content-Type':'application/json','X-Zhongjian-Token':nonce},body:JSON.stringify({key:field('desktop-key').value,model:field('desktop-model').value})});
      const data=await r.json();if(!r.ok)throw Error(data.message||'保存失败，请重试。');
      field('desktop-key').value='';location.reload();
    }catch(e){field('desktop-status').textContent=e.message;}
    finally{field('desktop-save').disabled=false;}
  });
  fetch('/api/session').then(r=>r.json()).then(s=>{if(!s.ready)open();});
})();
