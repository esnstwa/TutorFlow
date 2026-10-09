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
  document.addEventListener('click', async (event) => {
    const control = event.target.closest('[data-student-edit], [data-student-invite], [data-student-archive], [data-lifecycle-close], [data-copy-invite]');
    if (!control) return;
    const root = control.closest('[data-student-lifecycle]');
    if (!root) return;
    if (control.hasAttribute('data-lifecycle-close')) { control.closest('dialog').close(); return; }
    if (control.hasAttribute('data-student-edit')) { root.querySelector('[data-student-edit-dialog]').showModal(); return; }
    if (control.hasAttribute('data-student-archive')) { root.querySelector('[data-student-archive-dialog]').showModal(); return; }
    const error = root.querySelector('[data-lifecycle-error]');
    showError(error, '');
    control.disabled = true;
    try {
      if (control.hasAttribute('data-copy-invite')) {
        const input = root.querySelector('[data-invite-url]');
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(input.value);
        else { input.focus(); input.select(); showError(error, 'Ссылка выделена. Скопируйте её с помощью Ctrl+C.'); }
      } else {
        const result = await api(`/api/students/${root.dataset.studentId}/invite`, {});
        const link = new URL(result.invitation.url, window.location.origin);
        if (link.origin !== window.location.origin || link.pathname !== '/invite') throw new Error('Некорректная ссылка приглашения.');
        root.querySelector('[data-invite-url]').value = link.href;
        root.querySelector('[data-invite-result]').hidden = false;
        root.querySelector('[data-invite-expiry]').textContent = `Срок действия: ${new Date(result.invitation.expires_at).toLocaleString('ru-RU')}. Письмо автоматически не отправляется.`;
        control.textContent = 'Новое приглашение';
        root.querySelector('[data-invite-url]').focus();
      }
    } catch (failure) { showError(error, failure.message); }
    finally { control.disabled = false; }
  });
  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!form.matches('[data-student-edit-form], [data-student-archive-form]')) return;
    event.preventDefault();
    const root = form.closest('[data-student-lifecycle]');
    const editing = form.hasAttribute('data-student-edit-form');
    const error = form.querySelector(editing ? '[data-edit-error]' : '[data-archive-error]');
    const button = form.querySelector('[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    showError(error, '');
    try {
      const data = editing ? Object.fromEntries(new FormData(form)) : {};
      await api(`/api/students/${root.dataset.studentId}${editing ? '' : '/archive'}`, data, editing ? 'PATCH' : 'POST');
      window.location.assign(editing ? `/students/${root.dataset.studentId}` : '/students');
    } catch (failure) { showError(error, failure.message); button.disabled = false; }
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
