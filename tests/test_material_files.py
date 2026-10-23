from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import FileResource, Student
from tests.test_teacher_schedule import schedule_case


@pytest.fixture
def files_case(schedule_case, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_storage_path", str(tmp_path / "uploads"))
    return schedule_case


def test_json_metadata_cannot_claim_a_server_file(files_case):
    response = files_case["client"].post("/api/materials", json={
        "title": "Подмена", "original_name": "private.txt", "path": "../private.txt",
        "stored_name": "private.txt", "mime_type": "text/plain", "size": 7,
    })
    assert response.status_code == 422, response.text
    with files_case["sessions"]() as db:
        assert list(db.scalars(select(FileResource))) == []


def test_valid_metadata_only_material_remains_supported(files_case):
    response = files_case["client"].post("/api/materials", json={
        "title": "Методические заметки", "kind": "Запись", "description": "Описание",
    })
    assert response.status_code == 200, response.text
    assert response.json()["material"]["title"] == "Методические заметки"


def saved_file(case, *, owner_id=None, content=b"Lesson notes\n", name="notes.txt"):
    from app.storage import store_bytes

    stored_name, path = store_bytes(name, content)
    with case["sessions"]() as db:
        item = FileResource(owner_id=owner_id or case["teacher_id"], original_name=name,
                            stored_name=stored_name, storage_path=path, size=len(content),
                            mime_type="text/plain", title="Заметки", kind="Файл")
        db.add(item)
        db.commit()
        return item.id, Path(path)


def test_canonical_metadata_has_no_server_path(files_case):
    file_id, path = saved_file(files_case)
    response = files_case["client"].get(f"/api/files/{file_id}")
    assert response.status_code == 200, response.text
    info = response.json()["file"]
    assert info["id"] == file_id
    assert info["download_url"] == f"/api/files/{file_id}/download"
    assert info["preview_url"] == f"/api/files/{file_id}/preview"
    assert not {"path", "storage_path", "stored_name"}.intersection(info)
    assert str(path.parent) not in response.text


def test_student_sees_only_explicitly_shared_material_and_loses_access_on_detach(files_case):
    from app.models import Lesson
    from tests.test_teacher_schedule import create

    file_id, _ = saved_file(files_case)
    student = files_case["student_client"]
    assert student.get(f"/api/files/{file_id}").status_code == 404
    with files_case["sessions"]() as db:
        db.get(Student, files_case["first"]).user_id = files_case["student_user_id"]
        db.commit()
    lesson = create(files_case)
    assert files_case["client"].post(f"/api/lessons/{lesson['id']}/materials/{file_id}").status_code == 200
    response = student.get(f"/api/files/{file_id}")
    assert response.status_code == 200, response.text
    assert not {"lessons", "homeworks", "path", "stored_name"}.intersection(response.json()["file"])
    assert files_case["foreign"].get(f"/api/files/{file_id}").status_code == 404
    assert files_case["client"].delete(f"/api/lessons/{lesson['id']}/materials/{file_id}").status_code == 200
    assert student.get(f"/api/files/{file_id}").status_code == 404


def test_metadata_requires_session(files_case):
    file_id, _ = saved_file(files_case)
    files_case["client"].cookies.clear()
    assert files_case["client"].get(f"/api/files/{file_id}").status_code == 401


def test_download_is_authorized_attachment_without_shared_cache(files_case):
    file_id, _ = saved_file(files_case, name="Заметки.txt")
    response = files_case["client"].get(f"/api/files/{file_id}/download")
    assert response.status_code == 200, response.text
    assert response.content == b"Lesson notes\n"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert "sandbox" in response.headers["content-security-policy"]
    assert files_case["foreign"].get(f"/api/files/{file_id}/download").status_code == 404
    assert files_case["student_client"].get(f"/api/files/{file_id}/download").status_code == 404
    files_case["client"].cookies.clear()
    assert files_case["client"].get(f"/api/files/{file_id}/download").status_code == 401


def test_missing_and_unsafe_paths_return_controlled_not_found(files_case, tmp_path):
    file_id, path = saved_file(files_case)
    path.unlink()
    assert files_case["client"].get(f"/api/files/{file_id}").json()["file"]["missing_file"] is True
    assert files_case["client"].get(f"/api/files/{file_id}/download").status_code == 404
    outside = tmp_path / "private.txt"
    outside.write_text("DO-NOT-DISCLOSE", encoding="utf-8")
    with files_case["sessions"]() as db:
        db.get(FileResource, file_id).storage_path = str(outside)
        db.commit()
    response = files_case["client"].get(f"/api/files/{file_id}/download")
    assert response.status_code == 404
    assert b"DO-NOT-DISCLOSE" not in response.content


def link_student(case):
    with case["sessions"]() as db:
        db.get(Student, case["first"]).user_id = case["student_user_id"]
        db.commit()


def create_homework(case):
    response = case["client"].post("/api/homework", json={
        "recipient_ids": [case["first"]], "title": "Задачи", "description": "Решить",
        "due_at": "2035-01-15T18:00:00+03:00",
    })
    assert response.status_code == 200, response.text
    return response.json()["homework"]


def test_assigned_homework_grants_and_detach_revokes_file_access(files_case):
    file_id, _ = saved_file(files_case)
    link_student(files_case)
    homework = create_homework(files_case)
    route = f"/api/homework/{homework['id']}/materials/{file_id}"
    assert files_case["student_client"].get(f"/api/files/{file_id}").status_code == 404
    assert files_case["client"].post(route).status_code == 200
    response = files_case["student_client"].get(f"/api/files/{file_id}/download")
    assert response.status_code == 200, response.text
    assert response.content == b"Lesson notes\n"
    assert files_case["client"].delete(route).status_code == 200
    assert files_case["student_client"].get(f"/api/files/{file_id}").status_code == 404


def test_teacher_can_read_only_files_explicitly_submitted_to_them(files_case):
    link_student(files_case)
    homework = create_homework(files_case)
    student = files_case["student_client"]
    uploaded = student.post("/api/student/files/upload", content=b"My answer\n", headers={
        "X-Filename": "answer.txt", "Content-Type": "text/plain",
    })
    assert uploaded.status_code == 200, uploaded.text
    file_id = uploaded.json()["file"]["id"]
    assert files_case["client"].get(f"/api/files/{file_id}").status_code == 404
    recipient_id = homework["recipients"][0]["id"]
    submitted = student.post(f"/api/student/homework/{recipient_id}/submissions", json={
        "comment": "Готово", "attachment_ids": [file_id],
    })
    assert submitted.status_code == 200, submitted.text
    response = files_case["client"].get(f"/api/files/{file_id}/download")
    assert response.status_code == 200, response.text
    assert response.content == b"My answer\n"
    assert files_case["foreign"].get(f"/api/files/{file_id}").status_code == 404


def test_teacher_material_metadata_includes_safe_actions_and_related_lessons(files_case):
    from tests.test_teacher_schedule import create

    file_id, _ = saved_file(files_case)
    before = files_case["client"].get(f"/api/materials/{file_id}").json()["material"]
    assert before["has_file"] is True
    assert before["availability"] == "private"
    lesson = create(files_case)
    assert files_case["client"].post(f"/api/lessons/{lesson['id']}/materials/{file_id}").status_code == 200
    after = files_case["client"].get(f"/api/materials/{file_id}").json()["material"]
    assert after["availability"] == "shared"
    assert after["lessons"][0]["id"] == lesson["id"]
    assert after["lessons"][0]["url"] == f"/lessons/{lesson['id']}"
    assert after["download_url"] == f"/api/files/{file_id}/download"


def test_materials_page_supplies_owned_attachment_options_and_limit(files_case):
    from tests.test_teacher_schedule import create

    lesson = create(files_case)
    foreign_lesson = create({**files_case, "client": files_case["foreign"], "first": files_case["foreign_student"]})
    homework = create_homework(files_case)
    page = files_case["client"].get("/materials")
    assert page.status_code == 200, page.text
    assert [row["id"] for row in page.context["material_lessons"]] == [lesson["id"]]
    assert foreign_lesson["id"] not in {row["id"] for row in page.context["material_lessons"]}
    assert [row["id"] for row in page.context["material_homeworks"]] == [homework["id"]]
    assert page.context["material_upload_max_bytes"] == settings.file_upload_max_bytes


def test_teacher_upload_streams_real_bytes_without_request_body(files_case, monkeypatch):
    from starlette.requests import Request
    from urllib.parse import quote

    async def forbidden_body(_):
        raise AssertionError("upload must stream instead of buffering request.body")

    monkeypatch.setattr(Request, "body", forbidden_body)
    content = "Упражнение 1\n".encode("utf-8")
    response = files_case["client"].post("/api/files/upload", content=content, headers={
        "X-Filename": quote("Упражнения.txt"), "X-Title": quote("Рабочий лист"),
        "Content-Type": "text/plain",
    })
    assert response.status_code == 200, response.text
    row = response.json()["file"]
    assert row["title"] == "Рабочий лист"
    assert row["original_name"] == "Упражнения.txt"
    assert row["mime_type"] == "text/plain" and row["size"] == len(content)
    with files_case["sessions"]() as db:
        saved = db.get(FileResource, row["id"])
        assert Path(saved.storage_path).read_bytes() == content
        assert saved.owner_id == files_case["teacher_id"]
    assert files_case["client"].get(row["download_url"]).content == content
    assert files_case["client"].get(f"/api/files/{row['id']}").json()["file"]["size"] == len(content)


def test_preview_uses_verified_text_and_sandbox_not_client_mime(files_case):
    content = b"<script>alert('not executable')</script>\n"
    file_id, _ = saved_file(files_case, content=content)
    response = files_case["client"].get(f"/api/files/{file_id}/preview")
    assert response.status_code == 200, response.text
    assert response.content == content
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"].startswith("inline;")
    assert "sandbox" in response.headers["content-security-policy"]
    assert files_case["foreign"].get(f"/api/files/{file_id}/preview").status_code == 404


def test_real_pdf_upload_can_download_but_never_preview(files_case):
    from io import BytesIO
    from pypdf import PdfWriter

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160)
    writer.write(buffer)
    content = buffer.getvalue()
    response = files_case["client"].post("/api/files/upload", content=content, headers={
        "X-Filename": "worksheet.pdf", "Content-Type": "application/pdf",
    })
    assert response.status_code == 200, response.text
    row = response.json()["file"]
    assert row["previewable"] is False and row["preview_url"] is None
    assert files_case["client"].get(row["download_url"]).content == content
    assert files_case["client"].get(f"/api/files/{row['id']}/preview").status_code == 415


def test_upload_attaches_atomically_and_grants_only_target_student(files_case):
    from tests.test_teacher_schedule import create

    link_student(files_case)
    lesson = create(files_case)
    homework = create_homework(files_case)
    response = files_case["client"].post(
        f"/api/files/upload?lesson_id={lesson['id']}&homework_id={homework['id']}",
        content=b"Exercises\n", headers={"X-Filename": "exercises.txt", "Content-Type": "text/plain"},
    )
    assert response.status_code == 200, response.text
    row = response.json()["file"]
    assert [item["id"] for item in row["lessons"]] == [lesson["id"]]
    assert [item["id"] for item in row["homeworks"]] == [homework["id"]]
    assert files_case["student_client"].get(row["download_url"]).content == b"Exercises\n"
    with files_case["sessions"]() as db:
        item = db.get(FileResource, row["id"])
        assert item.owner_id == files_case["teacher_id"]
        assert len(item.lessons) == len(item.homeworks) == 1


def test_upload_rejects_foreign_targets_before_consuming_body(files_case, monkeypatch):
    from starlette.requests import Request
    from tests.test_teacher_schedule import create

    lesson = create({**files_case, "client": files_case["foreign"], "first": files_case["foreign_student"]})

    async def forbidden_stream(_):
        raise AssertionError("foreign target must be rejected before consuming file")
        yield b""

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    response = files_case["client"].post(f"/api/files/upload?lesson_id={lesson['id']}",
        content=b"Notes", headers={"X-Filename": "notes.txt", "Content-Type": "text/plain"})
    assert response.status_code == 404, response.text
    with files_case["sessions"]() as db:
        assert list(db.scalars(select(FileResource))) == []


def test_upload_database_failure_returns_safe_error_and_removes_uncommitted_bytes(files_case):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    sessions = files_case["sessions"]

    def fail_before_commit(db):
        if any(isinstance(item, FileResource) for item in db.new):
            raise OperationalError("private sql", {}, RuntimeError("DO-NOT-DISCLOSE"))

    event.listen(sessions.class_, "before_commit", fail_before_commit)
    try:
        response = files_case["client"].post("/api/files/upload", content=b"Notes\n",
            headers={"X-Filename": "notes.txt", "Content-Type": "text/plain"})
    finally:
        event.remove(sessions.class_, "before_commit", fail_before_commit)
    assert response.status_code == 503, response.text
    assert "DO-NOT-DISCLOSE" not in response.text
    with sessions() as db:
        assert list(db.scalars(select(FileResource))) == []
    root = Path(settings.file_storage_path)
    assert not list(root.iterdir())


@pytest.mark.parametrize("extra_headers", [
    {"X-Filename": "%FF.txt"}, {"X-Filename": "%ZZ.txt"},
    {"X-Title": "x" * 201}, {"X-File-Kind": "x" * 81},
    {"X-Title": "%00bad"}, {"Content-Encoding": "gzip"},
])
def test_invalid_upload_headers_have_safe_validation_errors(files_case, extra_headers):
    headers = {"X-Filename": "notes.txt", "Content-Type": "text/plain", **extra_headers}
    response = files_case["client"].post("/api/files/upload", content=b"Notes\n", headers=headers)
    assert response.status_code in {415, 422}, response.text
    with files_case["sessions"]() as db:
        assert list(db.scalars(select(FileResource))) == []
    root = Path(settings.file_storage_path)
    assert not root.exists() or not list(root.iterdir())


def test_declared_oversize_is_rejected_before_body_read(files_case, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(settings, "file_upload_max_bytes", 8)

    async def forbidden_stream(_):
        raise AssertionError("declared oversize must not be read")
        yield b""

    monkeypatch.setattr(Request, "stream", forbidden_stream)
    response = files_case["client"].post("/api/files/upload", content=b"too large",
        headers={"X-Filename": "notes.txt", "Content-Type": "text/plain", "Content-Length": "9"})
    assert response.status_code == 413, response.text


def test_upload_requires_teacher_session_and_csrf(files_case):
    payload = {"content": b"Notes\n", "headers": {"X-Filename": "notes.txt", "Content-Type": "text/plain"}}
    assert files_case["student_client"].post("/api/files/upload", **payload).status_code == 403
    client = files_case["client"]
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/files/upload", **payload).status_code == 403
    client.cookies.clear()
    assert client.post("/api/files/upload", **payload).status_code == 401
    with files_case["sessions"]() as db:
        assert list(db.scalars(select(FileResource))) == []


def test_committed_upload_bytes_survive_unknown_commit_outcome(files_case):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    sessions = files_case["sessions"]

    def mark_material_commit(db):
        db.info["material_commit"] = any(isinstance(item, FileResource) for item in db.new)

    def lose_commit_acknowledgement(db):
        if db.info.get("material_commit"):
            raise OperationalError("commit acknowledgement", {}, RuntimeError("not public"))

    event.listen(sessions.class_, "before_commit", mark_material_commit)
    event.listen(sessions.class_, "after_commit", lose_commit_acknowledgement)
    try:
        response = files_case["client"].post("/api/files/upload", content=b"Keep these bytes\n",
            headers={"X-Filename": "notes.txt", "Content-Type": "text/plain"})
    finally:
        event.remove(sessions.class_, "before_commit", mark_material_commit)
        event.remove(sessions.class_, "after_commit", lose_commit_acknowledgement)
    assert response.status_code == 503, response.text
    with sessions() as db:
        saved = db.scalar(select(FileResource))
        assert saved is not None
        assert Path(saved.storage_path).read_bytes() == b"Keep these bytes\n"
        file_id = saved.id
    assert files_case["client"].get(f"/api/files/{file_id}/download").content == b"Keep these bytes\n"


def test_content_length_mismatch_does_not_leave_a_file_or_record(files_case):
    response = files_case["client"].post("/api/files/upload", content=b"Actual content\n", headers={
        "X-Filename": "notes.txt", "Content-Type": "text/plain", "Content-Length": "1",
    })
    assert response.status_code == 422, response.text
    with files_case["sessions"]() as db:
        assert list(db.scalars(select(FileResource))) == []
    assert not list(Path(settings.file_storage_path).iterdir())


def test_private_metadata_cannot_be_shared_cached(files_case):
    file_id, _ = saved_file(files_case)
    for route in (f"/api/files/{file_id}", f"/api/materials/{file_id}", "/api/materials"):
        response = files_case["client"].get(route)
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "private, no-store"


@pytest.mark.parametrize("kind", ["missing_file", "metadata_only"])
def test_delete_allows_absent_bytes_and_metadata_only_records(files_case, kind):
    if kind == "missing_file":
        file_id, path = saved_file(files_case)
        path.unlink()
    else:
        created = files_case["client"].post("/api/materials", json={"title": "Только заметка", "kind": "Запись"})
        assert created.status_code == 200, created.text
        file_id = created.json()["material"]["id"]

    response = files_case["client"].delete(f"/api/materials/{file_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "cleanup_pending": False}
    with files_case["sessions"]() as db:
        assert db.get(FileResource, file_id) is None
    assert files_case["client"].get(f"/api/materials/{file_id}").status_code == 404
    root = Path(settings.file_storage_path)
    assert not root.exists() or list(root.iterdir()) == []


@pytest.mark.parametrize("target_kind", ["lesson", "homework"])
def test_upload_revalidates_target_deleted_while_body_is_streaming(files_case, monkeypatch, target_kind):
    from starlette.requests import Request
    from app.models import Homework, Lesson
    from tests.test_teacher_schedule import create

    target = create(files_case) if target_kind == "lesson" else create_homework(files_case)
    model = Lesson if target_kind == "lesson" else Homework
    original_stream = Request.stream

    async def remove_target_during_stream(request):
        with files_case["sessions"]() as db:
            db.delete(db.get(model, target["id"]))
            db.commit()
        async for chunk in original_stream(request):
            yield chunk

    monkeypatch.setattr(Request, "stream", remove_target_during_stream)
    response = files_case["client"].post(f"/api/files/upload?{target_kind}_id={target['id']}",
        content=b"Never attached\n", headers={"X-Filename": "notes.txt", "Content-Type": "text/plain"})
    assert response.status_code == 404, response.text
    with files_case["sessions"]() as db:
        assert db.get(model, target["id"]) is None
        assert list(db.scalars(select(FileResource))) == []
    assert list(Path(settings.file_storage_path).iterdir()) == []


@pytest.mark.parametrize("failure_kind", ["root_configuration", "root_permission", "file_permission"])
def test_delete_unavailable_storage_preserves_record_and_live_bytes(files_case, monkeypatch, failure_kind):
    from app import storage

    file_id, path = saved_file(files_case)
    original_lstat = Path.lstat

    def unavailable_root():
        if failure_kind == "root_configuration":
            raise storage.FileStorageError(500, "DO-NOT-DISCLOSE configuration")
        raise PermissionError("DO-NOT-DISCLOSE root")

    def unavailable_lstat(target, *args, **kwargs):
        if target == path:
            raise PermissionError("DO-NOT-DISCLOSE file")
        return original_lstat(target, *args, **kwargs)

    with monkeypatch.context() as patcher:
        if failure_kind == "file_permission":
            patcher.setattr(Path, "lstat", unavailable_lstat)
        else:
            patcher.setattr(storage, "storage_root", unavailable_root)
        response = files_case["client"].delete(f"/api/materials/{file_id}")

    # Read back independently even on the broken implementation's HTTP 200.
    with files_case["sessions"]() as db:
        retained = db.get(FileResource, file_id) is not None
    assert path.read_bytes() == b"Lesson notes\n"
    assert list(path.parent.iterdir()) == [path]
    assert (response.status_code, retained) == (503, True), response.text
    assert "DO-NOT-DISCLOSE" not in response.text
    assert "cleanup_pending" not in response.json()
    assert files_case["client"].get(f"/api/files/{file_id}/download").content == b"Lesson notes\n"


def test_delete_database_failure_restores_content_and_returns_safe_error(files_case):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    file_id, path = saved_file(files_case)
    sessions = files_case["sessions"]

    def fail_before_commit(db):
        if any(isinstance(item, FileResource) for item in db.deleted):
            raise OperationalError("private sql", {}, RuntimeError("DO-NOT-DISCLOSE"))

    event.listen(sessions.class_, "before_commit", fail_before_commit)
    try:
        response = files_case["client"].delete(f"/api/materials/{file_id}")
    finally:
        event.remove(sessions.class_, "before_commit", fail_before_commit)
    assert response.status_code == 503, response.text
    assert "DO-NOT-DISCLOSE" not in response.text
    assert path.read_bytes() == b"Lesson notes\n"
    assert files_case["client"].get(f"/api/files/{file_id}/download").status_code == 200


@pytest.fixture
def file_delete_case(tmp_path, monkeypatch):
    """Real independent connections, unlike schedule_case's single StaticPool."""
    from contextlib import ExitStack
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.auth.router import router as auth_router
    from app.core.database import Base, get_db
    from app.web.router import router as web_router

    monkeypatch.setattr(settings, "file_storage_path", str(tmp_path / "uploads"))
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'delete.sqlite').as_posix()}",
                           connect_args={"check_same_thread": False, "timeout": 0.25})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    application = FastAPI()
    application.include_router(auth_router)
    application.include_router(web_router)

    def database():
        with sessions() as db:
            yield db

    application.dependency_overrides[get_db] = database
    try:
        with ExitStack() as stack:
            client = stack.enter_context(TestClient(application))
            contender = stack.enter_context(TestClient(application))
            registered = client.post("/api/auth/register", headers={"X-TutorFlow-Request": "auth"}, json={
                "first_name": "Лидия", "email": "delete-race@example.com", "role": "teacher",
                "password": "Delete-Race-Test-493!", "password_confirmation": "Delete-Race-Test-493!",
            })
            assert registered.status_code == 201, registered.text
            client.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
            contender.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
            contender.cookies.update(client.cookies)
            yield {"client": client, "contender": contender, "sessions": sessions,
                   "teacher_id": registered.json()["user"]["id"]}
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure_window", ["before_commit", "after_rollback", "during_restore"])
def test_overlapping_delete_cannot_commit_while_first_delete_is_staged(file_delete_case, monkeypatch, failure_window):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    case = file_delete_case
    file_id, path = saved_file(case)
    staged, release = Event(), Event()

    def fail_first_commit(db):
        if any(isinstance(item, FileResource) for item in db.deleted) and not staged.is_set():
            db.info["failing_delete"] = True
            if failure_window == "before_commit":
                staged.set()
                assert release.wait(5), "test did not release first DELETE"
            raise OperationalError("private sql", {}, RuntimeError("DO-NOT-DISCLOSE"))

    original_rollback = case["sessions"].class_.rollback

    def pause_after_rollback(db):
        original_rollback(db)
        if db.info.get("failing_delete") and failure_window == "after_rollback":
            staged.set()
            assert release.wait(5), "test did not release DELETE recovery"

    from app import materials
    original_restore = materials.restore_staged_file

    def pause_during_restore(value):
        original_restore(value)
        if value is not None and failure_window == "during_restore":
            staged.set()
            assert release.wait(5), "test did not release locked recovery"

    monkeypatch.setattr(materials, "restore_staged_file", pause_during_restore)
    monkeypatch.setattr(case["sessions"].class_, "rollback", pause_after_rollback)
    event.listen(case["sessions"].class_, "before_commit", fail_first_commit)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first = executor.submit(case["client"].delete, f"/api/materials/{file_id}")
            try:
                assert staged.wait(3), "first DELETE never reached controlled failure window"
                assert path.exists() is (failure_window == "during_restore")
                second = case["contender"].delete(f"/api/materials/{file_id}")
            finally:
                release.set()
            first_response = first.result(timeout=5)
    finally:
        event.remove(case["sessions"].class_, "before_commit", fail_first_commit)

    with case["sessions"]() as db:
        retained = db.get(FileResource, file_id) is not None
    assert (first_response.status_code, second.status_code, retained) == (503, 503, True)
    assert "DO-NOT-DISCLOSE" not in first_response.text + second.text
    assert "cleanup_pending" not in second.json()
    assert path.read_bytes() == b"Lesson notes\n"
    assert list(path.parent.iterdir()) == [path]
    assert case["client"].get(f"/api/files/{file_id}/download").content == b"Lesson notes\n"


@pytest.mark.parametrize("failure_point", ["after_commit", "after_return"])
def test_delete_lost_commit_acknowledgement_does_not_restore_orphan_bytes(file_delete_case, monkeypatch, failure_point):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    case = file_delete_case
    file_id, path = saved_file(case)

    def mark_delete(db):
        db.info["material_delete"] = any(isinstance(item, FileResource) for item in db.deleted)

    def lose_acknowledgement(db):
        if db.info.get("material_delete") and failure_point == "after_commit":
            raise OperationalError("private commit", {}, RuntimeError("DO-NOT-DISCLOSE"))

    original_commit = case["sessions"].class_.commit

    def lose_acknowledgement_after_return(db):
        original_commit(db)
        if db.info.get("material_delete") and failure_point == "after_return":
            raise OperationalError("private commit", {}, RuntimeError("DO-NOT-DISCLOSE"))

    monkeypatch.setattr(case["sessions"].class_, "commit", lose_acknowledgement_after_return)
    event.listen(case["sessions"].class_, "before_commit", mark_delete)
    event.listen(case["sessions"].class_, "after_commit", lose_acknowledgement)
    try:
        response = case["client"].delete(f"/api/materials/{file_id}")
    finally:
        event.remove(case["sessions"].class_, "before_commit", mark_delete)
        event.remove(case["sessions"].class_, "after_commit", lose_acknowledgement)

    with case["sessions"]() as db:
        assert db.get(FileResource, file_id) is None
    assert response.status_code == 503, response.text
    assert "DO-NOT-DISCLOSE" not in response.text
    assert "cleanup_pending" not in response.json()
    assert not path.exists(), "unknown commit must not restore unreferenced live bytes"
    residual = list(path.parent.iterdir())
    assert len(residual) == 1 and residual[0].name.endswith(".deleting")
    assert residual[0].read_bytes() == b"Lesson notes\n"
    assert case["client"].delete(f"/api/materials/{file_id}").status_code == 404
    assert case["client"].get(f"/api/files/{file_id}/download").status_code == 404


@pytest.mark.parametrize("failure_kind", ["recovery_database", "recovery_filesystem", "rollback"])
def test_delete_unverified_recovery_preserves_hidden_bytes(file_delete_case, monkeypatch, failure_kind):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from app import materials

    case = file_delete_case
    file_id, path = saved_file(case)

    def fail_commit(db):
        if any(isinstance(item, FileResource) for item in db.deleted):
            raise OperationalError("private sql", {}, RuntimeError("DO-NOT-DISCLOSE"))

    def fail_recovery(*args, **kwargs):
        raise OSError("DO-NOT-DISCLOSE recovery")

    original_rollback = case["sessions"].class_.rollback

    def fail_rollback(db):
        original_rollback(db)
        raise OperationalError("private rollback", {}, RuntimeError("DO-NOT-DISCLOSE"))

    event.listen(case["sessions"].class_, "before_commit", fail_commit)
    try:
        with monkeypatch.context() as patcher:
            if failure_kind == "recovery_database":
                patcher.setattr(materials, "Session", fail_recovery)
            elif failure_kind == "recovery_filesystem":
                patcher.setattr(materials, "restore_staged_file", fail_recovery)
            else:
                patcher.setattr(case["sessions"].class_, "rollback", fail_rollback)
            response = case["client"].delete(f"/api/materials/{file_id}")
    finally:
        event.remove(case["sessions"].class_, "before_commit", fail_commit)

    with case["sessions"]() as db:
        assert db.get(FileResource, file_id) is not None
    assert response.status_code == 503, response.text
    assert "DO-NOT-DISCLOSE" not in response.text
    assert "cleanup_pending" not in response.json()
    assert not path.exists()
    residual = list(path.parent.iterdir())
    assert len(residual) == 1 and residual[0].name.endswith(".deleting")
    assert residual[0].read_bytes() == b"Lesson notes\n"
    retry = case["contender"].delete(f"/api/materials/{file_id}")
    assert retry.status_code == 503, retry.text
    with case["sessions"]() as db:
        assert db.get(FileResource, file_id) is not None
    assert residual[0].read_bytes() == b"Lesson notes\n"


@pytest.mark.parametrize("fail_cleanup", [False, True])
def test_delete_cleanup_status_matches_committed_row_and_residual_bytes(file_delete_case, monkeypatch, fail_cleanup):
    case = file_delete_case
    file_id, path = saved_file(case)
    original_unlink = Path.unlink

    def unlink(target, *args, **kwargs):
        if fail_cleanup and target.name.endswith(".deleting"):
            raise PermissionError("DO-NOT-DISCLOSE")
        return original_unlink(target, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "unlink", unlink)
        response = case["client"].delete(f"/api/materials/{file_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "cleanup_pending": fail_cleanup}
    with case["sessions"]() as db:
        assert db.get(FileResource, file_id) is None
    assert not path.exists()
    residual = list(path.parent.iterdir())
    if fail_cleanup:
        assert len(residual) == 1 and residual[0].name.endswith(".deleting")
        assert residual[0].read_bytes() == b"Lesson notes\n"
    else:
        assert residual == []
    assert case["client"].get(f"/api/files/{file_id}/download").status_code == 404


def test_delete_stale_loaded_row_does_not_stage_after_competing_success(file_delete_case, monkeypatch):
    from fastapi import HTTPException
    from app import materials

    case = file_delete_case
    file_id, path = saved_file(case)
    with case["sessions"]() as stale:
        item = stale.get(FileResource, file_id)
        assert case["client"].delete(f"/api/materials/{file_id}").json() == {"ok": True, "cleanup_pending": False}

        def must_not_stage(*args):
            pytest.fail("stale DELETE touched filesystem after losing the row")

        monkeypatch.setattr(materials, "stage_deletion", must_not_stage)
        with pytest.raises(HTTPException) as caught:
            materials.delete_stored_material(stale, item)
        assert caught.value.status_code == 404
    with case["sessions"]() as db:
        assert db.get(FileResource, file_id) is None
    assert not path.exists() and list(path.parent.iterdir()) == []


def test_upload_format_inspection_does_not_block_event_loop(files_case, monkeypatch):
    import asyncio
    import threading
    from app import storage

    async def run():
        loop_thread = threading.get_ident()

        def inspect(path, name, declared_mime=None):
            assert threading.get_ident() != loop_thread, "format parser is running on the event loop"
            return "text/plain", True

        async def chunks():
            yield b"Notes\n"

        monkeypatch.setattr(storage, "inspect_file", inspect)
        upload = await storage.store_stream("notes.txt", chunks(), declared_mime="text/plain")
        assert Path(upload.storage_path).read_bytes() == b"Notes\n"

    asyncio.run(run())


def test_cancelled_upload_waits_for_parser_before_cleaning_staging(files_case, monkeypatch):
    import asyncio
    import threading
    from app import storage

    started, release = threading.Event(), threading.Event()

    def inspect(path, name, declared_mime=None):
        with path.open("rb") as source:
            started.set()
            assert release.wait(3), "test did not release parser"
            assert source.read() == b"Notes\n"
        return "text/plain", True

    async def chunks():
        yield b"Notes\n"

    async def run():
        task = asyncio.create_task(storage.store_stream("notes.txt", chunks()))
        try:
            assert await asyncio.to_thread(started.wait, 2), "parser did not start"
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), "cleanup raced with a still-open parser input"
            task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
            result = (await asyncio.gather(task, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)
        assert not list(Path(settings.file_storage_path).iterdir())

    monkeypatch.setattr(storage, "inspect_file", inspect)
    asyncio.run(run())
