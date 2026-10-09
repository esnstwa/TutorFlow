import pytest
from pydantic import ValidationError

from app.users.models import UserRole
from app.users.schemas import UserCreate


def test_user_create_accepts_valid_data() -> None:
    user = UserCreate(
        email="Tutor@example.com",
        password="strong-password",
        first_name=" Artem ",
        last_name=" Tutor ",
        role=UserRole.TUTOR,
    )

    assert user.email == "Tutor@example.com"
    assert user.first_name == "Artem"
    assert user.last_name == "Tutor"
    assert user.role is UserRole.TUTOR


def test_user_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="not-an-email",
            password="strong-password",
            first_name="Artem",
            last_name="Tutor",
            role=UserRole.TUTOR,
        )


def test_user_create_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="tutor@example.com",
            password="short",
            first_name="Artem",
            last_name="Tutor",
            role=UserRole.TUTOR,
        )
