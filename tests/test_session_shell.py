from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'app' / 'web'


def test_session_shell_supplies_csrf_and_runs_guard_before_page_scripts():
    text = (WEB / 'templates' / 'base.html').read_text(encoding='utf-8')
    assert 'name="csrf-token"' in text
    assert '/js/session.js' in text
    assert text.index('/js/session.js') < text.index('{% block scripts %}')
    for layout in ('teacher_layout.html', 'student_layout.html'):
        text = (WEB / 'templates' / layout).read_text(encoding='utf-8')
        assert 'name="csrf_token"' in text
        assert "url_for('auth_logout')" in text


def test_teacher_student_profile_has_real_lifecycle_controls():
    text = (WEB / 'templates' / 'pages' / 'student_profile.html').read_text(encoding='utf-8')
    assert 'data-student-edit' in text
    assert 'data-student-invite' in text
    assert 'data-student-archive' in text
    assert 'student.lifecycle_label' in text
    assert 'Учебная история сохранится' in text


def test_unlinked_student_has_invitation_onboarding_without_fake_history():
    path = WEB / 'templates' / 'pages' / 'student_unlinked.html'
    assert path.exists()
    text = path.read_text(encoding='utf-8')
    assert 'приглашение' in text.lower()
    assert 'get_current_student' not in text
    assert 'student_layout.html' in text


def test_invitation_hidden_controls_override_component_display():
    text = (WEB / 'templates' / 'pages' / 'invite.html').read_text(encoding='utf-8')
    assert '[data-invitation-page] [hidden]' in text
    assert 'display: none !important' in text


def test_invitation_requires_explicit_accept_and_does_not_put_token_in_query():
    path = WEB / 'static' / 'js' / 'student-lifecycle.js'
    assert path.exists()
    text = path.read_text(encoding='utf-8')
    assert '/api/student/invitations/accept' in text
    assert 'data-invite-accept' in text
    assert '?token=' not in text
    assert 'textContent' in text
