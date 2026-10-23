const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source=fs.readFileSync('budget/static/budget/loader.js','utf8');
function setup(){
  const handlers={},documentHandlers={},timers=new Map();let index=0,dirty=false;
  const loader={hidden:true,dataset:{}};
  const document={readyState:'loading',visibilityState:'visible',getElementById:()=>loader,querySelector:()=>dirty?{}:null,addEventListener(name,fn){documentHandlers[name]=fn}};
  const window={addEventListener(name,fn){handlers[name]=fn}};
  vm.runInNewContext(source,{document,window,navigator:{onLine:true},location:new URL('https://family.example/app/kalender/'),URL,Set,queueMicrotask,setTimeout(fn){timers.set(++index,fn);return index},clearTimeout(id){timers.delete(id)}});
  return{loader,window,documentHandlers,handlers,timers,dirty(value){dirty=value}};
}
test('supplied startup loader finishes immediately and content loading is token-aware and fail-open',()=>{
  const h=setup();assert.equal(h.loader.hidden,false);assert.equal(h.loader.dataset.mode,'boot');h.documentHandlers.DOMContentLoaded();assert.equal(h.loader.hidden,true);assert.equal(h.timers.size,0);
  const first=h.window.FamilieblikkLoader.start(),second=h.window.FamilieblikkLoader.start();h.window.FamilieblikkLoader.stop(first);assert.equal(h.loader.hidden,false);h.window.FamilieblikkLoader.stop(second);assert.equal(h.loader.hidden,true);
  h.window.FamilieblikkLoader.start();[...h.timers.values()][0]();assert.equal(h.loader.hidden,true);
});
test('loader clears on back navigation and failures and never masks dirty or cancelled navigation',async()=>{
  const h=setup();h.documentHandlers.DOMContentLoaded();
  const link={href:'https://family.example/app/poster/',target:'',hasAttribute:()=>false};
  const event={button:0,type:'click',defaultPrevented:false,target:{closest:()=>link}};
  h.dirty(true);h.documentHandlers.click(event);await Promise.resolve();assert.equal(h.loader.hidden,true);
  h.dirty(false);const cancelled={...event};h.documentHandlers.click(cancelled);cancelled.defaultPrevented=true;await Promise.resolve();assert.equal(h.loader.hidden,true);
  h.documentHandlers.click(event);await Promise.resolve();assert.equal(h.loader.hidden,false);
  for(const name of ['pageshow','popstate','error','unhandledrejection','offline','focus']){h.window.FamilieblikkLoader.start();h.handlers[name]();assert.equal(h.loader.hidden,true,name)}
});
test('saving an edited form shows progress after its submit handler accepts the save',async()=>{
  const h=setup();h.documentHandlers.DOMContentLoaded();h.dirty(true);
  const form={matches:()=>false,target:'',checkValidity:()=>true};
  const event={type:'submit',defaultPrevented:false,target:form};
  h.documentHandlers.submit(event);
  h.dirty(false); // app.js accepts the save and clears the form's dirty flag.
  await Promise.resolve();assert.equal(h.loader.hidden,false);
  h.handlers.pageshow();h.dirty(true);
  const cancelled={...event};h.documentHandlers.submit(cancelled);
  cancelled.defaultPrevented=true;
  await Promise.resolve();assert.equal(h.loader.hidden,true);
});
test('loader uses only local supplied resources and static reduced-motion fallback',()=>{
  const template=fs.readFileSync('budget/templates/budget/loader.html','utf8'),css=fs.readFileSync('budget/static/budget/loader.css','utf8');
  assert.match(template,/id="app-loader"[^>]+hidden/);assert.match(template,/viewBox="-20 -20 256 256"/);assert.match(template,/loader-logo.png/);assert.match(template,/loader-icon.png/);
  assert.doesNotMatch(template+css,/DCLogic|x-dc|fonts\.google|https?:\/\//);assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);assert.match(css,/pointer-events:none/);assert.match(css,/\.loader-static-icon\{display:block/);
  const {createHash}=require('node:crypto');
  const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  assert.equal(hash('budget/static/budget/loader-icon.png'),'3e0b74f3a50aea95bc32d41a6c5415a6aed276864b14c1fd28334c10354f1253');
  assert.equal(hash('budget/static/budget/loader-logo.png'),'f59512ac10267dc976ea18420c127a65fd02aa23d4670eccfa56c612af00f81a');
});
