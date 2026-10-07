from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_current_teacher
from app.core.database import get_db
from app.main import app
from app.models import Assignment, Lesson, Student, User
from tests.conftest import TestingSessionLocal

client = TestClient(app)


def test_user_role_and_unique_email() -> None:
    with TestingSessionLocal() as db:
        teacher = User(email="unique@example.test", password_hash="hash", first_name="Ирина", last_name="Лебедева", role="teacher")
        db.add(teacher)
        db.commit()
        assert teacher.role == "teacher"
        db.add(User(email="unique@example.test", password_hash="hash", first_name="Другая", last_name="", role="student"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("duplicate user email was accepted")


def test_student_crud_and_persistence() -> None:
    created = client.post("/api/students", json={"name": "Мария Воронова", "email": "maria@example.test", "subject": "Химия", "grade": "8 класс"})
    assert created.status_code == 200
    student_id = created.json()["student"]["id"]

    updated = client.patch(f"/api/students/{student_id}", json={"grade": "9 класс"})
    assert updated.json()["student"]["grade"] == "9 класс"
    with TestingSessionLocal() as new_session:
        assert new_session.get(Student, student_id).grade == "9 класс"

    assert client.delete(f"/api/students/{student_id}").status_code == 200
    assert client.get(f"/students/{student_id}").status_code == 404


def test_lesson_crud_status_note_and_date_range() -> None:
    created = client.post("/api/lessons", json={"student_id": "1", "topic": "Новая тема", "date": "2026-11-10", "start": "10:00", "end": "11:00"})
    assert created.status_code == 200
    lesson_id = created.json()["lesson"]["id"]

    updated = client.patch(f"/api/mock/lessons/{lesson_id}", json={"status": "completed_unpaid", "topic": "Новая тема", "location": "Кабинет 12", "materials": [], "teacher_note": "Обсудить прогресс"})
    assert updated.status_code == 200
    assert updated.json()["lesson"]["teacher_note"] == "Обсудить прогресс"

    ranged = client.get("/api/lessons?date_from=2026-11-10&date_to=2026-11-10").json()["lessons"]
    assert [item["id"] for item in ranged] == [lesson_id]
    with TestingSessionLocal() as new_session:
        stored = new_session.get(Lesson, lesson_id)
        assert stored.status == "completed_unpaid"
        assert stored.teacher_note == "Обсудить прогресс"

    assert client.delete(f"/api/mock/lessons/{lesson_id}").status_code == 200


def test_assignment_submission_files_multiple_attempts_and_review(tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "file_storage_path", str(tmp_path / "uploads"))
    assignment_response = client.post("/api/assignments", json={"student_id": "1", "title": "Тестовое задание", "due": "2026-12-01"})
    assignment_id = assignment_response.json()["assignment"]["id"]
    file_response = client.post("/api/files/upload", content=b"pdf-content", headers={"X-Filename": "solution.pdf", "X-Title": "Solution.pdf", "Content-Type": "application/pdf"})
    material = file_response.json()["file"]
    material_id = material["id"]
    assert material["size"] == len(b"pdf-content")

    first = client.post(f"/api/assignments/{assignment_id}/submissions", json={"comment": "Первая попытка", "file_ids": [material_id]})
    second = client.post(f"/api/assignments/{assignment_id}/submissions", json={"comment": "Вторая попытка", "file_ids": [material_id]})
    assert first.json()["submission"]["attempt_number"] == 1
    assert second.json()["submission"]["attempt_number"] == 2
    assert second.json()["submission"]["files"][0]["id"] == material_id

    submission_id = second.json()["submission"]["id"]
    review = client.post(f"/api/submissions/{submission_id}/reviews", json={"result": "revision_requested", "score": 6, "max_score": 10, "comment": "Исправить второй пункт"})
    assert review.status_code == 200
    assert review.json()["review"]["result"] == "revision_requested"
    with TestingSessionLocal() as new_session:
        assignment = new_session.get(Assignment, assignment_id)
        assert assignment.status == "revision_requested"

    assert client.delete(f"/api/materials/{material_id}").status_code == 200
    assert not (tmp_path / "uploads" / material["stored_name"]).exists()


def test_teacher_cannot_access_another_teachers_data() -> None:
    with TestingSessionLocal() as db:
        other = User(email="other-teacher@example.test", password_hash="hash", first_name="Ольга", last_name="", role="teacher")
        db.add(other)
        db.commit()
        other_id = other.id

    def other_teacher(db=Depends(get_db)):
        return db.get(User, other_id)

    app.dependency_overrides[get_current_teacher] = other_teacher
    try:
        assert client.get("/students/1").status_code == 404
        assert client.get("/lessons/101").status_code == 404
        assert client.patch("/api/assignments/201", json={"title": "Чужое"}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
