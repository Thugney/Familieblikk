const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('budget/static/budget/ui-refresh.js', 'utf8');
function node(attrs = {}) {
  return {attrs, events: {}, hidden: false, classList: {toggle() {}},
    getAttribute(k) { return this.attrs[k]; }, setAttribute(k,v) { this.attrs[k]=v; },
    addEventListener(k,fn) { this.events[k]=fn; }, focus() { this.focused=true; },
    querySelectorAll() { return []; }};
}
test('camera tabs support keyboard selection and panel relationships', () => {
  const tabs = ['manual','camera'].map(mode => node({'data-capture-mode':mode}));
  const panels = ['manual','camera'].map(mode => node({'data-capture-panel':mode}));
  const surface = {querySelectorAll: selector => selector.includes('mode') ? tabs : panels};
  const document = {querySelectorAll: selector => selector === '[data-entry-create-surface]' ? [surface] : []};
  vm.runInNewContext(source, {document});
  assert.equal(tabs[0].tabIndex,0); assert.equal(tabs[1].tabIndex,-1);
  let prevented=false;
  tabs[0].events.keydown({key:'ArrowRight',preventDefault(){prevented=true;}});
  assert.equal(prevented,true); assert.equal(tabs[1].focused,true);
  assert.equal(tabs[1].attrs['aria-selected'],'true'); assert.equal(panels[0].hidden,true);
  assert.equal(panels[1].attrs['aria-labelledby'],tabs[1].id);
  assert.equal(tabs[1].attrs['aria-controls'],panels[1].id);
});
test('quick actions move focus on open and return it on Escape', () => {
  const fab=node(), sheet=node(), link=node(); sheet.hidden=true;
  sheet.querySelector=()=>link;
  const container=node(); container.querySelector=s=>s.includes('fab') ? fab : sheet;
  container.contains=target=>[fab,sheet,link].includes(target);
  const document=node(); document.querySelectorAll=s=>s==='[data-mobile-quick-actions]' ? [container] : [];
  vm.runInNewContext(source,{document});
  fab.events.click({stopPropagation(){}});
  assert.equal(sheet.hidden,false); assert.equal(link.focused,true);
  document.events.keydown({key:'Escape',preventDefault(){}});
  assert.equal(sheet.hidden,true); assert.equal(fab.focused,true);
  fab.events.click({stopPropagation(){}});
  container.events.focusout({relatedTarget:{}});
  assert.equal(sheet.hidden,true);
});
test('calendar header shortcut forwards to the real calendar editor action', () => {
  const shortcut=node(); shortcut.hidden=true;
  let opened=0;
  const create={click(){opened++;}};
  const document={querySelectorAll:s=>s==='[data-calendar-quick-create]'?[shortcut]:[], getElementById:id=>id==='calendar-create'?create:null};
  vm.runInNewContext(source,{document});
  assert.equal(shortcut.hidden,false);
  shortcut.events.click();
  assert.equal(opened,1);
});
