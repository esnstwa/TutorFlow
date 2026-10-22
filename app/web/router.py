from __future__ import annotations

from datetime import date
from typing import Any, Literal
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.auth import get_current_student, get_current_teacher, get_current_user, optional_current_user
from app.core.database import get_db
from app.homework.schemas import HomeworkCreate, HomeworkReviewCreate, HomeworkSubmissionCreate
from app.homework.service import (
    create_homework,
    homework_dict,
    local_aware,
    recipient_dict,
    review_homework,
    search_students,
    student_recipient,
    student_recipients,
    submit_homework,
    teacher_homework,
    teacher_homeworks,
    teacher_recipient,
)

from app.models import Conversation, FileResource, Homework, HomeworkRecipient, HomeworkSubmission, Lesson, Student, User
from app.services import (
    assignment_dict,
    cabinet_data,
    calendar_events,
    create_entity,
    file_dict,
    ensure_lesson_slot,
    lesson_dict,
    lesson_material_labels,
    lesson_values,
    local_datetime,
    material_from_label,
    scoped_assignment,
    scoped_lesson,
    scoped_student,
    scoped_submission,
    student_dict,
    student_directory,
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


def render_student(request: Request, template: str, *, student: Student, **context: Any):
    data = {"student": student_dict(student), **context}
    return templates.TemplateResponse(request=request, name=template, context=data)


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/dashboard.html", section="dashboard", db=db, teacher=teacher)


@router.get("/schedule", response_class=HTMLResponse, name="schedule")
def schedule(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return render_teacher(request, "pages/schedule.html", section="schedule", db=db, teacher=teacher, calendar_events=calendar_events(db, teacher))


@router.get("/students", response_class=HTMLResponse, name="students")
def students(
    request: Request,
    q: str = Query("", max_length=200),
    subject: str = Query("", max_length=120),
    archived: Literal["active", "archived", "all"] = Query("active"),
    db: Session = Depends(get_db),
    teacher: User = Depends(get_current_teacher),
):
    directory = student_directory(db, teacher, q, subject, archived)
    return render_teacher(request, "pages/students.html", section="students", db=db, teacher=teacher, **directory)


@router.get("/students/{student_id}", response_class=HTMLResponse, name="student_profile")
def student_profile(request: Request, student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return render_teacher(request, "pages/student_profile.html", section="students", db=db, teacher=teacher, student=student_dict(item))


@router.get("/assignments", response_class=HTMLResponse, name="assignments")
def assignments(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    rows = [homework_dict(item) for item in teacher_homeworks(db, teacher.id)]
    return render_teacher(request, "pages/assignments.html", section="assignments", db=db, teacher=teacher, assignments=rows)


@router.get("/assignments/{assignment_id}", response_class=HTMLResponse, name="assignment")
def assignment(request: Request, assignment_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_assignment(db, teacher.id, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return render_teacher(request, "pages/assignment.html", section="assignments", db=db, teacher=teacher, assignment=homework_dict(item))


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
        legacy_submission = db.get(HomeworkSubmission, submission_id)
        if legacy_submission:
            item = teacher_recipient(db, teacher.id, legacy_submission.homework_recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    return render_teacher(request, "pages/submission.html", section="assignments", db=db, teacher=teacher, submission=submission_dict(item))


@router.get("/homework-recipients/{recipient_id}", response_class=HTMLResponse, name="homework_recipient")
def homework_recipient_page(request: Request, recipient_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_recipient(db, teacher.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    return render_teacher(request, "pages/submission.html", section="assignments", db=db, teacher=teacher, submission=submission_dict(item))


@router.get("/student/homework", response_class=HTMLResponse, name="student_homework_list")
def student_homework_list(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Требуется роль ученика")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        return templates.TemplateResponse(request=request, name="pages/student_unlinked.html", context={"student": {"initials": user.first_name[:1]}})
    rows = []
    for item in student_recipients(db, student.id):
        row = recipient_dict(item)
        row["homework"] = homework_dict(item.homework, include_recipients=False)
        rows.append(row)
    return render_student(request, "pages/student_homeworks.html", student=student, assignments=rows)


@router.get("/student/homework/{recipient_id}", response_class=HTMLResponse, name="student_homework")
def student_homework_page(request: Request, recipient_id: int, db: Session = Depends(get_db), student: Student = Depends(get_current_student)):
    item = student_recipient(db, student.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    row = recipient_dict(item, include_history=True)
    row["homework"] = homework_dict(item.homework, include_recipients=False)
    row["teacher"] = {"name": f"{item.homework.teacher.first_name} {item.homework.teacher.last_name}".strip()}
    return render_student(request, "pages/student_homework.html", student=student, recipient=row)


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


@router.post("/api/lessons/{lesson_id}/reschedule", response_class=JSONResponse)
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
        ensure_lesson_slot(db, teacher.id, start_at, end_at, exclude_id=item.id)
        item.start_at, item.end_at = start_at, end_at
        commit_or_422(db)
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
        values = lesson_values(db, teacher, payload, item=item)
        material_labels = lesson_material_labels(payload)
        for field, value in values.items():
            setattr(item, field, value)
        if "materials" in payload:
            item.materials = [material_from_label(db, teacher, label) for label in material_labels]
        commit_or_422(db)
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


@router.get("/api/students/search")
def search_students_api(q: str = Query("", max_length=120), db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    return {"ok": True, "students": [student_dict(item) for item in search_students(db, teacher.id, q)]}


@router.get("/api/students/{student_id}")
def get_student_api(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    return {"ok": True, "student": student_dict(item)}


@router.post("/api/students")
async def create_student(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    try:
        payload = payload_dict(await request.json())
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
    from app.students.schemas import validated_fields
    try:
        fields = validated_fields(payload_dict(await request.json()), partial=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if "email" in fields and fields["email"] != item.email:
        from sqlalchemy import update
        from app.models import utc_now
        from app.students.models import StudentInvitation
        # Lock/update Student before invitation rows, matching archive and invite order.
        db.execute(update(Student).where(Student.id == item.id).values(email=fields["email"]))
        db.execute(update(StudentInvitation).where(StudentInvitation.student_id == item.id, StudentInvitation.consumed_at.is_(None), StudentInvitation.revoked_at.is_(None)).values(revoked_at=utc_now()))
    for field, value in fields.items():
        setattr(item, field, value)
    commit_or_422(db)
    return {"ok": True, "student": student_dict(item)}


@router.delete("/api/students/{student_id}")
def delete_student(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = scoped_student(db, teacher.id, student_id)
    if not item:
        raise HTTPException(status_code=404, detail="Ученик не найден")
    from app.students.service import archive_student
    archive_student(db, item)
    return {"ok": True, "student": student_dict(item)}


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
    try:
        payload = payload_dict(await request.json())
        entity = create_entity(db, teacher, "lesson", payload)
        commit_or_422(db)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True, "lesson": entity}


@router.get("/api/homework")
@router.get("/api/assignments")
def list_homework_api(status: str | None = Query(None), q: str = Query("", max_length=200), db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    rows = [homework_dict(item) for item in teacher_homeworks(db, teacher.id)]
    needle = q.strip().casefold()
    if needle:
        rows = [row for row in rows if needle in f"{row['title']} {row['description']}".casefold()]
    if status == "waiting":
        rows = [row for row in rows if row["counts"]["ASSIGNED"] or row["counts"]["REVISION_REQUIRED"] or row["counts"]["OVERDUE"]]
    elif status == "review":
        rows = [row for row in rows if row["counts"]["SUBMITTED"]]
    elif status == "completed":
        rows = [row for row in rows if row["recipient_count"] and row["counts"]["COMPLETED"] == row["recipient_count"]]
    return {"ok": True, "homeworks": rows, "assignments": rows}


@router.get("/api/homework/{homework_id}")
@router.get("/api/assignments/{homework_id}")
def get_homework_api(homework_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_homework(db, teacher.id, homework_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    row = homework_dict(item)
    return {"ok": True, "homework": row, "assignment": row}


@router.get("/api/homework/{homework_id}/recipients")
def list_homework_recipients(homework_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_homework(db, teacher.id, homework_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return {"ok": True, "recipients": [recipient_dict(row, include_history=True) for row in item.recipients]}


@router.post("/api/homework")
@router.post("/api/assignments")
async def create_homework_api(request: Request, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    try:
        data = HomeworkCreate.model_validate(payload_dict(await request.json()))
        item = create_homework(db, teacher, data)
    except (ValidationError, ValueError) as error:
        db.rollback()
        detail = error.errors()[0]["msg"] if isinstance(error, ValidationError) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error
    row = homework_dict(item)
    return {"ok": True, "homework": row, "assignment": row}


@router.patch("/api/homework/{homework_id}")
@router.patch("/api/assignments/{homework_id}")
async def update_homework_api(request: Request, homework_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_homework(db, teacher.id, homework_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    payload = payload_dict(await request.json())
    if "title" in payload:
        title = str(payload["title"]).strip()
        if not title:
            raise HTTPException(status_code=422, detail="Укажите название")
        item.title = title
    if "description" in payload:
        item.description = str(payload["description"]).strip()
    if "due_at" in payload:
        parsed = HomeworkCreate.model_validate({"title": item.title, "description": item.description or "content", "recipient_ids": [item.recipients[0].student_id], "due_at": payload["due_at"]}).due_at
        item.due_at = local_aware(parsed)
    if not item.description and not item.attachments:
        raise HTTPException(status_code=422, detail="Добавьте описание или хотя бы один файл")
    commit_or_422(db)
    return {"ok": True, "homework": homework_dict(teacher_homework(db, teacher.id, item.id))}


@router.delete("/api/homework/{homework_id}")
@router.delete("/api/assignments/{homework_id}")
def delete_homework_api(homework_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_homework(db, teacher.id, homework_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/api/homework-recipients/{recipient_id}")
def get_teacher_recipient_api(recipient_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_recipient(db, teacher.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    row = recipient_dict(item, include_history=True)
    row["homework"] = homework_dict(item.homework, include_recipients=False)
    return {"ok": True, "recipient": row}


@router.post("/api/homework-recipients/{recipient_id}/reviews")
@router.post("/api/submissions/{recipient_id}/reviews")
async def review_homework_api(request: Request, recipient_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    item = teacher_recipient(db, teacher.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Работа не найдена")
    try:
        data = HomeworkReviewCreate.model_validate(payload_dict(await request.json()))
        updated = review_homework(db, teacher, item, data)
    except (ValidationError, ValueError, PermissionError) as error:
        db.rollback()
        detail = error.errors()[0]["msg"] if isinstance(error, ValidationError) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error
    return {"ok": True, "recipient": recipient_dict(updated, include_history=True)}


@router.get("/api/student/homework")
def list_student_homework_api(db: Session = Depends(get_db), student: Student = Depends(get_current_student)):
    rows = []
    for item in student_recipients(db, student.id):
        row = recipient_dict(item)
        row["homework"] = homework_dict(item.homework, include_recipients=False)
        rows.append(row)
    return {"ok": True, "assignments": rows}


@router.get("/api/student/homework/{recipient_id}")
def get_student_homework_api(recipient_id: int, db: Session = Depends(get_db), student: Student = Depends(get_current_student)):
    item = student_recipient(db, student.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    row = recipient_dict(item, include_history=True)
    row["homework"] = homework_dict(item.homework, include_recipients=False)
    return {"ok": True, "recipient": row}


@router.post("/api/student/homework/{recipient_id}/submissions")
async def submit_student_homework_api(request: Request, recipient_id: int, db: Session = Depends(get_db), student: Student = Depends(get_current_student)):
    item = student_recipient(db, student.id, recipient_id)
    if not item:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    try:
        data = HomeworkSubmissionCreate.model_validate(payload_dict(await request.json()))
        updated = submit_homework(db, student, item, data)
    except (ValidationError, ValueError, PermissionError) as error:
        db.rollback()
        detail = error.errors()[0]["msg"] if isinstance(error, ValidationError) else str(error)
        raise HTTPException(status_code=422, detail=detail) from error
    return {"ok": True, "recipient": recipient_dict(updated, include_history=True)}


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
    original_name = unquote(request.headers.get("X-Filename", "").strip())
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


@router.post("/api/student/files/upload")
async def upload_student_file(request: Request, db: Session = Depends(get_db), student: Student = Depends(get_current_student)):
    if not student.user_id:
        raise HTTPException(status_code=422, detail="Профиль ученика не связан с аккаунтом")
    original_name = unquote(request.headers.get("X-Filename", "").strip())
    if not original_name:
        raise HTTPException(status_code=422, detail="Передайте имя файла в X-Filename")
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Файл пуст")
    storage_path = None
    try:
        stored_name, storage_path = store_bytes(original_name, content)
        item = FileResource(
            owner_id=student.user_id,
            original_name=original_name,
            stored_name=stored_name,
            storage_path=storage_path,
            mime_type=request.headers.get("Content-Type"),
            size=len(content),
            title=request.headers.get("X-Title", original_name),
            kind=request.headers.get("X-File-Kind", "Файл"),
        )
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
        return scoped_assignment(db, teacher.id, resource_id), "attachments"
    if resource == "homework":
        return scoped_assignment(db, teacher.id, resource_id), "attachments"
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





@router.get("/", response_class=HTMLResponse, name="landing")
async def landing(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/landing.html",
        context={"navigation": get_auth_navigation(request)},
    )


@router.get("/invite", response_class=HTMLResponse, name="student_invite")
async def student_invite(request: Request, user: User | None = Depends(optional_current_user)):
    return templates.TemplateResponse(request=request, name="pages/invite.html", context={})


@router.get("/login", response_class=HTMLResponse, name="auth_login")
async def login(request: Request, user: User | None = Depends(optional_current_user)):
    if user is not None:
        return RedirectResponse("/dashboard" if user.role == "teacher" else "/student/homework", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="pages/login.html",
        context={"navigation": get_auth_navigation(request)},
    )


@router.get("/register", response_class=HTMLResponse, name="auth_register")
async def register(request: Request, user: User | None = Depends(optional_current_user)):
    if user is not None:
        return RedirectResponse("/dashboard" if user.role == "teacher" else "/student/homework", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="pages/register.html",
        context={"navigation": get_auth_navigation(request)},
    )
