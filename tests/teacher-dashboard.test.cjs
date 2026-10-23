const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../app/web/static/js/dashboard.js'), 'utf8');

function page({now = '2035-01-12T10:00:00Z', countdown = null, modal = null, students = []} = {}) {
  let currentTime = Date.parse(now);
  let currentCountdown = countdown;
  const listeners = new Map();
  const windowListeners = new Map();
  const timers = new Map();
  const requests = [];
  let timerId = 0;
  let shellUrl = 'http://testserver/dashboard';
  let respond = null;
  const view = {classList: {toggle() {}}, setAttribute() {}};
  const shell = {
    replaceWith(next) { currentCountdown = next.countdown; shellUrl = next.url; },
    querySelector: () => ({textContent: JSON.stringify(students)}),
  };
  const document = {
    title: '',
    querySelector(selector) {
      if (selector === '[data-lesson-countdown]') return currentCountdown;
      if (selector === '[data-dashboard-view]') return view;
      if (selector === '[data-teacher-shell]') return shell;
      if (selector === '[data-modal]') return modal;
      return null;
    },
    addEventListener(type, callback) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(callback);
    },
    dispatchEvent(event) { for (const callback of listeners.get(event.type) || []) callback(event); return !event.defaultPrevented; },
    importNode: node => node,
  };
  let nextCountdown = null;
  const fetch = async (url, options) => {
    requests.push({url, options});
    if (respond) return respond(url, options);
    return {ok: true, text: async () => new URL(url, location.href).href};
  };
  const location = {origin: 'http://testserver', href: 'http://testserver/dashboard'};
  const entries = [{url: location.href, state: {existing: 'retained'}}];
  let position = 0;
  const history = {
    get state() { return entries[position].state; },
    pushState(state, _, url) {
      entries.splice(++position);
      location.href = new URL(url, location.href).href;
      entries.push({url: location.href, state});
    },
    replaceState(state, _, url) {
      location.href = new URL(url, location.href).href;
      entries[position] = {url: location.href, state};
    },
    go(delta) {
      if (position + delta < 0 || position + delta >= entries.length) return;
      position += delta;
      location.href = entries[position].url;
      const event = {state: entries[position].state};
      Promise.resolve().then(() => windowListeners.get('popstate')?.(event));
    },
  };
  const window = {
    location, addEventListener(type, callback) { windowListeners.set(type, callback); }, scrollTo() {},
    setInterval(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearInterval(id) { timers.delete(id); },
    setTimeout() {},
  };
  class Clock extends Date { static now() { return currentTime; } }
  class DOMParser {
    parseFromString(url) { return {title: 'TutorFlow', querySelector: () => ({countdown: nextCountdown, url})}; }
  }
  vm.runInNewContext(code, {document, window, location, fetch, Date: Clock, DOMParser,
    history, FormData: class { constructor(form) { return Object.entries(form.values); } },
    CustomEvent: class { constructor(type, options = {}) { this.type = type; this.cancelable = options.cancelable; } preventDefault() { if (this.cancelable) this.defaultPrevented = true; } }, console,
  });
  return {
    window, requests, timers, document, history, entries,
    get shellUrl() { return shellUrl; },
    get position() { return position; },
    respond(fn) { respond = fn; },
    async submit(form) { for (const callback of listeners.get('submit') || []) await callback({target: form, preventDefault() {}}); },
    async traverse(delta) { history.go(delta); await new Promise(resolve => setImmediate(resolve)); },
    event(type) { windowListeners.get(type)?.(); },
    tick(at) { currentTime = Date.parse(at); for (const callback of [...timers.values()]) callback(); },
    async navigate(url, node = null) { nextCountdown = node; await window.TutorFlow.navigate(url); },
    async settings() {
      const status = {textContent: ''};
      const form = {matches: selector => selector === '[data-settings-form]', querySelector: () => status};
      for (const callback of listeners.get('submit') || []) await callback({target: form, preventDefault() {}});
      return status;
    },
  };
}

function countdown(startAt, endAt) {
  return {dataset: {startAt, endAt}, textContent: ''};
}

for (const [start, expected] of [
  ['2035-01-12T15:07:00+03:00', 'Через 2 ч 7 мин'],
  ['2035-01-13T15:00:00+03:00', 'Через 1 д 2 ч'],
  ['2035-01-12T13:00:30+03:00', 'Менее минуты'],
  ['2035-01-12T13:00:00+03:00', 'Идёт занятие'],
  ['2035-01-12T12:50:00+03:00', 'Идёт занятие'],
]) {
  test(`countdown uses the actual offset-aware time: ${expected}`, () => {
    const node = countdown(start, '2035-01-14T14:00:00+03:00');
    page({countdown: node});
    assert.equal(node.textContent, expected);
  });
}

test('countdown updates while open and changes to in-progress at the start', () => {
  const node = countdown('2035-01-12T13:02:00+03:00', '2035-01-12T14:00:00+03:00');
  const runtime = page({countdown: node});
  assert.equal(node.textContent, 'Через 2 мин');
  runtime.tick('2035-01-12T10:01:30Z');
  assert.equal(node.textContent, 'Менее минуты');
  runtime.tick('2035-01-12T10:02:00Z');
  assert.equal(node.textContent, 'Идёт занятие');
});

test('ending the lesson refreshes once to get the next lesson from the backend', async () => {
  const node = countdown('2035-01-12T12:00:00+03:00', '2035-01-12T13:01:00+03:00');
  const runtime = page({countdown: node});
  runtime.tick('2035-01-12T10:01:00Z');
  runtime.tick('2035-01-12T10:02:00Z');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(runtime.requests.length, 1);
  assert.equal(runtime.requests[0].url, 'http://testserver/dashboard');
  assert.equal(runtime.timers.size, 0);
});

test('partial navigation clears the old timer and initializes the new card once', async () => {
  const old = countdown('2035-01-12T14:00:00+03:00', '2035-01-12T15:00:00+03:00');
  const runtime = page({countdown: old});
  assert.equal(runtime.timers.size, 1);
  await runtime.navigate('/schedule');
  assert.equal(runtime.timers.size, 0);
  const next = countdown('2035-01-12T16:00:00+03:00', '2035-01-12T17:00:00+03:00');
  await runtime.navigate('/dashboard', next);
  assert.equal(runtime.timers.size, 1);
  assert.equal(next.textContent, 'Через 3 ч');
  runtime.tick('2035-01-12T11:00:00Z');
  assert.equal(next.textContent, 'Через 2 ч');
  assert.equal(old.textContent, 'Через 1 ч');
});

for (const reason of ['unsaved edit rejected', 'lesson mutation pending']) {
  test(`Back and Forward restore the exact history position when ${reason}`, async () => {
    const runtime = page();
    await runtime.navigate('/schedule');
    await runtime.navigate('/dashboard', countdown('2035-01-12T14:00:00+03:00', '2035-01-12T15:00:00+03:00'));
    let blocked = true, checks = 0;
    runtime.document.addEventListener('tutorflow:before-navigate', event => { checks++; if (blocked) event.preventDefault(); });
    const count = runtime.requests.length;
    await runtime.traverse(-1);
    assert.equal(runtime.position, 2);
    assert.equal(runtime.window.location.href, runtime.shellUrl);
    assert.equal(runtime.requests.length, count);
    assert.equal(runtime.timers.size, 1);
    assert.equal(checks, 1); // compensating popstate must not prompt or clear timers again
    blocked = false;
    await runtime.traverse(-1);
    assert.equal(runtime.position, 1);
    assert.equal(runtime.window.location.href, 'http://testserver/schedule');
    assert.equal(runtime.shellUrl, runtime.window.location.href);
    blocked = true;
    const afterBack = runtime.requests.length;
    await runtime.traverse(1);
    assert.equal(runtime.position, 1);
    assert.equal(runtime.window.location.href, runtime.shellUrl);
    assert.equal(runtime.requests.length, afterBack);
    blocked = false;
    await runtime.traverse(1);
    assert.equal(runtime.position, 2);
    assert.equal(runtime.window.location.href, runtime.shellUrl);
    assert.equal(runtime.entries.length, 3);
    assert.equal(runtime.entries[0].state.existing, 'retained');
  });
}

test('cancelled multi-entry history traversal and same-page refresh do not rewrite history', async () => {
  const runtime = page();
  await runtime.navigate('/schedule');
  await runtime.navigate('/lessons/7');
  let blocked = true;
  runtime.document.addEventListener('tutorflow:before-navigate', event => { if (blocked) event.preventDefault(); });
  await runtime.traverse(-2);
  assert.equal(runtime.position, 2);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
  blocked = false;
  await runtime.window.TutorFlow.navigate(runtime.window.location.href, {replace: true});
  assert.equal(runtime.entries.length, 3);
  await runtime.traverse(-2);
  assert.equal(runtime.position, 0);
  assert.equal(runtime.shellUrl, 'http://testserver/dashboard');
  await runtime.traverse(2);
  assert.equal(runtime.position, 2);
  assert.equal(runtime.shellUrl, 'http://testserver/lessons/7');
});

test('failed Back followed by Retry preserves the entry restored by a later veto', async t => {
  const errors = t.mock.method(console, 'error', () => {});
  const runtime = page();
  await runtime.navigate('/schedule');
  await runtime.navigate('/lessons/7');
  runtime.respond(() => ({ok: false, status: 503}));
  await runtime.traverse(-1);
  assert.equal(runtime.position, 1);
  assert.equal(runtime.window.location.href, 'http://testserver/schedule');
  assert.match(runtime.document.querySelector('[data-dashboard-view]').innerHTML, /data-retry-navigation="http:\/\/testserver\/schedule"/);
  assert.match(errors.mock.calls[0].arguments[0].message, /HTTP 503/);

  runtime.respond(null);
  const retry = {dataset: {retryNavigation: 'http://testserver/schedule'}};
  runtime.document.dispatchEvent({type: 'click', target: {
    closest: selector => selector === '[data-retry-navigation]' ? retry : null,
  }});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(runtime.shellUrl, 'http://testserver/schedule');
  let blocked = true;
  runtime.document.addEventListener('tutorflow:before-navigate', event => { if (blocked) event.preventDefault(); });
  const count = runtime.requests.length;
  await runtime.traverse(-1);
  assert.equal(runtime.position, 1);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
  assert.equal(runtime.requests.length, count);
  assert.deepEqual(runtime.entries.map(entry => entry.state.tutorflowPosition), [0, 1, 2]);

  blocked = false;
  await runtime.traverse(-1);
  assert.equal(runtime.position, 0);
  assert.equal(runtime.shellUrl, 'http://testserver/dashboard');
  await runtime.traverse(1);
  assert.equal(runtime.position, 1);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
  assert.equal(runtime.shellUrl, 'http://testserver/schedule');
  await runtime.traverse(1);
  assert.equal(runtime.position, 2);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
  assert.equal(runtime.shellUrl, 'http://testserver/lessons/7');
});

test('Back during a pending create restores URL without replacing the live modal, then works after failure', async () => {
  const dialog = modal();
  const runtime = page({modal: dialog});
  await runtime.navigate('/schedule');
  const form = dialog.querySelector('[data-modal-form]');
  form.matches = selector => selector === '[data-modal-form]';
  form.querySelector = dialog.querySelector;
  form.values = {student_id: '1', date: '2035-01-13', start: '10:00', end: '11:00', topic: 'Оптика'};
  runtime.window.TutorFlow.openModal('lesson');
  let resolve;
  runtime.respond(() => new Promise(done => { resolve = done; }));
  const pending = runtime.submit(form);
  const count = runtime.requests.length;
  await runtime.traverse(-1);
  assert.equal(runtime.position, 1);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
  assert.equal(runtime.requests.length, count);
  resolve({ok: false, json: async () => ({detail: 'Время занято'})});
  await pending;
  assert.equal(dialog.nodes.get('[data-modal-error]').textContent, 'Время занято');
  runtime.respond(null);
  await runtime.traverse(-1);
  assert.equal(runtime.position, 0);
  assert.equal(runtime.window.location.href, runtime.shellUrl);
});

test('empty dashboard creates no timer or network request', () => {
  const runtime = page();
  assert.equal(runtime.timers.size, 0);
  assert.equal(runtime.requests.length, 0);
});

test('server time prevents a fast client clock from refreshing an unexpired lesson in a loop', () => {
  const node = countdown('2035-01-12T14:00:00+03:00', '2035-01-12T15:00:00+03:00');
  node.dataset.serverNow = '2035-01-12T10:00:00Z';
  const runtime = page({now: '2035-01-12T16:00:00Z', countdown: node});
  assert.equal(node.textContent, 'Через 1 ч');
  assert.equal(runtime.requests.length, 0);
  runtime.tick('2035-01-12T17:00:00Z');
  assert.equal(node.textContent, 'Идёт занятие');
});

test('invalid lesson timestamps do not create timers or refresh loops', () => {
  const runtime = page({countdown: countdown('invalid', 'invalid')});
  assert.equal(runtime.timers.size, 0);
  assert.equal(runtime.requests.length, 0);
});

test('page restoration cannot reset the server clock or duplicate an expiry refresh', () => {
  const future = countdown('2035-01-12T14:00:00+03:00', '2035-01-12T15:00:00+03:00');
  future.dataset.serverNow = '2035-01-12T10:00:00Z';
  const runtime = page({countdown: future});
  runtime.tick('2035-01-12T10:30:00Z');
  runtime.event('pageshow');
  assert.equal(future.textContent, 'Через 30 мин');
  assert.equal(runtime.timers.size, 1);

  const expired = page({countdown: countdown('2035-01-12T11:00:00+03:00', '2035-01-12T12:00:00+03:00')});
  expired.event('pageshow');
  assert.equal(expired.requests.length, 1);
});

test('unsupported settings never report a successful save', async () => {
  const runtime = page();
  const status = await runtime.settings();
  assert.match(status.textContent, /недоступно/);
  assert.doesNotMatch(status.textContent, /Сохранено/);
  assert.equal(runtime.requests.length, 0);
});

function modal() {
  const nodes = new Map();
  for (const selector of ['[data-modal-title]', '[data-modal-submit]', '[data-modal-fields]', '[data-modal-error]']) {
    nodes.set(selector, {textContent: '', innerHTML: '', hidden: false});
  }
  nodes.set('[data-modal-form]', {elements: {namedItem: () => null}});
  return {nodes, showModal() {}, querySelector: selector => nodes.get(selector)};
}

test('obsolete metadata-only modal cannot masquerade as material upload', () => {
  const dialog = modal();
  const runtime = page({modal: dialog});
  runtime.window.TutorFlow.openModal('material');
  assert.equal(dialog.nodes.get('[data-modal-title]').textContent, '');
  assert.equal(dialog.nodes.get('[data-modal-fields]').innerHTML, '');
  assert.equal(runtime.requests.length, 0);
});

test('student names are escaped rather than interpreted as option markup', () => {
  const dialog = modal();
  const runtime = page({modal: dialog, students: [{id: 1, name: '<img src=x onerror=alert(1)>'}]});
  runtime.window.TutorFlow.openModal('student');
  // The lesson modal contains the student selector.
  runtime.window.TutorFlow.openModal('lesson');
  const markup = dialog.nodes.get('[data-modal-fields]').innerHTML;
  assert.doesNotMatch(markup, /<img/);
  assert.match(markup, /&lt;img/);
});
