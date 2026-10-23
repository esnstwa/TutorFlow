const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../app/web/', name), 'utf8');
class Element {
  constructor(dataset = {}) { Object.assign(this, {dataset, listeners: {}, value: '', textContent: '', innerHTML: '', hidden: false, disabled: false, open: false, isConnected: true}); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  async emit(type, event = {}) { event.preventDefault ||= () => { event.defaultPrevented = true; }; for (const fn of this.listeners[type] || []) await fn(event); return event; }
  setAttribute(name, value) { this[name] = value; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  matches(selector) { return this.selectors?.includes(selector) || false; }
  closest(selector) { return this.matches(selector) ? this : null; }
}
const file = (name = 'Задачи №1.txt', size = 12, type = 'text/plain') => new File([new Uint8Array(size)], name, {type});
const dto = (extra = {}) => ({id: 9, title: 'Задачи', kind: 'Пособие', original_name: 'Задачи №1.txt', size: 12, mime_type: 'text/plain', has_file: true, missing_file: false, download_url: '/api/files/9/download', preview_url: '/api/files/9/preview', previewable: true, lessons: [], homeworks: [], availability: 'private', ...extra});
const response = (body, status = 200) => ({ok: status >= 200 && status < 300, status, json: async () => body});
function page({materials = [], max = 20 * 1024 * 1024} = {}) {
  const root = new Element({uploadMaxBytes: String(max)}), document = new Element(), window = new Element();
  const nodes = new Map(['materials-dialog', 'materials-form', 'materials-list', 'materials-empty', 'materials-error', 'materials-status', 'materials-submit', 'materials-file', 'materials-selected', 'materials-data'].map(key => [`[data-${key}]`, new Element()]));
  nodes.get('[data-materials-data]').textContent = JSON.stringify(materials);
  const form = nodes.get('[data-materials-form]'); form.elements = {};
  for (const name of ['title', 'kind', 'lesson_id', 'homework_id']) form.elements[name] = new Element();
  const input = nodes.get('[data-materials-file]'); input.files = [];
  form.reset = () => { Object.values(form.elements).forEach(node => node.value = ''); input.files = []; input.value = ''; };
  const controls = [...Object.values(form.elements), input, nodes.get('[data-materials-submit]'), new Element()];
  root.querySelector = selector => nodes.get(selector) || null;
  root.querySelectorAll = selector => selector === 'button, input, select' ? controls : selector === 'input, select' ? [...Object.values(form.elements), input] : [];
  document.querySelector = selector => selector === '[data-materials-root]' ? root : null;
  const requests = [], confirms = []; let answer = true;
  let respond = async url => response(url.startsWith('/api/files/upload') ? {ok: true, file: dto()} : {ok: true, material: dto()});
  window.confirm = message => { confirms.push(message); return answer; };
  vm.runInNewContext(source('static/js/materials.js'), {document, window, fetch: async (url, options = {}) => { requests.push({url, ...options}); return respond(url, options); }, URLSearchParams, File, console});
  const click = (selector, dataset = {}) => root.emit('click', {target: Object.assign(new Element(dataset), {selectors: [selector]})});
  return {root, document, window, nodes, form, input, requests, confirms, node: key => nodes.get(`[data-materials-${key}]`), click,
    open: () => click('[data-materials-open]'), submit: () => form.emit('submit'),
    async select(selected = file()) { input.files = [selected]; await root.emit('change', {target: input}); return selected; },
    respond(fn) { respond = fn; }, confirm(value) { answer = value; },
  };
}
test('pending upload is single-flight and blocks close, Escape, navigation, unload and competing delete', async () => {
  const p = page({materials: [dto()]}); await p.open(); const selected = await p.select();
  const resolves = [];
  p.respond(() => new Promise(done => { resolves.push(done); }));
  const pending = p.submit();
  try {
    const duplicate = p.submit();
    assert.equal(p.requests.length, 1);
    assert.equal(p.node('submit').disabled, true);
    await p.click('[data-materials-close]');
    const cancel = await p.node('dialog').emit('cancel');
    assert.equal(cancel.defaultPrevented, true);
    await p.click('[data-materials-delete]', {materialsDelete: '9'});
    await p.open();
    assert.equal(p.input.files[0], selected);
    assert.equal(p.node('dialog').open, true);
    assert.equal(p.requests.length, 1);
    const nav = await p.document.emit('tutorflow:before-navigate');
    assert.equal(nav.defaultPrevented, true);
    const unload = await p.window.emit('beforeunload');
    assert.equal(unload.defaultPrevented, true);
    await duplicate;
  } finally { resolves.forEach(resolve => resolve(response({detail: 'Нет места'}, 503))); await pending; }
  assert.equal(p.node('submit').disabled, false);
  assert.match(p.node('error').textContent, /Нет места.*Проверьте список/);
  assert.equal(p.input.files[0], selected);
  assert.doesNotMatch(p.node('status').textContent, /Загружен/);
});

test('dirty form asks before close or navigation, cancelled dismissal preserves selected File', async () => {
  const p = page(); await p.open(); const selected = await p.select(); p.confirm(false);
  await p.click('[data-materials-close]');
  assert.equal(p.node('dialog').open, true);
  assert.equal((await p.node('dialog').emit('cancel')).defaultPrevented, true);
  assert.equal((await p.document.emit('tutorflow:before-navigate')).defaultPrevented, true);
  assert.equal((await p.window.emit('beforeunload')).defaultPrevented, true);
  assert.equal(p.input.files[0], selected);
  p.confirm(true); await p.click('[data-materials-close]');
  assert.equal(p.node('dialog').open, false);
  assert.ok(p.confirms.length >= 3);
});

test('file picker whitelist and quota reject invalid files before network, preserving choice for correction', async () => {
  for (const selected of [file('virus.exe'), file('a.txt', 101), file('empty.txt', 0)]) {
    const p = page({max: 100}); await p.open(); await p.select(selected); await p.submit();
    assert.equal(p.requests.length, 0); assert.equal(p.input.files[0], selected);
    assert.equal(p.node('error').hidden, false); assert.equal(p.node('submit').disabled, false);
  }
  for (const name of ['a.PDF', 'a.png', 'a.jpg', 'a.jpeg', 'a.txt']) {
    const p = page(); await p.open(); const selected = await p.select(file(name));
    p.respond(async () => response({detail: 'Проверка формата на сервере'}, 415)); await p.submit();
    assert.equal(p.requests.length, 1); assert.equal(p.requests[0].body, selected);
  }
});

test('server/network/non-JSON errors keep File and form; retry uses the same binary and clears error', async () => {
  for (const fail of [async () => { throw new Error('Нет сети'); }, async () => ({ok: false, status: 503, json: async () => { throw new Error('not JSON'); }}), ...[401, 403, 404, 413, 415, 422, 503].map(status => async () => response({detail: `Ошибка ${status}`}, status))]) {
    const p = page(); await p.open(); const selected = await p.select(); p.form.elements.title.value = 'Задачи';
    p.respond(fail); await p.submit();
    assert.equal(p.input.files[0], selected); assert.equal(p.form.elements.title.value, 'Задачи');
    assert.equal(p.node('dialog').open, true); assert.equal(p.node('error').hidden, false);
    p.respond(async url => response(url.startsWith('/api/files/upload') ? {ok: true, file: dto()} : {ok: true, material: dto()}));
    await p.submit(); assert.equal(p.requests[1].body, selected);
    assert.equal(p.node('error').hidden, true); assert.equal(p.node('dialog').open, false);
  }
});

test('untrusted upload results cannot produce success, cards, or arbitrary metadata fetches', async () => {
  for (const bad of [{}, {ok: true}, {ok: true, file: dto({id: '../1'})}, {ok: true, file: dto({original_name: 'other.txt'})}, {ok: true, file: dto({size: 1})}, {ok: true, file: dto({has_file: false})}]) {
    const p = page(); await p.open(); await p.select(); p.respond(async () => response(bad)); await p.submit();
    assert.equal(p.requests.length, 1); assert.equal(p.node('dialog').open, true);
    assert.equal(p.node('list').innerHTML, ''); assert.doesNotMatch(p.node('status').textContent, /Загружен/);
    assert.equal(p.node('error').hidden, false);
  }
});

test('failed readback is honest and retry checks existing ID without uploading twice', async () => {
  const p = page(); await p.open(); const selected = await p.select();
  p.respond(async url => url.startsWith('/api/files/upload') ? response({ok: true, file: dto()}) : response({detail: 'Нет сети'}, 503));
  await p.submit();
  assert.equal(p.node('dialog').open, true); assert.equal(p.input.files[0], selected);
  assert.doesNotMatch(p.node('status').textContent, /Загружен/);
  assert.match(p.node('submit').textContent, /Проверить/);
  assert.equal(p.input.disabled, true); assert.equal(p.form.elements.title.disabled, true);
  p.confirm(false); await p.click('[data-materials-close]');
  assert.match(p.confirms.at(-1), /принят.*не проверен/);
  p.respond(async () => response({ok: true, material: dto()})); await p.submit();
  assert.equal(p.requests.length, 3); assert.equal(p.requests[2].url, '/api/materials/9');
  assert.equal(p.node('dialog').open, false);
});

test('readback must match saved ID, original filename and size; stale detached responses never change UI', async () => {
  for (const bad of [dto({id: 10}), dto({original_name: 'other.txt'}), dto({size: 2}), dto({missing_file: true})]) {
    const p = page(); await p.open(); await p.select();
    p.respond(async url => response(url.startsWith('/api/files/upload') ? {ok: true, file: dto()} : {ok: true, material: bad}));
    await p.submit(); assert.equal(p.node('dialog').open, true); assert.equal(p.node('list').innerHTML, '');
  }
  const p = page(); await p.open(); await p.select(); let resolve;
  p.respond(() => new Promise(done => { resolve = done; })); const pending = p.submit();
  p.root.isConnected = false; resolve(response({ok: true, file: dto()})); await pending;
  assert.equal(p.node('list').innerHTML, ''); assert.equal(p.node('status').textContent, '');
  assert.equal(p.requests.length, 1);
});

test('saved cards expose only checked local download/preview and owned relationships; no PDF inline preview', () => {
  const p = page({materials: [dto({title: '<img onerror=1>', lessons: [{id: 3, topic: 'Дроби', student_name: 'Анна', date: '2035-01-01', url: 'javascript:alert(1)'}], homeworks: [{id: 4, title: 'Повторить', url: 'https://evil.invalid'}], availability: 'shared'}), dto({id: 10, mime_type: 'application/pdf', preview_url: '/api/files/10/preview', previewable: true, download_url: '/api/files/10/download'}), dto({id: 11, download_url: 'javascript:alert(1)', preview_url: 'https://evil.invalid'})]});
  const html = p.node('list').innerHTML;
  assert.match(html, /&lt;img onerror=1&gt;/); assert.doesNotMatch(html, /<img/);
  assert.match(html, /href="\/api\/files\/9\/download"/); assert.match(html, /href="\/api\/files\/9\/preview"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /href="\/api\/files\/10\/preview"|javascript:|evil\.invalid|<iframe|<object/);
  assert.match(html, /href="\/lessons\/3"/); assert.match(html, /href="\/assignments\/4"/);
  assert.match(html, /Анна/); assert.match(html, /Доступен ученикам/); assert.match(html, /Только вам/);
  assert.match(html, /text\/plain/); assert.match(html, /12 байт/);
});

test('metadata-only and lost files have explicit honest states, without download or preview actions', () => {
  for (const item of [dto({has_file: false, stored_name: null, url: 'javascript:alert(1)', download_url: null, preview_url: null}), dto({missing_file: true})]) {
    const p = page({materials: [item]}); const html = p.node('list').innerHTML;
    assert.match(html, item.missing_file ? /Файл недоступен/ : /Запись\/ссылка — файл не загружен/);
    assert.doesNotMatch(html, /href="\/api\/files|javascript:/);
  }
});

test('confirmed deletion removes the record only after 404 readback and warns about relationships', async () => {
  const p = page({materials: [dto({lessons: [{id: 3, topic: 'Дроби'}]})]}); p.confirm(false);
  await p.click('[data-materials-delete]', {materialsDelete: '9'}); assert.equal(p.requests.length, 0);
  p.confirm(true); p.respond(async (url, options) => options.method === 'DELETE' ? response({ok: true}) : response({detail: 'Не найден'}, 404));
  await p.click('[data-materials-delete]', {materialsDelete: '9'});
  assert.equal(p.requests[0].url, '/api/materials/9'); assert.equal(p.requests[0].method, 'DELETE');
  assert.equal(p.requests[1].url, '/api/materials/9'); assert.equal(p.node('list').innerHTML, '');
  assert.match(p.confirms[0], /занятий|заданий/); assert.match(p.node('status').textContent, /удалён/);
});

test('pending delete blocks duplicate delete, upload, navigation; failure keeps card and restores controls', async () => {
  const p = page({materials: [dto()]}); const resolves = [];
  p.respond(() => new Promise(done => resolves.push(done)));
  const pending = p.click('[data-materials-delete]', {materialsDelete: '9'});
  try {
    const duplicate = p.click('[data-materials-delete]', {materialsDelete: '9'});
    assert.equal(p.requests.length, 1); await duplicate; await p.open(); await p.submit();
    assert.equal(p.node('dialog').open, false); assert.equal(p.requests.length, 1);
    assert.equal((await p.document.emit('tutorflow:before-navigate')).defaultPrevented, true);
  } finally { resolves.forEach(resolve => resolve(response({detail: 'Удаление запрещено'}, 403))); await pending; }
  assert.match(p.node('list').innerHTML, /Задачи/); assert.match(p.node('status').textContent, /Удаление запрещено/);
  assert.equal(p.node('submit').disabled, false);
});

test('lost DELETE acknowledgement keeps the card and asks to refresh the list before retrying', async () => {
  const p = page({materials: [dto()]});
  const originalCard = p.node('list').innerHTML;
  p.respond(async () => { throw new Error('Нет сети'); });
  await p.click('[data-materials-delete]', {materialsDelete: '9'});
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].method, 'DELETE');
  assert.equal(p.node('list').innerHTML, originalCard);
  assert.match(p.node('status').textContent, /Нет сети.*Обновите страницу.*проверьте список.*перед повтором/);
  assert.doesNotMatch(p.node('status').textContent, /Материал удалён/);
  assert.equal(p.node('submit').disabled, false);
  assert.equal(p.root['aria-busy'], 'false');
});

test('accepted delete without verified absence never claims success or hides card', async () => {
  const p = page({materials: [dto()]}); p.respond(async (url, options) => response(options.method === 'DELETE' ? {ok: true} : {ok: true, material: dto()}));
  await p.click('[data-materials-delete]', {materialsDelete: '9'});
  assert.match(p.node('list').innerHTML, /Задачи/); assert.doesNotMatch(p.node('status').textContent, /Материал удалён/);
  assert.match(p.node('status').textContent, /не подтверждено/);
});

test('teacher page has native upload, SSR cards and owned audience choices; assets use static_version', () => {
  const html = source('templates/pages/materials.html'), layout = source('templates/teacher_layout.html');
  assert.match(html, /type="file"[^>]*accept="\.pdf,\.png,\.jpg,\.jpeg,\.txt"/);
  assert.match(html, /material_upload_max_bytes/); assert.match(html, /material_lessons/); assert.match(html, /material_homeworks/);
  assert.match(html, /name="lesson_id"/); assert.match(html, /name="homework_id"/);
  assert.match(html, /ученикам выбранного занятия/); assert.match(html, /получателям выбранного задания/);
  assert.match(html, /{% for item in materials %}/); assert.match(html, /Запись\/ссылка — файл не загружен/); assert.match(html, /Файл недоступен/);
  assert.doesNotMatch(html, /href="{{ item\.(?:url|path|download_url|preview_url)/);
  assert.match(layout, /static_version\('css\/materials\.css'\)/); assert.match(layout, /static_version\('js\/materials\.js'\)/);
  assert.doesNotMatch(source('static/js/dashboard.js'), /material: \{|type === "material"/);
});

test('materials CSS is page scoped and mobile controls remain readable with single-column layout', () => {
  const css = source('static/css/materials.css');
  assert.match(css, /@media \(max-width: 640px\)/); assert.match(css, /grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(css, /input\[type="file"\]/); assert.match(css, /min-width: 0/); assert.match(css, /overflow-wrap: anywhere/);
  const selectors = css.replace(/\/\*[\s\S]*?\*\//g, '').match(/[^{}]+(?=\{)/g).map(s => s.trim()).filter(s => !s.startsWith('@'));
  assert.ok(selectors.every(s => s.split(',').every(part => part.trim().startsWith('.materials-page'))), selectors.join('\n'));
});

test('a new attempt clears earlier success and exposes only the current failure', async () => {
  const p = page(); await p.open(); await p.select(); await p.submit();
  assert.match(p.node('status').textContent, /Загружен/);
  await p.open(); await p.select(); p.respond(async () => response({detail: 'Нет места'}, 503)); await p.submit();
  assert.doesNotMatch(p.node('status').textContent, /Загружен/);
  assert.match(p.node('error').textContent, /Нет места.*Проверьте список/);
});

test('readback remains single-flight, guards navigation, and locks saved input until verification', async () => {
  const p = page(); await p.open(); await p.select(); const resolves = [];
  p.respond(async url => url.startsWith('/api/files/upload') ? response({ok: true, file: dto()}) : new Promise(done => resolves.push(done)));
  const pending = p.submit();
  try {
    for (let turn = 0; !resolves.length && turn < 10; turn++) await new Promise(done => setImmediate(done));
    assert.equal(resolves.length, 1);
    const duplicate = p.submit(); assert.equal(p.requests.length, 2); await duplicate;
    assert.equal((await p.document.emit('tutorflow:before-navigate')).defaultPrevented, true);
    assert.equal(p.node('dialog').open, true); assert.doesNotMatch(p.node('status').textContent, /Загружен/);
  } finally { resolves.forEach(resolve => resolve(response({ok: true, material: dto()}))); await pending; }
  assert.equal(p.node('dialog').open, false);
});

test('reinitializing the same SPA page never registers duplicate listeners or upload requests', async () => {
  const p = page(); await p.document.emit('tutorflow:navigated'); await p.document.emit('tutorflow:navigated');
  await p.open(); await p.select(); await p.submit(); assert.equal(p.requests.length, 2);
});

test('uploads the actual File with Unicode headers, then independently reads saved metadata before success', async () => {
  const p = page(); await p.open(); const selected = await p.select();
  p.form.elements.title.value = 'Задачи'; p.form.elements.kind.value = 'Пособие';
  p.form.elements.lesson_id.value = '3'; p.form.elements.homework_id.value = '4';
  await p.submit();
  assert.equal(p.requests[0].url, '/api/files/upload?lesson_id=3&homework_id=4');
  assert.equal(p.requests[0].body, selected);
  assert.equal(p.requests[0].method, 'POST');
  assert.deepEqual({...p.requests[0].headers}, {'Content-Type': 'text/plain', 'X-Filename': encodeURIComponent(selected.name), 'X-Title': encodeURIComponent('Задачи'), 'X-File-Kind': encodeURIComponent('Пособие')});
  assert.equal(p.requests[1].url, '/api/materials/9');
  assert.equal(p.node('dialog').open, false);
  assert.match(p.node('status').textContent, /Загружен/);
  assert.match(p.node('list').innerHTML, /Задачи/);
});

test('native Escape is intercepted before the browser close watcher while upload is pending', async () => {
  const p = page(); await p.open(); await p.select(); let resolve;
  p.respond(() => new Promise(done => { resolve = done; }));
  const pending = p.submit();
  try {
    let stopped = false;
    const event = await p.document.emit('keydown', {key: 'Escape', stopImmediatePropagation() { stopped = true; }});
    assert.equal(event.defaultPrevented, true);
    assert.equal(stopped, true);
    assert.equal(p.node('dialog').open, true);
    assert.equal(p.requests.length, 1);
  } finally { resolve(response({detail: 'Отмена проверки'}, 422)); await pending; }
});

test('native Escape honors rejected dirty confirmation instead of relying on cancel.cancelable', async () => {
  const p = page(); await p.open(); const selected = await p.select(); p.confirm(false);
  const event = await p.document.emit('keydown', {key: 'Escape', stopImmediatePropagation() {}});
  assert.equal(event.defaultPrevented, true);
  assert.equal(p.node('dialog').open, true);
  assert.equal(p.input.files[0], selected);
  p.confirm(true); await p.document.emit('keydown', {key: 'Escape', stopImmediatePropagation() {}});
  assert.equal(p.node('dialog').open, false);
});

test('blank optional metadata is omitted so backend defaults remain valid', async () => {
  const p = page(); await p.open(); await p.select(); await p.submit();
  assert.equal(Object.hasOwn(p.requests[0].headers, 'X-Title'), false);
  assert.equal(Object.hasOwn(p.requests[0].headers, 'X-File-Kind'), false);
  assert.equal(p.node('dialog').open, false);
});

test('deferred physical cleanup is reported honestly after confirmed logical deletion', async () => {
  const p = page({materials: [dto()]});
  p.respond(async (url, options) => options.method === 'DELETE' ? response({ok: true, cleanup_pending: true}) : response({detail: 'Не найден'}, 404));
  await p.click('[data-materials-delete]', {materialsDelete: '9'});
  assert.equal(p.node('list').innerHTML, '');
  assert.match(p.node('status').textContent, /очистка.*отложена|сверк/);
});

test('ambiguous upload failure warns and requires consent before another POST', async () => {
  const p = page(); await p.open(); const selected = await p.select();
  p.respond(async () => { throw new Error('Ответ потерян'); });
  await p.submit();
  assert.match(p.node('error').textContent, /Проверьте список/);
  p.confirm(false); await p.submit();
  assert.equal(p.requests.length, 1);
  assert.equal(p.input.files[0], selected);
  p.confirm(true);
  p.respond(async url => response(url.startsWith('/api/files/upload') ? {ok: true, file: dto()} : {ok: true, material: dto()}));
  await p.submit();
  assert.equal(p.requests.length, 3);
  assert.equal(p.node('dialog').open, false);
});
