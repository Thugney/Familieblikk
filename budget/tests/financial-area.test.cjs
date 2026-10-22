const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/budget/financial-area.js'), 'utf8');

function tab(area) {
  const calls = [];
  const location = new URL('https://example.test/app/oversikt/' + (area ? '?area=' + area : ''));
  const window = {fetch: async (input, options) => { calls.push({input, options}); return 'ok'; }};
  vm.runInNewContext(source, {window, location, URL, Request});
  return {fetch: window.fetch, calls};
}

test('two tabs send their own area without changing explicit request targets', async () => {
  const personal = tab('personal'), shared = tab('shared');
  await personal.fetch('/app/forbruk/data/?month=2026-10');
  await shared.fetch('/app/plan/data/');
  await personal.fetch('/app/plan/data/?area=explicit');
  assert.equal(new URL(personal.calls[0].input).searchParams.get('area'), 'personal');
  assert.equal(new URL(shared.calls[0].input).searchParams.get('area'), 'shared');
  assert.equal(personal.calls[1].input, '/app/plan/data/?area=explicit');
});

test('scope is not sent to external or calendar requests and has no fallback', async () => {
  const selected = tab('private');
  for (const url of ['https://other.test/dokument/1/', '/app/kalender/data/', '/push/summary/']) {
    await selected.fetch(url);
    assert.equal(selected.calls.at(-1).input, url);
  }
  const absent = tab();
  await absent.fetch('/app/plan/save/', {method: 'POST'});
  assert.equal(absent.calls[0].input, '/app/plan/save/');
});

test('Request inputs retain method, body and headers when adding the area', async () => {
  const selected = tab('private');
  const request = new Request('https://example.test/app/plan/save/', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': 'synthetic'},
    body: JSON.stringify({confirm: true})
  });
  await selected.fetch(request);
  const actual = selected.calls[0].input;
  assert.equal(new URL(actual.url).searchParams.get('area'), 'private');
  assert.equal(actual.method, 'POST');
  assert.equal(actual.headers.get('X-CSRFToken'), 'synthetic');
  assert.deepEqual(await actual.json(), {confirm: true});
});
