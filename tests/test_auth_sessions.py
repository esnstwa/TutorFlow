"""Real HTTP auth; only the shared database dependency is overridden."""
import importlib.util
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import verify_password
from app.models import User
from app.auth.router import router
from tests.conftest import TestingSessionLocal, override_get_db


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "app_env", "production")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    from fastapi import Depends, Request
    from app.core.auth import get_current_teacher, get_current_student, optional_current_user

    @app.get("/dashboard")
    def dashboard(user=Depends(get_current_teacher)):
        return {"id": user.id}

    @app.api_route("/api/protected/teacher", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def teacher(request: Request, user=Depends(get_current_teacher)):
        return {"id": user.id, "csrf_token": request.state.csrf_token}

    @app.get("/api/protected/student")
    def student(profile=Depends(get_current_student)):
        return {"id": profile.id, "user_id": profile.user_id}

    @app.get("/api/optional")
    def optional(user=Depends(optional_current_user)):
        return {"user_id": user.id if user else None}

    @app.middleware("http")
    async def untrusted_state(request, call_next):
        from types import SimpleNamespace
        request.state.user = SimpleNamespace(id=1)
        return await call_next(request)

    with TestClient(app, base_url="https://testserver", follow_redirects=False) as browser:
        yield browser


def payload(**changes):
    data = dict(first_name="Анна", last_name="", email=f"auth-{uuid4().hex}@example.com",
                password="Password123", password_confirmation="Password123", role="teacher")
    data.update(changes)
    return data


def register(client, **changes):
    return client.post("/api/auth/register", json=payload(**changes),
                       headers={"X-TutorFlow-Request": "auth"})


@pytest.mark.parametrize("changes,field", [
    ({"password_confirmation": "Different123"}, "password_confirmation"),
    ({"password": "abcdefgh", "password_confirmation": "abcdefgh"}, "password"),
    ({"password": "12345678", "password_confirmation": "12345678"}, "password"),
    ({"password": "A1" * 65}, "password"),
    ({"first_name": "John"}, "first_name"),
    ({"first_name": "А"}, "first_name"),
    ({"first_name": "А" * 31}, "first_name"),
    ({"first_name": "--"}, "first_name"),
    ({"first_name": "Анна-"}, "first_name"),
    ({"first_name": "Анна-М"}, "first_name"),
    ({"first_name": "Анна-Мария-Ева"}, "first_name"),
    ({"last_name": "А" * 101}, "last_name"),
    ({"role": "admin"}, "role"),
    ({"email": "invalid"}, "email"),
])
def test_registration_field_errors_are_russian_without_password_echo(client, changes, field):
    response = register(client, **changes)
    assert response.status_code == 422
    assert field in response.json()["fields"]
    assert isinstance(response.json()["detail"], str)
    assert "Password123" not in response.text
    assert changes.get("password", "Password123") not in response.text


@pytest.mark.parametrize("route", ["register", "login"])
@pytest.mark.parametrize("headers", [
    {}, {"Origin": "https://evil.example", "X-TutorFlow-Request": "auth"},
    {"Origin": "null"}, {"Origin": "https://testserver.evil.example"},
    {"Origin": "https://testserver", "Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site", "X-TutorFlow-Request": "auth"},
])
def test_auth_rejects_cross_origin_and_missing_origin_without_header(client, route, headers):
    response = client.post(f"/api/auth/{route}", json=payload(), headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize("route", ["register", "login"])
def test_auth_requires_json_and_handles_malformed_json(client, route):
    response = client.post(f"/api/auth/{route}", data={"email": "user@example.com"}, headers={"X-TutorFlow-Request": "auth"})
    assert response.status_code == 415
    response = client.post(f"/api/auth/{route}", content="{broken", headers={"X-TutorFlow-Request": "auth", "Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"detail": "Некорректный JSON", "fields": {}}


def test_duplicate_normalized_email_is_409(client):
    email = payload()["email"]
    assert register(client, email=email).status_code == 201
    duplicate = register(client, email=" " + email.upper() + " ")
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Этот email уже зарегистрирован", "fields": {"email": "Этот email уже зарегистрирован"}}


@pytest.mark.parametrize("damage", ["tamper", "missing", "expired", "revoked", "overlong"])
def test_unusable_cookies_are_rejected_by_server(client, damage):
    from datetime import timedelta
    from app.auth.models import AuthSession
    from app.auth.sessions import token_digest
    from app.models import utc_now
    created = register(client).json()
    raw = client.cookies.get("tutorflow_session")
    if damage in {"expired", "revoked"}:
        with TestingSessionLocal() as db:
            session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
            if damage == "expired":
                session.expires_at = utc_now() - timedelta(seconds=1)
            else:
                session.revoked_at = utc_now()
            db.commit()
    elif damage == "tamper":
        raw += "tampered"
    elif damage == "missing":
        raw = "unknown-session"
    else:
        raw = "a" * 129
    headers = {"Cookie": f"tutorflow_session={raw}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/optional", headers=headers).json() == {"user_id": None}


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_protected_unsafe_requests_require_session_bound_csrf(client, method):
    created = register(client).json()
    assert client.request(method, "/api/protected/teacher").status_code == 403
    assert client.request(method, "/api/protected/teacher", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.request(method, "/api/protected/teacher", headers={"X-CSRF-Token": created["csrf_token"], "Origin": "https://evil.example"}).status_code == 403
    response = client.request(method, "/api/protected/teacher", headers={"X-CSRF-Token": created["csrf_token"], "Origin": "https://testserver"})
    assert response.status_code == 200
    assert response.json() == {"id": created["user"]["id"], "csrf_token": created["csrf_token"]}


def test_student_registration_is_unlinked_until_canonical_profile_link(client):
    from app.models import Student
    teacher = register(client).json()["user"]
    teacher_cookie = client.cookies.get("tutorflow_session")
    created = register(client, role="student", first_name="Анна-Мария").json()
    assert created["redirect"] == "/student/homework"
    assert client.get("/api/protected/teacher").status_code == 403
    assert client.get("/api/protected/student").status_code == 403
    with TestingSessionLocal() as db:
        assert db.scalar(select(Student).where(Student.user_id == created["user"]["id"])) is None
        profile = Student(teacher_id=teacher["id"], user_id=created["user"]["id"], first_name="Анна", last_name="", grade="7", subject="Математика")
        db.add(profile)
        db.commit()
        profile_id = profile.id
    response = client.get("/api/protected/student")
    assert response.status_code == 200
    assert response.json() == {"id": profile_id, "user_id": created["user"]["id"]}
    # Registration rotates the previous account's session too.
    assert client.get("/api/auth/me", headers={"Cookie": f"tutorflow_session={teacher_cookie}"}).status_code == 401


def test_teacher_is_forbidden_from_student_resources(client):
    register(client)
    assert client.get("/api/protected/student").status_code == 403


def test_same_origin_signup_trims_names_and_default_last_name(client):
    data = payload(first_name=" Анна ")
    data.pop("last_name")
    response = client.post("/api/auth/register", json=data, headers={"Origin": "https://testserver", "Sec-Fetch-Site": "same-origin"})
    assert response.status_code == 201
    assert response.json()["user"]["first_name"] == "Анна"
    assert response.json()["user"]["last_name"] == ""
    assert "Max-Age" not in response.headers["set-cookie"]
    from app.auth.models import AuthSession
    with TestingSessionLocal() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == response.json()["user"]["id"]))
        assert (session.expires_at - session.created_at).total_seconds() == pytest.approx(43200, abs=1)


def test_login_invalid_stored_hash_returns_generic_401(client):
    created = register(client).json()
    with TestingSessionLocal() as db:
        db.get(User, created["user"]["id"]).password_hash = "seed-placeholder"
        db.commit()
    response = client.post("/api/auth/login", json={"email": created["user"]["email"], "password": "Password123", "remember": False}, headers={"X-TutorFlow-Request": "auth"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Неверный email или пароль"}


def test_auth_migration_adds_only_session_table_and_roundtrips():
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect
    path = Path(__file__).resolve().parents[1] / "migrations/versions/c1a2b3c4d5e6_auth_sessions.py"
    assert path.exists()
    spec = importlib.util.spec_from_file_location("auth_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "c1a2b3c4d5e6"
    assert migration.down_revision == "9b2c4e7f1a30"
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        User.__table__.create(connection)
        operations = Operations(MigrationContext.configure(connection))
        with operations.context(operations.migration_context):
            migration.upgrade()
            assert set(inspect(connection).get_table_names()) == {"users", "auth_sessions"}
            from app.auth.models import AuthSession
            columns = {c["name"] for c in inspect(connection).get_columns("auth_sessions")}
            assert columns == set(AuthSession.__table__.columns.keys())
            migration.downgrade()
            assert inspect(connection).get_table_names() == ["users"]
    engine.dispose()


def test_local_http_cookie_requires_explicit_environment(client, monkeypatch):
    from app.core.config import Settings, settings
    assert getattr(Settings(_env_file=None, app_env="development"), "session_cookie_secure", None) is False
    monkeypatch.setattr(settings, "app_env", "development")
    response = client.post("http://testserver/api/auth/register", json=payload(), headers={"X-TutorFlow-Request": "auth"})
    assert response.status_code == 201
    assert "Secure" not in response.headers["set-cookie"]
    assert client.get("http://testserver/api/auth/me").status_code == 200
    from app.core.config import Settings
    assert Settings(_env_file=None).session_cookie_secure is True
    assert Settings(_env_file=None, app_env="production").session_cookie_secure is True
    assert Settings(_env_file=None, app_env="test").session_cookie_secure is False


def test_anonymous_html_redirects_without_development_or_upstream_state_bypass(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "enable_dev_teacher_fallback", True)
    assert client.get("/api/protected/teacher").status_code == 401
    assert client.get("/api/protected/student").status_code == 401
    assert client.get("/api/optional").json() == {"user_id": None}
    response = client.get("/dashboard", headers={"Accept": "text/html"})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_anonymous_form_logout_redirects_to_login(client):
    response = client.post("/logout", data={"csrf_token": "invalid"})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_form_logout_parses_urlencoded_csrf_without_multipart(client):
    created = register(client).json()
    old = client.cookies.get("tutorflow_session")
    assert client.post("/logout", data={"csrf_token": "wrong"}).status_code == 403
    response = client.post("/logout", data={"csrf_token": created["csrf_token"]}, headers={"Origin": "https://testserver"})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/api/auth/me", headers={"Cookie": f"tutorflow_session={old}"}).status_code == 401
    assert str(client.app.url_path_for("auth_logout")) == "/logout"


def test_api_logout_requires_csrf_revokes_session_and_deletes_cookie(client):
    created = register(client).json()
    old = client.cookies.get("tutorflow_session")
    assert client.post("/api/auth/logout", json={}).status_code == 403
    assert client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    response = client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": created["csrf_token"]})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "redirect": "/login"}
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/me", headers={"Cookie": f"tutorflow_session={old}"}).status_code == 401


def test_failed_login_without_active_session_creates_no_session_or_cookie(client):
    from app.auth.models import AuthSession
    from app.auth.sessions import COOKIE_NAME
    from app.core.security import hash_password

    data = payload()
    with TestingSessionLocal() as db:
        user = User(email=data["email"], password_hash=hash_password(data["password"]),
                    first_name=data["first_name"], last_name=data["last_name"], role=data["role"])
        db.add(user)
        db.commit()
        user_id = user.id
        assert db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)).all() == []

    assert client.cookies.get(COOKIE_NAME) is None
    response = client.post("/api/auth/login", json={"email": data["email"], "password": "bad", "remember": False}, headers={"X-TutorFlow-Request": "auth"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Неверный email или пароль"}
    assert COOKIE_NAME not in response.headers.get("set-cookie", "")
    assert client.cookies.get(COOKIE_NAME) is None

    with TestingSessionLocal() as db:
        assert db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)).all() == []


def test_login_verifies_password_rotates_cookie_and_remembers(client):
    from app.auth.models import AuthSession
    from app.auth.sessions import COOKIE_NAME, token_digest

    data = payload()
    registered = client.post("/api/auth/register", json=data, headers={"X-TutorFlow-Request": "auth"}).json()
    old_cookie = client.cookies.get(COOKIE_NAME)
    with TestingSessionLocal() as db:
        old_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(old_cookie)))
        assert old_session is not None
        old_session_id = old_session.id
        old_csrf_token = old_session.csrf_token
        session_count_before_bad = len(db.scalars(select(AuthSession).where(AuthSession.user_id == registered["user"]["id"])).all())

    bad = client.post("/api/auth/login", json={"email": data["email"], "password": "bad", "remember": False}, headers={"X-TutorFlow-Request": "auth"})
    assert bad.status_code == 401
    assert bad.json() == {"detail": "Неверный email или пароль"}
    assert COOKIE_NAME not in bad.headers.get("set-cookie", "")
    assert client.cookies.get(COOKIE_NAME) == old_cookie
    with TestingSessionLocal() as db:
        unchanged_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(old_cookie)))
        assert unchanged_session is not None
        assert unchanged_session.id == old_session_id
        assert unchanged_session.revoked_at is None
        assert unchanged_session.csrf_token == old_csrf_token
        assert len(db.scalars(select(AuthSession).where(AuthSession.user_id == registered["user"]["id"])).all()) == session_count_before_bad
    old_session_response = client.get("/api/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old_cookie}"})
    assert old_session_response.status_code == 200
    assert old_session_response.json()["csrf_token"] == old_csrf_token

    good = client.post("/api/auth/login", json={"email": " " + data["email"].upper() + " ", "password": data["password"], "remember": True}, headers={"X-TutorFlow-Request": "auth"})
    assert good.status_code == 200
    assert good.json()["user"] == registered["user"]
    assert client.cookies.get(COOKIE_NAME) != old_cookie
    assert good.json()["csrf_token"] != registered["csrf_token"]
    assert client.post("/api/protected/teacher", headers={"X-CSRF-Token": registered["csrf_token"]}).status_code == 403
    assert client.post("/api/protected/teacher", headers={"X-CSRF-Token": good.json()["csrf_token"]}).status_code == 200
    assert "Max-Age=2592000" in good.headers["set-cookie"]
    with TestingSessionLocal() as db:
        current = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(client.cookies.get(COOKIE_NAME))))
        assert (current.expires_at - current.created_at).total_seconds() == pytest.approx(2592000, abs=1)
    old = client.get("/api/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old_cookie}"})
    assert old.status_code == 401


def test_me_resolves_cookie_and_rejects_anonymous(client):
    assert client.get("/api/auth/me").status_code == 401
    created = register(client).json()
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "user": created["user"], "csrf_token": created["csrf_token"]}


def test_register_creates_real_user_and_opaque_session(client):
    data = payload()
    response = client.post("/api/auth/register", json=data, headers={"X-TutorFlow-Request": "auth"})
    assert response.status_code == 201
    body = response.json()
    assert body["ok"] is True
    assert body["redirect"] == "/dashboard"
    assert body["user"]["email"] == data["email"]
    assert set(body["user"]) == {"id", "email", "role", "first_name", "last_name"}
    assert body["csrf_token"]
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    assert "Secure" in cookie
    from app.auth.models import AuthSession
    import hashlib
    raw = client.cookies.get("tutorflow_session")
    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == data["email"]))
        assert verify_password(data["password"], user.password_hash)
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert session.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert session.token_hash != raw
        assert session.csrf_token == body["csrf_token"]
