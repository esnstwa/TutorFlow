from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.homework.schemas import HomeworkCreate
from app.homework.service import (
    homework_dict,
    recipient_dict,
    teacher_homework,
    teacher_homeworks,
    teacher_recipient,
)
from app.models import (
    Conversation,
    FileResource,
    Homework,
    HomeworkRecipient,
    HomeworkReview,
    Lesson,
    Message,
    Student,
    User,
)
from app.schedule.calendar import CalendarEventService, MOSCOW, localize
from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource

LESSON_STATUSES = {"scheduled", "completed_unpaid", "completed_paid", "cancelled"}
MONTHS = ("", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


def local_datetime(date_value: str, time_value: str) -> datetime:
    return datetime.combine(date.fromisoformat(date_value), time.fromisoformat(time_value), tzinfo=MOSCOW)


def date_label(value: datetime) -> str:
    value = localize(value)
    return f"{value.day} {MONTHS[value.month]}"


def initials(first_name: str, last_name: str = "") -> str:
    return "".join(part[0] for part in (first_name, last_name) if part).upper()


def student_dict(student: Student) -> dict[str, Any]:
    from sqlalchemy.orm import object_session
    from app.students.service import lifecycle
    state = lifecycle(object_session(student), student)
    name = " ".join(part for part in (student.first_name, student.last_name) if part)
    return {
        "archived": student.archived_at is not None,
        "lifecycle": state,
        "lifecycle_label": {"unlinked": "Не связан", "invited": "Приглашен", "linked": "Связан"}[state],
        "id": student.id,
        "name": name,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "initials": initials(student.first_name, student.last_name),
        "subject": student.subject,
        "grade": student.grade,
        "email": student.email or (student.user.email if student.user else ""),
        "avatar": student.avatar,
    }


def student_directory(db: Session, teacher: User, query: str = "", subject: str = "", archived: str = "active") -> dict[str, Any]:
    if archived not in {"active", "archived", "all"}:
        raise ValueError("Неизвестный фильтр архива")
    statement = select(Student).options(selectinload(Student.user)).where(Student.teacher_id == teacher.id)
    if archived == "active":
        statement = statement.where(Student.archived_at.is_(None))
    elif archived == "archived":
        statement = statement.where(Student.archived_at.is_not(None))
    rows = [student_dict(item) for item in db.scalars(statement.order_by(Student.id))]
    query, subject = query.strip(), subject.strip()
    terms = query.casefold().replace("ё", "е").split()
    visible = []
    for row in rows:
        searchable = " ".join(row[field] for field in ("name", "email", "grade", "subject"))
        searchable = searchable.casefold().replace("ё", "е")
        if (not subject or row["subject"] == subject) and all(term in searchable for term in terms):
            visible.append(row)
    return {
        "directory_students": visible,
        "directory_total": len(rows),
        "directory_subjects": sorted({row["subject"] for row in rows if row["subject"]}),
        "directory_query": query,
        "directory_subject": subject,
        "directory_archived": archived,
    }


def file_dict(item: FileResource) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "kind": item.kind,
        "type": item.kind,
        "description": item.description,
        "url": item.url,
        "original_name": item.original_name,
        "stored_name": item.stored_name,
        "path": item.storage_path,
        "mime_type": item.mime_type,
        "size": item.size,
        "updated": "Сегодня" if item.updated_at.date() == datetime.now(timezone.utc).date() else date_label(item.updated_at),
    }


def lesson_dict(lesson: Lesson, *, next_id: int | None = None) -> dict[str, Any]:
    start = localize(lesson.start_at)
    end = localize(lesson.end_at)
    student = student_dict(lesson.student)
    return {
        "id": lesson.id,
        "student_id": lesson.student_id,
        "student": student,
        "subject": lesson.subject,
        "topic": lesson.topic,
        "date": date_label(start),
        "date_iso": start.date().isoformat(),
        "start": start.strftime("%H:%M"),
        "end": end.strftime("%H:%M"),
        "is_next": lesson.id == next_id,
        "status": lesson.status,
        "location": lesson.location or lesson.meeting_url or "",
        "meeting_url": lesson.meeting_url,
        "teacher_note": lesson.teacher_note,
        "materials": [item.title for item in lesson.materials],
        "material_items": [file_dict(item) for item in lesson.materials],
        "homeworks": [homework_dict(item, include_recipients=False) for item in lesson.homeworks],
    }


def assignment_dict(item: Homework) -> dict[str, Any]:
    """Compatibility serializer for templates that still call assignments homeworks."""
    return homework_dict(item)


def submission_dict(item: HomeworkRecipient) -> dict[str, Any]:
    row = recipient_dict(item, include_history=True)
    row["assignment"] = homework_dict(item.homework, include_recipients=False)
    return row


def review_dict(item: HomeworkReview) -> dict[str, Any]:
    return {
        "id": item.id,
        "recipient_id": item.homework_recipient_id,
        "result": item.action,
        "comment": item.teacher_comment,
        "reviewed_at": item.created_at.isoformat(),
    }


def teacher_dict(teacher: User) -> dict[str, Any]:
    return {
        "id": teacher.id,
        "name": teacher.first_name,
        "first_name": teacher.first_name,
        "last_name": teacher.last_name,
        "initials": initials(teacher.first_name, teacher.last_name),
        "subject": "Математика",
        "email": teacher.email,
        "avatar": teacher.avatar,
    }


def scoped_student(db: Session, teacher_id: int, student_id: int) -> Student | None:
    return db.scalar(select(Student).options(selectinload(Student.user)).where(Student.id == student_id, Student.teacher_id == teacher_id))


def scoped_lesson(db: Session, teacher_id: int, lesson_id: int) -> Lesson | None:
    return db.scalar(
        select(Lesson)
        .options(
            selectinload(Lesson.student).selectinload(Student.user),
            selectinload(Lesson.materials),
            selectinload(Lesson.homeworks).selectinload(Homework.attachments),
            selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.student),
            selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.submissions),
            selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.reviews),
        )
        .where(Lesson.id == lesson_id, Lesson.teacher_id == teacher_id)
    )


def scoped_assignment(db: Session, teacher_id: int, assignment_id: int) -> Homework | None:
    return teacher_homework(db, teacher_id, assignment_id)


def scoped_submission(db: Session, teacher_id: int, submission_id: int) -> HomeworkRecipient | None:
    return teacher_recipient(db, teacher_id, submission_id)


def scoped_review(db: Session, teacher_id: int, review_id: int) -> HomeworkReview | None:
    return db.scalar(
        select(HomeworkReview)
        .join(HomeworkRecipient)
        .join(Homework)
        .where(HomeworkReview.id == review_id, Homework.teacher_id == teacher_id)
    )


def cabinet_data(db: Session, teacher: User) -> dict[str, Any]:
    students = list(db.scalars(select(Student).options(selectinload(Student.user)).where(Student.teacher_id == teacher.id, Student.archived_at.is_(None)).order_by(Student.id)))
    lessons = list(db.scalars(select(Lesson).options(
        selectinload(Lesson.student).selectinload(Student.user),
        selectinload(Lesson.materials),
        selectinload(Lesson.homeworks).selectinload(Homework.attachments),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.student),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.submissions),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.reviews),
    ).where(Lesson.teacher_id == teacher.id).order_by(Lesson.start_at)))
    assignments = teacher_homeworks(db, teacher.id)
    materials = list(db.scalars(select(FileResource).where(FileResource.owner_id == teacher.id).order_by(FileResource.id)))
    now = datetime.now(timezone.utc)
    next_lesson = next((item for item in lessons if item.start_at.replace(tzinfo=item.start_at.tzinfo or timezone.utc) >= now and item.status == "scheduled"), lessons[0] if lessons else None)
    lesson_rows = [lesson_dict(item, next_id=next_lesson.id if next_lesson else None) for item in lessons]
    assignment_rows = [assignment_dict(item) for item in assignments]
    today = datetime.now(MOSCOW).date()
    notifications = notification_rows(db, teacher.id)
    return {
        "teacher": teacher_dict(teacher),
        "students": [student_dict(item) for item in students],
        "lessons": lesson_rows,
        "today_lessons": [item for item in lesson_rows if item["date_iso"] == today.isoformat()],
        "assignments": assignment_rows,
        "materials": [file_dict(item) for item in materials],
        "notifications": notifications,
        "next_lesson": next((item for item in lesson_rows if item["is_next"]), lesson_rows[0] if lesson_rows else None),
        "calendar_today": today.isoformat(),
        "calendar_time": datetime.now(MOSCOW).strftime("%H:%M"),
    }


def notification_rows(db: Session, teacher_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    submission = db.scalar(select(HomeworkRecipient).join(Homework).options(selectinload(HomeworkRecipient.student), selectinload(HomeworkRecipient.homework)).where(Homework.teacher_id == teacher_id, HomeworkRecipient.status == "SUBMITTED").order_by(HomeworkRecipient.submitted_at.desc()))
    if submission:
        rows.append({"id": submission.id, "kind": "submission", "target_id": submission.id, "icon": "assignment", "tone": "blue", "title": "Новая работа на проверку", "description": f"{student_dict(submission.student)['name']} · {submission.homework.title}", "when": "Недавно"})
    overdue = db.scalar(select(HomeworkRecipient).join(Homework).options(selectinload(HomeworkRecipient.student), selectinload(HomeworkRecipient.homework)).where(Homework.teacher_id == teacher_id, Homework.due_at < datetime.now(timezone.utc), HomeworkRecipient.status == "ASSIGNED").order_by(Homework.due_at))
    if overdue:
        rows.append({"id": overdue.homework_id, "kind": "assignment", "target_id": overdue.homework_id, "icon": "alert", "tone": "orange", "title": "Просроченное задание", "description": f"{student_dict(overdue.student)['name']} · {overdue.homework.title}", "when": date_label(overdue.homework.due_at)})
    conversation = db.scalar(select(Conversation).options(selectinload(Conversation.student), selectinload(Conversation.messages)).where(Conversation.teacher_id == teacher_id).order_by(Conversation.updated_at.desc()))
    if conversation and conversation.messages:
        message = sorted(conversation.messages, key=lambda item: item.sent_at)[-1]
        rows.append({"id": conversation.id, "kind": "message", "target_id": conversation.id, "icon": "message", "tone": "purple", "title": "Новое сообщение", "description": f"{conversation.student.first_name}: «{message.body}»", "when": localize(message.sent_at).strftime("%H:%M")})
    return rows


def calendar_events(db: Session, teacher: User, *, date_from: date | None = None, date_to: date | None = None) -> list[dict[str, Any]]:
    """Compatibility entry point used by the schedule page and lessons API.

    This is the production composition point: bind the shared consumer to the
    caller's SQLAlchemy session and the existing lesson serializer. HTTP
    consumers keep their original call and response shape.
    """
    source = SQLAlchemyCalendarEventSource(db, lesson_dict)
    projected = CalendarEventService(source).list_events(
        teacher_id=teacher.id,
        date_from=date_from,
        date_to=date_to,
    )
    events: list[dict[str, Any]] = []
    for event in projected:
        if event.kind == "lesson":
            row = event.details
            assert row is not None
            student = row["student"]
            events.append(
                {
                    "id": f"lesson-{event.entity_id}",
                    "entity_id": event.entity_id,
                    "type": "lessons",
                    "title": student["name"],
                    "subtitle": f"{student['subject']} · {row['topic']}",
                    "avatar": student["initials"],
                    "date": event.start_at.date().isoformat(),
                    "start": event.start_at.strftime("%H:%M"),
                    "end": event.end_at.strftime("%H:%M"),
                    "url": f"/lessons/{event.entity_id}",
                    "draggable": True,
                    "status": event.status,
                    "lesson": row,
                }
            )
        else:
            events.append(
                {
                    "id": f"review-{event.entity_id}",
                    "type": "reviews",
                    "title": "Проверка задания",
                    "subtitle": "Работа ученика",
                    "date": event.start_at.date().isoformat(),
                    "start": event.start_at.strftime("%H:%M"),
                    "end": event.end_at.strftime("%H:%M"),
                    "url": f"/homework-recipients/{event.entity_id}",
                    "draggable": False,
                }
            )
    return events


def create_entity(db: Session, teacher: User, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "student":
        from app.students.schemas import validated_fields
        item = Student(teacher_id=teacher.id, **validated_fields(payload))
        db.add(item)
        db.flush()
        return student_dict(item)
    if kind == "lesson":
        student = scoped_student(db, teacher.id, int(payload["student_id"]))
        if not student or student.archived_at is not None:
            raise ValueError("Ученик не найден")
        start_at = local_datetime(str(payload["date"]), str(payload["start"]))
        end_at = local_datetime(str(payload["date"]), str(payload["end"]))
        if end_at <= start_at:
            raise ValueError("Окончание занятия должно быть позже начала")
        collision = db.scalar(select(Lesson.id).where(Lesson.teacher_id == teacher.id, Lesson.start_at < end_at, Lesson.end_at > start_at))
        if collision:
            raise ValueError("Это время уже занято")
        status = str(payload.get("status", "scheduled"))
        if status not in LESSON_STATUSES:
            raise ValueError("Неизвестный статус занятия")
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise ValueError("Укажите тему занятия")
        teacher_note = str(payload.get("teacher_note", ""))
        if len(teacher_note) > 500:
            raise ValueError("Заметка не должна превышать 500 символов")
        location = str(payload.get("location", "Онлайн · TutorFlow")).strip()
        meeting_url = str(payload.get("meeting_url", "")).strip() or None
        item = Lesson(teacher_id=teacher.id, student_id=student.id, subject=str(payload.get("subject") or student.subject), topic=topic, start_at=start_at, end_at=end_at, location=location, meeting_url=meeting_url, teacher_note=teacher_note, status=status)
        db.add(item)
        db.flush()
        item.student = student
        return lesson_dict(item)
    if kind == "assignment":
        due = datetime.combine(date.fromisoformat(str(payload["due"])), time(23, 59), tzinfo=MOSCOW)
        data = HomeworkCreate(
            title=str(payload["title"]).strip(),
            description=str(payload.get("description") or payload["title"]).strip(),
            recipient_ids=[int(payload["student_id"])],
            due_at=due,
        )
        from app.homework.service import create_homework

        return assignment_dict(create_homework(db, teacher, data))
    if kind == "material":
        title = str(payload["title"]).strip()
        kind_value = str(payload["kind"]).strip()
        item = FileResource(owner_id=teacher.id, original_name=title, title=title, kind=kind_value, size=0)
        db.add(item)
        db.flush()
        return file_dict(item)
    raise ValueError("Неизвестный тип сущности")


def material_from_label(db: Session, teacher: User, label: str) -> FileResource:
    item = db.scalar(select(FileResource).where(FileResource.owner_id == teacher.id, FileResource.title == label))
    if item:
        return item
    is_url = bool(urlparse(label).scheme)
    item = FileResource(owner_id=teacher.id, original_name=Path(urlparse(label).path).name or label, title=label, kind="Ссылка" if is_url else "Материал", url=label if is_url else None, size=0)
    db.add(item)
    db.flush()
    return item
