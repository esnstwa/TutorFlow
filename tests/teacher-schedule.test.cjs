const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../app/web/', name), 'utf8');

class Node {
  constructor(dataset = {}) { this.dataset = dataset; this.listeners = {}; this.hidden = false; this.disabled = false; this.value = ''; this.textContent = ''; this.innerHTML = ''; this.open = false; this.isConnected = true; this.classList = {add() {}, remove() {}, toggle() {}}; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  async emit(type, event = {}) { event.preventDefault ||= () => { event.defaultPrevented = true; }; for (const fn of this.listeners[type] || []) await fn(event); return event; }
  setAttribute(name, value) { this[name] = value; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest(selector) { return this.selectors?.includes(selector) ? this : null; }
  matches(selector) { return this.closest(selector) !== null; }
}
class FormDataStub {
  constructor(form) { this.rows = Object.entries(form.elements).filter(([, field]) => field && typeof field !== 'function').flatMap(([name, field]) => name === 'material' ? field.value.map(value => [name, value]) : [[name, field.value]]); }
  get(name) { return this.rows.find(row => row[0] === name)?.[1] ?? null; }
  getAll(name) { return this.rows.filter(row => row[0] === name).map(row => row[1]); }
  [Symbol.iterator]() { return this.rows[Symbol.iterator](); }
}
const lesson = (extra = {}) => ({id: 7, student_id: 1, student: {id: 1, name: 'Анна', initials: 'АН', subject: 'Алгебра', grade: '9'}, subject: 'Алгебра', topic: 'Дроби', date_iso: '2035-01-12', end_date_iso: '2035-01-12', start: '10:00', end: '11:00', status: 'scheduled', location: 'Кабинет', meeting_url: '', teacher_note: '', materials: [], homeworks: [], ...extra});
const calendarEvent = row => ({id: `lesson-${row.id}`, entity_id: row.id, type: 'lessons', title: row.student.name, avatar: row.student.initials, subtitle: row.topic, date: row.date_iso, start: row.start, end: row.end, status: row.status, url: `/lessons/${row.id}`, draggable: true, lesson: row});
const trigger = (selector, dataset = {}) => Object.assign(new Node(dataset), {selectors: [selector]});
function schedule({lessons = [lesson()], raw, search = ''} = {}) {
  const root = new Node({today: '2035-01-12', currentTime: '12:00'});
  const nodes = new Map();
  for (const key of ['calendar-canvas', 'period-label', 'mini-title', 'mini-grid', 'lesson-dialog', 'lesson-form', 'material-list', 'note-count', 'lesson-avatar', 'lesson-student', 'lesson-meta', 'lesson-date', 'lesson-time', 'lesson-error', 'lesson-save', 'lesson-delete', 'lesson-homeworks', 'event-dialog', 'lesson-close', 'calendar-status']) nodes.set(`[data-${key}]`, new Node());
  nodes.set('[data-calendar-events]', {textContent: raw ?? JSON.stringify(lessons.map(calendarEvent))});
  root.querySelector = selector => nodes.get(selector) || null;
  const form = nodes.get('[data-lesson-form]');
  form.elements = {};
  for (const name of ['student_id', 'date', 'start', 'end', 'end_date', 'duration', 'subject', 'topic', 'status', 'location', 'meeting_url', 'teacher_note']) form.elements[name] = Object.assign(new Node(), {name});
  form.elements.material = {value: []};
  form.reset = () => {};
  nodes.get('[data-lesson-dialog]').querySelector = root.querySelector;
  root.querySelectorAll = selector => selector === '[data-lesson-close]' ? [nodes.get('[data-lesson-close]')] : [];
  const document = new Node();
  document.querySelector = selector => selector === '[data-schedule-root]' ? root : selector === '[data-student-options]' ? {textContent: JSON.stringify([{id: 2, name: 'Борис', initials: 'БО', subject: 'Физика'}])} : null;
  document.dispatchEvent = event => { for (const fn of document.listeners[event.type] || []) fn(event); return !event.defaultPrevented; };
  const requests = [], toasts = [], confirms = [];
  let answer = true;
  let response = async () => ({ok: true, json: async () => ({ok: true, lesson: lesson()})});
  const window = {confirm: message => { confirms.push(message); return answer; }, TutorFlow: {showToast: message => toasts.push(message)}, location: {search}};
  vm.runInNewContext(source('static/js/schedule.js'), {document, window, location: window.location, URLSearchParams, FormData: FormDataStub, fetch: async (url, options) => { requests.push({url, ...options}); return response(); }, CustomEvent: class {constructor(type, options) { this.type = type; Object.assign(this, options); }}, console});
  return {root, nodes, form, requests, toasts, confirms, document,
    node: key => nodes.get(`[data-${key}]`),
    click: (selector, dataset) => root.emit('click', {target: trigger(selector, dataset)}),
    open: (id = 'lesson-7') => root.emit('click', {target: trigger('[data-event-id]', {eventId: id})}),
    submit: () => form.emit('submit'),
    input: name => root.emit('input', {target: form.elements[name]}),
    respond(fn) { response = fn; }, confirm(value) { answer = value; },
  };
}

test('edit form sends complete canonical payload and adopts the returned lesson, not stale event fields', async () => {
  const p = schedule(); await p.open();
  assert.equal(p.form.elements.date.value, '2035-01-12');
  assert.equal(p.form.elements.duration.value, 60);
  assert.match(p.form.elements.student_id.innerHTML, /Анна/); // archived current student remains selectable
  const values = {student_id: '2', date: '2035-02-01', start: '23:30', end_date: '2035-02-02', end: '01:00', subject: 'Физика', topic: 'Волны', location: 'Зал', meeting_url: 'https://example.org/lesson', teacher_note: 'Помнить', status: 'completed_paid'};
  Object.entries(values).forEach(([key, value]) => p.form.elements[key].value = value);
  p.form.elements.material.value = [' Учебник ', '', 'https://example.org/file'];
  const saved = lesson({...values, student_id: 2, date_iso: values.date, end_date_iso: values.end_date, student: {id: 2, name: 'Борис', initials: 'БО', subject: 'Физика', grade: '10'}, materials: ['Учебник', 'https://example.org/file']});
  p.respond(async () => ({ok: true, json: async () => ({ok: true, lesson: saved})}));
  await p.submit();
  assert.equal(p.requests[0].url, '/api/lessons/7');
  assert.deepEqual(JSON.parse(p.requests[0].body), {...values, student_id: 2, materials: ['Учебник', 'https://example.org/file']});
  assert.equal(p.node('lesson-dialog').open, false);
  assert.deepEqual(p.toasts, ['Изменения сохранены']);
  assert.match(p.node('calendar-canvas').innerHTML, /Борис/);
  assert.match(p.node('calendar-canvas').innerHTML, /БО/);
  assert.match(p.node('calendar-canvas').innerHTML, /completed_paid/);
  assert.match(p.node('calendar-canvas').innerHTML, /2035-02-01/);
  await p.open();
  assert.equal(p.node('lesson-student').textContent, 'Борис');
  assert.equal(p.form.elements.meeting_url.value, values.meeting_url);
  assert.equal(p.form.elements.date.value, values.date);
});

test('save is single-flight and blocks close, reopen, delete, escape and SPA navigation until settled', async () => {
  const p = schedule({lessons: [lesson(), lesson({id: 8, topic: 'Второй'})]}); await p.open();
  let resolve;
  p.respond(() => new Promise(done => { resolve = done; }));
  const pending = p.submit();
  assert.equal(p.node('lesson-save').disabled, true);
  const duplicate = p.submit();
  assert.equal(p.requests.length, 1);
  await p.click('[data-lesson-close]');
  await p.node('lesson-dialog').emit('cancel');
  await p.open('lesson-8');
  await p.click('[data-lesson-delete]');
  assert.equal(p.node('lesson-dialog').open, true);
  assert.equal(p.form.elements.topic.value, 'Дроби');
  assert.equal(p.requests.length, 1);
  const nav = {type: 'tutorflow:before-navigate', preventDefault() { this.defaultPrevented = true; }};
  p.document.dispatchEvent(nav);
  assert.equal(nav.defaultPrevented, true);
  resolve({ok: false, json: async () => ({detail: 'Время занято'})}); await pending;
  assert.equal(p.node('lesson-dialog').open, true);
  assert.equal(p.node('lesson-error').textContent, 'Время занято');
  assert.equal(p.node('lesson-save').disabled, false);
  assert.equal(p.node('lesson-delete').disabled, false);
  assert.deepEqual(p.toasts, []);
});

test('cancel status and deletion ask confirmation; rejected/network failures never remove the lesson', async () => {
  const p = schedule(); await p.open();
  p.form.elements.status.value = 'cancelled'; p.confirm(false);
  await p.submit(); assert.equal(p.requests.length, 0);
  await p.click('[data-lesson-delete]'); assert.equal(p.requests.length, 0);
  p.confirm(true);
  p.respond(async () => { throw new Error('Нет сети'); });
  await p.submit();
  assert.equal(p.node('lesson-error').textContent, 'Нет сети');
  assert.equal(p.node('lesson-dialog').open, true); assert.deepEqual(p.toasts, []);
  p.respond(async () => ({ok: false, json: async () => ({ok: false, error: 'Нельзя удалить'})}));
  await p.click('[data-lesson-delete]');
  assert.equal(p.requests.at(-1).url, '/api/lessons/7');
  assert.equal(p.node('lesson-error').textContent, 'Нельзя удалить');
  assert.match(p.node('calendar-canvas').innerHTML, /data-event-id="lesson-7"/);
  p.respond(async () => ({ok: true, json: async () => ({ok: true})}));
  await p.click('[data-lesson-delete]');
  assert.equal(p.node('lesson-dialog').open, false);
  assert.doesNotMatch(p.node('calendar-canvas').innerHTML, /data-event-id="lesson-7"/);
  assert.deepEqual(p.toasts, ['Занятие удалено']);
});

test('delete is single-flight and protects the active lesson while pending', async () => {
  const p = schedule(); await p.open();
  let resolve; p.respond(() => new Promise(done => { resolve = done; }));
  const pending = p.click('[data-lesson-delete]');
  const duplicate = p.click('[data-lesson-delete]');
  assert.equal(p.requests.length, 1);
  await duplicate; await p.submit(); await p.click('[data-lesson-close]'); await p.open();
  assert.equal(p.requests.length, 1); assert.equal(p.node('lesson-dialog').open, true);
  resolve({ok: true, json: async () => ({ok: true})}); await pending;
  assert.equal(p.node('lesson-dialog').open, false);
});

test('duration and wall-time edits stay synchronized across midnight without local timezone conversion', async () => {
  const p = schedule(); await p.open();
  p.form.elements.date.value = '2035-03-10';
  p.form.elements.start.value = '23:30';
  p.form.elements.duration.value = '90';
  await p.input('duration');
  assert.equal(p.form.elements.end_date.value, '2035-03-11');
  assert.equal(p.form.elements.end.value, '01:00');
  p.form.elements.date.value = '2035-03-12'; await p.input('date');
  assert.equal(p.form.elements.end_date.value, '2035-03-13');
  p.form.elements.end.value = '02:00'; await p.input('end');
  assert.equal(p.form.elements.duration.value, 150);
});

test('cross-midnight lesson appears on both days, not with a negative or artificial duration', async () => {
  const p = schedule({lessons: [lesson({date_iso: '2035-01-12', end_date_iso: '2035-01-13', start: '23:30', end: '01:00'})]});
  assert.equal((p.node('calendar-canvas').innerHTML.match(/data-event-id="lesson-7"/g) || []).length, 2);
  assert.match(p.node('calendar-canvas').innerHTML, /23:30–24:00/);
  assert.match(p.node('calendar-canvas').innerHTML, /00:00–01:00/);
  await p.click('[data-calendar-view]', {calendarView: 'month'});
  assert.equal((p.node('calendar-canvas').innerHTML.match(/data-event-id="lesson-7"/g) || []).length, 2);
});

test('review ending at midnight stays visible in week and month without bleeding into the next day', async () => {
  const review = {id: 'review-1', type: 'reviews', title: 'Проверка задания', subtitle: 'Работа ученика', date: '2035-01-12', start: '23:00', end_date: '2035-01-13', end: '00:00', url: '/homework-recipients/1', draggable: false};
  const p = schedule({raw: JSON.stringify([review])});
  assert.equal((p.node('calendar-canvas').innerHTML.match(/data-calendar-event="review-1"/g) || []).length, 1);
  assert.match(p.node('calendar-canvas').innerHTML, /23:00–24:00/);
  await p.click('[data-calendar-view]', {calendarView: 'month'});
  assert.equal((p.node('calendar-canvas').innerHTML.match(/href="\/homework-recipients\/1"/g) || []).length, 1);
  await p.click('[data-month-day]', {monthDay: '2035-01-13'});
  assert.doesNotMatch(p.node('calendar-canvas').innerHTML, /data-calendar-event="review-1"/);
});

test('more than three lessons remain reachable in month view', async () => {
  const p = schedule({lessons: Array.from({length: 5}, (_, index) => lesson({id: index + 1}))});
  await p.click('[data-calendar-view]', {calendarView: 'month'});
  assert.equal((p.node('calendar-canvas').innerHTML.match(/data-event-id=/g) || []).length, 5);
});

test('empty period has an honest state and no excluded integration UI', () => {
  const p = schedule({lessons: []});
  assert.match(p.node('calendar-status').textContent, /Нет событий/);
  assert.doesNotMatch(source('templates/pages/schedule.html') + source('static/js/schedule.js') + source('static/css/schedule.css'), /google|oauth/i);
});

test('lesson deep-link opens its date and editor', () => {
  const p = schedule({search: '?lesson=7', lessons: [lesson({date_iso: '2035-07-01', end_date_iso: '2035-07-01'})]});
  assert.equal(p.node('lesson-dialog').open, true);
  assert.equal(p.form.elements.date.value, '2035-07-01');
  assert.match(p.node('calendar-canvas').innerHTML, /2035-07-01/);
});

test('creation posts canonically, is single-flight, and preserves the form on validation errors', async () => {
  const document = new Node(), modal = new Node(), form = new Node();
  const nodes = new Map(['modal-title', 'modal-submit', 'modal-fields', 'modal-error'].map(key => [`[data-${key}]`, new Node()]));
  nodes.set('[data-modal-form]', form);
  form.selectors = ['[data-modal-form]'];
  form.elements = Object.fromEntries(Object.entries({student_id: '1', topic: 'Тема', date: '2035-01-13', start: '23:00', end_date: '', end: '23:45'}).map(([key, value]) => [key, Object.assign(new Node(), {value})]));
  form.elements.namedItem = name => form.elements[name];
  modal.querySelector = form.querySelector = selector => nodes.get(selector) || null;
  document.querySelector = selector => selector === '[data-modal]' ? modal : null;
  document.dispatchEvent = event => { for (const fn of document.listeners[event.type] || []) fn(event); };
  const calls = []; let resolve;
  const window = Object.assign(new Node(), {clearInterval() {}, setInterval() {}, setTimeout() {}});
  vm.runInNewContext(source('static/js/dashboard.js'), {document, window, location: {href: 'http://testserver/schedule'}, history: {state: null, replaceState() {}}, FormData: FormDataStub, CustomEvent: class {constructor(type) {this.type = type;}}, fetch: (url, options) => {calls.push({url, ...options}); return new Promise(done => {resolve = done;});}, console});
  window.TutorFlow.openModal('lesson');
  const pending = document.emit('submit', {target: form});
  const duplicate = document.emit('submit', {target: form});
  window.TutorFlow.openModal('student');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/lessons');
  assert.equal('end_date' in JSON.parse(calls[0].body), false);
  assert.equal(nodes.get('[data-modal-title]').textContent, 'Создать занятие');
  resolve({ok: false, json: async () => ({detail: 'Время занято'})}); await pending;
  assert.equal(nodes.get('[data-modal-error]').textContent, 'Время занято');
  assert.equal(nodes.get('[data-modal-submit]').disabled, false);
});
