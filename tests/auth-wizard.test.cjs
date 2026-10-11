const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
class Element {
  constructor(dataset = {}) { this.dataset = dataset; this.value = ''; this.hidden = false; this.disabled = false; this.checked = false; this.type = 'password'; this.textContent = ''; this.attrs = {}; this.listeners = {}; this.children = {}; this.classes = new Set(); this.classList = {add: x => this.classes.add(x), remove: x => this.classes.delete(x), toggle: (x, on) => on ? this.classes.add(x) : this.classes.delete(x)}; }
  querySelector(s) { return this.children[s] || null; }
  addEventListener(s, fn) { (this.listeners[s] ||= []).push(fn); }
  async emit(s, extra = {}) { for (const fn of this.listeners[s] || []) await fn({preventDefault() {}, ...extra}); }
  setAttribute(k,v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  removeAttribute(k) { delete this.attrs[k]; }
  focus() { this.focused = true; }
  closest() { return this.field; }
  setCustomValidity() {}
  setSelectionRange() {}
}
function storage(initial) { const data = new Map(Object.entries(initial)); return {data, getItem: k => data.get(k) || null, setItem: (k,v) => data.set(k,v), removeItem: k => data.delete(k)}; }
function fixture({saved = {}, local = {}, hash = '', login = false, fetch = async () => ({ok: true, json: async () => ({ok: true, redirect: '/dashboard'})})} = {}) {
  const selectors = {};
  const node = s => selectors[s] ||= new Element();
  const steps = [1,2,3,4,5].map(n => new Element({registerStep: String(n)}));
  const progress = steps.map((_, i) => { const e = new Element({registerProgress: String(i+1)}); e.children[':scope > span'] = new Element(); return e; });
  const cards = ['teacher','student'].map(role => { const e = new Element(); const radio = new Element(); radio.value = role; radio.checked = role === 'teacher'; e.children['input[name="role"]'] = radio; return e; });
  for (const s of ['.role-form','[data-name-form]','[data-email-form]','[data-password-form]','#register-name','#register-email','#register-password','#register-password-confirmation','[data-name-error]','[data-email-error]','[data-password-error]','[data-password-confirmation-error]','[data-register-success-title]','[data-register-goto]','[data-role-error]']) node(s);
  node('#register-email').field = new Element();
  node('.role-form').querySelector = () => cards.map(c => c.children['input[name="role"]']).find(r => r.checked);
  node('[data-password-form]').children['button[type="submit"]'] = new Element();
  if (login) for (const s of ['.login-form','#login-email','#login-password','[name="remember"]','[data-login-error]','[data-login-email-error]','[data-login-password-error]']) node(s);
  if (login) node('.login-form').children['button[type="submit"]'] = new Element();
  const listeners = {};
  const location = {pathname: login ? '/login' : '/register', search: '', hash, assign: url => { location.destination = url; }};
  const urls = [location.pathname + hash]; let index = 0; const calls = [];
  function apply(url) { location.hash = url.includes('#') ? url.slice(url.indexOf('#')) : ''; }
  const history = {pushState(_,__,url) { calls.push('push'); urls.splice(++index); urls.push(url); apply(url); }, replaceState(_,__,url) { calls.push('replace'); urls[index] = url; apply(url); }};
  const sessionStorage = storage({'tutorflow.registration': JSON.stringify(saved), invite: 'preserve'});
  const localStorage = storage({'tutorflow.registration': JSON.stringify(local), invite: 'preserve'});
  const context = {document: {querySelector: s => selectors[s] || null, querySelectorAll: s => ({'.role-card': cards,'[data-register-step]':steps,'[data-register-progress]':progress,'[data-password-requirement]':[],'[data-password-toggle]':[]}[s] || []), getElementById() { return null; }}, location, history, sessionStorage, localStorage, fetch, console};
  context.window = {matchMedia: () => ({matches: true, addEventListener() {}}), addEventListener: (s,f) => (listeners[s] ||= []).push(f)};
  vm.runInNewContext(fs.readFileSync(path.join(root, 'app/web/static/js', login ? 'login.js' : 'register.js'),'utf8'), context);
  return {node, steps, cards, sessionStorage, localStorage, location, calls, urls, async sync(event = 'popstate') { for (const fn of listeners[event] || []) await fn(); }, async back() { apply(urls[--index]); await this.sync(); await this.sync('hashchange'); }, async forward() { apply(urls[++index]); await this.sync(); await this.sync('hashchange'); }};
}
test('registration waits for real success, sends contract once and clears only registration state', async () => {
  let resolve; const requests = [];
  const f = fixture({fetch: (url, options) => { requests.push({url,options}); return new Promise(r => {resolve = r;}); }});
  await reachPassword(f); passwords(f);
  const request = f.node('[data-password-form]').emit('submit');
  assert.equal(active(f),4); assert.equal(requests.length,1);
  assert.equal(f.node('[data-password-form]').children['button[type="submit"]'].disabled,true);
  await f.node('[data-password-form]').emit('submit'); assert.equal(requests.length,1);
  assert.deepEqual(JSON.parse(requests[0].options.body), {first_name:'Анна',last_name:'',email:'anna@example.org',password:'Example123',password_confirmation:'Example123',role:'teacher'});
  assert.equal(requests[0].url,'/api/auth/register'); assert.equal(requests[0].options.credentials,'same-origin');
  assert.equal(requests[0].options.headers['X-TutorFlow-Request'],'auth');
  resolve({ok:true,json:async () => ({ok:true,redirect:'/dashboard'})}); await request;
  assert.equal(active(f),5); assert.equal(f.node('[data-register-success-title]').focused,true);
  assert.equal(f.node('[data-register-goto]').attrs.href,'/dashboard');
  assert.equal(f.sessionStorage.getItem('tutorflow.registration'),null);
  assert.equal(f.sessionStorage.getItem('invite'),'preserve'); assert.equal(f.node('#register-password').value,'');
  assert.equal(f.node('#register-password-confirmation').value,'');
  await f.back(); assert.equal(active(f),4);
  await f.forward(); assert.equal(active(f),5);
});
test('duplicate email routes to step 3; 422 fields route to their inputs; network stays on password alert', async () => {
  for (const [status,fields,step,selector,message] of [[409,{email:'Почта занята'},3,'[data-email-error]','Почта занята'],[422,{first_name:'Ошибка имени'},2,'[data-name-error]','Ошибка имени'],[422,{password_confirmation:'Не совпадает'},4,'[data-password-confirmation-error]','Не совпадает']]) {
    const f = fixture({fetch:async () => ({ok:false,status,json:async () => ({fields})})}); await reachPassword(f); passwords(f); await f.node('[data-password-form]').emit('submit');
    assert.equal(active(f),step); assert.equal(f.node(selector).textContent,message);
  }
  const f = fixture({fetch:async () => {throw new Error('offline');}}); await reachPassword(f); passwords(f); await f.node('[data-password-form]').emit('submit');
  assert.equal(active(f),4); assert.match(f.node('[data-password-error]').textContent,/соединение/);
  assert.equal(f.node('[data-password-form]').children['button[type="submit"]'].disabled,false);
});
test('login submits on form event, guards pending, uses remember and generic 401 then role redirect', async () => {
  let resolve; const requests = [];
  const f = fixture({login:true,fetch:(url,options) => {requests.push({url,options}); return new Promise(r => {resolve = r;});}});
  f.node('#login-email').value = 'anna@example.org'; f.node('#login-password').value = 'Example123'; f.node('[name="remember"]').checked = true;
  const request = f.node('.login-form').emit('submit'); assert.equal(requests.length,1);
  await f.node('.login-form').emit('submit'); assert.equal(requests.length,1);
  assert.deepEqual(JSON.parse(requests[0].options.body),{email:'anna@example.org',password:'Example123',remember:true});
  assert.equal(requests[0].url,'/api/auth/login'); assert.equal(requests[0].options.headers['Content-Type'],'application/json'); assert.equal(requests[0].options.credentials,'same-origin');
  resolve({ok:false,status:401,json:async () => ({detail:'secret internal account state'})}); await request;
  assert.equal(f.node('[data-login-error]').textContent,'Неверная почта или пароль'); assert.equal(f.node('[data-login-error]').hidden,false);
  assert.equal(f.node('.login-form').children['button[type="submit"]'].disabled,false);
  const retry = f.node('.login-form').emit('submit'); resolve({ok:true,json:async () => ({ok:true,redirect:'/student/homework'})}); await retry;
  assert.equal(f.location.destination,'/student/homework'); assert.equal(f.node('#login-password').value,'');
});
test('unknown hashes are replaced without adding history entries', async () => {
  const f = fixture(); f.location.hash = '#unknown'; await f.sync('hashchange');
  assert.equal(f.location.hash,''); assert.equal(active(f),1); assert.deepEqual(f.calls,['replace','replace']);
});
test('invalid password submit explains missing requirements instead of silently failing', async () => {
  const f = fixture(); await reachPassword(f); f.node('#register-password').value = 'weak';
  await f.node('[data-password-form]').emit('submit');
  assert.equal(active(f),4); assert.match(f.node('[data-password-error]').textContent,/8/);
  assert.match(f.node('[data-password-confirmation-error]').textContent,/Повторите/);
});
test('password input never writes secrets; valid refresh resumes only to password; malformed storage is safe', async () => {
  const f = fixture(); await reachPassword(f); passwords(f);
  await f.node('#register-password').emit('input'); await f.node('#register-password-confirmation').emit('input');
  const saved = JSON.parse(f.sessionStorage.getItem('tutorflow.registration'));
  assert.deepEqual(Object.keys(saved).sort(),['email','name','role','step']);
  assert.equal(JSON.stringify(saved).includes('Example123'),false);
  const refreshed = fixture({saved:{...saved,step:5},hash:'#step-5'});
  assert.equal(active(refreshed),4); assert.equal(refreshed.node('#register-password').value,'');
  for (const saved of [null,[],42,{role:{bad:true},name:123,email:[],step:'4'}]) {
    const safe = fixture({saved}); assert.equal(active(safe),1);
    assert.deepEqual(JSON.parse(safe.sessionStorage.getItem('tutorflow.registration')), {role:'teacher',name:'',email:'',step:1});
  }
});
test('login 422 field messages are text-only; network retry preserves email and re-enables submit', async () => {
  const f = fixture({login:true,fetch:async () => ({ok:false,status:422,json:async () => ({fields:{email:'Неверная почта'},detail:'Проверьте данные'})})});
  f.node('#login-email').value='anna@example.org'; f.node('#login-password').value='Example123';
  await f.node('.login-form').emit('submit'); assert.equal(f.node('[data-login-email-error]').textContent,'Неверная почта');
  assert.equal(f.node('#login-email').attrs['aria-invalid'],'true');
  await f.node('#login-email').emit('input'); assert.equal(f.node('[data-login-email-error]').hidden,true);
  const offline = fixture({login:true,fetch:async () => {throw new Error('offline');}});
  offline.node('#login-email').value='anna@example.org'; offline.node('#login-password').value='Example123';
  await offline.node('.login-form').emit('submit'); assert.match(offline.node('[data-login-error]').textContent,/соединение/);
  assert.equal(offline.node('.login-form').children['button[type="submit"]'].disabled,false);
  assert.equal(offline.node('#login-email').value,'anna@example.org');
});
function active(f) { return Number(f.steps.find(s => !s.hidden).dataset.registerStep); }
async function reachPassword(f) { await f.node('.role-form').emit('submit'); f.node('#register-name').value = 'Анна'; await f.node('[data-name-form]').emit('submit'); f.node('#register-email').value = 'anna@example.org'; await f.node('[data-email-form]').emit('submit'); }
function passwords(f) { f.node('#register-password').value = 'Example123'; f.node('#register-password-confirmation').value = 'Example123'; }
test('legacy secrets purged from both stores; typed whitelist and prerequisites prevent fake success', () => {
  const f = fixture({saved: {role: 'student', name: {bad: true}, email: 12, password: 'legacy', passwordConfirmation: 'legacy', step: 5}, local: {password: 'legacy'}, hash: '#step-5'});
  assert.equal(f.node('#register-password').value, '');
  assert.equal(active(f), 2);
  assert.equal(f.node('#register-name').value, '');
  assert.deepEqual(JSON.parse(f.sessionStorage.getItem('tutorflow.registration')), {role:'student',name:'',email:'',step:2});
  assert.equal(f.localStorage.getItem('tutorflow.registration'), null);
  assert.equal(f.localStorage.getItem('invite'), 'preserve');
});
test('forward steps push history; Back/Forward and hash synchronize without loops and focus role', async () => {
  const f = fixture(); await reachPassword(f);
  assert.equal(active(f),4); assert.deepEqual(f.calls,['replace','push','push','push']);
  await f.back(); assert.equal(active(f),3); await f.forward(); assert.equal(active(f),4);
  assert.equal(f.calls.length,4);
  f.location.hash = ''; await f.sync('hashchange'); assert.equal(active(f),1);
  assert.equal(f.cards[0].children['input[name="role"]'].focused,true);
  f.node('#register-name').value = ''; await f.node('#register-name').emit('input'); f.location.hash = '#step-4'; await f.sync('hashchange'); assert.equal(active(f),2); assert.equal(f.location.hash,'#name');
});
