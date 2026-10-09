from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.seed import seed_dev_data


TEST_ENGINE = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=TEST_ENGINE, autoflush=False, expire_on_commit=False)


@event.listens_for(TEST_ENGINE, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> Generator[None, None, None]:
    Base.metadata.create_all(TEST_ENGINE)
    with TestingSessionLocal() as db:
        seed_dev_data(db)
    yield
    Base.metadata.drop_all(TEST_ENGINE)


@pytest.fixture
def legacy_cabinet_auth() -> Generator[None, None, None]:
    """Explicit seeded identities for cabinet/service tests, not auth tests.

    Tests of actual sessions and role isolation must never request this fixture.
    """
    from fastapi import Depends
    from app.core.auth import get_current_student, get_current_teacher
    from app.models import Student, User

    def teacher(db: Session = Depends(get_db)) -> User:
        return db.get(User, 1)

    def student(db: Session = Depends(get_db)) -> Student:
        return db.get(Student, 1)

    previous = {dependency: app.dependency_overrides.get(dependency)
                for dependency in (get_current_teacher, get_current_student)}
    app.dependency_overrides[get_current_teacher] = teacher
    app.dependency_overrides[get_current_student] = student
    yield
    for dependency, original in previous.items():
        if original is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = original
