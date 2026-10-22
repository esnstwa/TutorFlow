from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import services
from app.core.database import Base, get_db
from app.main import app
from app.models import Lesson, Student, User

MOSCOW = ZoneInfo("Europe/Moscow")
NOW = datetime(2035, 1, 12, 13, 0, tzinfo=MOSCOW)


@pytest.fixture
def dashboard(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(services, "datetime", Clock)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def database():
        with sessions() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    with TestClient(app) as client, sessions() as db:
        result = client.post("/api/auth/register", headers={"X-TutorFlow-Request": "auth"}, json={
            "first_name": "Лидия", "email": "dashboard@example.com", "role": "teacher",
            "password": "Dashboard-Test-493!", "password_confirmation": "Dashboard-Test-493!",
        })
        assert result.status_code == 201, result.text
        teacher = db.get(User, result.json()["user"]["id"])
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        student = Student(teacher_id=teacher.id, first_name="Игорь", last_name="Соколов", subject="Физика", grade="10 класс")
        db.add(student)
        db.commit()

        def lesson(start, end, status="scheduled", topic="Динамика", owner=None):
            row = Lesson(teacher_id=(owner or teacher).id, student_id=student.id,
                         subject="Физика", topic=topic, start_at=start, end_at=end, status=status)
            db.add(row)
            db.commit()
            return row

        yield client, db, teacher, lesson
    engine.dispose()


@pytest.mark.parametrize("status,start,end", [
    ("scheduled", NOW - timedelta(hours=2), NOW - timedelta(hours=1)),
    ("scheduled", NOW - timedelta(hours=1), NOW),
    ("cancelled", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
    ("completed_paid", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
    ("completed_unpaid", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
])
def test_dashboard_has_no_fallback_to_ineligible_lesson(dashboard, status, start, end):
    client, db, teacher, add_lesson = dashboard
    add_lesson(start, end, status)

    data = services.cabinet_data(db, teacher)
    assert data["next_lesson"] is None
    assert not any(row["is_next"] for row in data["lessons"])
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Ближайших занятий нет" in page.text
    assert "data-lesson-countdown" not in page.text


def test_dashboard_without_lessons_has_no_countdown_or_sample_data(dashboard):
    client, _, _, _ = dashboard
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Ближайших занятий нет" in page.text
    assert "data-lesson-countdown" not in page.text
    assert "Лидия" in page.text
    for sample in ("Через 1 ч 20 мин", "Математика", "Анна", "Всё под контролем!"):
        assert sample not in page.text


@pytest.mark.parametrize("delta,label", [
    (timedelta(hours=2, minutes=7), "Через 2 ч 7 мин"),
    (timedelta(days=1, hours=2), "Через 1 д 2 ч"),
    (timedelta(seconds=30), "Менее минуты"),
    (timedelta(0), "Идёт занятие"),
    (timedelta(minutes=-15), "Идёт занятие"),
])
def test_dashboard_selects_current_lesson_and_computes_countdown(dashboard, delta, label):
    client, db, teacher, add_lesson = dashboard
    add_lesson(NOW - timedelta(hours=3), NOW - timedelta(hours=2))
    add_lesson(NOW + timedelta(minutes=1), NOW + timedelta(hours=1), "cancelled")
    chosen = add_lesson(NOW + delta, NOW + delta + timedelta(hours=1))
    add_lesson(NOW + timedelta(days=3), NOW + timedelta(days=3, hours=1))
    chosen.subject = "Астрономия"
    db.commit()

    data = services.cabinet_data(db, teacher)
    assert data["next_lesson"]["id"] == chosen.id
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert label in page.text
    assert f'data-start-at="{chosen.start_at.isoformat()}"' in page.text
    assert f'data-end-at="{chosen.end_at.isoformat()}"' in page.text
    assert "Астрономия" in page.text
    assert "Сегодня, " not in page.text
    assert 'href="http://testserver/schedule"' in page.text
    assert f'href="http://testserver/lessons/{chosen.id}"' in page.text


def test_dashboard_uses_moscow_wall_time_after_database_reload(dashboard):
    client, db, _, add_lesson = dashboard
    # 12:30 Moscow is 09:30 UTC: the lesson ended before NOW (10:00 UTC).
    add_lesson(NOW - timedelta(hours=1), NOW - timedelta(minutes=30))
    chosen = add_lesson(NOW + timedelta(hours=1), NOW + timedelta(hours=2))
    db.expire_all()
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Через 1 ч" in page.text
    assert f'data-start-at="{chosen.start_at.isoformat()}+03:00"' in page.text


def test_dashboard_shows_full_date_across_year_boundary(dashboard):
    client, _, _, add_lesson = dashboard
    add_lesson(datetime(2036, 1, 2, 10, 0, tzinfo=MOSCOW), datetime(2036, 1, 2, 11, 0, tzinfo=MOSCOW))
    assert "2 января 2036" in client.get("/dashboard").text


def test_dashboard_never_uses_another_teachers_lesson(dashboard):
    client, db, teacher, add_lesson = dashboard
    other = User(email="other-dashboard@example.com", first_name="Олег", last_name="", role="teacher", password_hash="not-a-login")
    db.add(other)
    db.commit()
    add_lesson(NOW + timedelta(minutes=1), NOW + timedelta(hours=1), topic="Чужая тема", owner=other)
    data = services.cabinet_data(db, teacher)
    assert data["next_lesson"] is None
    page = client.get("/dashboard")
    assert "Чужая тема" not in page.text
    assert "Ближайших занятий нет" in page.text


def test_teacher_subject_is_not_invented_when_the_model_has_no_subject(dashboard):
    client, _, teacher, _ = dashboard
    assert services.teacher_dict(teacher)["subject"] == ""
    page = client.get("/profile")
    assert page.status_code == 200
    assert "Лидия" in page.text
    assert "Математика" not in page.text
    assert "Преподаватель ·" not in page.text


def test_dashboard_quick_material_action_does_not_claim_to_upload_a_file(dashboard):
    client, _, _, _ = dashboard
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert 'href="http://testserver/materials"' in page.text
    assert 'data-open-modal="material"' not in page.text
    assert "Загрузить материал" not in page.text


def test_dashboard_reflects_persisted_create_reschedule_and_cancel(dashboard):
    client, db, teacher, _ = dashboard
    student = db.query(Student).filter_by(teacher_id=teacher.id).one()
    created = client.post("/api/lessons", json={
        "student_id": student.id, "topic": "Оптика", "date": "2035-01-12", "start": "14:00", "end": "15:00",
    })
    assert created.status_code == 200, created.text
    lesson_id = created.json()["lesson"]["id"]
    assert "Через 1 ч" in client.get("/dashboard").text

    moved = client.post(f"/api/mock/lessons/{lesson_id}/reschedule", json={"date": "2035-01-13", "start": "14:00"})
    assert moved.status_code == 200, moved.text
    page = client.get("/dashboard")
    assert "13 января 2035" in page.text
    assert "Через 1 д 1 ч" in page.text

    cancelled = client.patch(f"/api/lessons/{lesson_id}", json={"topic": "Оптика", "status": "cancelled", "materials": []})
    assert cancelled.status_code == 200, cancelled.text
    page = client.get("/dashboard")
    assert "Ближайших занятий нет" in page.text
    assert "data-lesson-countdown" not in page.text
    db.expire_all()
    assert db.get(Lesson, lesson_id).status == "cancelled"
