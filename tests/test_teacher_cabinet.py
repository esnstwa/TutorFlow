from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.usefixtures("legacy_cabinet_auth")

from app.main import app

client = TestClient(app)


def test_teacher_pages_are_available() -> None:
    paths = (
        "/dashboard",
        "/schedule",
        "/students",
        "/students/1",
        "/assignments",
        "/assignments/201",
        "/materials",
        "/lessons/101",
        "/settings",
        "/notifications",
        "/submissions/501",
        "/messages/601",
        "/profile",
    )

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "data-teacher-shell" in response.text
        assert "dashboard.js" in response.text


def test_dashboard_contains_working_navigation(monkeypatch) -> None:
    from datetime import datetime, timezone
    from app import services

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 9, 29, 10, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(services, "datetime", Clock)
    response = client.get("/dashboard")

    assert 'href="http://testserver/schedule"' in response.text
    assert 'href="http://testserver/students/' in response.text
    assert 'href="http://testserver/lessons/' in response.text
    assert 'data-open-modal="lesson"' in response.text
    assert 'aria-current="page"' in response.text


def test_missing_entities_return_not_found() -> None:
    for path in ("/students/999", "/assignments/999", "/lessons/999", "/submissions/999", "/messages/999"):
        assert client.get(path).status_code == 404


def test_mock_entity_creation_updates_list() -> None:
    response = client.post(
        "/api/mock/student",
        json={"name": "Елена Орлова", "email": "elena@example.test", "subject": "Алгебра", "grade": "8 класс"},
    )

    assert response.status_code == 200
    student_id = response.json()["entity"]["id"]
    page = client.get("/students")
    assert "Елена Орлова" in page.text
    assert f"/students/{student_id}" in page.text


def test_mock_entity_validation() -> None:
    response = client.post("/api/mock/material", json={"title": "", "kind": "PDF"})
    assert response.status_code == 422


def test_logout_returns_to_public_page() -> None:
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_schedule_has_interactive_calendar_data() -> None:
    response = client.get("/schedule")

    assert response.status_code == 200
    assert 'data-calendar-view="week"' in response.text
    assert 'data-calendar-events' in response.text
    assert 'data-calendar-filter' in response.text
    assert "data-google" not in response.text
    assert "Google Calendar" not in response.text
    assert "data-lesson-dialog" in response.text
    assert 'value="completed_unpaid"' in response.text
    assert 'maxlength="500"' in response.text
    assert "OAuth" not in response.text
    for name in ("student_id", "date", "start", "end_date", "end", "duration"):
        assert f'name="{name}"' in response.text


def test_lesson_can_be_rescheduled_to_a_free_slot() -> None:
    response = client.post(
        "/api/mock/lessons/109/reschedule",
        json={"date": "2026-10-03", "start": "13:00"},
    )

    assert response.status_code == 200
    assert response.json()["lesson"]["date_iso"] == "2026-10-03"
    assert response.json()["lesson"]["end"] == "14:00"


def test_lesson_reschedule_rejects_a_busy_slot() -> None:
    response = client.post(
        "/api/mock/lessons/104/reschedule",
        json={"date": "2026-09-29", "start": "14:00"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "Это время уже занято"


def test_lesson_details_can_be_updated() -> None:
    response = client.patch(
        "/api/mock/lessons/101",
        json={
            "status": "completed_paid",
            "topic": "Квадратные уравнения: практика",
            "location": "https://meet.example.test/lesson",
            "materials": ["Рабочий лист", "Домашнее задание"],
            "teacher_note": "Разобрать ошибку в задании 4.",
        },
    )

    assert response.status_code == 200
    lesson = response.json()["lesson"]
    assert lesson["status"] == "completed_paid"
    assert lesson["materials"] == ["Рабочий лист", "Домашнее задание"]
    assert lesson["teacher_note"] == "Разобрать ошибку в задании 4."


def test_lesson_update_rejects_invalid_status_and_long_note() -> None:
    base = {"topic": "Тема", "location": "Онлайн", "materials": []}

    invalid_status = client.patch(
        "/api/mock/lessons/102",
        json={**base, "status": "cancelled_by_student", "teacher_note": ""},
    )
    long_note = client.patch(
        "/api/mock/lessons/102",
        json={**base, "status": "scheduled", "teacher_note": "x" * 501},
    )

    assert invalid_status.status_code == 422
    assert long_note.status_code == 422


def test_lesson_can_be_deleted() -> None:
    created = client.post(
        "/api/mock/lesson",
        json={"student_id": "1", "topic": "Временное занятие", "date": "2026-10-04", "start": "12:00", "end": "13:00"},
    )
    lesson_id = created.json()["entity"]["id"]

    response = client.delete(f"/api/mock/lessons/{lesson_id}")

    assert response.status_code == 200
    assert client.get(f"/lessons/{lesson_id}").status_code == 404
