const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const sourcePath = path.join(__dirname, '../budget/static/budget/spending.js');
const {parseOre, equation, requestGate, money, assetContribution, entryUrl} = require(sourcePath);
const {harness} = require('./spending-dom-harness.cjs');

test('NOK fields distinguish unknown, explicit zero and exact two decimal ore', () => {
  assert.equal(parseOre(''), null);
  assert.equal(parseOre('  '), null);
  assert.equal(parseOre('0'), 0);
  assert.equal(parseOre('0.00'), 0);
  assert.equal(parseOre('12,34'), 1234);
  assert.equal(parseOre('12000.01'), 1200001);
  assert.equal(parseOre('0.29'), 29);
  assert.equal(parseOre('-10'), null);
  assert.equal(parseOre('1.234'), null);
  assert.equal(parseOre('Infinity'), null);
  assert.equal(parseOre('3e4'), null);
});

test('forecast subtracts fixed, variable and each configured plan once and preserves deficit', () => {
  const plan = {totals:{ordinary_fixed_ore:20000},assets:[{id:'save',kind:'savings'},{id:'debt',kind:'debt'},{id:'fund',kind:'fund'}]};
  const draft = {expected_income_ore:40000,categories:[{id:'food',other_ore:10000}],assets:[{id:'save',amount_ore:5000},{id:'debt',amount_ore:7000},{id:'fund',amount_ore:3000}]};
  assert.deepEqual(equation(plan,draft),{ordinary_fixed_ore:20000,other_categories_ore:10000,savings_ore:5000,debt_ore:7000,funds_ore:3000,planned_remainder_ore:-5000});
  draft.categories[0].other_ore = null;
  assert.equal(equation(plan,draft).planned_remainder_ore,null);
  draft.categories[0].other_ore = 0;
  assert.equal(equation(plan,draft).planned_remainder_ore,5000);
  draft.expected_income_ore = null;
  assert.equal(equation(plan,draft).planned_remainder_ore,null);
});

test('old responses are invalidated immediately while the next search still waits for debounce', () => {
  const gate = requestGate();
  const first = gate.begin();
  assert.equal(first.current(), true);
  gate.invalidate();
  assert.equal(first.signal.aborted, true);
  assert.equal(first.current(), false);
  const second = gate.begin();
  assert.equal(second.current(), true);
  const third = gate.begin();
  assert.equal(second.current(), false);
  assert.equal(second.signal.aborted, true);
  assert.equal(third.current(), true);
});

test('refund and unknown amounts retain their meaning in Norwegian display', () => {
  assert.equal(money(null), 'Ukjent');
  assert.match(money(-40000), /400/);
  assert.match(money(-40000), /[-−]/);
  assert.match(money(0), /0/);
});

test('debt obligation floors and fund gaps match server forecast without duplicate obligations', () => {
  assert.equal(assetContribution({kind:'debt',obligation_ore:10000},3000),10000);
  assert.equal(assetContribution({kind:'debt',obligation_ore:10000},12000),12000);
  assert.equal(assetContribution({kind:'fund',obligation_ore:15000,available_balance_ore:8000},3000),7000);
  assert.equal(assetContribution({kind:'fund',obligation_ore:15000,available_balance_ore:20000},3000),3000);
  assert.equal(assetContribution({kind:'fund',obligation_ore:15000,available_balance_ore:8000},null),null);
});

test('privacy and explicit confirmation invariants remain in frontend', () => {
  const source = fs.readFileSync(sourcePath,'utf8');
  assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|\.innerHTML\s*=/);
  assert.match(source, /confirmation_digest:preview\.confirmation_digest,confirm:true,key:saveKey/);
  assert.match(source, /cache:'no-store'/);
  assert.match(source, /setTimeout\(loadSpending,300\)/);
  assert.match(source, /form\.dataset\.dirty = 'true'/);
  assert.doesNotMatch(source, /id:tab===/);
  assert.match(source, /breakdown\(result\.categories,c=>openDetail\(c,params\),'sp-annual-breakdown'\)/);
});

test('category detail links require readable history, exact area and month on the same origin', () => {
  const origin='http://localhost:4180';
  const path='/historikk/entry/01234567-89ab-cdef-0123-456789abcdef/';
  const area='abcdef01-2345-6789-abcd-ef0123456789';
  const route=path+'?area='+area+'&month=2026-09';
  assert.equal(entryUrl(route,origin),origin+route);
  assert.equal(entryUrl(origin+route,origin),origin+route);
  assert.equal(entryUrl('https://example.com'+route,origin),null);
  assert.equal(entryUrl('javascript:alert(1)',origin),null);
  assert.equal(entryUrl('/endre/asset/01234567-89ab-cdef-0123-456789abcdef/',origin),null);
  assert.equal(entryUrl(route.replace('/historikk/', '/endre/'),origin),null);
  for(const invalid of [path, path+'?area='+area, path+'?month=2026-09', route+'&area='+area,
    route+'&month=2026-10', route.replace('2026-09','2026-13'), route.replace(area,'-'.repeat(36)),
    route.replace('01234567-89ab-cdef-0123-456789abcdef','-'.repeat(36)), route+'&operation=reverse',
    route+'#other', 'http://user:password@localhost:4180'+route]) assert.equal(entryUrl(invalid,origin),null,invalid);
});

test('actual module previews only until explicit confirmation; cancel never saves and confirm saves once',async()=>{
  const app=await harness();
  await app.input('#sp-amount-income-income','1200');
  await app.form.dispatch('submit');
  assert.deepEqual(app.requests.filter(r=>r.method==='POST').map(r=>r.path),['/preview']);
  assert.equal(app.$('#sp-confirm').open,true);
  await app.$('#close-confirm').click();
  assert.equal(app.$('#sp-confirm').open,false);
  assert.equal(app.requests.filter(r=>r.path==='/save').length,0);
  await app.form.dispatch('submit');
  assert.equal(app.requests.filter(r=>r.path==='/save').length,0);
  await app.$('#sp-confirm-action').click();
  assert.equal(app.requests.filter(r=>r.path==='/save').length,1);
  assert.equal(app.requests.find(r=>r.path==='/save').body.confirm,true);
  assert.equal(app.requests.find(r=>r.path==='/save').body.draft.expected_income_ore,120000);
});

test('failed month replacement retains dirty fields and Retry fetches the originally requested target',async()=>{
  const app=await harness();
  await app.input('#sp-amount-income-income','1234');
  app.failPlanning();
  await app.change('#sp-target','2026-12');
  await app.$('#sp-confirm-action').click();
  assert.equal(app.form.dataset.dirty,'true');
  assert.equal(app.$('#sp-amount-income-income').value,'1234');
  assert.equal(app.$('#sp-target').value,'2026-11');
  await app.$('#sp-retry').click();
  assert.equal(app.requests.at(-1).path,'/planning');
  assert.equal(app.requests.at(-1).target,'2026-12');
  assert.equal(app.requests.filter(r=>r.path==='/preview').length,0);
  assert.equal(app.$('#sp-target').value,'2026-12');
  assert.equal(app.form.dataset.dirty,undefined);
});

test('discard confirmation works after reconnect and failed discard preserves the dirty guard',async()=>{
  const app=await harness();
  await app.input('#sp-amount-income-income','1234');
  const discard=app.root.querySelectorAll('button').find(b=>b.textContent==='Forkast utkast');
  await discard.click();
  await app.online(false);assert.equal(app.$('#sp-confirm-action').disabled,true);
  await app.online(true);assert.equal(app.$('#sp-confirm-action').disabled,false);
  app.failPlanning();await app.$('#sp-confirm-action').click();
  assert.equal(app.form.dataset.dirty,'true');
  assert.equal(app.$('#sp-amount-income-income').value,'1234');
  await app.$('#sp-retry').click();assert.equal(app.form.dataset.dirty,undefined);
});

test('failed preview Retry repeats preview without saving',async()=>{
  const app=await harness();app.failPreview();await app.form.dispatch('submit');
  await app.$('#sp-retry').click();
  assert.deepEqual(app.requests.filter(r=>r.method==='POST').map(r=>r.path),['/preview','/preview']);
  assert.equal(app.$('#sp-confirm').open,true);
});

test('future overview opens the selected plan month rather than the default next month',async()=>{
  const app=await harness({initial_tab:'planning',plan_month:'2026-12'});
  assert.equal(app.requests.find(r=>r.path==='/planning').target,'2026-12');
  assert.equal(app.$('#sp-target').value,'2026-12');
});

test('annual graph supplies a visible monetary scale and exact titles for every month',async()=>{
  const app=await harness({initial_tab:'annual'});
  const range=app.$('#sp-annual-results').querySelectorAll('p').find(p=>p.textContent.startsWith('Beløpsskala:'));
  assert.ok(range);
  assert.ok(range.textContent.includes(money(0))&&range.textContent.includes(money(12345)));
  const titles=app.$('#sp-annual-results').querySelectorAll('title');
  assert.equal(titles.length,12);
  assert.ok(titles.some(title=>title.textContent.includes('september')&&title.textContent.includes(money(12345))));
  assert.ok(titles.some(title=>title.textContent.includes('Mangler grunnlag')));
});

test('tab keyboard navigation visits only visible permitted tabs with real focus',async()=>{
  for(const flags of [{can_plan:false,can_annual:true},{can_plan:true,can_annual:false},{can_plan:false,can_annual:false}]){
    const app=await harness({initial_tab:'spending',...flags});
    const spending=app.$('#sp-tab-spending'),annual=app.$('#sp-tab-annual'),planning=app.$('#sp-tab-planning');
    const visible=[spending,...(flags.can_annual?[annual]:[]),...(flags.can_plan?[planning]:[])];
    assert.equal(annual.hidden,!flags.can_annual);assert.equal(planning.hidden,!flags.can_plan);
    spending.focus();assert.equal(app.document.activeElement,spending);
    for(const [key,index] of [['End',visible.length-1],['Home',0],['ArrowLeft',visible.length-1],['ArrowRight',0],['ArrowRight',1%visible.length]]){
      const event=await app.keydown(key);
      assert.equal(event.defaultPrevented,true);
      assert.equal(app.document.activeElement,visible[index],key);
      assert.equal(visible[index].getAttribute('aria-selected'),'true');
      assert.equal(visible[index].tabIndex,0);
      assert.equal(visible[index].hidden,false);
    }
    assert.equal(app.requests.some(r=>r.path==='/planning'),flags.can_plan);
    const selected=app.document.activeElement;
    const ignored=await app.keydown('Escape');assert.equal(ignored.defaultPrevented,undefined);
    assert.equal(app.document.activeElement,selected);
    if(!flags.can_annual)assert.equal(annual.getAttribute('aria-selected'),'false');
    if(!flags.can_plan)assert.equal(planning.getAttribute('aria-selected'),'false');
  }
});
