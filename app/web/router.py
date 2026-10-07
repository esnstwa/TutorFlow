from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_teacher
from app.core.database import get_db
from app.integrations.google_calendar import google_calendar
from app.models import Assignment, AssignmentReview, AssignmentSubmission, Conversation, FileResource, Lesson, Student, User
from app.services import (
    ASSIGNMENT_STATUSES,
    LESSON_STATUSES,
    assignment_dict,
    cabinet_data,
    calendar_events,
    create_entity,
    file_dict,
    lesson_dict,
    local_datetime,
    material_from_label,
    review_dict,
    scoped_assignment,
    scoped_lesson,
    scoped_review,
    scoped_student,
    scoped_submission,
    student_dict,
    submission_dict,
)
from app.storage import finish_staged_deletion, restore_staged_file, stage_deletion, store_bytes
from app.web.navigation import TEACHER_NAVIGATION, get_auth_navigation
from app.web.templating import templates

router = APIRouter()
MOSCOW = ZoneInfo("Europe/Moscow")


def payload_dict(request_payload: Any) -> dict[str, Any]:
    if not isinstance(request_payload, dict):
        raise ValueError("Некорректные данные")
    return request_payload


def commit_or_422(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=422, detail="Данные нарушают ограничения") from error


def render_teacher(request: Request, template: str, *, section: str, db: Session, teacher: User, **context: Any):
    data = cabinet_data(db, teacher)
    data.update(context)
    data.update({"active_section": section, "teacher_navigation": TEACHER_NAVIGATION})
    return templates.TemplateResponse(request=request, name=template, context=data)


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/dashboard.html", section="dashboard", db=db, teacher=teacher)


@router.get("/schedule", response_class=HTMLResponse, name="schedule")
def schedule(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/schedule.html", section="schedule", db=db, teacher=teacher, calendar_events=calendar_events(db, teacher), google_calendar=google_calendar.get_state())


@router.get("/students", response_class=HTMLResponse, name="students")
def students(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/students.html", section="students", db=db, teacher=teacher)


@router.get("/students/{student_id}", response_class=HTMLResponse, name="student_profile")
def student_profile(request: Request, student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return render_teacher(request, "pages/student_profile.html", section="students", db=db, teacher=teacher, student=student_dict(item))


@router.get("/assignments", response_class=HTMLResponse, name="assignments")
def assignments(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/assignments.html", section="assignments", db=db, teacher=teacher)


@router.get("/assignments/{assignment_id}", response_class=HTMLResponse, name="assignment")
def assignment(request: Request, assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_assignment(db, teacher.id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return render_teacher(request, "pages/assignment.html", section="assignments", db=db, teacher=teacher, assignment=assignment_dict(item))


@router.get("/materials", response_class=HTMLResponse, name="materials")
def materials(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/materials.html", section="materials", db=db, teacher=teacher)


@router.get("/lessons/{lesson_id}", response_class=HTMLResponse, name="lesson")
def lesson(request: Request, lesson_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_lesson(db, teacher.id, lesson_id)
    if not item:
        raise HTTPException(status_code=404, detail="Занятие не найдено")
    return render_teacher(request, "pages/lesson.html", section="schedule", db=db, teacher=teacher, lesson=lesson_dict(item))


@router.get("/settings", response_class=HTMLResponse, name="settings")
def settings_page(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/settings.html", section="settings", db=db, teacher=teacher)


@router.get("/notifications", response_class=HTMLResponse, name="notifications")
def notifications(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/notifications.html", section="notifications", db=db, teacher=teacher)


@router.get("/submissions/{submission_id}", response_class=HTMLResponse, name="submission")
def submission(request: Request, submission_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_submission(db, teacher.id, submission_id)
    if not item:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    return render_teacher(request, "pages/submission.html", section="assignments", db=db, teacher=teacher, submission=submission_dict(item))


@router.get("/messages/{dialog_id}", response_class=HTMLResponse, name="dialog")
def dialog(request: Request, dialog_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = db.scalar(select(Conversation).options(selectinload(Conversation.student), selectinload(Conversation.messages)).where(Conversation.id == dialog_id, Conversation.teacher_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    student = student_dict(item.student)
    result = {"id": item.id, "student_id": item.student_id, "student": student, "messages": [{"author": teacher.first_name if message.author_role == "teacher" else student["first_name"], "text": message.body, "time": message.sent_at.astimezone(MOSCOW).strftime("%H:%M")} for message in sorted(item.messages, key=lambda row: row.sent_at)]}
    return render_teacher(request, "pages/dialog.html", section="notifications", db=db, teacher=teacher, dialog=result)


@router.get("/profile", response_class=HTMLResponse, name="teacher_profile")
def teacher_profile(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/profile.html", section="profile", db=db, teacher=teacher)


@router.post("/api/mock/{kind}", response_class=JSONResponse, name="create_mock_entity")
async def create_compatible_entity(request: Request, kind: str, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    try:
        payload = payload_dict(await request.json())
        if any(not str(value).strip() for value in payload.values()):
            raise ValueError("Заполните все поля")
        entity = create_entity(db, teacher, kind, payload)
        commit_or_422(db)
    except (KeyError, TypeError, ValueError) as error:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(error)}, status_code=422)
    return {"ok": True, "entity": entity}


@router.post("/api/mock/lessons/{lesson_id}/reschedule", response_class=JSONResponse, name="reschedule_mock_lesson")
async def reschedule(request: Request, lesson_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    try:
        payload = payload_dict(await request.json())
        item = scoped_lesson(db, teacher.id, lesson_id)
        if not item:
            raise ValueError("Занятие не найдено")
        duration = item.end_at - item.start_at
        start_at = local_datetime(str(payload["date"]), str(payload["start"]))
        end_at = start_at + duration
        collision = db.scalar(select(Lesson.id).where(Lesson.teacher_id == teacher.id, Lesson.id != item.id, Lesson.start_at < end_at, Lesson.end_at > start_at))
        if collision:
            raise ValueError("Это время уже занято")
        item.start_at, item.end_at = start_at, end_at
        db.commit()
        db.refresh(item)
        result = lesson_dict(scoped_lesson(db, teacher.id, item.id))
    except (KeyError, TypeError, ValueError) as error:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(error)}, status_code=422)
    return {"ok": True, "lesson": result}


@router.patch("/api/lessons/{lesson_id}", response_class=JSONResponse)
@router.patch("/api/mock/lessons/{lesson_id}", response_class=JSONResponse, name="update_mock_lesson")
async def update_compatible_lesson(request: Request, lesson_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    try:
        payload = payload_dict(await request.json())
        item = scoped_lesson(db, teacher.id, lesson_id)
        if not item:
            raise ValueError("Занятие не найдено")
        status_value = str(payload.get("status", ""))
        topic = str(payload.get("topic", "")).strip()
        note = str(payload.get("teacher_note", ""))
        material_labels = payload.get("materials", [])
        if status_value not in LESSON_STATUSES:
            raise ValueError("Неизвестный статус занятия")
        if not topic:
            raise ValueError("Укажите тему занятия")
        if len(note) > 500:
            raise ValueError("Заметка не должна превышать 500 символов")
        if not isinstance(material_labels, list):
            raise ValueError("Некорректный список материалов")
        item.status, item.topic, item.teacher_note = status_value, topic, note
        item.location = str(payload.get("location", "")).strip()
        item.meeting_url = item.location if item.location.startswith(("http://", "https://")) else None
        item.materials = [material_from_label(db, teacher, str(label).strip()) for label in material_labels if str(label).strip()]
        db.commit()
        result = lesson_dict(scoped_lesson(db, teacher.id, lesson_id))
    except (TypeError, ValueError) as error:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(error)}, status_code=422)
    return {"ok": True, "lesson": result}


@router.delete("/api/lessons/{lesson_id}", response_class=JSONResponse)
@router.delete("/api/mock/lessons/{lesson_id}", response_class=JSONResponse, name="delete_mock_lesson")
def delete_compatible_lesson(lesson_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_lesson(db, teacher.id, lesson_id)
    if not item:
        return JSONResponse({"ok": False, "error": "Занятие не найдено"}, status_code=404)
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/api/students")
def list_students(db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    rows = db.scalars(select(Student).options(selectinload(Student.user)).where(Student.teacher_id == teacher.id).order_by(Student.id))
    return {"ok": True, "students": [student_dict(item) for item in rows]}


@router.get("/api/students/{student_id}")
def get_student_api(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return {"ok": True, "student": student_dict(item)}


@router.post("/api/students")
async def create_student(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    payload = payload_dict(await request.json())
    try:
        entity = create_entity(db, teacher, "student", payload)
        commit_or_422(db)
    except (KeyError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True, "student": entity}


@router.patch("/api/students/{student_id}")
async def update_student(request: Request, student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    payload = payload_dict(await request.json())
    if "name" in payload:
        parts = str(payload["name"]).strip().split(maxsplit=1)
        if not parts:
            raise HTTPException(status_code=422, detail="Укажите имя")
        item.first_name, item.last_name = parts[0], parts[1] if len(parts) > 1 else ""
    for field in ("email", "subject", "grade", "avatar"):
        if field in payload:
            setattr(item, field, str(payload[field]).strip() or None if field in ("email", "avatar") else str(payload[field]).strip())
    commit_or_422(db)
    return {"ok": True, "student": student_dict(item)}


@router.delete("/api/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/api/lessons")
def list_lessons(date_from: date | None = Query(None), date_to: date | None = Query(None), db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return {"ok": True, "lessons": [item["lesson"] for item in calendar_events(db, teacher, date_from=date_from, date_to=date_to) if item["type"] == "lessons"]}


@router.get("/api/lessons/{lesson_id}")
def get_lesson_api(lesson_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_lesson(db, teacher.id, lesson_id)
    if not item:
        raise HTTPException(status_code=404, detail="Занятие не найдено")
    return {"ok": True, "lesson": lesson_dict(item)}


@router.post("/api/lessons")
async def create_lesson(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    payload = payload_dict(await request.json())
    try:
        entity = create_entity(db, teacher, "lesson", payload)
        commit_or_422(db)
    except (KeyError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True, "lesson": entity}


@router.get("/api/assignments")
def list_assignments(db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    rows = db.scalars(select(Assignment).options(selectinload(Assignment.student), selectinload(Assignment.materials)).where(Assignment.teacher_id == teacher.id))
    return {"ok": True, "assignments": [assignment_dict(item) for item in rows]}


@router.get("/api/assignments/{assignment_id}")
def get_assignment_api(assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_assignment(db, teacher.id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return {"ok": True, "assignment": assignment_dict(item)}


@router.post("/api/assignments")
async def create_assignment(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    payload = payload_dict(await request.json())
    try:
        entity = create_entity(db, teacher, "assignment", payload)
        commit_or_422(db)
    except (KeyError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True, "assignment": entity}


@router.patch("/api/assignments/{assignment_id}")
async def update_assignment(request: Request, assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_assignment(db, teacher.id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    payload = payload_dict(await request.json())
    if "status" in payload and payload["status"] not in ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=422, detail="Неизвестный статус задания")
    for field in ("title", "description", "subject", "status"):
        if field in payload:
            setattr(item, field, str(payload[field]).strip())
    if "due_at" in payload:
        item.due_at = datetime.fromisoformat(str(payload["due_at"]))
    commit_or_422(db)
    return {"ok": True, "assignment": assignment_dict(item)}


@router.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_assignment(db, teacher.id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/api/assignments/{assignment_id}/submissions")
async def create_submission(request: Request, assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    assignment = scoped_assignment(db, teacher.id, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    payload = payload_dict(await request.json())
    attempt = db.scalar(select(func.max(AssignmentSubmission.attempt_number)).where(AssignmentSubmission.assignment_id == assignment.id)) or 0
    item = AssignmentSubmission(assignment_id=assignment.id, student_id=assignment.student_id, attempt_number=attempt + 1, comment=str(payload.get("comment", "")), status="submitted")
    file_ids = [int(value) for value in payload.get("file_ids", [])]
    if file_ids:
        files = list(db.scalars(select(FileResource).where(FileResource.owner_id == teacher.id, FileResource.id.in_(file_ids))))
        if len(files) != len(set(file_ids)):
            raise HTTPException(status_code=404, detail="Файл не найден")
        item.files = files
    assignment.status = "submitted"
    db.add(item)
    commit_or_422(db)
    return {"ok": True, "submission": submission_dict(scoped_submission(db, teacher.id, item.id))}


@router.post("/api/submissions/{submission_id}/reviews")
async def create_review(request: Request, submission_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    submission = scoped_submission(db, teacher.id, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    payload = payload_dict(await request.json())
    result = str(payload.get("result", ""))
    if result not in {"accepted", "revision_requested"}:
        raise HTTPException(status_code=422, detail="Некорректный результат проверки")
    score = payload.get("score")
    max_score = payload.get("max_score")
    if score is not None and int(score) < 0:
        raise HTTPException(status_code=422, detail="Оценка не может быть отрицательной")
    if score is not None and max_score is not None and int(score) > int(max_score):
        raise HTTPException(status_code=422, detail="Оценка превышает максимум")
    review = AssignmentReview(submission_id=submission.id, teacher_id=teacher.id, result=result, score=int(score) if score is not None else None, max_score=int(max_score) if max_score is not None else None, comment=str(payload.get("comment", "")))
    submission.status = "reviewed" if result == "accepted" else "revision_requested"
    submission.assignment.status = submission.status
    db.add(review)
    commit_or_422(db)
    return {"ok": True, "review": review_dict(review)}


@router.get("/api/materials")
def list_materials(db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    rows = db.scalars(select(FileResource).where(FileResource.owner_id == teacher.id).order_by(FileResource.id))
    return {"ok": True, "materials": [file_dict(item) for item in rows]}


@router.get("/api/materials/{material_id}")
def get_material_api(material_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = db.scalar(select(FileResource).where(FileResource.id == material_id, FileResource.owner_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="Материал не найден")
    return {"ok": True, "material": file_dict(item)}


@router.post("/api/materials")
async def create_material(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    payload = payload_dict(await request.json())
    item = FileResource(owner_id=teacher.id, original_name=str(payload.get("original_name") or payload.get("title") or "material"), stored_name=payload.get("stored_name"), storage_path=payload.get("path"), mime_type=payload.get("mime_type"), size=int(payload.get("size", 0)), title=str(payload.get("title") or payload.get("original_name") or "Материал"), kind=str(payload.get("kind") or payload.get("type") or "Файл"), description=str(payload.get("description", "")), url=payload.get("url"))
    db.add(item)
    commit_or_422(db)
    return {"ok": True, "material": file_dict(item)}


@router.post("/api/files/upload")
async def upload_file(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    original_name = request.headers.get("X-Filename", "").strip()
    if not original_name:
        raise HTTPException(status_code=422, detail="Передайте имя файла в X-Filename")
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Файл пуст")
    stored_name = storage_path = None
    try:
        stored_name, storage_path = store_bytes(original_name, content)
        item = FileResource(owner_id=teacher.id, original_name=original_name, stored_name=stored_name, storage_path=storage_path, mime_type=request.headers.get("Content-Type"), size=len(content), title=request.headers.get("X-Title", original_name), kind=request.headers.get("X-File-Kind", "Файл"))
        db.add(item)
        commit_or_422(db)
        return {"ok": True, "file": file_dict(item)}
    except Exception:
        db.rollback()
        if storage_path:
            staged = stage_deletion(storage_path)
            finish_staged_deletion(staged)
        raise


@router.patch("/api/materials/{material_id}")
async def update_material(request: Request, material_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = db.scalar(select(FileResource).where(FileResource.id == material_id, FileResource.owner_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="Материал не найден")
    payload = payload_dict(await request.json())
    for field in ("title", "kind", "description", "url"):
        if field in payload:
            setattr(item, field, str(payload[field]).strip() or None if field == "url" else str(payload[field]).strip())
    commit_or_422(db)
    return {"ok": True, "material": file_dict(item)}


@router.delete("/api/materials/{material_id}")
def delete_material(material_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = db.scalar(select(FileResource).where(FileResource.id == material_id, FileResource.owner_id == teacher.id))
    if not item:
        raise HTTPException(status_code=404, detail="Материал не найден")
    staged = stage_deletion(item.storage_path)
    try:
        db.delete(item)
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_file(staged)
        raise
    finish_staged_deletion(staged)
    return {"ok": True}


def attachment_owner(db: Session, teacher: User, resource: str, resource_id: int):
    if resource == "lessons":
        return scoped_lesson(db, teacher.id, resource_id), "materials"
    if resource == "assignments":
        return scoped_assignment(db, teacher.id, resource_id), "materials"
    if resource == "submissions":
        return scoped_submission(db, teacher.id, resource_id), "files"
    if resource == "reviews":
        return scoped_review(db, teacher.id, resource_id), "files"
    raise HTTPException(status_code=404, detail="Неизвестный ресурс")


@router.post("/api/{resource}/{resource_id}/materials/{material_id}")
def attach_material(resource: str, resource_id: int, material_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    owner, attribute = attachment_owner(db, teacher, resource, resource_id)
    material = db.scalar(select(FileResource).where(FileResource.id == material_id, FileResource.owner_id == teacher.id))
    if not owner or not material:
        raise HTTPException(status_code=404, detail="Ресурс или материал не найден")
    collection = getattr(owner, attribute)
    if material not in collection:
        collection.append(material)
    db.commit()
    return {"ok": True}


@router.delete("/api/{resource}/{resource_id}/materials/{material_id}")
def detach_material(resource: str, resource_id: int, material_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    owner, attribute = attachment_owner(db, teacher, resource, resource_id)
    material = db.scalar(select(FileResource).where(FileResource.id == material_id, FileResource.owner_id == teacher.id))
    if not owner or not material:
        raise HTTPException(status_code=404, detail="Ресурс или материал не найден")
    collection = getattr(owner, attribute)
    if material in collection:
        collection.remove(material)
    db.commit()
    return {"ok": True}


@router.post("/logout", name="auth_logout")
def logout():
    return RedirectResponse(url="/", status_code=303)


@router.get("/", response_class=HTMLResponse, name="landing")
def landing(request: Request):
    return templates.TemplateResponse(request=request, name="pages/landing.html", context={"navigation": get_auth_navigation(request)})
