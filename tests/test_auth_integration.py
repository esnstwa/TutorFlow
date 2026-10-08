from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings


@pytest.fixture
def session_client(monkeypatch):
    monkeypatch.setattr(settings, 'app_env', 'test')
    with TestClient(app) as client:
        yield client


def register(client, role='student'):
    response = client.post('/api/auth/register', headers={'X-TutorFlow-Request': 'auth'}, json={
        'first_name': 'Кирилл', 'email': f'integration-{uuid4().hex}@example.com',
        'password': 'Integration-Test-493!', 'password_confirmation': 'Integration-Test-493!',
        'role': role,
    })
    assert response.status_code == 201, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return response.json()


def test_main_application_registers_real_auth_routes(session_client):
    result = register(session_client)
    assert session_client.get('/api/auth/me').json()['user']['id'] == result['user']['id']
    assert str(app.url_path_for('auth_logout')) == '/logout'


def test_unlinked_signup_renders_student_onboarding(session_client):
    register(session_client)
    response = session_client.get('/student/homework')
    assert response.status_code == 200
    assert 'Аккаунт ученика создан' in response.text
    assert 'csrf-token' in response.text
    assert 'приглашение' in response.text.lower()
    assert session_client.get('/dashboard').status_code == 403


def test_teacher_cannot_use_student_onboarding(session_client):
    register(session_client, 'teacher')
    assert session_client.get('/dashboard').status_code == 200
    assert session_client.get('/student/homework').status_code == 403


def test_public_invite_and_authenticated_public_routing(session_client):
    assert session_client.get('/invite').status_code == 200
    register(session_client, 'teacher')
    for path in ('/login', '/register'):
        response = session_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/dashboard'


def test_teacher_directory_exposes_archived_students(session_client):
    register(session_client, 'teacher')
    result = session_client.post('/api/students', json={'name': 'Антон Козлов', 'email': 'archived-ui@example.com', 'subject': 'Математика', 'grade': '9 класс'})
    assert result.status_code == 200
    student_id = result.json()['student']['id']
    assert session_client.post(f'/api/students/{student_id}/archive', json={}).status_code == 200
    assert f'data-directory-student="{student_id}"' not in session_client.get('/students').text
    archived = session_client.get('/students?archived=archived')
    assert archived.status_code == 200
    assert f'data-directory-student="{student_id}"' in archived.text
    assert 'В архиве' in archived.text
    assert 'name="archived"' in archived.text


def test_form_logout_revokes_session_in_main_app(session_client):
    result = register(session_client, 'teacher')
    response = session_client.post('/logout', data={'csrf_token': result['csrf_token']}, follow_redirects=False)
    assert response.status_code == 303
    assert session_client.get('/api/auth/me').status_code == 401
    assert session_client.get('/dashboard', follow_redirects=False).status_code == 303
