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
  const view = {classList: {toggle() {}}, setAttribute() {}};
  const shell = {
    replaceWith(next) { currentCountdown = next.countdown; },
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
    dispatchEvent(event) { for (const callback of listeners.get(event.type) || []) callback(event); },
    importNode: node => node,
  };
  let nextCountdown = null;
  const fetch = async (url, options) => {
    requests.push({url, options});
    return {ok: true, text: async () => ''};
  };
  const location = {origin: 'http://testserver', href: 'http://testserver/dashboard'};
  const window = {
    location, addEventListener(type, callback) { windowListeners.set(type, callback); }, scrollTo() {},
    setInterval(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearInterval(id) { timers.delete(id); },
    setTimeout() {},
  };
  class Clock extends Date { static now() { return currentTime; } }
  class DOMParser {
    parseFromString() { return {title: 'TutorFlow', querySelector: () => ({countdown: nextCountdown})}; }
  }
  vm.runInNewContext(code, {document, window, location, fetch, Date: Clock, DOMParser,
    history: {pushState() {}, replaceState() {}},
    CustomEvent: class { constructor(type) { this.type = type; } }, console,
  });
  return {
    window, requests, timers,
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

test('metadata-only material action says that it creates a record, not an upload', () => {
  const dialog = modal();
  const runtime = page({modal: dialog});
  runtime.window.TutorFlow.openModal('material');
  assert.match(dialog.nodes.get('[data-modal-title]').textContent, /запись/);
  assert.doesNotMatch(dialog.nodes.get('[data-modal-title]').textContent, /Загрузить/);
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
