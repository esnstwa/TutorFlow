import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.auth.models import AuthSession
from app.auth.sessions import COOKIE_NAME, token_digest
from app.core.config import MAX_SESSION_LIFETIME_SECONDS, Settings, settings
from app.main import app
from tests.conftest import TestingSessionLocal


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUTH_HEADERS = {"X-TutorFlow-Request": "auth"}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as browser:
        yield browser


def _payload(email: str, **changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "first_name": "Анна",
        "last_name": "",
        "email": email,
        "password": "Password123",
        "password_confirmation": "Password123",
        "role": "teacher",
    }
    payload.update(changes)
    return payload


def _session_for_cookie(raw_cookie: str) -> AuthSession:
    with TestingSessionLocal() as db:
        session = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_digest(raw_cookie))
        )
        assert session is not None
        db.expunge(session)
        return session


def test_session_settings_preserve_previous_default_lifetimes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SESSION_LIFETIME_SECONDS", raising=False)
    monkeypatch.delenv("REMEMBER_SESSION_LIFETIME_SECONDS", raising=False)

    configured = Settings(_env_file=None)

    assert configured.session_lifetime_seconds == 43200
    assert configured.remember_session_lifetime_seconds == 2592000


@pytest.mark.parametrize("field", ["session_lifetime_seconds", "remember_session_lifetime_seconds"])
def test_session_settings_accept_only_datetime_safe_upper_boundary(field: str) -> None:
    configured = Settings(_env_file=None, **{field: MAX_SESSION_LIFETIME_SECONDS})

    assert getattr(configured, field) == MAX_SESSION_LIFETIME_SECONDS

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, **{field: MAX_SESSION_LIFETIME_SECONDS + 1})

    assert field in {str(error["loc"][0]) for error in raised.value.errors()}


@pytest.mark.parametrize("field", ["session_lifetime_seconds", "remember_session_lifetime_seconds"])
def test_101_digit_session_lifetime_is_rejected(field: str) -> None:
    oversized = int("1" + "0" * 100)

    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, **{field: oversized})

    assert field in {str(error["loc"][0]) for error in raised.value.errors()}


def test_session_settings_accept_positive_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_LIFETIME_SECONDS", "60")
    monkeypatch.setenv("REMEMBER_SESSION_LIFETIME_SECONDS", "120")

    configured = Settings(_env_file=None)

    assert configured.session_lifetime_seconds == 60
    assert configured.remember_session_lifetime_seconds == 120


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("session_lifetime_seconds", 0),
        ("session_lifetime_seconds", -1),
        ("remember_session_lifetime_seconds", 0),
        ("remember_session_lifetime_seconds", -1),
        ("session_lifetime_seconds", "not-a-number"),
    ],
)
def test_invalid_session_settings_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(_env_file=None, **{field: value})

    assert field in {str(error["loc"][0]) for error in raised.value.errors()}


def test_session_settings_allow_independent_positive_lifetimes() -> None:
    configured = Settings(
        _env_file=None,
        session_lifetime_seconds=120,
        remember_session_lifetime_seconds=60,
    )

    assert configured.session_lifetime_seconds == 120
    assert configured.remember_session_lifetime_seconds == 60


def test_auth_routes_use_configured_lifetimes_for_both_session_modes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "session_lifetime_seconds", 61)
    monkeypatch.setattr(settings, "remember_session_lifetime_seconds", 121)
    email = f"config-{uuid4().hex}@example.com"

    registered = client.post(
        "/api/auth/register", json=_payload(email), headers=AUTH_HEADERS
    )
    assert registered.status_code == 201
    normal_cookie = client.cookies.get(COOKIE_NAME)
    assert normal_cookie is not None
    normal_session = _session_for_cookie(normal_cookie)
    assert (normal_session.expires_at - normal_session.created_at).total_seconds() == pytest.approx(61, abs=1)
    assert "Max-Age=" not in registered.headers["set-cookie"]

    remembered = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123", "remember": True},
        headers=AUTH_HEADERS,
    )
    assert remembered.status_code == 200
    remembered_cookie = client.cookies.get(COOKIE_NAME)
    assert remembered_cookie is not None
    remembered_session = _session_for_cookie(remembered_cookie)
    assert (remembered_session.expires_at - remembered_session.created_at).total_seconds() == pytest.approx(121, abs=1)
    assert "Max-Age=121" in remembered.headers["set-cookie"]


@pytest.mark.parametrize(
    ("environment_name", "field_name"),
    [
        ("SESSION_LIFETIME_SECONDS", "session_lifetime_seconds"),
        ("REMEMBER_SESSION_LIFETIME_SECONDS", "remember_session_lifetime_seconds"),
    ],
)
def test_runtime_diagnostic_rejects_101_digit_session_setting_without_secret_leak(
    environment_name: str, field_name: str
) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            environment_name: "1" + "0" * 100,
            "DATABASE_URL": "diagnostic-secret-marker",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.core.runtime_diagnostics"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 2
    assert "configuration_error" in result.stderr
    assert field_name in result.stderr
    assert "diagnostic-secret-marker" not in result.stdout + result.stderr
    assert "component_result status=error" in result.stderr
