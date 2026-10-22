from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

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

MOSCOW = ZoneInfo("Europe/Moscow")
LESSON_STATUSES = {"scheduled", "completed_unpaid", "completed_paid", "cancelled"}
MONTHS = ("", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


def local_datetime(date_value: str, time_value: str) -> datetime:
    clock = time.fromisoformat(time_value)
    if clock.tzinfo is not None:
        raise ValueError("Укажите местное время Europe/Moscow без смещения")
    return datetime.combine(date.fromisoformat(date_value), clock, tzinfo=MOSCOW)


def localize(value: datetime) -> datetime:
    if value.tzinfo is None:
        # SQLite used by tests drops tzinfo; application datetimes are authored in Moscow time.
        return value.replace(tzinfo=MOSCOW)
    return value.astimezone(MOSCOW)


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
        "end_date_iso": end.date().isoformat(),
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
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
        "subject": "",
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
    ).where(Lesson.teacher_id == teacher.id).order_by(Lesson.start_at, Lesson.id)))
    assignments = teacher_homeworks(db, teacher.id)
    materials = list(db.scalars(select(FileResource).where(FileResource.owner_id == teacher.id).order_by(FileResource.id)))
    now = datetime.now(timezone.utc)
    next_lesson = next((item for item in lessons if item.status == "scheduled" and localize(item.end_at) > now), None)
    lesson_rows = [lesson_dict(item, next_id=next_lesson.id if next_lesson else None) for item in lessons]
    next_row = next((item for item in lesson_rows if item["is_next"]), None)
    if next_row is not None and next_lesson is not None:
        start, end = localize(next_lesson.start_at), localize(next_lesson.end_at)
        seconds = (start - now).total_seconds()
        if seconds <= 0:
            countdown = "Идёт занятие"
        elif seconds < 60:
            countdown = "Менее минуты"
        else:
            days, minutes = divmod(ceil(seconds / 60), 1440)
            hours, minutes = divmod(minutes, 60)
            parts = [f"{value} {unit}" for value, unit in ((days, "д"), (hours, "ч"), (minutes, "мин")) if value]
            countdown = "Через " + " ".join(parts)
        next_row.update(start_at=start.isoformat(), end_at=end.isoformat(),
                        date_full=f"{next_row['date']} {start.year}", countdown=countdown,
                        server_now=now.isoformat())
    assignment_rows = [assignment_dict(item) for item in assignments]
    today = now.astimezone(MOSCOW).date()
    notifications = notification_rows(db, teacher.id)
    return {
        "teacher": teacher_dict(teacher),
        "students": [student_dict(item) for item in students],
        "lessons": lesson_rows,
        "today_lessons": [item for item in lesson_rows if item["date_iso"] == today.isoformat()],
        "assignments": assignment_rows,
        "materials": [file_dict(item) for item in materials],
        "notifications": notifications,
        "next_lesson": next_row,
        "calendar_today": today.isoformat(),
        "calendar_time": now.astimezone(MOSCOW).strftime("%H:%M"),
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
    stmt = select(Lesson).options(
        selectinload(Lesson.student).selectinload(Student.user),
        selectinload(Lesson.materials),
        selectinload(Lesson.homeworks).selectinload(Homework.attachments),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.student),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.submissions),
        selectinload(Lesson.homeworks).selectinload(Homework.recipients).selectinload(HomeworkRecipient.reviews),
    ).where(Lesson.teacher_id == teacher.id)
    if date_from:
        stmt = stmt.where(Lesson.end_at > datetime.combine(date_from, time.min, tzinfo=MOSCOW))
    if date_to:
        stmt = stmt.where(Lesson.start_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW))
    lessons = list(db.scalars(stmt.order_by(Lesson.start_at)))
    events = []
    for lesson in lessons:
        row = lesson_dict(lesson)
        events.append({
            "id": f"lesson-{lesson.id}", "entity_id": lesson.id, "type": "lessons",
            "title": row["student"]["name"], "subtitle": f"{row['subject']} · {row['topic']}",
            "avatar": row["student"]["initials"], "date": row["date_iso"], "start": row["start"], "end": row["end"],
            "url": f"/lessons/{lesson.id}", "draggable": True, "status": lesson.status, "lesson": row,
        })
    submissions = list(db.scalars(select(HomeworkRecipient).join(Homework).where(Homework.teacher_id == teacher.id, HomeworkRecipient.status == "SUBMITTED")))
    for item in submissions:
        submitted = localize(item.submitted_at)
        end = submitted + timedelta(hours=1)
        events.append({"id": f"review-{item.id}", "type": "reviews", "title": "Проверка задания", "subtitle": "Работа ученика", "date": submitted.date().isoformat(), "start": submitted.strftime("%H:00"), "end_date": end.date().isoformat(), "end": end.strftime("%H:00"), "url": f"/homework-recipients/{item.id}", "draggable": False})
    return events


def ensure_lesson_slot(db: Session, teacher_id: int, start_at: datetime, end_at: datetime, *, exclude_id: int | None = None) -> None:
    if end_at <= start_at:
        raise ValueError("Окончание занятия должно быть позже начала")
    statement = select(Lesson.id).where(Lesson.teacher_id == teacher_id, Lesson.start_at < end_at, Lesson.end_at > start_at)
    if exclude_id is not None:
        statement = statement.where(Lesson.id != exclude_id)
    if db.scalar(statement):
        raise ValueError("Это время уже занято")


def lesson_values(db: Session, teacher: User, payload: dict[str, Any], *, item: Lesson | None = None) -> dict[str, Any]:
    """Validate a complete proposed state before mutating a lesson."""
    raw_id = payload.get("student_id", item.student_id if item else None)
    if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)) or not str(raw_id).isdecimal():
        raise ValueError("Ученик не найден")
    if int(raw_id) > 2**63 - 1:
        raise ValueError("Ученик не найден")
    student = scoped_student(db, teacher.id, int(raw_id))
    if student is None or (student.archived_at is not None and (item is None or student.id != item.student_id)):
        raise ValueError("Ученик не найден")

    def text(field: str, default: str, maximum: int, *, required: bool = False) -> str:
        value = payload.get(field, default)
        if not isinstance(value, str):
            raise ValueError("Поля занятия должны быть строками")
        value = value.strip() if field != "teacher_note" else value
        if required and not value:
            raise ValueError("Укажите тему занятия" if field == "topic" else "Укажите предмет")
        if len(value) > maximum:
            raise ValueError("Заметка не должна превышать 500 символов" if field == "teacher_note" else "Поле занятия слишком длинное")
        return value

    status = payload.get("status", item.status if item else "scheduled")
    if not isinstance(status, str) or status not in LESSON_STATUSES:
        raise ValueError("Неизвестный статус занятия")
    start_date = payload.get("date", localize(item.start_at).date().isoformat() if item else "")
    start_time = payload.get("start", localize(item.start_at).time().isoformat() if item else "")
    end_time = payload.get("end", localize(item.end_at).time().isoformat() if item else "")
    if not all(isinstance(value, str) for value in (start_date, start_time, end_time)):
        raise ValueError("Некорректная дата или время")
    start_at = local_datetime(start_date, start_time)
    day_offset = localize(item.end_at).date() - localize(item.start_at).date() if item else timedelta()
    end_date = payload.get("end_date", (start_at.date() + day_offset).isoformat())
    if not isinstance(end_date, str):
        raise ValueError("Некорректная дата или время")
    end_at = local_datetime(end_date, end_time)
    if end_at <= start_at:
        raise ValueError("Окончание занятия должно быть позже начала")
    if item is None or start_at != localize(item.start_at) or end_at != localize(item.end_at):
        ensure_lesson_slot(db, teacher.id, start_at, end_at, exclude_id=item.id if item else None)
    location = text("location", item.location if item else "", 300)
    meeting_url = text("meeting_url", item.meeting_url or "" if item else "", 1000) if "meeting_url" in payload else (
        location if "location" in payload and location.startswith(("http://", "https://")) else item.meeting_url if item and "location" not in payload else None
    )
    return {
        "student_id": student.id, "student": student, "start_at": start_at, "end_at": end_at, "status": status,
        "subject": text("subject", item.subject if item else student.subject, 120, required=True),
        "topic": text("topic", item.topic if item else "", 200, required=True), "location": location,
        "meeting_url": meeting_url or None, "teacher_note": text("teacher_note", item.teacher_note if item else "", 500),
    }


def lesson_material_labels(payload: dict[str, Any]) -> list[str]:
    labels = payload.get("materials", [])
    if not isinstance(labels, list) or any(not isinstance(label, str) or len(label) > 200 for label in labels):
        raise ValueError("Некорректный список материалов")
    return [label.strip() for label in labels if label.strip()]


def create_entity(db: Session, teacher: User, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "student":
        from app.students.schemas import validated_fields
        item = Student(teacher_id=teacher.id, **validated_fields(payload))
        db.add(item)
        db.flush()
        return student_dict(item)
    if kind == "lesson":
        values = lesson_values(db, teacher, payload)
        labels = lesson_material_labels(payload)
        item = Lesson(teacher_id=teacher.id, **values)
        db.add(item)
        item.materials = [material_from_label(db, teacher, label) for label in labels]
        db.flush()
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
