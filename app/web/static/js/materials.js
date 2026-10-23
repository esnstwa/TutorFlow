(() => {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const validId = id => Number.isSafeInteger(id) && id > 0;
  const matchesFile = (item, file) => item && validId(item.id) && item.original_name === file.name && item.size === file.size && item.has_file === true && !item.missing_file;
  const related = (items, type) => (Array.isArray(items) ? items : []).filter(item => validId(item.id)).map(item => `<a href="/${type}/${item.id}" data-spa>${escape(type === 'lessons' ? [item.topic || 'Занятие', item.date, item.student_name].filter(Boolean).join(' · ') : item.title || 'Задание')}</a>`).join('');
  const card = item => {
    const available = item.has_file === true && !item.missing_file;
    const download = available && item.download_url === `/api/files/${item.id}/download`;
    const preview = available && item.previewable === true && ['image/png', 'image/jpeg', 'text/plain'].includes(item.mime_type) && item.preview_url === `/api/files/${item.id}/preview`;
    return `<article class="materials-card" data-material-id="${item.id}">
      <div class="materials-card-top"><span class="materials-file-icon" aria-hidden="true">${escape(item.mime_type === 'application/pdf' ? 'PDF' : available ? 'Файл' : 'Запись')}</span><span class="materials-access${item.availability === 'shared' ? ' is-shared' : ''}">${item.availability === 'shared' ? 'Доступен ученикам' : 'Только вам'}</span></div>
      <h3>${escape(item.title || item.original_name || 'Материал')}</h3>
      <p class="materials-meta">${escape(item.kind || 'Материал')} · ${escape(item.mime_type || 'Без файла')}${Number.isSafeInteger(item.size) && item.size >= 0 ? ` · ${item.size} байт` : ''}</p>
      ${available ? `<p class="materials-filename">${escape(item.original_name)}</p>` : `<p class="materials-file-warning">${item.missing_file ? 'Файл недоступен — содержимое отсутствует в хранилище' : 'Запись/ссылка — файл не загружен'}</p>`}
      ${item.description ? `<p class="materials-description">${escape(item.description)}</p>` : ''}
      <div class="materials-relations">${related(item.lessons, 'lessons')}${related(item.homeworks, 'assignments')}</div>
      <div class="materials-actions">${download ? `<a class="dashboard-secondary" href="/api/files/${item.id}/download" download>Скачать</a>` : ''}${preview ? `<a class="dashboard-secondary" href="/api/files/${item.id}/preview" target="_blank" rel="noopener noreferrer">Просмотр</a>` : ''}<button class="materials-delete" type="button" data-materials-delete="${item.id}" aria-label="Удалить ${escape(item.title || 'материал')}">Удалить</button></div>
    </article>`;
  };
  let active = null;
  document.addEventListener('tutorflow:before-navigate', event => {
    if (active && !active.canLeave()) event.preventDefault();
  });
  window.addEventListener('beforeunload', event => {
    if (active?.needsGuard()) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') active?.handleEscape(event);
  }, true);
  function init() {
    const root = document.querySelector('[data-materials-root]');
    if (!root || root.materialsInstalled) return;
    root.materialsInstalled = true;
    const node = name => root.querySelector(`[data-materials-${name}]`);
    const form = node('form'), dialog = node('dialog');
    let pending = false, checkRecord = null, uncertainUpload = false;
    const limit = Number(root.dataset.uploadMaxBytes) > 0 ? Number(root.dataset.uploadMaxBytes) : 20 * 1024 * 1024;
    const dirty = () => dialog.open && (node('file').files.length > 0 || ['title', 'kind', 'lesson_id', 'homework_id'].some(key => form.elements[key].value));
    const canLeave = () => !root.isConnected || (!pending && (!dirty() || window.confirm(checkRecord ? 'Файл принят сервером, но ещё не проверен. Закрыть форму? Проверьте список перед новой загрузкой.' : uncertainUpload ? 'Загрузка могла сохраниться. Закрыть форму? Проверьте список перед новой загрузкой.' : 'Не сохранять выбранный файл и закрыть форму?')));
    active = {canLeave, needsGuard: () => root.isConnected && (pending || dirty()), handleEscape: event => {
      if (!root.isConnected || !dialog.open) return;
      // Native close watchers can emit a non-cancelable dialog cancel event.
      event.preventDefault(); event.stopImmediatePropagation(); close();
    }};
    const setPending = value => {
      pending = value;
      root.setAttribute('aria-busy', String(value));
      root.querySelectorAll('button, input, select').forEach(control => { control.disabled = value; });
      if (checkRecord) root.querySelectorAll('input, select').forEach(control => { control.disabled = true; });
      node('submit').textContent = value ? 'Загружаем и проверяем…' : checkRecord ? 'Проверить сохранение' : 'Загрузить файл';
    };
    const close = () => { if (canLeave()) { dialog.close(); form.reset(); checkRecord = null; uncertainUpload = false; setPending(false); } };
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    let rows;
    try { const data = JSON.parse(node('data').textContent); rows = Array.isArray(data) ? data.filter(item => item && validId(item.id)) : []; } catch { rows = []; }
    const render = () => {
      node('list').innerHTML = rows.map(card).join('');
      node('empty').hidden = rows.length > 0;
    };
    root.addEventListener('click', async event => {
      if (pending) return;
      if (event.target.closest('[data-materials-open]')) {
        if (!dialog.open) { form.reset(); checkRecord = null; node('error').hidden = true; node('selected').textContent = 'Файл не выбран'; setPending(false); dialog.showModal(); node('file').focus(); }
        return;
      }
      if (event.target.closest('[data-materials-close]') || event.target === dialog) { close(); return; }
      const trigger = event.target.closest('[data-materials-delete]');
      if (!trigger || dialog.open) return;
      const id = Number(trigger.dataset.materialsDelete), item = rows.find(row => row.id === id);
      if (!item || !window.confirm(`Удалить «${item.title || item.original_name || 'Материал'}» и его содержимое?${item.lessons?.length || item.homeworks?.length ? ' Материал также исчезнет из связанных занятий и заданий.' : ''}`)) return;
      setPending(true); node('status').textContent = 'Удаляем и проверяем…';
      let deleteResponseReceived = false;
      try {
        const response = await fetch(`/api/materials/${id}`, {method: 'DELETE'});
        deleteResponseReceived = true;
        const result = await response.json().catch(() => null);
        if (!root.isConnected) return;
        if (!response.ok || result?.ok !== true) throw new Error(typeof result?.detail === 'string' ? result.detail : 'Не удалось удалить материал');
        const verify = await fetch(`/api/materials/${id}`, {cache: 'no-store'});
        if (!root.isConnected) return;
        if (verify.status !== 404) throw new Error('Удаление не подтверждено. Обновите страницу и проверьте список.');
        rows = rows.filter(row => row.id !== id); render(); node('status').textContent = result.cleanup_pending === true ? 'Материал удалён из списка; физическая очистка отложена и требует сверки хранилища.' : 'Материал удалён';
      } catch (error) { if (root.isConnected) node('status').textContent = error.message + (!deleteResponseReceived ? ' Обновите страницу и проверьте список материалов перед повтором удаления.' : ''); }
      finally { if (root.isConnected) setPending(false); }
    });
    root.addEventListener('change', event => {
      if (event.target === node('file') && !pending) {
        const file = node('file').files[0];
        node('selected').textContent = file ? `${file.name} · ${file.size} байт` : 'Файл не выбран';
      }
    });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (pending) return;
      if (!checkRecord && uncertainUpload && !window.confirm('Предыдущая загрузка могла сохраниться. Проверьте список материалов перед новой отправкой. Всё равно повторить?')) return;
      setPending(true);
      node('status').textContent = '';
      node('error').hidden = true;
      const file = node('file').files[0];
      const params = new URLSearchParams();
      for (const key of ['lesson_id', 'homework_id']) if (form.elements[key].value) params.set(key, form.elements[key].value);
      try {
        if (!checkRecord) {
          if (!(file instanceof File)) throw new Error('Выберите файл');
          if (!/\.(pdf|png|jpe?g|txt)$/i.test(file.name)) throw new Error('Допустимы только PDF, PNG, JPEG и TXT (UTF-8)');
          if (file.size < 1 || file.size > limit) throw new Error(`Размер файла должен быть от 1 до ${limit} байт`);
          if (form.elements.title.value.trim().length > 200 || form.elements.kind.value.trim().length > 80) throw new Error('Название — до 200 символов, тип материала — до 80');
          const headers = {'Content-Type': file.type || 'application/octet-stream', 'X-Filename': encodeURIComponent(file.name)};
          if (form.elements.title.value.trim()) headers['X-Title'] = encodeURIComponent(form.elements.title.value.trim());
          if (form.elements.kind.value.trim()) headers['X-File-Kind'] = encodeURIComponent(form.elements.kind.value.trim());
          uncertainUpload = true;
          const response = await fetch('/api/files/upload' + (params.size ? `?${params}` : ''), {method: 'POST', headers, body: file});
          const result = await response.json().catch(() => null);
          if (!root.isConnected) return;
          if (!response.ok) {
            if (response.status < 500) uncertainUpload = false;
            throw new Error(typeof result?.detail === 'string' ? result.detail : `Не удалось загрузить файл (HTTP ${response.status})`);
          }
          if (result?.ok !== true || !matchesFile(result.file, file)) throw new Error('Сервер не подтвердил файл. Проверьте список материалов перед повторной загрузкой.');
          checkRecord = result.file;
          uncertainUpload = false;
        }
        const savedResponse = await fetch(`/api/materials/${checkRecord.id}`, {cache: 'no-store'});
        const saved = await savedResponse.json().catch(() => null);
        if (!root.isConnected) return;
        if (!savedResponse.ok || saved?.ok !== true || !matchesFile(saved.material, file) || saved.material.id !== checkRecord.id) throw new Error('Файл принят сервером, но сохранение не проверено. Нажмите «Проверить сохранение» — повторной загрузки не будет.');
        rows = rows.filter(item => item.id !== saved.material.id); rows.unshift(saved.material);
        checkRecord = null; render(); dialog.close(); form.reset();
        node('status').textContent = `Загружен: ${saved.material.title || saved.material.original_name}`;
      } catch (error) { if (root.isConnected) { node('error').textContent = error.message + (uncertainUpload ? ' Проверьте список материалов перед повторной загрузкой.' : ''); node('error').hidden = false; } }
      finally { if (root.isConnected) setPending(false); }
    });
    render();
  }
  document.addEventListener('tutorflow:navigated', init);
  init();
})();
