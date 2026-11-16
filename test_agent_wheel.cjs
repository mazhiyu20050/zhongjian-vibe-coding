const {test}=require('node:test'), assert=require('node:assert/strict');
const {readFileSync}=require('node:fs'), vm=require('node:vm');
function setup(){
 const elements=new Map();
 function el(id){const h={}, attrs={}, classes=new Set();return {id,attrs,children:[],value:'',hidden:id==='agent-search-form',style:{setProperty(){}},dataset:{},append(...c){this.children.push(...c)},after(){},contains(target){return target===this||this.children.includes(target)},replaceChildren(){this.children=[]},setAttribute(k,v){attrs[k]=v},hasAttribute(k){return k in attrs},querySelector(){return el()},querySelectorAll(){return []},classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k),toggle(k,on){on?classes.add(k):classes.delete(k)}},addEventListener(k,f){(h[k]??=[]).push(f)},async fire(k,e={}){for(const f of h[k]??[])await f(e)}}}
 function $(id){if(!elements.has(id))elements.set(id,el(id));return elements.get(id)}
 const doc=el('document');doc.body=el('body');doc.createElement=()=>el();doc.querySelector=()=>el();doc.dispatchEvent=()=>{};
 const w=el('window');w.innerWidth=1400;w.matchMedia=()=>({matches:true});
 let raf;
 vm.runInNewContext(readFileSync(require('node:path').join(__dirname,'web','agents.js'),'utf8'),{document:doc,window:w,$,node:()=>el(),agentPerson:null,getJSON:async()=>({agents:['甲','乙','丙'].map(person=>({person,tags:[]}))}),requestAnimationFrame:f=>(raf=f,1),cancelAnimationFrame:()=>{raf=null},clearTimeout,setTimeout});
 return {$,w,dock:doc.body.children[0],flush(){const f=raf;raf=null;f?.()}};
}
test('right slider selects and follows wheel position',async()=>{
 const {$,dock,flush}=setup();await $('agent-trigger').fire('pointerenter');
 assert.match(dock.innerHTML,/id="agent-scroll"[^>]*type="range"/);
 const slider=$('agent-scroll');assert.equal(String(slider.max),'2');slider.value='2';await slider.fire('input');flush();
 assert.equal($('agent-cards').children[2].classList.contains('is-center'),true);
 await $('agent-panel').fire('wheel',{deltaY:95,preventDefault(){}});flush();assert.equal(String(slider.value),'1');
});
test('moving inside does not close; leaving panel closes for mouse, not touch',async()=>{
 const {$,dock}=setup();await $('agent-trigger').fire('pointerenter');
 await $('agent-default').fire('pointerenter',{pointerType:'mouse'});assert.equal(dock.classList.contains('open'),true);
 await $('agent-panel').fire('pointerleave',{pointerType:'touch'});assert.equal(dock.classList.contains('open'),true);
 await $('agent-panel').fire('pointerleave',{pointerType:'mouse'});assert.equal(dock.classList.contains('open'),false);
});

test('drag stays open outside until release, then closes',async()=>{
 const {$,dock,w}=setup();await $('agent-trigger').fire('pointerenter');
 const panel=$('agent-panel');panel.getBoundingClientRect=()=>({left:0,right:1400,top:0,bottom:250});
 await $('agent-scroll').fire('pointerdown',{pointerType:'mouse'});
 await panel.fire('pointerleave',{pointerType:'mouse'});
 assert.equal(dock.classList.contains('open'),true);
 await w.fire('pointerup',{clientX:1401,clientY:150});
 assert.equal(dock.classList.contains('open'),false);
});
