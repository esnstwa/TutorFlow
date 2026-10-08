const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../app/web/static/js/student-lifecycle.js'), 'utf8');
function run(page, pending, search = '') {
  const redirects = [];
  const document = {querySelector: () => null, addEventListener: () => {}};
  const window = {location: {pathname: page, search, replace: url => redirects.push(url)}};
  const sessionStorage = {getItem: key => key === 'tutorflow.pendingInvitation' ? pending : null};
  vm.runInNewContext(code, {window, document, sessionStorage, URLSearchParams});
  return redirects;
}
const INVITE_KEY = 'tutorflow.pendingInvitation';
const TOKEN = 'a'.repeat(43);
async function invitePage({previewStatus = 200, acceptStatus = 200, authStatus = 200, role = 'student', networkFailure = false, acceptNetworkFailure = false, removeThrows = false, hash = ''} = {}) {
  const nodes = new Map();
  function node(hidden = false) {
    return {hidden, disabled: false, textContent: '', listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; }};
  }
  for (const name of ['error', 'description', 'accept', 'auth', 'discard']) nodes.set(`[data-invite-${name}]`, node(['accept', 'auth', 'discard'].includes(name)));
  const invitation = {querySelector: selector => nodes.get(selector)};
  const csrf = {content: ''};
  const document = {addEventListener() {}, querySelector: selector => selector === '[data-invitation-page]' ? invitation : csrf};
  const redirects = [];
  const requests = [];
  const stored = new Map([[INVITE_KEY, TOKEN]]);
  const sessionStorage = {
    getItem: key => stored.get(key) || null,
    setItem: (key, value) => stored.set(key, value),
    removeItem(key) { if (removeThrows) throw new Error('Storage blocked'); stored.delete(key); }
  };
  const window = {location: {pathname: '/invite', search: '', hash, assign: url => redirects.push(url)}};
  const fetch = async (url, options) => {
    requests.push({url, options});
    if (url === '/api/auth/me') return {status: authStatus, ok: authStatus === 200, json: async () => ({user: {role}, csrf_token: 'csrf'})};
    if (networkFailure || (acceptNetworkFailure && url.endsWith('/accept'))) throw new Error('Network unavailable');
    const status = url.endsWith('/preview') ? previewStatus : acceptStatus;
    return {status, ok: status === 200, json: async () => status === 200 ? {invitation: {student_name: 'Student'}} : {detail: 'Invitation unavailable'}};
  };
  vm.runInNewContext(code, {window, document, sessionStorage, fetch, URLSearchParams, history: {replaceState() {}}});
  const flush = () => new Promise(resolve => setImmediate(resolve));
  await flush();
  return {nodes, stored, requests, redirects, async click(name) { const action = nodes.get(`[data-invite-${name}]`).listeners.click; assert.equal(typeof action, 'function'); await action(); await flush(); }};
}
test('fatal preview clears pending invitation and shows a discard escape', async () => {
  const page = await invitePage({previewStatus: 422});
  assert.equal(page.stored.has(INVITE_KEY), false);
  assert.equal(page.nodes.get('[data-invite-discard]').hidden, false);
  assert.equal(page.nodes.get('[data-invite-accept]').hidden, true);
  assert.match(page.nodes.get('[data-invite-error]').textContent, /Invitation unavailable/);
});
test('discard escapes a fatal preview even when storage cleanup throws', async () => {
  const page = await invitePage({previewStatus: 422, removeThrows: true});
  await page.click('discard');
  assert.deepEqual(page.redirects, ['/student/homework?skip_invitation=1']);
  assert.deepEqual(run('/student/homework', TOKEN, '?skip_invitation=1'), []);
  assert.equal(page.requests.some(request => request.url.endsWith('/accept')), false);
});
test('discard returns a teacher to dashboard and an anonymous visitor to login', async () => {
  for (const [options, destination] of [[{role: 'teacher'}, '/dashboard'], [{authStatus: 401}, '/login']]) {
    const page = await invitePage(options);
    assert.equal(page.nodes.get('[data-invite-discard]').hidden, false);
    await page.click('discard');
    assert.deepEqual(page.redirects, [destination]);
    assert.equal(page.stored.has(INVITE_KEY), false);
  }
});
test('wrong-account preview offers discard without enabling accept', async () => {
  const page = await invitePage({previewStatus: 403});
  assert.equal(page.nodes.get('[data-invite-discard]').hidden, false);
  assert.equal(page.nodes.get('[data-invite-accept]').hidden, true);
  await page.click('discard');
  assert.deepEqual(page.redirects, ['/student/homework']);
  assert.equal(page.stored.has(INVITE_KEY), false);
});
test('accept success navigates once even when sessionStorage cleanup is unavailable', async () => {
  const page = await invitePage({removeThrows: true});
  await page.click('accept');
  assert.deepEqual(page.redirects, ['/student/homework?skip_invitation=1']);
  assert.equal(page.nodes.get('[data-invite-error]').hidden, true);
  assert.equal(page.nodes.get('[data-invite-accept]').disabled, true);
  await page.click('accept');
  assert.equal(page.requests.filter(request => request.url.endsWith('/accept')).length, 1);
  assert.deepEqual(run('/student/homework', TOKEN, '?skip_invitation=1'), []);
});
for (const status of [400, 404, 410, 422, 403]) {
  test(`preview ${status} cannot leave a fatal pending invitation`, async () => {
    const page = await invitePage({previewStatus: status});
    assert.equal(page.stored.has(INVITE_KEY), false);
    assert.equal(page.nodes.get('[data-invite-discard]').hidden, false);
    assert.equal(page.nodes.get('[data-invite-accept]').hidden, true);
  });
  test(`accept ${status} clears pending state instead of retrying an invalid invitation`, async () => {
    const page = await invitePage({acceptStatus: status});
    await page.click('accept');
    assert.equal(page.stored.has(INVITE_KEY), false);
    assert.equal(page.nodes.get('[data-invite-accept]').disabled, true);
    assert.equal(page.nodes.get('[data-invite-discard]').hidden, false);
    assert.deepEqual(page.redirects, []);
  });
}
for (const [label, options] of [
  ['anonymous auth', {authStatus: 401}],
  ['preview unauthorized', {previewStatus: 401}],
  ['preview network failure', {networkFailure: true}],
  ['preview server failure', {previewStatus: 503}]
]) {
  test(`${label} preserves pending invitation for retry`, async () => {
    const page = await invitePage(options);
    assert.equal(page.stored.get(INVITE_KEY), TOKEN);
    assert.equal(page.nodes.get('[data-invite-accept]').hidden, true);
    assert.deepEqual(page.redirects, []);
    if (options.authStatus === 401) assert.equal(page.nodes.get('[data-invite-auth]').hidden, false);
  });
}
for (const [label, options] of [['unauthorized', {acceptStatus: 401}], ['network failure', {acceptNetworkFailure: true}]]) {
  test(`accept ${label} preserves pending invitation and permits retry`, async () => {
    const page = await invitePage(options);
    await page.click('accept');
    assert.equal(page.stored.get(INVITE_KEY), TOKEN);
    assert.equal(page.nodes.get('[data-invite-accept]').disabled, false);
    assert.deepEqual(page.redirects, []);
    await page.click('accept');
    assert.equal(page.requests.filter(request => request.url.endsWith('/accept')).length, 2);
  });
}
test('accept success clears pending and uses the normal student destination', async () => {
  const page = await invitePage();
  await page.click('accept');
  assert.equal(page.stored.has(INVITE_KEY), false);
  assert.deepEqual(page.redirects, ['/student/homework']);
  assert.equal(page.nodes.get('[data-invite-error]').hidden, true);
});
test('invite template exposes discard using the existing dashboard button style', () => {
  const template = fs.readFileSync(path.join(__dirname, '../app/web/templates/pages/invite.html'), 'utf8');
  assert.match(template, /<button[^>]*class="dashboard-secondary"[^>]*data-invite-discard/);
});
test('student landing resumes pending invitation after login/register', () => {
  assert.deepEqual(run('/student/homework', 'a'.repeat(43)), ['/invite']);
});
test('invalid pending state cannot redirect and teacher cabinet stays independent', () => {
  assert.deepEqual(run('/student/homework', 'malformed'), []);
  assert.deepEqual(run('/student/homework', null), []);
  assert.deepEqual(run('/dashboard', 'a'.repeat(43)), []);
});
