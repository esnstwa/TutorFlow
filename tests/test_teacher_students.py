"""Teacher student management through real sessions and isolated databases."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import select

from app.models import Homework, HomeworkRecipient, Lesson, Student, User
from app.students.models import StudentInvitation
from tests.test_teacher_schedule import schedule_case


def test_archived_card_rejects_direct_patch_without_changing_data(schedule_case):
    case = schedule_case
    student_id = case["first"]
    assert case["client"].post(f"/api/students/{student_id}/archive").status_code == 200
    before = case["client"].get(f"/api/students/{student_id}").json()["student"]
    response = case["client"].patch(f"/api/students/{student_id}", json={
        "name": "Изменённое Имя", "email": "changed@example.com", "subject": "Другой предмет", "grade": "11", "avatar": "https://example.com/avatar.png",
    })
    assert response.status_code == 409, response.text
    assert case["client"].get(f"/api/students/{student_id}").json()["student"] == before
    assert case["client"].patch(f"/api/students/{student_id}", json={}).status_code == 409


def test_email_change_revokes_invitations_even_with_a_stale_identity_map(schedule_case):
    from app.core.database import get_db
    case = schedule_case
    student_id = case["first"]
    with case["sessions"]() as stale:
        cached = stale.get(Student, student_id)
        original_email = cached.email
        assert case["client"].patch(f"/api/students/{student_id}", json={"email": "new@example.com"}).status_code == 200
        assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 200
        assert cached.email == original_email
        api = case["client"].app
        previous = api.dependency_overrides[get_db]
        api.dependency_overrides[get_db] = lambda: stale
        try:
            response = case["client"].patch(f"/api/students/{student_id}", json={"email": original_email})
            assert response.status_code == 200, response.text
        finally:
            api.dependency_overrides[get_db] = previous
    with case["sessions"]() as db:
        invitation = db.scalar(select(StudentInvitation).where(StudentInvitation.student_id == student_id))
        assert invitation.revoked_at is not None


def test_card_contains_only_this_students_existing_homework_links(schedule_case):
    case = schedule_case
    for student_id, title in ((case["first"], "Задание первого"), (case["second"], "Задание другого")):
        response = case["client"].post("/api/homework", json={"title": title, "description": "Практика", "recipient_ids": [student_id]})
        assert response.status_code == 200, response.text
    foreign = case["foreign"].post("/api/homework", json={"title": "Чужое задание", "description": "Практика", "recipient_ids": [case["foreign_student"]]})
    assert foreign.status_code == 200
    for archived in (False, True):
        if archived:
            assert case["client"].post(f"/api/students/{case['first']}/archive").status_code == 200
        page = case["client"].get(f"/students/{case['first']}")
        assert page.status_code == 200
        assert [row["title"] for row in page.context["student_assignments"]] == ["Задание первого"]


def test_restore_allows_edit_and_preserves_existing_history(schedule_case):
    case = schedule_case
    student_id = case["first"]
    lesson = case["client"].post("/api/lessons", json={"student_id": student_id, "date": "2035-01-15", "start": "10:00", "end": "11:00", "topic": "История ученика"}).json()["lesson"]
    hw = case["client"].post("/api/homework", json={"title": "История заданий", "description": "Сохранить", "recipient_ids": [student_id], "lesson_id": lesson["id"]}).json()["homework"]
    for _ in range(2):
        assert case["client"].post(f"/api/students/{student_id}/archive").json()["student"]["archived"]
    with case["sessions"]() as db:
        archived_at = db.get(Student, student_id).archived_at
    assert case["client"].delete(f"/api/students/{student_id}").status_code == 200
    with case["sessions"]() as db:
        assert db.get(Student, student_id).archived_at == archived_at
        assert db.get(Lesson, lesson["id"]) is not None
        assert db.get(Homework, hw["id"]) is not None
        assert db.scalar(select(HomeworkRecipient.student_id).where(HomeworkRecipient.homework_id == hw["id"])) == student_id
    for _ in range(2):
        result = case["client"].post(f"/api/students/{student_id}/restore")
        assert result.status_code == 200 and not result.json()["student"]["archived"]
    edited = {"name": "Новое Имя", "subject": "Химия", "grade": "11", "email": None, "avatar": None}
    response = case["client"].patch(f"/api/students/{student_id}", json=edited)
    assert response.status_code == 200, response.text
    assert case["client"].get(f"/api/students/{student_id}").json()["student"] == response.json()["student"]
    with case["sessions"]() as db:
        saved = db.get(Student, student_id)
        assert (saved.first_name, saved.last_name, saved.subject, saved.grade, saved.email, saved.archived_at) == ("Новое", "Имя", "Химия", "11", None, None)
    assert case["client"].get(f"/lessons/{lesson['id']}").status_code == 200
    assert case["client"].get(f"/assignments/{hw['id']}").status_code == 200


@pytest.mark.parametrize("method,suffix", [("get", ""), ("patch", ""), ("delete", ""), ("post", "/invite"), ("post", "/archive"), ("post", "/restore")])
def test_foreign_ids_are_not_disclosed_or_mutated(schedule_case, method, suffix):
    case = schedule_case
    student_id = case["first"]
    before = case["client"].get(f"/api/students/{student_id}").json()["student"]
    options = {"json": {"name": "Подмена"}} if method == "patch" else {}
    response = getattr(case["foreign"], method)(f"/api/students/{student_id}{suffix}", **options)
    assert response.status_code == 404
    assert before["name"] not in response.text and before["email"] not in response.text
    assert case["foreign"].get(f"/students/{student_id}").status_code == 404
    assert case["client"].get(f"/api/students/{student_id}").json()["student"] == before


@pytest.mark.parametrize("method,suffix", [("patch", ""), ("delete", ""), ("post", "/archive"), ("post", "/restore"), ("post", "/invite")])
def test_teacher_mutations_require_real_session_role_and_csrf(schedule_case, method, suffix):
    from fastapi.testclient import TestClient
    case = schedule_case
    path = f"/api/students/{case['first']}{suffix}"
    options = {"json": {"name": "Подмена"}} if method == "patch" else {}
    assert getattr(case["student_client"], method)(path, **options).status_code == 403
    with TestClient(case["client"].app) as anonymous:
        assert getattr(anonymous, method)(path, **options).status_code == 401
    csrf = case["client"].headers.pop("X-CSRF-Token")
    try:
        assert getattr(case["client"], method)(path, **options).status_code == 403
    finally:
        case["client"].headers["X-CSRF-Token"] = csrf


def test_reissue_and_accept_keep_existing_invitation_contract(schedule_case):
    case = schedule_case
    student_id = case["first"]
    with case["sessions"]() as db:
        email = db.get(User, case["student_user_id"]).email
    assert case["client"].patch(f"/api/students/{student_id}", json={"email": email}).status_code == 200
    issued = [case["client"].post(f"/api/students/{student_id}/invite").json() for _ in range(2)]
    assert all(row["ok"] and row["student"]["lifecycle"] == "invited" for row in issued)
    old, current = [row["invitation"]["url"].split("#", 1)[1] for row in issued]
    assert old != current
    with case["sessions"]() as db:
        invitations = list(db.scalars(select(StudentInvitation).where(StudentInvitation.student_id == student_id)))
        assert len(invitations) == 2
        assert sum(row.revoked_at is None for row in invitations) == 1
        assert abs((invitations[-1].expires_at - invitations[-1].created_at).total_seconds() - timedelta(days=7).total_seconds()) < 2
        assert all(row.token_hash not in (old, current) for row in invitations)
    assert case["student_client"].post("/api/student/invitations/preview", json={"token": old}).status_code == 422
    assert case["student_client"].post("/api/student/invitations/accept", json={"token": current}).status_code == 200
    assert case["client"].get(f"/api/students/{student_id}").json()["student"]["lifecycle"] == "linked"
    assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 422
    assert case["student_client"].post("/api/student/invitations/accept", json={"token": current}).status_code == 422


def test_archival_and_email_change_permanently_revoke_issued_links(schedule_case):
    case = schedule_case
    student_id = case["first"]
    issued = case["client"].post(f"/api/students/{student_id}/invite").json()
    assert case["client"].patch(f"/api/students/{student_id}", json={"email": "replacement@example.com"}).status_code == 200
    assert case["client"].get(f"/api/students/{student_id}").json()["student"]["lifecycle"] == "unlinked"
    assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 200
    assert case["client"].post(f"/api/students/{student_id}/archive").status_code == 200
    assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 422
    assert case["client"].post(f"/api/students/{student_id}/restore").status_code == 200
    assert case["client"].get(f"/api/students/{student_id}").json()["student"]["lifecycle"] == "unlinked"
    with case["sessions"]() as db:
        assert all(row.revoked_at is not None for row in db.scalars(select(StudentInvitation).where(StudentInvitation.student_id == student_id)))


def test_expiry_and_missing_email_keep_existing_unlinked_semantics(schedule_case):
    case = schedule_case
    student_id = case["first"]
    assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 200
    with case["sessions"]() as db:
        db.scalar(select(StudentInvitation).where(StudentInvitation.student_id == student_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert case["client"].get(f"/api/students/{student_id}").json()["student"]["lifecycle"] == "unlinked"
    assert case["client"].patch(f"/api/students/{student_id}", json={"email": None}).status_code == 200
    assert case["client"].post(f"/api/students/{student_id}/invite").status_code == 422


def test_archive_after_cached_read_still_blocks_writes(schedule_case):
    from app.core.database import get_db
    case = schedule_case
    student_id = case["first"]
    with case["sessions"]() as stale:
        cached = stale.get(Student, student_id)
        name = cached.first_name
        assert case["client"].post(f"/api/students/{student_id}/archive").status_code == 200
        assert cached.archived_at is None
        api = case["client"].app
        previous = api.dependency_overrides[get_db]
        api.dependency_overrides[get_db] = lambda: stale
        try:
            response = case["client"].patch(f"/api/students/{student_id}", json={"name": "Нельзя изменить"})
            assert response.status_code == 409, response.text
        finally:
            api.dependency_overrides[get_db] = previous
    with case["sessions"]() as db:
        saved = db.get(Student, student_id)
        assert saved.archived_at is not None and saved.first_name == name


@pytest.mark.parametrize("data", [[], None, {"teacher_id": 999}, {"user_id": 999}, {"archived_at": None}])
def test_protected_and_non_object_patch_payloads_are_rejected(schedule_case, data):
    case = schedule_case
    path = f"/api/students/{case['first']}"
    before = case["client"].get(path).json()
    response = case["client"].patch(path, content=json.dumps(data), headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert case["client"].get(path).json() == before


def test_create_without_email_is_a_real_unlinked_card(schedule_case):
    case = schedule_case
    result = case["client"].post("/api/students", json={"name": "Без Почты", "email": "", "subject": "Физика", "grade": "10"})
    assert result.status_code == 200, result.text
    row = result.json()["student"]
    assert row["lifecycle"] == "unlinked" and row["email"] == ""
    assert case["client"].get(f"/api/students/{row['id']}").json()["student"] == row
    with case["sessions"]() as db:
        saved = db.get(Student, row["id"])
        assert saved.teacher_id == case["teacher_id"] and saved.user_id is None and saved.email is None
