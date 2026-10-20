const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

test('service worker caches only public resources and replaces old deploy cache', async () => {
  const origin = 'https://family.example';
  const normalize = value => new URL(typeof value === 'string' ? value : value.url, origin).href;
  const storage = new Map([['familieblikk-public-old', new Map()]]);
  const handlers = {};
  const calls = [];
  let fail = false;
  const cacheApi = {
    open: async name => {
      if (!storage.has(name)) storage.set(name, new Map());
      return {put: async (request, response) => storage.get(name).set(normalize(request), response)};
    },
    keys: async () => [...storage.keys()],
    delete: async name => storage.delete(name),
    match: async request => { for (const cache of storage.values()) if (cache.has(normalize(request))) return cache.get(normalize(request)); }
  };
  const fetch = async (request, options) => {
    calls.push({url: normalize(request), cache: options?.cache || request.cache, credentials: request.credentials});
    if (fail) throw new Error('offline');
    return new Response(normalize(request).endsWith('/offline/') ? 'Koble til for å se budsjettet' : 'public asset');
  };
  vm.runInNewContext(fs.readFileSync('budget/static/budget/sw.js', 'utf8').replace('__PUBLIC_VERSION__', 'new'), {
    self: {location: {origin}, addEventListener: (name, callback) => handlers[name] = callback, skipWaiting: async () => {}, clients: {claim: async () => {}}},
    caches: cacheApi, fetch, Request, Response, URL
  });
  async function lifecycle(name) { let task; handlers[name]({waitUntil: promise => task = promise}); await task; }
  await lifecycle('install');
  await lifecycle('activate');
  assert.deepEqual([...storage.keys()], ['familieblikk-public-new']);
  const expected = ['/offline/', '/static/budget/app.css', '/static/budget/app.js', '/static/budget/icon.svg'].map(path => origin + path).sort();
  assert.deepEqual([...storage.get('familieblikk-public-new').keys()].sort(), expected);
  assert.ok(calls.every(call => call.cache === 'no-store' && call.credentials === 'omit'));
  async function request(path, mode = 'navigate', method = 'GET') {
    let task;
    handlers.fetch({request: {url: origin + path, method, mode}, respondWith: promise => task = promise});
    return task ? await task : undefined;
  }
  await request('/app/oversikt/');
  await request('/innlogging/');
  await request('/private-data/source.json', 'cors');
  assert.equal(await request('/app/poster/', 'cors', 'POST'), undefined);
  assert.deepEqual([...storage.get('familieblikk-public-new').keys()].sort(), expected);
  fail = true;
  const offline = await request('/app/oversikt/');
  assert.equal(await offline.text(), 'Koble til for å se budsjettet');
  assert.deepEqual([...storage.get('familieblikk-public-new').keys()].sort(), expected);
});
