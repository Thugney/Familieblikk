const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/budget/shopping.js'), 'utf8');

function scenario({preserved = false, errors = false, online = true, hidden = false, response = {ok:true, redirected:false, json:async()=>({version:2})}} = {}) {
  const callbacks = {}, notice = {hidden:true};
  let reloads = 0, requests = 0, poll;
  const root = {dataset:{shoppingRevision:'1', revisionUrl:'/synthetic/revision', preservedDraft:String(preserved)}};
  vm.runInNewContext(source, {document:{hidden, querySelector:s=>s==='[data-shopping-revision]'?root:errors?{}:null,
      getElementById:()=>notice, addEventListener:(name, callback)=>{callbacks[name]=callback;}},
    navigator:{onLine:online}, location:{reload:()=>reloads++},
    fetch:async(url, options)=>{requests++; assert.equal(url,'/synthetic/revision'); assert.equal(options.cache,'no-store'); return response;},
    setInterval:callback=>{poll=callback;}});
  return {callbacks, notice, poll, reloads:()=>reloads, requests:()=>requests};
}
test('clean list reloads only when another member changes its revision', async()=>{
  const changed = scenario(); await changed.poll(); assert.equal(changed.reloads(),1);
  const same = scenario({response:{ok:true,json:async()=>({version:1})}}); await same.poll(); assert.equal(same.reloads(),0);
});
test('typed, failed and recovered drafts survive refresh without any new input', async()=>{
  for (const options of [{preserved:true}, {errors:true}, {}]) {
    const state = scenario(options);
    if (!options.preserved && !options.errors) state.callbacks.input();
    await state.poll();
    assert.equal(state.reloads(),0);
    assert.equal(state.notice.hidden,false);
  }
});
test('offline, hidden, denied and redirected responses do not reload private views', async()=>{
  for (const options of [{online:false},{hidden:true},{response:{ok:false}},{response:{ok:true,redirected:true}}]) {
    const state = scenario(options); await state.poll(); assert.equal(state.reloads(),0);
    if (options.online===false || options.hidden) assert.equal(state.requests(),0);
  }
});
