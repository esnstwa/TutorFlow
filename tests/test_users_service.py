import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.core.security import verify_password
from app.users.exceptions import UserAlreadyExistsError
from app.users.models import User, UserRole
from app.users.schemas import UserCreate
from app.users.service import create_user


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    with TestingSessionLocal() as session:
        yield session


def test_create_user_persists_user_with_hashed_password(db_session: Session) -> None:
    password = "strong-password"
    user_data = UserCreate(
        email="Tutor@Example.COM ",
        password=password,
        first_name="Artem",
        last_name="Tutor",
        role=UserRole.TUTOR,
    )

    user = create_user(db_session, user_data)

    assert user.id is not None
    assert user.email == "tutor@example.com"
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)

    saved_user = db_session.get(User, user.id)
    assert saved_user is not None


def test_create_user_rejects_duplicate_email(db_session: Session) -> None:
    first_user = UserCreate(
        email="student@example.com",
        password="strong-password",
        first_name="First",
        last_name="Student",
        role=UserRole.STUDENT,
    )
    duplicate_user = UserCreate(
        email=" STUDENT@example.com ",
        password="another-password",
        first_name="Second",
        last_name="Student",
        role=UserRole.STUDENT,
    )

    create_user(db_session, first_user)

    with pytest.raises(UserAlreadyExistsError):
        create_user(db_session, duplicate_user)
