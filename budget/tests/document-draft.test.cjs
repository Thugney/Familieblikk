const test = require('node:test');
const assert = require('node:assert/strict');
const {suggestionsForDraft, install} = require('../static/budget/document-draft.js');

test('accepts only validated fields and actual calendar dates', () => {
  assert.deepEqual(suggestionsForDraft({supplier: ' Testbutikk ', amount: '1 250,00', kid: '123 456',
    document_date: '22.10.2026', due_date: '31.02.2026', category: 'secret', action: 'expense'}),
    {supplier: 'Testbutikk', amount: '1250.00', kid: '123456', document_date: '2026-10-22'});
  assert.deepEqual(suggestionsForDraft({amount: '-10,00', kid: '123X', due_date: '31.13.2026', supplier: 'bad\ntext'}), {});
  assert.equal(suggestionsForDraft({document_date: '29.02.2028'}).document_date, '2028-02-29');
  assert.equal(suggestionsForDraft({document_date: '29.02.2027'}).document_date, undefined);
});

test('explicit copy preserves saved, typed and intentionally cleared values and never submits', () => {
  const handlers = {}, buttons = {};
  const fields = Object.fromEntries(['supplier','amount','document_date','due_date','kid'].map(name => [name,
    {name, value:'', defaultValue:'', dispatchEvent(event) {handlers[event.type]?.({target:this});}}]));
  fields.supplier.value = fields.supplier.defaultValue = 'Saved shop';
  fields.amount.value = '999,00';
  fields.kid.defaultValue = '555'; // Saved value intentionally cleared before copy.
  const status = {textContent:''};
  let submitted = 0;
  const form = {elements:{namedItem:name=>fields[name]}, addEventListener:(name, handler)=>{handlers[name]=handler;}, submit:()=>submitted++};
  const button = {hidden:true, addEventListener:(name, handler)=>{buttons[name]=handler;}};
  const nodes = {'document-draft-form':form, 'use-document-suggestions':button,
    'document-suggestions':{textContent:JSON.stringify({supplier:'OCR shop',amount:'1250,00',document_date:'22.10.2026',due_date:'30.10.2026',kid:'123'})},
    'document-suggestions-status':status};
  install({getElementById:name=>nodes[name]});
  assert.equal(fields.document_date.value, ''); // No automatic application.
  handlers.input({target:fields.due_date}); // Typed then cleared by the user.
  buttons.click();
  assert.equal(fields.supplier.value, 'Saved shop');
  assert.equal(fields.amount.value, '999,00');
  assert.equal(fields.kid.value, '');
  assert.equal(fields.due_date.value, '');
  assert.equal(fields.document_date.value, '2026-10-22');
  assert.match(status.textContent, /1 tomme felt/);
  buttons.click();
  assert.match(status.textContent, /Ingen urørte/);
  assert.equal(submitted, 0);
});

test('uncertain supplier is left for manual review', () => {
  const handlers = {};
  const status = {textContent:''};
  const nodes = {'document-draft-form':{elements:{namedItem:()=>null},addEventListener:()=>{}},
    'use-document-suggestions':{addEventListener:(name,handler)=>{handlers[name]=handler;}},
    'document-suggestions':{textContent:'{}'},'document-suggestions-status':status};
  install({getElementById:name=>nodes[name]});
  handlers.click();
  assert.match(status.textContent, /Leverandør \/ butikk må fylles ut manuelt/);
});
