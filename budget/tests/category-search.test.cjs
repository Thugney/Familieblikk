const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function harness(enhanced = true) {
  const events = target => Object.assign(target, {listeners: {}, addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }, fire(name) { const event = {preventDefault() { this.prevented = true; }}; for (const fn of this.listeners[name] || []) fn(event); return event; }});
  const fields = Object.fromEntries(Object.entries({category_q: '', category_status: 'active', month: '2026-09', category_all: '1'}).map(([key, value]) => [key, events({value})]));
  const form = events({id: 'category-filters', elements: {namedItem: key => fields[key]}, dataset: {}, hasAttribute: () => false, querySelector: () => null});
  const result = {content: 'original', attributes: {}, setAttribute(key, value) { this.attributes[key] = value; }, replaceChildren(...nodes) { this.content = nodes.join(''); }};
  const status = {textContent: ''};
  const calls = [], history = [], timers = new Map(); let timerId = 0;
  const document = {body: {classList: {toggle() {}}}, getElementById: key => ({'offline-banner': {}, 'category-filters': form, 'category-results': result, 'category-search-status': status}[key]), querySelectorAll: key => key === 'form' ? [form] : [], querySelector: () => null};
  const fetch = (url, options) => new Promise((resolve, reject) => calls.push({url, options, resolve, reject}));
  const window = {location: {href: 'https://familie.test/app/oversikt/?month=2026-09'}, history: {replaceState(a, b, url) { history.push(url); }}, addEventListener() {}, ...(enhanced ? {fetch, AbortController} : {})};
  const context = {document, window, navigator: {onLine: true}, location: {reload() {}}, fetch, AbortController, URL, DOMParser: class {parseFromString(text) {return {getElementById: () => text === 'missing' ? null : {childNodes: [text]}};}}, setTimeout(fn, delay) {assert.equal(delay, 300); timers.set(++timerId, fn); return timerId;}, clearTimeout(id) {timers.delete(id);}};
  vm.runInNewContext(fs.readFileSync('budget/static/budget/app.js', 'utf8'), context);
  const tick = async () => {await new Promise(resolve => setImmediate(resolve));};
  const runTimer = () => {for (const [id, fn] of timers) {timers.delete(id); fn();}};
  const respond = async (index, content, ok = true) => {calls[index].resolve({ok, redirected: false, text: async () => content}); await tick();};
  return {form, fields, result, status, calls, history, timers, runTimer, respond, tick};
}

test('category input debounces; only results update and successful URL preserves scope', async () => {
  const h = harness();
  h.fields.category_q.value = 'Ma'; h.fields.category_q.fire('input');
  h.fields.category_q.value = 'Mat'; h.fields.category_q.fire('input');
  assert.equal(h.calls.length, 0); assert.equal(h.timers.size, 1);
  h.runTimer(); assert.equal(h.calls.length, 1);
  const url = new URL(h.calls[0].url);
  assert.equal(url.origin, 'https://familie.test');
  assert.equal(url.searchParams.get('category_q'), 'Mat');
  assert.equal(url.searchParams.get('month'), '2026-09');
  assert.equal(url.searchParams.get('category_all'), '1');
  assert.equal(h.calls[0].options.cache, 'no-store');
  assert.equal(h.result.attributes['aria-busy'], 'true');
  await h.respond(0, 'Mat result');
  assert.equal(h.result.content, 'Mat result');
  assert.equal(h.fields.category_q.value, 'Mat');
  assert.equal(h.history.length, 1);
  assert.equal(h.result.attributes['aria-busy'], 'false');
  h.fields.category_q.value = ''; h.fields.category_q.fire('search'); h.runTimer();
  assert.equal(new URL(h.calls[1].url).searchParams.has('category_q'), false);
  await h.respond(1, 'all results');
  h.fields.category_status.value = 'archived'; h.fields.category_status.fire('change');
  assert.equal(new URL(h.calls[2].url).searchParams.get('category_status'), 'archived');
});

test('stale responses cannot win; failure retains old result and canonical URL; submit retries', async () => {
  const h = harness();
  h.fields.category_q.value = 'old'; h.form.fire('submit');
  h.fields.category_q.value = 'new'; h.fields.category_q.fire('input');
  assert.equal(h.calls[0].options.signal.aborted, true);
  await h.respond(0, 'stale'); assert.equal(h.result.content, 'original');
  h.runTimer(); await h.respond(1, 'fresh');
  const successURL = h.history[0];
  h.fields.category_q.value = 'unavailable';
  assert.equal(h.form.fire('submit').prevented, true);
  await h.respond(2, 'server error', false);
  assert.equal(h.result.content, 'fresh'); assert.equal(h.history.at(-1), successURL);
  assert.match(h.status.textContent, /Tidligere resultat vises/);
  assert.equal(h.form.dataset.submitting, undefined);
  h.form.fire('submit'); await h.respond(3, 'retry result');
  assert.equal(h.result.content, 'retry result');
});

test('without fetch support category form retains native GET submission', () => {
  const h = harness(false);
  assert.equal(h.form.fire('submit').prevented, undefined);
  assert.equal(h.calls.length, 0);
});
