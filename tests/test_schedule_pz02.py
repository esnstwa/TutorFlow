"""Артём — индивидуальные проверки FR-07 (ПЗ №2).

Каждый тест получает отдельную SQLite-БД и синтетических пользователей;
никакой тест не использует demo seed или mock бизнес-логики.
"""
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_teacher
from app.core.database import Base, get_db
from app.auth.router import router as auth_router
from app.models import Lesson, Student, User
from app.web.router import router as web_router
from app.web.templating import STATIC_DIR


@pytest.fixture
def schedule_case() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as db:
        teacher = User(email="schedule-teacher@example.test", password_hash="test-hash", first_name="Артём", last_name="", role="teacher")
        other_teacher = User(email="other-schedule-teacher@example.test", password_hash="test-hash", first_name="Другой", last_name="", role="teacher")
        db.add_all([teacher, other_teacher])
        db.flush()
        active_student = Student(teacher_id=teacher.id, first_name="Тест", last_name="Активный", grade="8", subject="Математика")
        second_student = Student(teacher_id=teacher.id, first_name="Тест", last_name="Второй", grade="8", subject="Математика")
        archived_student = Student(teacher_id=teacher.id, first_name="Тест", last_name="Архивный", grade="8", subject="Математика", archived_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        foreign_student = Student(teacher_id=other_teacher.id, first_name="Чужой", last_name="Ученик", grade="8", subject="Математика")
        db.add_all([active_student, second_student, archived_student, foreign_student])
        db.commit()
        teacher_id = teacher.id
        active_student_id = active_student.id
        second_student_id = second_student.id
        archived_student_id = archived_student.id
        foreign_student_id = foreign_student.id

    def override_get_db() -> Generator[Session, None, None]:
        with SessionLocal() as db:
            yield db

    def override_teacher(db: Session = Depends(get_db)) -> User:
        return db.get(User, teacher_id)

    test_app = FastAPI()
    test_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    test_app.include_router(auth_router)
    test_app.include_router(web_router)
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_teacher] = override_teacher
    try:
        with TestClient(test_app) as client:
            yield {
                "client": client,
                "session_factory": SessionLocal,
                "teacher_id": teacher_id,
                "active_student_id": active_student_id,
                "second_student_id": second_student_id,
                "archived_student_id": archived_student_id,
                "foreign_student_id": foreign_student_id,
            }
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def lesson_payload(student_id: int, *, start: str = "10:00", end: str = "11:00") -> dict:
    return {
        "student_id": student_id,
        "topic": "Алгебра",
        "date": "2026-11-10",
        "start": start,
        "end": end,
    }


def lesson_count(case: dict) -> int:
    with case["session_factory"]() as db:
        return db.scalar(select(func.count()).select_from(Lesson))


def create_lesson(case: dict, *, student_id: int, start: str = "10:00", end: str = "11:00"):
    return case["client"].post(
        "/api/lessons",
        json=lesson_payload(student_id, start=start, end=end),
    )


def test_a_sch_01_create_own_active_student_lesson_persists(schedule_case):
    """A-SCH-01 / FR-07, FR-16: valid creation survives a new DB session."""
    case = schedule_case
    response = create_lesson(case, student_id=case["active_student_id"])
    assert response.status_code == 200, response.text
    lesson_id = response.json()["lesson"]["id"]

    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.teacher_id == case["teacher_id"]
        assert saved.student_id == case["active_student_id"]
        assert saved.start_at.date().isoformat() == "2026-11-10"
        assert saved.start_at.strftime("%H:%M") == "10:00"
        assert saved.end_at.strftime("%H:%M") == "11:00"
        assert saved.topic == "Алгебра"
        assert saved.status == "scheduled"

    listed = case["client"].get(
        "/api/lessons",
        params={"date_from": "2026-11-10", "date_to": "2026-11-10"},
    )
    assert listed.status_code == 200
    lessons = listed.json()["lessons"]
    assert [item["id"] for item in lessons] == [lesson_id]
    unfiltered = case["client"].get("/api/lessons")
    assert unfiltered.status_code == 200
    assert [item["id"] for item in unfiltered.json()["lessons"]] == [lesson_id]
    detail = case["client"].get(f"/api/lessons/{lesson_id}")
    assert detail.status_code == 200
    assert detail.json()["lesson"]["topic"] == "Алгебра"


@pytest.mark.parametrize(
    ("start", "end"),
    [("10:00", "10:00"), ("11:00", "10:00")],
    ids=["equal-boundary", "end-before-start"],
)
def test_a_sch_02_03_reject_non_positive_interval(schedule_case, start, end):
    """A-SCH-02/03 / FR-07: end_at <= start_at is rejected without insert."""
    case = schedule_case
    before = lesson_count(case)
    response = create_lesson(case, student_id=case["active_student_id"], start=start, end=end)
    assert response.status_code == 422
    assert response.json()["detail"] == "Окончание занятия должно быть позже начала"
    assert lesson_count(case) == before


@pytest.mark.parametrize("student_key", ["foreign_student_id", "archived_student_id"], ids=["foreign", "archived"])
def test_a_sch_04_05_reject_foreign_or_archived_student(schedule_case, student_key):
    """A-SCH-04/05 / FR-07: only the teacher's active student is eligible."""
    case = schedule_case
    before = lesson_count(case)
    response = create_lesson(case, student_id=case[student_key])
    assert response.status_code >= 400
    assert lesson_count(case) == before


@pytest.mark.parametrize(
    ("start", "end"),
    [("09:30", "10:30"), ("10:15", "10:45"), ("10:30", "11:30")],
    ids=["overlap-left", "contained", "overlap-right"],
)
def test_a_sch_08_reject_partial_or_contained_overlap_on_create(schedule_case, start, end):
    """A-SCH-08 / FR-07 + task acceptance: reject strict same-teacher overlap."""
    case = schedule_case
    existing = create_lesson(case, student_id=case["active_student_id"])
    assert existing.status_code == 200, existing.text
    before = lesson_count(case)

    response = create_lesson(case, student_id=case["second_student_id"], start=start, end=end)
    assert response.status_code == 422
    assert response.json()["detail"] == "Это время уже занято"
    assert lesson_count(case) == before


@pytest.mark.parametrize(
    ("status", "expected_status"),
    [
        ("scheduled", 200),
        ("completed_unpaid", 200),
        ("completed_paid", 200),
        ("cancelled", 200),
        ("cancelled_by_student", 422),
    ],
    ids=["scheduled", "completed-unpaid", "completed-paid", "cancelled", "unknown"],
)
def test_a_sch_07_accept_only_documented_lesson_statuses(schedule_case, status, expected_status):
    """A-SCH-07 / FR-07: accept the four enumerated statuses only."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"])
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    before_status = "scheduled"
    response = case["client"].patch(
        f"/api/lessons/{lesson_id}",
        json={"status": status, "topic": "Алгебра", "location": "Кабинет", "materials": [], "teacher_note": ""},
    )
    assert response.status_code == expected_status
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.status == (status if expected_status == 200 else before_status)


@pytest.mark.parametrize(
    ("note_length", "expected_status"),
    [(500, 200), (501, 422)],
    ids=["max-500", "over-max-501"],
)
def test_a_sch_06_teacher_note_length_boundary(schedule_case, note_length, expected_status):
    """A-SCH-06 / FR-07: accept 500 chars and reject 501 without mutation."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"])
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    note = "x" * note_length
    response = case["client"].patch(
        f"/api/lessons/{lesson_id}",
        json={"status": "scheduled", "topic": "Алгебра", "location": "Кабинет", "materials": [], "teacher_note": note},
    )
    assert response.status_code == expected_status
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.teacher_note == (note if expected_status == 200 else "")


@pytest.mark.parametrize(
    "start",
    ["09:30", "10:15", "10:30"],
    ids=["overlap-left", "contained", "overlap-right"],
)
def test_a_sch_11_reject_partial_overlap_on_reschedule_without_mutation(schedule_case, start):
    """A-SCH-11 / FR-07 + task acceptance: failed reschedule is atomic."""
    case = schedule_case
    moving = create_lesson(case, student_id=case["active_student_id"], start="13:00", end="14:00")
    blocker = create_lesson(case, student_id=case["second_student_id"], start="10:00", end="11:00")
    assert moving.status_code == blocker.status_code == 200
    lesson_id = moving.json()["lesson"]["id"]
    response = case["client"].post(
        f"/api/mock/lessons/{lesson_id}/reschedule",
        json={"date": "2026-11-10", "start": start},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "Это время уже занято"
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.start_at.strftime("%H:%M") == "13:00"
        assert saved.end_at.strftime("%H:%M") == "14:00"


def test_a_sch_10_reschedule_preserves_duration_and_persists(schedule_case):
    """A-SCH-10 / FR-07, FR-16: move a lesson and retain its 60-minute duration."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"], start="09:00", end="10:00")
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    response = case["client"].post(
        f"/api/mock/lessons/{lesson_id}/reschedule",
        json={"date": "2026-11-12", "start": "13:00"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["lesson"]["date_iso"] == "2026-11-12"
    assert response.json()["lesson"]["start"] == "13:00"
    assert response.json()["lesson"]["end"] == "14:00"
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.start_at.date().isoformat() == "2026-11-12"
        assert saved.start_at.strftime("%H:%M") == "13:00"
        assert saved.end_at.strftime("%H:%M") == "14:00"


def test_a_sch_13_missing_lesson_operations_return_errors_without_insert(schedule_case):
    """A-SCH-13 (added): unknown lesson IDs do not alter schedule state."""
    case = schedule_case
    missing_id = 999999
    before = lesson_count(case)
    detail = case["client"].get(f"/api/lessons/{missing_id}")
    update = case["client"].patch(
        f"/api/lessons/{missing_id}",
        json={"status": "scheduled", "topic": "Алгебра", "location": "", "materials": [], "teacher_note": ""},
    )
    reschedule = case["client"].post(
        f"/api/mock/lessons/{missing_id}/reschedule",
        json={"date": "2026-11-12", "start": "13:00"},
    )
    delete = case["client"].delete(f"/api/lessons/{missing_id}")
    assert detail.status_code == 404
    assert update.status_code == 422
    assert update.json()["error"] == "Занятие не найдено"
    assert reschedule.status_code == 422
    assert reschedule.json()["error"] == "Занятие не найдено"
    assert delete.status_code == 404
    assert lesson_count(case) == before


def test_a_sch_07_creation_rejects_unknown_status_without_insert(schedule_case):
    """A-SCH-07: FR-07 rejects an unknown status during creation too."""
    case = schedule_case
    payload = lesson_payload(case["active_student_id"])
    payload["status"] = "cancelled_by_student"
    before = lesson_count(case)

    response = case["client"].post("/api/lessons", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"] == "Неизвестный статус занятия"
    assert lesson_count(case) == before


@pytest.mark.parametrize(
    ("patch_fields", "expected_error"),
    [
        ({"topic": ""}, "Укажите тему занятия"),
        ({"topic": "Алгебра", "materials": "not-a-list"}, "Некорректный список материалов"),
    ],
    ids=["empty-topic", "materials-not-list"],
)
def test_a_sch_14_invalid_lesson_update_payload_rolls_back(schedule_case, patch_fields, expected_error):
    """A-SCH-14: invalid lesson updates fail and preserve stored values."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"])
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    before_count = lesson_count(case)
    response = case["client"].patch(
        f"/api/lessons/{lesson_id}",
        json={"status": "scheduled", "topic": "Алгебра", "location": "", "materials": [], "teacher_note": "", **patch_fields},
    )
    assert response.status_code == 422
    assert response.json()["error"] == expected_error
    assert lesson_count(case) == before_count
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.topic == "Алгебра"
        assert saved.status == "scheduled"


def test_a_sch_15_missing_required_create_field_does_not_insert(schedule_case):
    """A-SCH-15: missing FR-07 topic is rejected without persistence."""
    case = schedule_case
    payload = lesson_payload(case["active_student_id"])
    payload.pop("topic")
    before = lesson_count(case)

    response = case["client"].post("/api/lessons", json=payload)
    assert response.status_code == 422
    assert lesson_count(case) == before


def test_a_sch_16_reschedule_missing_start_preserves_original_interval(schedule_case):
    """A-SCH-16: missing reschedule input is rejected atomically."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"], start="09:00", end="10:00")
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]

    response = case["client"].post(
        f"/api/mock/lessons/{lesson_id}/reschedule",
        json={"date": "2026-11-12"},
    )
    assert response.status_code == 422
    with case["session_factory"]() as db:
        saved = db.get(Lesson, lesson_id)
        assert saved is not None
        assert saved.start_at.strftime("%H:%M") == "09:00"
        assert saved.end_at.strftime("%H:%M") == "10:00"
        assert saved.start_at.date().isoformat() == "2026-11-10"


def test_a_sch_17_delete_existing_lesson_removes_persisted_record(schedule_case):
    """A-SCH-17: deleting a real lesson removes it from storage."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"])
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    assert lesson_count(case) == 1

    deleted = case["client"].delete(f"/api/lessons/{lesson_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert lesson_count(case) == 0
    assert case["client"].get(f"/api/lessons/{lesson_id}").status_code == 404


@pytest.mark.parametrize("blank_topic", [False, True], ids=["valid", "empty-required-field"])
def test_a_sch_18_schedule_compat_creation_route_persists_or_rejects(schedule_case, blank_topic):
    """A-SCH-18: exercise the schedule UI's /api/mock/lesson creation route."""
    case = schedule_case
    payload = lesson_payload(case["active_student_id"])
    payload["topic"] = "" if blank_topic else payload["topic"]
    before = lesson_count(case)

    response = case["client"].post("/api/mock/lesson", json=payload)
    if blank_topic:
        assert response.status_code == 422
        assert response.json()["error"] == "Заполните все поля"
        assert lesson_count(case) == before
    else:
        assert response.status_code == 200, response.text
        lesson_id = response.json()["entity"]["id"]
        with case["session_factory"]() as db:
            saved = db.get(Lesson, lesson_id)
            assert saved is not None
            assert saved.student_id == case["active_student_id"]
            assert saved.topic == "Алгебра"
        assert lesson_count(case) == before + 1


def test_a_sch_18_non_object_payload_is_rejected(schedule_case):
    """A-SCH-18: the compatibility endpoint rejects non-object JSON cleanly."""
    case = schedule_case
    before = lesson_count(case)

    response = case["client"].post("/api/mock/lesson", json=["not", "an", "object"])
    assert response.status_code == 422
    assert response.json()["error"] == "Некорректные данные"
    assert lesson_count(case) == before


def test_a_sch_19_database_integrity_failure_rolls_back_creation(schedule_case):
    """A-SCH-19: HTTP commit guard handles a real SQLite CHECK-constraint failure."""
    case = schedule_case
    engine = case["session_factory"].kw["bind"]

    def add_invalid_status_before_commit(db):
        if db.get_bind() is engine:
            db.add(
                Lesson(
                    teacher_id=case["teacher_id"],
                    student_id=case["active_student_id"],
                    subject="Математика",
                    topic="Синтетическая запись для CHECK constraint",
                    start_at=datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc),
                    end_at=datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc),
                    status="invalid-status",
                )
            )

    event.listen(Session, "before_commit", add_invalid_status_before_commit)
    try:
        response = create_lesson(case, student_id=case["active_student_id"])
    finally:
        event.remove(Session, "before_commit", add_invalid_status_before_commit)

    assert response.status_code == 422
    assert response.json()["detail"] == "Данные нарушают ограничения"
    assert lesson_count(case) == 0


def test_a_sch_20_schedule_page_renders_created_lesson(schedule_case):
    """A-SCH-20: the schedule page renders the current teacher's calendar event."""
    case = schedule_case
    created = create_lesson(case, student_id=case["active_student_id"])
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]

    response = case["client"].get("/schedule")
    assert response.status_code == 200, response.text
    assert 'data-calendar-events' in response.text
    assert f'lesson-{lesson_id}' in response.text