const {test}=require('node:test'), assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs');
function setup(){
  function element(){return {children:[],handlers:{},style:{},classList:{add(){}},value:'',append(...c){this.children.push(...c)},replaceChildren(...c){this.children=c},setAttribute(){},removeAttribute(){},addEventListener(k,f){this.handlers[k]=f},scrollIntoView(){this.scrolled=true},focus(){this.focused=true},remove(){this.removed=true},contains(target){return target===this||this.children.some(child=>child.contains?.(target))},getBoundingClientRect(){return {left:50,bottom:80,width:180,height:40}}}}
  const nodes=new Map(), $=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
  let pending;const body=element(), events=[], handlers={};
  const ctx=vm.createContext({AbortController,document:{getElementById:$,createElement:element,querySelector:()=>element(),body,dispatchEvent(e){events.push(e)},addEventListener(k,f){handlers[k]=f}},window:{innerWidth:300,innerHeight:200,addEventListener(){},matchMedia:()=>({matches:true})},Event:class{},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},fetch:url=>url==='/api/session'?Promise.resolve({ok:true,json:async()=>({ready:true})}):new Promise(r=>{pending=r})});
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'web/app.js'),'utf8'),ctx);
  return {$,ctx,body,events,handlers,send(q){$('question').value=q;return $('query-form').handlers.submit({preventDefault(){}})},finish(ok){pending({ok,json:async()=>ok?{result:{cards:[]}}:{message:'测试错误'}})}};
}
test('questions show immediately; later replies and failures preserve prior turns',async()=>{
  const f=setup();const r=f.$('results');
  let request=f.send('第一问');
  assert.equal(r.children[0]?.children[0]?.textContent,'第一问');
  f.finish(true);await request;
  const first=r.children[0];
  request=f.send('第二问');assert.equal(r.children[0],first);
  assert.equal(r.children[1]?.children[0]?.textContent,'第二问');
  r.children[1].scrolled=false;
  f.finish(false);await request;
  assert.equal(r.children.length,2);assert.equal(r.children[0],first);
  assert.equal(r.children[1].children[1].children[0].textContent,'测试错误');
  assert.equal(r.children[1].scrolled,false);
  assert.equal(f.$('question').value,'第二问');
});
test('reopening a saved conversation renders the same turn layout',()=>{
  const f=setup();
  vm.runInContext("showConversation({id:'saved',turns:[{question:'旧问题',result:{cards:[]}}]})",f.ctx);
  const turn=f.$('results').children[0];
  assert.equal(turn.children[0].textContent,'旧问题');
  assert.equal(turn.children[1].className,'turn-answer');
});

test('right-clicking a viewpoint opens a character-specific chat menu instead of an arrow',()=>{
  const f=setup();
  vm.runInContext("render({cards:[{display:{person:'苏轼',excerpt:'原文'}}]},'提问',$('results'))",f.ctx);
  const card=f.$('results').children.find(el=>el.className==='cards-grid').children[0], summary=card.children[0];
  assert.equal(summary.children[0].children.length,1);
  let prevented=false;
  card.handlers.contextmenu({clientX:299,clientY:199,preventDefault(){prevented=true}});
  assert.equal(prevented,true);
  let menu=f.body.children[0], action=menu.children[0];
  assert.equal(menu.removed,undefined);
  assert.equal(menu.style.left,'112px');
  assert.equal(action.textContent,'与苏轼对话');
  assert.equal(action.focused,true);
  f.handlers.keydown({key:'Escape',preventDefault(){},stopPropagation(){}});
  assert.equal(menu.removed,true);
  assert.equal(summary.focused,true);
  summary.handlers.keydown({key:'F10',shiftKey:true,preventDefault(){}});
  menu=f.body.children.at(-1);action=menu.children[0];action.handlers.click();
  assert.equal(menu.removed,true);
  assert.equal(f.events.at(-1).type,'zhongjian:choose-agent');
  assert.equal(f.events.at(-1).detail,'苏轼');
});


test('the summary follows the viewpoint cards in each answer',()=>{
  const f=setup();
  vm.runInContext("render({question_title:'感到孤独没有连接',cards:[{display:{person:'孔子',excerpt:'原文'}}]},'提问',$('results'))",f.ctx);
  const parts=f.$('results').children;
  assert.equal(parts[0].className,'cards-grid');
  assert.equal(parts.at(-1).className,'question-title');
  assert.equal(parts.at(-1).children.at(-1).textContent,'感到孤独没有连接');
});


test('space in an empty question is left to normal typing',()=>{
  const f=setup(), q=f.$('question');
  let prevented=false;
  q.handlers.keydown({key:' ',preventDefault(){prevented=true}});
  assert.equal(prevented,false);
});
