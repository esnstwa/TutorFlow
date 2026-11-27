from contextlib import ExitStack
from datetime import datetime, timedelta
from itertools import count
import json
import re
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import services
from app.auth.router import router as auth_router
from app.core.database import Base, get_db
from app.models import Homework, HomeworkRecipient, Lesson, Student
from app.students.router import router as students_router
from app.web.router import router as web_router
from app.web.templating import STATIC_DIR

NOW = datetime(2035, 1, 12, 13, tzinfo=ZoneInfo("Europe/Moscow"))


@pytest.fixture
def schedule_case(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "app_env", "test")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(services, "datetime", Clock)
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    test_app = FastAPI()
    test_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in (auth_router, students_router, web_router):
        test_app.include_router(router)

    def database():
        with sessions() as db:
            yield db

    test_app.dependency_overrides[get_db] = database
    with ExitStack() as stack:
        identities = count(1)
        def user(role, name):
            client = stack.enter_context(TestClient(test_app))
            result = client.post("/api/auth/register", headers={"X-TutorFlow-Request": "auth"}, json={
                "first_name": name, "email": f"{role}-{next(identities)}@example.com", "role": role,
                "password": "Scheduling-Test-493!", "password_confirmation": "Scheduling-Test-493!",
            })
            assert result.status_code == 201, result.text
            client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
            return client, result.json()["user"]["id"]

        client, teacher_id = user("teacher", "Лидия")
        foreign, _ = user("teacher", "Ольга")
        student_client, student_user_id = user("student", "Игорь")

        def student(owner, name):
            result = owner.post("/api/students", json={"name": name, "email": f"{name.split()[0]}@example.com", "subject": "Физика", "grade": "10 класс"})
            assert result.status_code == 200, result.text
            return result.json()["student"]["id"]

        first = student(client, "Игорь Соколов")
        second = student(client, "Павел Орлов")
        foreign_student = student(foreign, "Денис Петров")
        archived = student(client, "Антон Смирнов")
        assert client.post(f"/api/students/{archived}/archive", json={}).status_code == 200
        yield {"client": client, "foreign": foreign, "student_client": student_client,
               "sessions": sessions, "first": first, "second": second, "foreign_student": foreign_student,
               "archived": archived, "teacher_id": teacher_id, "student_user_id": student_user_id}
    engine.dispose()


def payload(case, **changes):
    return {"student_id": case["first"], "date": "2035-01-13", "start": "10:00", "end": "11:00", "topic": "Оптика", **changes}


def create(case, **changes):
    response = case["client"].post("/api/lessons", json=payload(case, **changes))
    assert response.status_code == 200, response.text
    return response.json()["lesson"]


def test_form_edit_persists_student_interval_and_fields_after_reload(schedule_case):
    case = schedule_case
    lesson = create(case)
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={
        "student_id": case["second"], "date": "2035-01-14", "start": "13:15", "end": "14:45",
        "topic": "Механика", "subject": "Астрономия", "status": "scheduled", "location": "https://example.com/lesson",
        "teacher_note": "Проверить решение", "materials": ["Рабочий лист"],
    })
    assert response.status_code == 200, response.text
    updated = response.json()["lesson"]
    assert (updated["student_id"], updated["date_iso"], updated["start"], updated["end"]) == (case["second"], "2035-01-14", "13:15", "14:45")
    assert updated["subject"] == "Астрономия"
    assert updated["meeting_url"] == "https://example.com/lesson"
    assert updated["materials"] == ["Рабочий лист"]
    with case["sessions"]() as db:
        saved = db.get(Lesson, lesson["id"])
        assert saved.end_at - saved.start_at == timedelta(minutes=90)
        assert saved.student_id == case["second"]
        assert saved.teacher_note == "Проверить решение"
    detail = case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"]
    assert detail == updated
    page = case["client"].get("/schedule")
    assert page.status_code == 200
    embedded = re.search(r'data-calendar-events>(.*?)</script>', page.text, re.S)
    assert embedded is not None
    events = json.loads(embedded.group(1))
    assert events[0]["lesson"]["topic"] == "Механика"
    assert events[0]["subtitle"] == "Астрономия · Механика"
    assert "Механика" in case["client"].get("/dashboard").text


@pytest.mark.parametrize("route", ["/api/lessons/{id}", "/api/mock/lessons/{id}"])
@pytest.mark.parametrize("fields", [
    {"date": "2035-01-13", "start": "11:30", "end": "12:30"},
    {"student_id": "foreign_student"}, {"student_id": "archived"},
    {"start": "11:00", "end": "10:00"}, {"start": "10:00", "end": "10:00"},
    {"date": "not-a-date"}, {"start": "10:00+02:00"}, {"student_id": True},
    {"topic": "x" * 201}, {"location": "x" * 301},
])
def test_invalid_edits_are_atomic(schedule_case, route, fields):
    case = schedule_case
    lesson, before = seed_lessons_with_controls(case)
    fields = {key: case.get(value, value) if isinstance(value, str) else value for key, value in fields.items()}
    response = case["client"].patch(
        route.format(id=lesson["id"]), json={"status": "completed_paid", "topic": "Механика", **fields}
    )
    assert response.status_code == 422, response.text
    assert lesson_snapshot(case["sessions"]) == before
    after = case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"]
    assert after == lesson


@pytest.mark.parametrize("status", ["scheduled", "completed_unpaid", "completed_paid", "cancelled"])
def test_status_only_patch_preserves_fields_and_current_conflict_semantics(schedule_case, status):
    case = schedule_case
    lesson = create(case, teacher_note="Private", location="Кабинет", materials=["Лист"])
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={"status": status})
    assert response.status_code == 200, response.text
    result = response.json()["lesson"]
    for field in ("student_id", "date_iso", "start", "end", "topic", "subject", "materials", "teacher_note", "location"):
        assert result[field] == lesson[field]
    assert result["status"] == status
    conflict = case["client"].post("/api/lessons", json=payload(case, start="10:30", end="11:30"))
    assert conflict.status_code == 422
    assert conflict.json()["detail"] == "Это время уже занято"


def test_status_only_patch_preserves_distinct_meeting_link(schedule_case):
    case = schedule_case
    lesson = create(case, location="https://example.com/location", meeting_url="https://example.com/meeting")
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={"status": "completed_paid"})
    assert response.status_code == 200, response.text
    updated = response.json()["lesson"]
    assert updated["location"] == lesson["location"]
    assert updated["meeting_url"] == "https://example.com/meeting"
    assert case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"] == updated


@pytest.mark.parametrize("start,end", [("09:00", "10:00"), ("11:00", "12:00")])
def test_touching_boundaries_allowed_for_create_and_edit(schedule_case, start, end):
    case = schedule_case
    create(case)
    other = create(case, start=start, end=end)
    response = case["client"].patch(f"/api/lessons/{other['id']}", json={"start": start, "end": end})
    assert response.status_code == 200


def test_reschedule_alias_preserves_duration_across_midnight_and_returns_explicit_offsets(schedule_case):
    case = schedule_case
    lesson = create(case, start="20:00", end="21:30")
    response = case["client"].post(f"/api/lessons/{lesson['id']}/reschedule", json={"date": "2035-01-13", "start": "23:30"})
    assert response.status_code == 200, response.text
    result = response.json()["lesson"]
    assert result["end_date_iso"] == "2035-01-14"
    assert result["start_at"] == "2035-01-13T23:30:00+03:00"
    assert result["end_at"] == "2035-01-14T01:00:00+03:00"
    assert (result["start"], result["end"]) == ("23:30", "01:00")
    listed = case["client"].get("/api/lessons?date_from=2035-01-14&date_to=2035-01-14").json()["lessons"]
    assert [row["id"] for row in listed] == [lesson["id"]]
    blocked = case["client"].post("/api/lessons", json=payload(case, date="2035-01-14", start="00:30", end="01:30"))
    assert blocked.status_code == 422
    case["client"].patch(f"/api/lessons/{lesson['id']}", json={"end_date": "2035-01-14", "end": "02:00"}).raise_for_status()
    with case["sessions"]() as db:
        row = db.get(Lesson, lesson["id"])
        assert row.end_at - row.start_at == timedelta(minutes=150)


@pytest.mark.parametrize("new_date", ["2035-01-13", "2035-01-16"])
def test_date_only_patch_preserves_cross_midnight_day_offset(schedule_case, new_date):
    case = schedule_case
    lesson = create(case, start="23:30", end="01:00", end_date="2035-01-14")
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={"date": new_date})
    assert response.status_code == 200, response.text
    updated = response.json()["lesson"]
    if new_date == lesson["date_iso"]:
        assert updated == lesson
    expected_end = (datetime.fromisoformat(new_date) + timedelta(days=1)).date().isoformat()
    assert (updated["date_iso"], updated["end_date_iso"], updated["start"], updated["end"]) == (new_date, expected_end, "23:30", "01:00")
    assert case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"] == updated
    with case["sessions"]() as db:
        saved = db.get(Lesson, lesson["id"])
        assert saved.end_at - saved.start_at == timedelta(minutes=90)


def test_review_calendar_event_has_explicit_midnight_end_date(schedule_case):
    case = schedule_case
    response = case["client"].post("/api/homework", json={"title": "Практика", "description": "Решить", "recipient_ids": [case["first"]]})
    assert response.status_code == 200, response.text
    with case["sessions"]() as db:
        recipient = db.scalar(select(HomeworkRecipient).where(HomeworkRecipient.homework_id == response.json()["homework"]["id"]))
        recipient.status = "SUBMITTED"
        recipient.submitted_at = NOW.replace(hour=23, minute=30)
        db.commit()
    page = case["client"].get("/schedule")
    assert page.status_code == 200
    embedded = re.search(r'data-calendar-events>(.*?)</script>', page.text, re.S)
    assert embedded is not None
    events = json.loads(embedded.group(1))
    review = next(row for row in events if row["type"] == "reviews")
    assert (review["date"], review["start"], review["end_date"], review["end"]) == ("2035-01-12", "23:00", "2035-01-13", "00:00")


def test_create_explicit_end_date_and_offset_aware_output(schedule_case):
    lesson = create(schedule_case, start="23:45", end="00:15", end_date="2035-01-14")
    assert lesson["end_date_iso"] == "2035-01-14"
    assert lesson["start_at"].endswith("+03:00")
    assert lesson["end_at"].endswith("+03:00")


@pytest.mark.parametrize("method,suffix", [("get", ""), ("patch", ""), ("delete", ""), ("post", "/reschedule")])
def test_foreign_lesson_is_inaccessible_and_cannot_be_mutated(schedule_case, method, suffix):
    case = schedule_case
    lesson = create(case)
    options = {} if method in {"get", "delete"} else {"json": {"date": "2035-01-15", "start": "12:00", "topic": "Чужое", "status": "cancelled"}}
    response = getattr(case["foreign"], method)(f"/api/lessons/{lesson['id']}{suffix}", **options)
    assert response.status_code in {404, 422}, response.text
    assert case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"] == lesson
    assert not case["foreign"].get("/api/lessons").json()["lessons"]


def lesson_snapshot(sessions):
    """Read all persisted lesson columns in a fresh session."""
    table = Lesson.__table__
    with sessions() as db:
        return {row["id"]: dict(row) for row in db.execute(select(table)).mappings()}


def seed_lessons_with_controls(case):
    lesson = create(case, location="Кабинет", teacher_note="Сохранить после переноса")
    own = create(case, student_id=case["second"], start="12:00", end="13:00", topic="Акустика")
    response = case["foreign"].post(
        "/api/lessons", json=payload(case, student_id=case["foreign_student"], topic="Динамика")
    )
    assert response.status_code == 200, response.text
    foreign = response.json()["lesson"]
    before = lesson_snapshot(case["sessions"])
    assert set(before) == {lesson["id"], own["id"], foreign["id"]}
    assert len(before) == 3
    assert before[lesson["id"]]["teacher_id"] == before[own["id"]]["teacher_id"] == case["teacher_id"]
    assert before[foreign["id"]]["teacher_id"] != case["teacher_id"]
    return lesson, before


@pytest.mark.parametrize("route,method", [
    ("/api/lessons", "POST"),
    ("/api/mock/lesson", "POST"),
    ("/api/lessons/{id}", "PATCH"),
    ("/api/mock/lessons/{id}", "PATCH"),
    ("/api/lessons/{id}/reschedule", "POST"),
    ("/api/mock/lessons/{id}/reschedule", "POST"),
    ("/api/lessons/{id}", "DELETE"),
    ("/api/mock/lessons/{id}", "DELETE"),
])
def test_session_role_and_csrf_protections_cover_schedule_mutations(schedule_case, route, method):
    case = schedule_case
    lesson, before = seed_lessons_with_controls(case)
    path = route.format(id=lesson["id"])
    client = case["client"]
    same_origin = {"Origin": str(client.base_url), "Sec-Fetch-Site": "same-origin"}
    if "{id}" not in route:
        data = {"json": payload(case, start="14:00", end="15:00")}
    elif route.endswith("/reschedule"):
        data = {"json": {"date": "2035-01-14", "start": "12:00"}}
    elif method == "PATCH":
        data = {"json": {"topic": "Механика"}}
    else:
        data = {}
    valid_token = client.headers.pop("X-CSRF-Token")

    for headers in (
        same_origin,
        {**same_origin, "X-CSRF-Token": "invalid-test-token"},
        {"Origin": "https://other.example", "X-CSRF-Token": valid_token},
    ):
        response = client.request(method, path, headers=headers, **data)
        assert response.status_code == 403
        assert lesson_snapshot(case["sessions"]) == before

    student = case["student_client"]
    assert student.request(method, path, headers=same_origin, **data).status_code == 403
    assert lesson_snapshot(case["sessions"]) == before
    with TestClient(client.app) as anonymous:
        assert anonymous.request(method, path, headers=same_origin, **data).status_code == 401
    assert lesson_snapshot(case["sessions"]) == before

    response = client.request(
        method, path, headers={**same_origin, "X-CSRF-Token": valid_token}, **data
    )
    assert response.status_code == 200
    after = lesson_snapshot(case["sessions"])
    lesson_id = lesson["id"]
    if "{id}" not in route:
        added_ids = after.keys() - before.keys()
        assert len(added_ids) == 1
        added_id = added_ids.pop()
        saved = after.pop(added_id)
        assert after == before
        assert saved["teacher_id"] == case["teacher_id"]
        assert saved["student_id"] == case["first"]
        assert saved["subject"] == "Физика"
        assert saved["topic"] == "Оптика"
        assert saved["status"] == "scheduled"
        assert saved["start_at"] == datetime(2035, 1, 13, 14)
        assert saved["end_at"] == datetime(2035, 1, 13, 15)
        assert (saved["location"], saved["meeting_url"], saved["teacher_note"]) == ("", None, "")
    elif method == "DELETE":
        assert after == {key: row for key, row in before.items() if key != lesson_id}
    else:
        assert after.keys() == before.keys()
        for key in before.keys() - {lesson_id}:
            assert after[key] == before[key]
        previous = {key: value for key, value in before[lesson_id].items() if key != "updated_at"}
        current = {key: value for key, value in after[lesson_id].items() if key != "updated_at"}
        if route.endswith("/reschedule"):
            duration = previous["end_at"] - previous["start_at"]
            start_at = datetime(2035, 1, 14, 12)
            assert current == {**previous, "start_at": start_at, "end_at": start_at + duration}
        else:
            assert current == {**previous, "topic": "Механика"}


@pytest.mark.parametrize("fields", [
    {"start": "11:00", "end": "10:00"},
    {"start": "10:00", "end": "10:00"},
    {"student_id": "foreign_student"},
    {"student_id": "archived"},
    {"status": "unknown"},
    {"topic": "   "},
    {"teacher_note": "x" * 501},
], ids=["reversed", "equal", "foreign", "archived", "unknown-status", "blank-topic", "note-501"])
def test_creation_rejects_invalid_schedule_without_inserting(schedule_case, fields):
    case = schedule_case
    create(case)
    before = lesson_snapshot(case["sessions"])
    fields = {key: case[value] if key == "student_id" else value for key, value in fields.items()}
    response = case["client"].post(
        "/api/lessons", json=payload(case, date="2035-01-14", **fields)
    )
    assert response.status_code == 422
    if "student_id" in fields:
        assert response.json() == {"detail": "Ученик не найден"}
    elif "start" in fields:
        assert response.json() == {"detail": "Окончание занятия должно быть позже начала"}
    assert lesson_snapshot(case["sessions"]) == before


@pytest.mark.parametrize("fields,subject", [
    ({}, "Физика"),
    ({"subject": "Астрономия"}, "Астрономия"),
])
def test_created_lesson_subject_and_optional_field_contract(schedule_case, fields, subject):
    lesson = create(schedule_case, **fields)
    expected = {"subject": subject, "status": "scheduled", "location": "", "meeting_url": None}
    assert {key: lesson[key] for key in expected} == expected
    saved = lesson_snapshot(schedule_case["sessions"])[lesson["id"]]
    assert {key: saved[key] for key in expected} == expected
    assert schedule_case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"] == lesson


@pytest.mark.parametrize("subject", ["", "  ", None])
def test_create_rejects_explicitly_invalid_subject(schedule_case, subject):
    before = lesson_snapshot(schedule_case["sessions"])
    response = schedule_case["client"].post("/api/lessons", json=payload(schedule_case, subject=subject))
    assert response.status_code == 422
    assert lesson_snapshot(schedule_case["sessions"]) == before


@pytest.mark.parametrize("source_headers,has_token,expected_status", [
    ({}, True, 200),
    ({}, False, 403),
    ({"Origin": "http://testserver"}, True, 200),
    ({"Sec-Fetch-Site": "same-origin"}, True, 200),
    ({"Sec-Fetch-Site": "none"}, True, 200),
    ({"Sec-Fetch-Site": "cross-site"}, True, 403),
])
def test_schedule_edit_source_metadata(schedule_case, source_headers, has_token, expected_status):
    case = schedule_case
    lesson, before = seed_lessons_with_controls(case)
    client = case["client"]
    if not has_token:
        client.headers.pop("X-CSRF-Token")
    lesson_id = lesson["id"]
    response = client.patch(f"/api/lessons/{lesson_id}", headers=source_headers, json={"topic": "Механика"})
    assert response.status_code == expected_status, response.text
    after = lesson_snapshot(case["sessions"])
    if expected_status == 200:
        expected = {**before[lesson_id], "topic": "Механика", "updated_at": after[lesson_id]["updated_at"]}
        assert after == {**before, lesson_id: expected}
    else:
        assert after == before


def test_created_lesson_with_maximum_note_persists_and_appears_in_calendar(schedule_case):
    case = schedule_case
    note = "я" * 500
    lesson = create(case, teacher_note=note)
    with case["sessions"]() as db:
        saved = db.get(Lesson, lesson["id"])
        assert saved.student_id == case["first"]
        assert saved.end_at - saved.start_at == timedelta(hours=1)
        assert (saved.topic, saved.status, saved.teacher_note) == ("Оптика", "scheduled", note)
        assert saved.location == ""
        assert saved.meeting_url is None

    assert case["client"].get(f"/api/lessons/{lesson['id']}").json()["lesson"] == lesson
    page = case["client"].get("/schedule")
    assert page.status_code == 200
    embedded = re.search(r'data-calendar-events>(.*?)</script>', page.text, re.S)
    assert embedded is not None
    events = json.loads(embedded.group(1))
    assert [entry["lesson"]["id"] for entry in events if entry["type"] == "lessons"] == [lesson["id"]]


def test_schedule_page_redirects_unauthenticated_browser(schedule_case):
    with TestClient(schedule_case["client"].app) as anonymous:
        response = anonymous.get("/schedule", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/login"


def test_delete_preserves_assigned_homework_and_its_recipients(schedule_case):
    case = schedule_case
    lesson = create(case)
    result = case["client"].post("/api/homework", json={"title": "Практика", "description": "Решить", "recipient_ids": [case["first"]], "lesson_id": lesson["id"]})
    assert result.status_code == 200, result.text
    homework_id = result.json()["homework"]["id"]
    assert case["client"].delete(f"/api/lessons/{lesson['id']}").status_code == 200
    assert case["client"].get(f"/api/lessons/{lesson['id']}").status_code == 404
    with case["sessions"]() as db:
        homework = db.get(Homework, homework_id)
        assert homework.lesson_id is None
        assert db.scalar(select(HomeworkRecipient.student_id).where(HomeworkRecipient.homework_id == homework_id)) == case["first"]


@pytest.mark.parametrize("data", [[], None, {"student_id": []}, {"student_id": 10**100}, {"start": "bad"}])
def test_malformed_requests_fail_cleanly_without_insert(schedule_case, data):
    case = schedule_case
    response = case["client"].post("/api/lessons", content="null" if data is None else json.dumps(data), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert case["client"].get("/api/lessons").json()["lessons"] == []


def test_student_homework_lesson_reference_stays_compatible_and_private(schedule_case):
    case = schedule_case
    with case["sessions"]() as db:
        db.get(Student, case["first"]).user_id = case["student_user_id"]
        db.commit()
    lesson = create(case, teacher_note="PRIVATE-SCHEDULING-NOTE")
    homework = case["client"].post("/api/homework", json={"title": "Практика", "description": "Решить", "recipient_ids": [case["first"]], "lesson_id": lesson["id"]})
    assert homework.status_code == 200, homework.text
    before = case["student_client"].get("/api/student/homework").json()["assignments"][0]
    assert set(before["homework"]["lesson"]) == {"id", "subject", "topic", "date"}
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={"student_id": case["second"], "date": "2035-01-15", "subject": "Механика", "topic": "Силы"})
    assert response.status_code == 200, response.text
    after = case["student_client"].get("/api/student/homework")
    assert after.status_code == 200
    row = after.json()["assignments"][0]
    assert row["id"] == before["id"]
    assert row["homework"]["lesson"] == {"id": lesson["id"], "subject": "Механика", "topic": "Силы", "date": "15.01.2035"}
    assert "PRIVATE-SCHEDULING-NOTE" not in after.text and "teacher_note" not in after.text
    assert case["client"].delete(f"/api/lessons/{lesson['id']}").status_code == 200
    after_delete = case["student_client"].get("/api/student/homework").json()["assignments"][0]
    assert after_delete["id"] == before["id"] and after_delete["homework"]["lesson"] is None


def test_existing_archived_student_lesson_can_still_be_managed(schedule_case):
    case = schedule_case
    lesson = create(case)
    assert case["client"].post(f"/api/students/{case['first']}/archive", json={}).status_code == 200
    response = case["client"].patch(f"/api/lessons/{lesson['id']}", json={"status": "cancelled", "date": "2035-01-16"})
    assert response.status_code == 200, response.text
    assert response.json()["lesson"]["date_iso"] == "2035-01-16"
