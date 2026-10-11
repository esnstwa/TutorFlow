from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))

    def by_id(self, identifier):
        return next((tag, attrs) for tag, attrs in self.nodes if attrs.get('id') == identifier)


def test_login_is_real_submit_with_required_fields_and_honest_recovery():
    with TestClient(app) as client:
        response = client.get('/login')
    assert response.status_code == 200
    parsed = Elements(response.text)
    for identifier in ('login-email', 'login-password'):
        _, attrs = parsed.by_id(identifier)
        assert 'required' in attrs
        assert 'aria-describedby' in attrs
    assert any(tag == 'button' and attrs.get('class') == 'login-submit' and attrs.get('type') == 'submit' for tag, attrs in parsed.nodes)
    tag, attrs = parsed.by_id('password-recovery')
    assert tag == 'span' and attrs.get('aria-disabled') == 'true' and 'href' not in attrs
    assert 'Восстановление пароля пока недоступно' in response.text
    _, attrs = parsed.by_id('login-error')
    assert attrs.get('role') == 'alert' and 'hidden' in attrs


def test_register_keeps_rich_success_step_with_real_destination():
    with TestClient(app) as client:
        response = client.get('/register')
    assert response.status_code == 200
    parsed = Elements(response.text)
    assert [attrs['data-register-step'] for _, attrs in parsed.nodes if 'data-register-step' in attrs] == ['1', '2', '3', '4', '5']
    tag, attrs = parsed.by_id('register-complete-title')
    assert tag == 'h1' and attrs.get('tabindex') == '-1'
    assert any(tag == 'a' and 'data-register-goto' in attrs and attrs.get('href') == '/dashboard' for tag, attrs in parsed.nodes)
    assert any(
        tag == 'img'
        and 'augustin-teacher-complete.webp' in attrs.get('src', '')
        and 'augustin-student-complete.png' in attrs.get('data-student-src', '')
        and 'register-complete__character' in attrs.get('class', '')
        for tag, attrs in parsed.nodes
    )
    assert not any(attrs.get('name') == 'last_name' for _, attrs in parsed.nodes)
    for identifier in ('register-password-error', 'register-password-confirmation-error'):
        assert parsed.by_id(identifier)[1].get('role') == 'alert'


def test_added_login_messages_have_no_default_layout_footprint():
    css = (Path(__file__).parents[1] / 'app/web/static/css/login.css').read_text(encoding='utf-8')
    assert '.login-error[hidden]' in css
    assert '.login-recovery-note' in css
