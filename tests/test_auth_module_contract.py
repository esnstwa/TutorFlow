from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import Argon2PasswordVerifier
from app.auth.passwords import get_password_verifier
from app.core.security import hash_password
from app.main import app
from app.models import User
from tests.conftest import TestingSessionLocal
from tests.support.passwords import FixedPasswordVerifier


@pytest.mark.parametrize("implementation", ["argon2", "fixed"])
def test_password_verifier_contract_covers_normal_boundary_and_error_inputs(implementation):
    password = "Password123"
    if implementation == "argon2":
        stored_hash = hash_password(password)
        verifier = Argon2PasswordVerifier()
    else:
        stored_hash = "not-an-argon2-hash"
        verifier = FixedPasswordVerifier({(password, stored_hash): True})

    assert verifier.verify(password, stored_hash) is True
    assert verifier.verify("Wrong123", stored_hash) is False
    assert verifier.verify("", stored_hash) is False
    assert verifier.verify(password, "") is False
    assert verifier.verify(password, "malformed") is False


@pytest.mark.parametrize("implementation", ["argon2", "fixed"])
def test_one_login_consumer_accepts_both_verifier_implementations(implementation):
    password = "Password123"
    email = f"contract-{uuid4().hex}@example.com"
    if implementation == "argon2":
        stored_hash = hash_password(password)
        verifier = Argon2PasswordVerifier()
    else:
        stored_hash = "test-only-stored-value"
        verifier = FixedPasswordVerifier({(password, stored_hash): True})

    with TestingSessionLocal() as db:
        db.add(User(email=email, password_hash=stored_hash, first_name="Анна", last_name="", role="teacher"))
        db.commit()

    previous = app.dependency_overrides.get(get_password_verifier)
    app.dependency_overrides[get_password_verifier] = lambda: verifier
    try:
        with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
            response = client.post(
                "/api/auth/login",
                json={"email": email, "password": password, "remember": False},
                headers={"X-TutorFlow-Request": "auth"},
            )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_password_verifier, None)
        else:
            app.dependency_overrides[get_password_verifier] = previous

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


def test_default_password_verifier_is_production_argon2_implementation():
    assert isinstance(get_password_verifier(), Argon2PasswordVerifier)


def test_argon2_verifier_rejects_non_ascii_malformed_hash():
    assert Argon2PasswordVerifier().verify("Password123", "не-argon2-хэш") is False


def test_login_maps_non_ascii_malformed_hash_to_generic_401_without_session():
    from sqlalchemy import select

    from app.auth.models import AuthSession

    email = f"malformed-{uuid4().hex}@example.com"
    with TestingSessionLocal() as db:
        db.add(User(email=email, password_hash="не-argon2-хэш", first_name="Анна", last_name="", role="teacher"))
        db.commit()

    with TestClient(app, base_url="https://testserver", follow_redirects=False) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Password123", "remember": False},
            headers={"X-TutorFlow-Request": "auth"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Неверный email или пароль"}
    assert "tutorflow_session" not in response.headers.get("set-cookie", "")
    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all() == []
