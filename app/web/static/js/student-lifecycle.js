(() => {
  'use strict';
  if (window.tutorflowLifecycleInstalled) return;
  window.tutorflowLifecycleInstalled = true;
  const INVITE_KEY = 'tutorflow.pendingInvitation';
  const showError = (node, message) => {
    if (!node) return;
    node.textContent = message || '';
    node.hidden = !message;
  };
  const api = async (url, data, method = 'POST') => {
    const response = await fetch(url, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const failure = new Error(typeof result.detail === 'string' ? result.detail : result.error || 'Не удалось выполнить действие. Проверьте данные и повторите.');
      failure.status = response.status;
      throw failure;
    }
    return result;
  };
  // Teacher mutations share one lock; the invitation page below is independent.
  let teacherPending = null;
  const lockTeacher = (root) => {
    teacherPending = root;
    const controls = Array.from(root.querySelectorAll('button, input, select, textarea')).filter(node => !node.hasAttribute('data-invite-url')).map(node => [node, node.disabled]);
    controls.forEach(([node]) => { node.disabled = true; });
    root.setAttribute('aria-busy', 'true');
    return () => {
      teacherPending = null;
      if (!root.isConnected) return;
      controls.forEach(([node, disabled]) => { node.disabled = disabled; });
      root.removeAttribute('aria-busy');
    };
  };
  const teacherStudent = (result, root, archived) => {
    const student = result?.student;
    if (result?.ok !== true || !student || String(student.id) !== root.dataset.studentId || student.archived !== archived || !['linked', 'invited', 'unlinked'].includes(student.lifecycle) || typeof student.lifecycle_label !== 'string' || !student.lifecycle_label.trim()) {
      throw new Error('Сервер не подтвердил изменение ученика. Обновите карточку и проверьте данные.');
    }
    return student;
  };
  document.addEventListener('tutorflow:before-navigate', event => {
    if (teacherPending) event.preventDefault();
  });
  document.addEventListener('cancel', event => {
    if (teacherPending && event.target.closest('[data-student-lifecycle]')) event.preventDefault();
  }, true);
  document.addEventListener('keydown', event => {
    if (teacherPending && event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener('click', async (event) => {
    if (teacherPending && event.target.closest('[data-student-lifecycle], [data-open-modal]')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    const control = event.target.closest('[data-student-edit], [data-student-invite], [data-student-archive], [data-student-restore], [data-lifecycle-close], [data-copy-invite]');
    if (!control) return;
    const root = control.closest('[data-student-lifecycle]');
    if (!root || !root.isConnected) return;
    if (root.dataset.archived === 'true' && !control.hasAttribute('data-student-restore') && !control.hasAttribute('data-lifecycle-close')) {
      showError(root.querySelector('[data-lifecycle-error]'), 'Ученик в архиве. Сначала восстановите карточку.');
      return;
    }
    if (control.hasAttribute('data-student-invite')) {
      const reason = root.dataset.lifecycle === 'linked' ? 'Аккаунт ученика уже привязан.' : !root.dataset.email?.trim() ? 'Чтобы пригласить ученика, укажите почту в карточке.' : '';
      if (reason) { showError(root.querySelector('[data-lifecycle-error]'), reason); return; }
      if (root.dataset.lifecycle === 'invited' && !window.confirm('Перевыпустить приглашение? Предыдущая ссылка станет недействительной. Передайте ученику новую ссылку.')) return;
    }
    if (control.disabled) return;
    if (control.hasAttribute('data-lifecycle-close')) { control.closest('dialog').close(); return; }
    if (control.hasAttribute('data-student-edit')) { root.querySelector('[data-student-edit-dialog]').showModal(); return; }
    if (control.hasAttribute('data-student-archive')) { root.querySelector('[data-student-archive-dialog]').showModal(); return; }
    const error = root.querySelector('[data-lifecycle-error]');
    showError(error, '');
    const unlock = lockTeacher(root);
    try {
      if (control.hasAttribute('data-student-restore')) {
        const result = await api(`/api/students/${root.dataset.studentId}/restore`, {});
        if (!root.isConnected) return;
        teacherStudent(result, root, false);
        window.location.assign(`/students/${root.dataset.studentId}`);
      } else if (control.hasAttribute('data-copy-invite')) {
        const input = root.querySelector('[data-invite-url]');
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(input.value);
        else { input.focus(); input.select(); showError(error, 'Ссылка выделена. Скопируйте её с помощью Ctrl+C.'); }
      } else {
        root.querySelector('[data-invite-result]').hidden = true;
        root.querySelector('[data-invite-url]').value = '';
        root.querySelector('[data-invite-expiry]').textContent = '';
        const result = await api(`/api/students/${root.dataset.studentId}/invite`, {});
        if (!root.isConnected) return;
        const student = teacherStudent(result, root, false);
        const invitation = result.invitation;
        if (student.lifecycle !== 'invited' || typeof invitation?.url !== 'string' || typeof invitation.expires_at !== 'string') throw new Error('Сервер не подтвердил приглашение. Обновите карточку.');
        const link = new URL(invitation.url, window.location.origin);
        const expiry = Date.parse(invitation.expires_at);
        if (link.origin !== window.location.origin || link.pathname !== '/invite' || link.search || link.username || link.password || !/^#[A-Za-z0-9_-]{32,128}$/.test(link.hash) || !Number.isFinite(expiry) || expiry <= Date.now()) throw new Error('Некорректная ссылка или срок приглашения. Обновите карточку.');
        root.querySelector('[data-invite-url]').value = link.href;
        root.querySelector('[data-invite-result]').hidden = false;
        root.querySelector('[data-invite-expiry]').textContent = `Срок действия: ${new Date(expiry).toLocaleString('ru-RU')}. Письмо автоматически не отправляется.`;
        root.dataset.lifecycle = student.lifecycle;
        root.querySelector('[data-student-lifecycle-label]').textContent = student.lifecycle_label;
        control.textContent = 'Перевыпустить приглашение';
        root.querySelector('[data-invite-url]').focus();
      }
    } catch (failure) {
      if (root.isConnected) showError(error, failure.message + (control.hasAttribute('data-student-invite') ? ' При повторном приглашении предыдущая ссылка могла быть отменена. Обновите карточку перед повтором.' : ''));
    }
    finally { unlock(); }
  }, true);
  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!form.matches('[data-student-edit-form], [data-student-archive-form]')) return;
    event.preventDefault();
    if (teacherPending) return;
    const root = form.closest('[data-student-lifecycle]');
    if (!root || !root.isConnected || root.dataset.archived === 'true') return;
    const editing = form.hasAttribute('data-student-edit-form');
    const error = form.querySelector(editing ? '[data-edit-error]' : '[data-archive-error]');
    const button = form.querySelector('[type="submit"]');
    if (button.disabled) return;
    const data = editing ? Object.fromEntries(Array.from(new FormData(form)).filter(([name]) => ['name', 'email', 'subject', 'grade', 'avatar'].includes(name))) : {};
    const unlock = lockTeacher(root);
    showError(error, '');
    try {
      const result = await api(`/api/students/${root.dataset.studentId}${editing ? '' : '/archive'}`, data, editing ? 'PATCH' : 'POST');
      if (!root.isConnected) return;
      teacherStudent(result, root, !editing);
      window.location.assign(`/students/${root.dataset.studentId}`);
    } catch (failure) { if (root.isConnected) showError(error, failure.message); }
    finally { unlock(); }
  });
  const invitation = document.querySelector('[data-invitation-page]');
  if (!invitation) {
    if (window.location.pathname === '/student/homework' && new URLSearchParams(window.location.search).get('skip_invitation') !== '1') {
      try {
        const pending = sessionStorage.getItem(INVITE_KEY);
        if (pending && /^[A-Za-z0-9_-]{32,128}$/.test(pending)) window.location.replace('/invite');
      } catch (_) { /* Storage may be disabled; the original invitation link still works. */ }
    }
    return;
  }
  const error = invitation.querySelector('[data-invite-error]');
  const description = invitation.querySelector('[data-invite-description]');
  const accept = invitation.querySelector('[data-invite-accept]');
  const discard = invitation.querySelector('[data-invite-discard]');
  let token = '';
  let role = '';
  const clearPending = () => {
    token = '';
    try { sessionStorage.removeItem(INVITE_KEY); return true; }
    catch (_) { return false; }
  };
  discard.hidden = false;
  discard.addEventListener('click', () => {
    const cleared = clearPending();
    accept.disabled = true;
    const destination = role === 'teacher' ? '/dashboard' : role === 'student' ? '/student/homework' : '/login';
    window.location.assign(destination + (destination === '/student/homework' && !cleared ? '?skip_invitation=1' : ''));
  });
  try {
    const fragment = window.location.hash.slice(1);
    if (fragment) {
      if (!/^[A-Za-z0-9_-]{32,128}$/.test(fragment)) throw new Error('Некорректная ссылка приглашения.');
      token = fragment;
      sessionStorage.setItem(INVITE_KEY, token);
      history.replaceState(null, '', '/invite');
    } else { token = sessionStorage.getItem(INVITE_KEY) || ''; }
  } catch (failure) { showError(error, failure.message); }
  if (!token) { description.textContent = 'Откройте полную ссылку, полученную от преподавателя.'; return; }
  (async () => {
    try {
      const response = await fetch('/api/auth/me', {credentials: 'same-origin'});
      if (response.status === 401) {
        description.textContent = 'Для подтверждения приглашения войдите или создайте аккаунт ученика.';
        invitation.querySelector('[data-invite-auth]').hidden = false;
        return;
      }
      if (!response.ok) throw new Error('Не удалось проверить сессию. Попробуйте войти заново.');
      const session = await response.json();
      role = session.user.role;
      if (role !== 'student') throw new Error('Приглашение предназначено для аккаунта ученика. Выйдите из аккаунта преподавателя и войдите как ученик.');
      document.querySelector('meta[name="csrf-token"]').content = session.csrf_token;
      const result = await api('/api/student/invitations/preview', {token});
      const info = result.invitation || result;
      description.textContent = `Приглашение для ${info.student_name || info.student?.name || 'ученика'} от преподавателя ${result.teacher?.name || 'TutorFlow'}. Проверьте данные и подтвердите привязку.`;
      accept.hidden = false;
    } catch (failure) {
      if ([400, 403, 404, 410, 422].includes(failure.status)) clearPending();
      description.textContent = 'Приглашение не подтверждено.';
      showError(error, failure.message);
    }
  })();
  accept.addEventListener('click', async () => {
    if (accept.disabled) return;
    accept.disabled = true;
    showError(error, '');
    try {
      await api('/api/student/invitations/accept', {token});
    } catch (failure) {
      const fatal = [400, 403, 404, 410, 422].includes(failure.status);
      if (fatal) { clearPending(); accept.hidden = true; }
      showError(error, failure.message);
      accept.disabled = fatal;
      return;
    }
    // Acceptance is already committed; storage failure must not turn it into a retry.
    const cleared = clearPending();
    window.location.assign(cleared ? '/student/homework' : '/student/homework?skip_invitation=1');
  });
})();
