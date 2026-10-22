const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../app/web/', name), 'utf8');

test('teacher stylesheet uses the existing cache version helper', () => {
  assert.ok(source('templates/teacher_layout.html').includes("path='/css/dashboard.css') }}?v={{ static_version('css/dashboard.css') }}"));
});
const TOKEN = 'a'.repeat(43);
const student = extra => ({id: 7, name: 'Анна', archived: false, lifecycle: 'unlinked', lifecycle_label: 'Без аккаунта', ...extra});
const reply = data => ({ok: true, json: async () => data});
class Node {
  constructor(attrs = [], root = null) { this.attrs = attrs; this.root = root; this.dataset = {}; this.disabled = false; this.hidden = false; this.isConnected = true; this.open = false; this.value = ''; this.textContent = ''; this.attributes = {}; }
  matches(selector) { return selector.split(',').some(part => this.attrs.includes(part.trim())); }
  hasAttribute(name) { return this.attrs.includes(`[${name}]`); }
  closest(selector) { if (this.matches(selector)) return this; if (selector === 'dialog') return this.dialog; return this.root?.matches(selector) ? this.root : null; }
  querySelector(selector) { return this.nodes?.get(selector) || null; }
  querySelectorAll() { return this.controls || []; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() { this.focused = true; }
  select() { this.selected = true; }
}
function page({archived = false, email = 'a@example.org', lifecycle = 'unlinked', secure = true} = {}) {
  const root = new Node(['[data-student-lifecycle]']);
  root.dataset = {studentId: '7', archived: String(archived), email, lifecycle};
  root.nodes = new Map(); root.controls = [];
  const node = name => root.nodes.get(`[data-${name}]`);
  for (const name of ['student-edit', 'student-invite', 'student-archive', 'student-restore', 'lifecycle-close', 'copy-invite', 'student-edit-dialog', 'student-archive-dialog', 'student-edit-form', 'student-archive-form', 'lifecycle-error', 'edit-error', 'archive-error', 'invite-url', 'invite-result', 'invite-expiry', 'student-lifecycle-label']) {
    const item = new Node([`[data-${name}]`], root); root.nodes.set(`[data-${name}]`, item);
    if (/^(student-(edit|invite|archive|restore)|lifecycle-close|copy-invite)$/.test(name)) root.controls.push(item);
  }
  node('invite-result').hidden = true;
  for (const name of ['edit', 'archive']) {
    const form = node(`student-${name}-form`); form.nodes = root.nodes;
    form.values = {name: 'Новая Анна', email: '', subject: 'Физика', grade: '10'};
    const submit = new Node(['[type="submit"]'], root); form.nodes = new Map(root.nodes); form.nodes.set('[type="submit"]', submit); root.controls.push(submit);
  }
  node('lifecycle-close').dialog = node('student-edit-dialog');
  const listeners = new Map(), requests = [], redirects = [], copies = [], confirms = [];
  const document = {querySelector: () => null, addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); }};
  let respond = () => reply({ok: true, student: student({archived: false})});
  let confirmation = true;
  const window = {location: {origin: 'https://testserver', pathname: '/students/7', assign: url => redirects.push(url)}, isSecureContext: secure, confirm: message => { confirms.push(message); return confirmation; }};
  const navigator = {clipboard: {writeText: async text => copies.push(text)}};
  vm.runInNewContext(source('static/js/student-lifecycle.js'), {window, document, navigator, URL, Date, fetch: async (url, options) => { requests.push({url, ...options}); return respond(); }, FormData: class {constructor(form) { return Object.entries(form.values); }}});
  async function emit(type, target, extra = {}) {
    const event = {type, target, preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...extra};
    for (const callback of listeners.get(type) || []) { await callback(event); if (event.stopped) break; }
    return event;
  }
  return {root, node, document, requests, redirects, copies, confirms, respond(fn) { respond = fn; }, confirm(value) { confirmation = value; }, emit,
    click: name => emit('click', node(name)), submit: (name = 'edit') => emit('submit', node(`student-${name}-form`)),
  };
}

function createPage() {
  const modal = new Node(); modal.nodes = new Map();
  for (const name of ['title', 'submit', 'fields', 'error', 'form']) modal.nodes.set(`[data-modal-${name}]`, new Node());
  const form = modal.querySelector('[data-modal-form]'); form.attrs = ['[data-modal-form]'];
  form.nodes = modal.nodes; form.elements = {namedItem: () => null};
  form.values = {name: 'А'.repeat(100) + ' ' + 'Б'.repeat(100), email: '', subject: 'Физика', grade: '10'};
  const listeners = new Map(), requests = [];
  const shell = {querySelector: () => ({textContent: '[]'}), replaceWith() {}};
  const document = {
    querySelector: selector => selector === '[data-modal]' ? modal : selector === '[data-teacher-shell]' ? shell : null,
    addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); },
    dispatchEvent(event) { for (const fn of listeners.get(event.type) || []) fn(event); return !event.defaultPrevented; }, importNode: node => node,
  };
  const location = {href: 'https://testserver/students', origin: 'https://testserver'};
  const window = {location, addEventListener() {}, clearInterval() {}, scrollTo() {}, setTimeout() {}};
  vm.runInNewContext(source('static/js/dashboard.js'), {window, document, location, history: {state: {}, replaceState() {}, pushState() {}},
    FormData: class {constructor(form) { return Object.entries(form.values); }},
    CustomEvent: class {constructor(type, options = {}) {this.type = type; Object.assign(this, options); } preventDefault() {this.defaultPrevented = true; }},
    DOMParser: class {parseFromString() { return {querySelector: () => shell}; }},
    fetch: async (url, options = {}) => { requests.push({url, ...options}); return {ok: true, json: async () => ({ok: true, student: student()}), text: async () => ''}; }, console});
  return {modal, form, requests, open: kind => window.TutorFlow.openModal(kind), async submit() {for (const fn of listeners.get('submit') || []) await fn({target: form, preventDefault() {}}); }};
}

test('student creation makes only email optional and posts blank email to the canonical API', async () => {
  const p = createPage(); p.open('student');
  const fields = p.modal.querySelector('[data-modal-fields]').innerHTML;
  assert.doesNotMatch(fields.match(/<input[^>]*name="email"[^>]*>/)[0], /required/);
  for (const name of ['name', 'subject', 'grade']) assert.match(fields.match(new RegExp(`<input[^>]*name="${name}"[^>]*>`))[0], /required/);
  assert.equal(p.form.values.name.length, 201);
  await p.submit();
  assert.equal(p.requests[0].url, '/api/students');
  assert.equal(p.requests[0].method, 'POST');
  assert.equal(JSON.parse(p.requests[0].body).email, '');
  assert.equal(JSON.parse(p.requests[0].body).name.length, 201);
  assert.equal(p.requests[1].url, '/students');
  p.open('lesson');
  p.form.values = {student_id: '7', topic: 'Тема', date: '2035-01-12', start: '10:00', end: '11:00'};
  await p.submit();
  assert.equal(p.requests[2].url, '/api/lessons');
});

test('profile exposes an archived read-only branch with restore, while edit and invite remain active-only', () => {
  const html = source('templates/pages/student_profile.html');
  assert.match(html, /{% if student.archived %}[\s\S]*?только для чтения[\s\S]*?data-student-restore[\s\S]*?{% else %}[\s\S]*?data-student-edit/);
  assert.match(html, /data-student-lifecycle-label/);
  assert.match(html, /name="name"[^>]*maxlength="201"/);
  assert.match(html, /name="grade"[^>]*required/);
  assert.match(html, /{% if not student.archived %}[\s\S]*?<dialog[\s\S]*?{% endif %}/);
});

for (const action of ['edit', 'archive', 'restore', 'invite']) {
  test(`${action} is single-flight, blocks close/Escape/competing actions/navigation, and restores controls on failure`, async () => {
    const p = page({archived: action === 'restore'});
    await p.click('student-edit');
    let settle;
    const wait = new Promise(resolve => { settle = resolve; });
    p.respond(() => wait);
    const start = () => ['edit', 'archive'].includes(action) ? p.submit(action) : p.click(`student-${action}`);
    const pending = start();
    try {
      const duplicate = start();
      assert.equal(p.requests.length, 1);
      await duplicate;
      assert.equal(p.node('lifecycle-close').disabled, true);
      assert.equal(p.root.attributes['aria-busy'], 'true');
      await p.click('lifecycle-close');
      await p.click('student-archive');
      await p.click('student-invite');
      assert.equal(p.node('student-edit-dialog').open, action !== 'restore');
      assert.equal(p.node('student-archive-dialog').open, false);
      assert.equal(p.requests.length, 1);
      assert.equal((await p.emit('cancel', p.node('student-edit-dialog'))).defaultPrevented, true);
      assert.equal((await p.emit('keydown', p.node('student-edit-dialog'), {key: 'Escape'})).defaultPrevented, true);
      assert.equal((await p.emit('tutorflow:before-navigate', null)).defaultPrevented, true);
      assert.deepEqual(p.redirects, []);
    } finally {
      settle({ok: false, status: 409, json: async () => ({detail: 'Действие недоступно'})});
      await pending;
    }
    const error = p.node(['edit', 'archive'].includes(action) ? `${action}-error` : 'lifecycle-error');
    assert.match(error.textContent, /^Действие недоступно/);
    assert.equal(p.node('student-edit-dialog').open, action !== 'restore');
    assert.equal(p.node('lifecycle-close').disabled, false);
    assert.equal(p.node('student-edit-form').values.name, 'Новая Анна');
    assert.notEqual((await p.emit('tutorflow:before-navigate', null)).defaultPrevented, true);
    assert.deepEqual(p.redirects, []);
  });
}

for (const action of ['edit', 'archive', 'restore']) {
  test(`${action} rejects malformed or mismatched mutation successes without navigating`, async () => {
    for (const payload of [{}, {ok: false, student: student()}, {ok: true}, {ok: true, student: student({id: 8})}, {ok: true, student: student({archived: 'false'})}]) {
      const p = page({archived: action === 'restore'});
      p.respond(() => reply(payload));
      if (action === 'restore') await p.click('student-restore'); else await p.submit(action);
      assert.deepEqual(p.redirects, [], JSON.stringify(payload));
      assert.equal(p.node(action === 'restore' ? 'lifecycle-error' : `${action}-error`).hidden, false);
      assert.equal(p.node('lifecycle-close').disabled, false);
    }
  });
  test(`${action} ignores a late response after its card is detached`, async () => {
    const p = page({archived: action === 'restore'});
    let settle; p.respond(() => new Promise(resolve => { settle = resolve; }));
    const pending = action === 'restore' ? p.click('student-restore') : p.submit(action);
    p.root.isConnected = false;
    settle(reply({ok: true, student: student({archived: action === 'archive'})}));
    await pending;
    assert.deepEqual(p.redirects, []);
    assert.notEqual((await p.emit('tutorflow:before-navigate', null)).defaultPrevented, true);
  });
}

test('edit sends only permitted fields; archive uses its native confirmation form and preserves the same card', async () => {
  const p = page();
  p.node('student-edit-form').values.teacher_id = '99';
  p.node('student-edit-form').values.user_id = '99';
  await p.submit();
  assert.equal(p.requests[0].url, '/api/students/7');
  assert.equal(p.requests[0].method, 'PATCH');
  assert.deepEqual(JSON.parse(p.requests[0].body), {name: 'Новая Анна', email: '', subject: 'Физика', grade: '10'});
  assert.deepEqual(p.redirects, ['/students/7']);
  const a = page();
  await a.click('student-archive');
  assert.equal(a.node('student-archive-dialog').open, true);
  assert.equal(a.requests.length, 0);
  a.respond(() => reply({ok: true, student: student({archived: true})}));
  await a.submit('archive');
  assert.equal(a.requests[0].url, '/api/students/7/archive');
  assert.equal(a.requests[0].method, 'POST');
  assert.deepEqual(a.redirects, ['/students/7']);
});

test('invites require email, an active card, and an unlinked account in both UI and handler', async () => {
  for (const [options, message] of [[{email: ''}, /почт/], [{lifecycle: 'linked'}, /привязан/], [{archived: true}, /архив/]]) {
    const p = page(options);
    await p.click('student-invite');
    assert.equal(p.requests.length, 0);
    assert.match(p.node('lifecycle-error').textContent, message);
  }
  const html = source('templates/pages/student_profile.html');
  assert.match(html, /data-student-invite{% if not student.email %} disabled{% endif %}/);
  assert.match(html, /Чтобы пригласить ученика, укажите почту/);
  assert.match(html, /student.lifecycle != 'linked'/);
});

test('archived card rejects stale edit/archive controls and forms without requests', async () => {
  const p = page({archived: true});
  await p.click('student-edit'); await p.click('student-archive'); await p.submit(); await p.submit('archive');
  assert.equal(p.requests.length, 0);
  assert.equal(p.node('student-edit-dialog').open, false);
});

test('reissue requires explicit confirmation that the previous link is revoked', async () => {
  const p = page({lifecycle: 'invited'}); p.confirm(false);
  await p.click('student-invite');
  assert.equal(p.requests.length, 0);
  assert.match(p.confirms[0], /предыдущ[а-я]* ссылк[а-я]*.*недействительн/i);
  p.confirm(true); await p.click('student-invite');
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].url, '/api/students/7/invite');
  assert.match(source('templates/pages/student_profile.html'), /Перевыпустить приглашение/);
});

test('invite displays the actual URL and expiry, adopts backend status, and confirms every later reissue', async () => {
  const p = page();
  const invitation = {url: `/invite#${TOKEN}`, expires_at: '2035-01-20T12:00:00+00:00'};
  p.respond(() => reply({ok: true, student: student({lifecycle: 'invited', lifecycle_label: 'Приглашён сервером'}), invitation}));
  await p.click('student-invite');
  assert.equal(p.node('invite-url').value, `https://testserver/invite#${TOKEN}`);
  assert.equal(p.node('invite-result').hidden, false);
  assert.match(p.node('invite-expiry').textContent, /2035/);
  assert.match(p.node('invite-expiry').textContent, /автоматически не отправляется/);
  assert.equal(p.node('student-lifecycle-label').textContent, 'Приглашён сервером');
  assert.equal(p.root.dataset.lifecycle, 'invited');
  assert.equal(p.node('student-invite').textContent, 'Перевыпустить приглашение');
  p.confirm(false); await p.click('student-invite');
  assert.equal(p.requests.length, 1);
  assert.equal(p.node('invite-url').value, `https://testserver/invite#${TOKEN}`);
  await p.click('copy-invite');
  assert.deepEqual(p.copies, [`https://testserver/invite#${TOKEN}`]);
});

test('malformed invite responses never expose a URL, expiry, or successful status', async () => {
  const invitation = {url: `/invite#${TOKEN}`, expires_at: '2035-01-20T12:00:00Z'};
  const valid = {ok: true, student: student({lifecycle: 'invited'}), invitation};
  for (const payload of [
    {...valid, ok: false}, {...valid, student: student({id: 9, lifecycle: 'invited'})}, {...valid, student: student()},
    ...['https://evil.test/invite#' + TOKEN, '/other#' + TOKEN, '/invite', '/invite#short', '/invite?token=x#' + TOKEN, 'https://name@testserver/invite#' + TOKEN].map(url => ({...valid, invitation: {...invitation, url}})),
    ...['invalid', null, '2020-01-20T12:00:00Z'].map(expires_at => ({...valid, invitation: {...invitation, expires_at}})),
  ]) {
    const p = page(); p.respond(() => reply(payload)); await p.click('student-invite');
    assert.equal(p.node('invite-result').hidden, true, JSON.stringify(payload));
    assert.equal(p.node('invite-url').value, '');
    assert.equal(p.root.dataset.lifecycle, 'unlinked');
    assert.equal(p.node('lifecycle-error').hidden, false);
  }
});

test('late detached invite response does not publish a token or status', async () => {
  const p = page(); let settle; p.respond(() => new Promise(resolve => { settle = resolve; }));
  const pending = p.click('student-invite'); p.root.isConnected = false;
  settle(reply({ok: true, student: student({lifecycle: 'invited'}), invitation: {url: `/invite#${TOKEN}`, expires_at: '2035-01-20T12:00:00Z'}}));
  await pending;
  assert.equal(p.node('invite-result').hidden, true);
  assert.equal(p.node('invite-url').value, '');
  assert.equal(p.root.dataset.lifecycle, 'unlinked');
});

test('failed reissue hides the potentially revoked old URL and preserves an honest retry state', async () => {
  const p = page();
  p.respond(() => reply({ok: true, student: student({lifecycle: 'invited'}), invitation: {url: `/invite#${TOKEN}`, expires_at: '2035-01-20T12:00:00Z'}}));
  await p.click('student-invite');
  p.respond(async () => { throw new Error('Нет сети'); });
  await p.click('student-invite');
  assert.equal(p.node('invite-result').hidden, true);
  assert.equal(p.node('invite-url').value, '');
  assert.match(p.node('lifecycle-error').textContent, /Нет сети/);
  assert.match(p.node('lifecycle-error').textContent, /предыдущая ссылка могла/);
  assert.equal(p.node('student-invite').disabled, false);
  assert.equal(p.root.dataset.lifecycle, 'invited');
});

test('clipboard fallback selects the readonly URL without a request or token storage', async () => {
  const p = page({secure: false});
  p.node('invite-url').value = `https://testserver/invite#${TOKEN}`;
  p.node('invite-result').hidden = false;
  p.root.controls.push(p.node('invite-url'));
  p.node('invite-url').focus = function () { if (!this.disabled) this.focused = true; };
  p.node('invite-url').select = function () { if (!this.disabled) this.selected = true; };
  await p.click('copy-invite');
  assert.equal(p.node('invite-url').focused, true);
  assert.equal(p.node('invite-url').selected, true);
  assert.match(p.node('lifecycle-error').textContent, /Ctrl\+C/);
  assert.equal(p.requests.length, 0);
  const teacherCode = source('static/js/student-lifecycle.js').split("  const invitation = document.querySelector('[data-invitation-page]');")[0].split('  // Teacher mutations')[1];
  assert.doesNotMatch(teacherCode, /(?:sessionStorage|localStorage)/);
});

test('profile renders real student-scoped lesson and homework history outside the archive/edit branch', () => {
  const html = source('templates/pages/student_profile.html');
  assert.match(html, /for item in lessons if item.student_id == student.id/);
  assert.match(html, /url_for\('lesson', lesson_id=item.id\)/);
  const history = html.slice(html.indexOf('  </section>'));
  assert.match(history, /for item in student_assignments/);
  assert.match(history, /url_for\('assignment', assignment_id=item.id\)/);
  assert.match(history, /{{ item.title }}/);
  assert.match(history, /{{ item.due }}/);
  assert.match(history, /Занятий пока нет/);
  assert.match(history, /Заданий пока нет/);
  assert.doesNotMatch(history, /if not student.archived/);
});

test('directory reset preserves the selected archive filter', () => {
  const html = source('templates/pages/students.html');
  assert.match(html, /href="{{ url_for\('students'\) }}\?archived={{ directory_archived }}" data-spa>Сбросить/);
});

test('long student names and history layout have teacher-student-scoped styles', () => {
  const css = source('static/css/dashboard.css');
  assert.match(css, /\.teacher-dashboard \[data-directory-student\] strong[^}]*overflow-wrap:\s*anywhere/);
  assert.match(css, /\.teacher-dashboard \[data-student-lifecycle\][^}]*overflow-wrap:\s*anywhere/);
  assert.match(css, /\.teacher-dashboard \.student-profile-history[^}]*gap:/);
});

test('restore posts to the existing API and reloads the same card only after a matching success', async () => {
  const p = page({archived: true});
  await p.click('student-restore');
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].url, '/api/students/7/restore');
  assert.equal(p.requests[0].method, 'POST');
  assert.deepEqual(JSON.parse(p.requests[0].body), {});
  assert.deepEqual(p.redirects, ['/students/7']);
});
