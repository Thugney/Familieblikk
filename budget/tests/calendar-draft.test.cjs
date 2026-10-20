const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const handlers = {}, formHandlers = {};
  let reloads = 0, resets = 0;
  const form = {dataset:{}, hasAttribute:name=>name==='data-dirty-warning', addEventListener:(name,fn)=>formHandlers[name]=fn, reset:()=>resets++};
  const dialog = {addEventListener:(name,fn)=>handlers['dialog:'+name]=fn};
  const context = {document:{getElementById:()=>({}), body:{classList:{toggle(){}}}, querySelectorAll:key=>key==='form'?[form]:[], querySelector:key=>key==='[data-dirty="true"]' && form.dataset.dirty==='true'?form:null}, window:{addEventListener:(name,fn)=>handlers[name]=fn}, navigator:{onLine:true}, location:{reload:()=>reloads++}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/budget/app.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/budget/calendar.js'),'utf8'),context);
  context.installCalendarDraftGuard(form,dialog);
  return {form,handlers,formHandlers,context,reloads:()=>reloads,resets:()=>resets};
}
test('offline reconnect retains changed calendar fields without page reload',()=>{
  const h=harness();h.formHandlers.input();
  h.context.navigator.onLine=false;h.handlers.offline();
  h.context.navigator.onLine=true;h.handlers.online();
  assert.equal(h.form.dataset.dirty,'true');assert.equal(h.reloads(),0);assert.equal(h.resets(),0);
});
test('explicit close including Escape clears discarded draft and allows reconnect refresh',()=>{
  const h=harness();h.formHandlers.input();h.handlers['dialog:close']();
  assert.equal(h.form.dataset.dirty,undefined);assert.equal(h.resets(),1);
  h.handlers.online();assert.equal(h.reloads(),1);
});
