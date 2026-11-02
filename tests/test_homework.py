from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.usefixtures("legacy_cabinet_auth")

from app.core.auth import get_current_student, get_current_teacher
from app.core.database import get_db
from app.main import app
from app.models import Homework, Student, User
from tests.conftest import TestingSessionLocal


client = TestClient(app)


def test_multi_recipient_homework_search_and_lesson_link() -> None:
    second = client.post("/api/students", json={"name": "Мария Иванова", "email": "ivanova@example.test", "subject": "Алгебра", "grade": "8 класс"}).json()["student"]
    search = client.get("/api/students/search?q=Ива")
    assert search.status_code == 200
    assert any(row["id"] == second["id"] for row in search.json()["students"])

    response = client.post("/api/homework", json={"title": "Общее задание", "description": "Решить упражнения", "recipient_ids": [1, second["id"], 1], "lesson_id": 101, "due_at": "2026-12-20T18:00:00+03:00"})
    assert response.status_code == 200
    homework = response.json()["homework"]
    assert homework["recipient_count"] == 2
    assert homework["lesson"]["id"] == 101
    assert client.get(f"/assignments/{homework['id']}").status_code == 200


def test_file_only_homework_and_derived_overdue(tmp_path, monkeypatch) -> None:
    from io import BytesIO
    from pypdf import PdfWriter
    from app.core.config import settings

    monkeypatch.setattr(settings, "file_storage_path", str(tmp_path / "uploads"))
    content = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160)
    writer.write(content)
    uploaded = client.post("/api/files/upload", content=content.getvalue(), headers={"X-Filename": "task.pdf", "Content-Type": "application/pdf"})
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file"]["id"]
    due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post("/api/homework", json={"title": "Файл без описания", "recipient_ids": [1], "attachment_ids": [file_id], "due_at": due})
    assert response.status_code == 200
    recipient = response.json()["homework"]["recipients"][0]
    assert recipient["status_value"] == "OVERDUE"
    assert response.json()["homework"]["counts"]["OVERDUE"] == 1


def test_student_and_teacher_scope_is_enforced() -> None:
    created = client.post("/api/homework", json={"title": "Приватное", "description": "Только адресату", "recipient_ids": [1]}).json()["homework"]
    recipient_id = created["recipients"][0]["id"]
    with TestingSessionLocal() as db:
        teacher = db.get(User, 1)
        stranger_user = User(email="stranger-student@example.test", password_hash="hash", first_name="Чужой", last_name="Ученик", role="student")
        db.add(stranger_user); db.flush()
        stranger = Student(teacher_id=teacher.id, user_id=stranger_user.id, first_name="Чужой", last_name="Ученик", email=stranger_user.email, subject="Математика", grade="7 класс")
        db.add(stranger); db.commit(); stranger_id = stranger.id

    def current_stranger(db=Depends(get_db)):
        return db.get(Student, stranger_id)

    app.dependency_overrides[get_current_student] = current_stranger
    try:
        assert client.get(f"/api/student/homework/{recipient_id}").status_code == 404
        assert client.post(f"/api/student/homework/{recipient_id}/submissions", json={"comment": "Чужой ответ"}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_student, None)

    with TestingSessionLocal() as db:
        other_teacher = User(email="homework-other@example.test", password_hash="hash", first_name="Другой", last_name="Учитель", role="teacher")
        db.add(other_teacher); db.commit(); other_teacher_id = other_teacher.id

    def current_other_teacher(db=Depends(get_db)):
        return db.get(User, other_teacher_id)

    app.dependency_overrides[get_current_teacher] = current_other_teacher
    try:
        assert client.get(f"/api/homework/{created['id']}").status_code == 404
        assert client.post(f"/api/homework-recipients/{recipient_id}/reviews", json={"action": "COMPLETED"}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)


def test_homework_persists_in_new_session() -> None:
    response = client.post("/api/homework", json={"title": "Сохраняемое", "description": "После reload", "recipient_ids": [1]})
    homework_id = response.json()["homework"]["id"]
    with TestingSessionLocal() as db:
        assert db.get(Homework, homework_id).title == "Сохраняемое"
