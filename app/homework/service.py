from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.homework.schemas import HomeworkCreate, HomeworkReviewCreate, HomeworkSubmissionCreate
from app.models import (
    FileResource,
    Homework,
    HomeworkRecipient,
    HomeworkReview,
    HomeworkSubmission,
    Lesson,
    Student,
    User,
)

MOSCOW = ZoneInfo("Europe/Moscow")
RECIPIENT_LABELS = {
    "ASSIGNED": "Выполняет",
    "SUBMITTED": "На проверке",
    "REVISION_REQUIRED": "На доработке",
    "COMPLETED": "Выполнено",
}


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def local_aware(value: datetime | None) -> datetime | None:
    """SQLite drops offsets; due dates and lessons are authored in Moscow wall time."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=MOSCOW)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def attachment_dict(item: FileResource) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "name": item.original_name,
        "kind": item.kind,
        "size": item.size,
        "mime_type": item.mime_type,
        "url": item.url,
    }


def student_brief(item: Student) -> dict[str, Any]:
    name = " ".join(part for part in (item.first_name, item.last_name) if part).strip()
    return {
        "id": item.id,
        "name": name,
        "first_name": item.first_name,
        "last_name": item.last_name,
        "initials": "".join(part[:1] for part in (item.first_name, item.last_name) if part).upper(),
        "grade": item.grade,
        "subject": item.subject,
    }


def is_overdue(item: HomeworkRecipient, *, now: datetime | None = None) -> bool:
    due = local_aware(item.homework.due_at)
    return bool(item.status == "ASSIGNED" and due and due < (now or now_utc()))


def recipient_status(item: HomeworkRecipient) -> tuple[str, str]:
    if is_overdue(item):
        return "OVERDUE", "Просрочено"
    return item.status, RECIPIENT_LABELS[item.status]


def submission_dict(item: HomeworkSubmission) -> dict[str, Any]:
    return {
        "id": item.id,
        "comment": item.comment,
        "created_at": aware(item.created_at).isoformat(),
        "created": aware(item.created_at).astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M"),
        "attachments": [attachment_dict(file) for file in item.attachments],
    }


def review_dict(item: HomeworkReview) -> dict[str, Any]:
    return {
        "id": item.id,
        "action": item.action,
        "teacher_comment": item.teacher_comment,
        "created_at": aware(item.created_at).isoformat(),
        "created": aware(item.created_at).astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M"),
    }


def recipient_dict(item: HomeworkRecipient, *, include_history: bool = False) -> dict[str, Any]:
    status_value, status_label = recipient_status(item)
    result = {
        "id": item.id,
        "student": student_brief(item.student),
        "status_value": status_value,
        "status": status_label,
        "assigned_at": aware(item.assigned_at).isoformat(),
        "submitted_at": aware(item.submitted_at).isoformat() if item.submitted_at else None,
        "completed_at": aware(item.completed_at).isoformat() if item.completed_at else None,
        "submission_count": len(item.submissions),
        "latest_review": review_dict(item.reviews[-1]) if item.reviews else None,
    }
    if include_history:
        result["submissions"] = [submission_dict(row) for row in item.submissions]
        result["reviews"] = [review_dict(row) for row in item.reviews]
    return result


def homework_dict(item: Homework, *, include_recipients: bool = True) -> dict[str, Any]:
    counts = {"ASSIGNED": 0, "SUBMITTED": 0, "REVISION_REQUIRED": 0, "COMPLETED": 0, "OVERDUE": 0}
    recipient_rows = []
    for recipient in item.recipients:
        row = recipient_dict(recipient)
        counts[row["status_value"]] += 1
        recipient_rows.append(row)
    lesson = None
    if item.lesson:
        lesson = {
            "id": item.lesson.id,
            "subject": item.lesson.subject,
            "topic": item.lesson.topic,
            "date": local_aware(item.lesson.start_at).astimezone(MOSCOW).strftime("%d.%m.%Y"),
        }
    due = local_aware(item.due_at)
    result = {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "due_at": due.isoformat() if due else None,
        "due": due.astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M") if due else "Без срока",
        "lesson": lesson,
        "attachments": [attachment_dict(file) for file in item.attachments],
        "recipient_count": len(item.recipients),
        "counts": counts,
        "created_at": aware(item.created_at).isoformat(),
    }
    if include_recipients:
        result["recipients"] = recipient_rows
    return result


def _homework_options():
    return (
        selectinload(Homework.lesson),
        selectinload(Homework.attachments),
        selectinload(Homework.recipients).selectinload(HomeworkRecipient.student).selectinload(Student.user),
        selectinload(Homework.recipients).selectinload(HomeworkRecipient.submissions).selectinload(HomeworkSubmission.attachments),
        selectinload(Homework.recipients).selectinload(HomeworkRecipient.reviews),
    )


def teacher_homeworks(db: Session, teacher_id: int) -> list[Homework]:
    return list(
        db.scalars(
            select(Homework)
            .options(*_homework_options())
            .where(Homework.teacher_id == teacher_id)
            .order_by(Homework.created_at.desc(), Homework.id.desc())
        ).unique()
    )


def teacher_homework(db: Session, teacher_id: int, homework_id: int) -> Homework | None:
    return db.scalar(
        select(Homework)
        .options(*_homework_options())
        .where(Homework.id == homework_id, Homework.teacher_id == teacher_id)
    )


def teacher_recipient(db: Session, teacher_id: int, recipient_id: int) -> HomeworkRecipient | None:
    return db.scalar(
        select(HomeworkRecipient)
        .join(Homework)
        .options(
            selectinload(HomeworkRecipient.student).selectinload(Student.user),
            selectinload(HomeworkRecipient.homework).selectinload(Homework.lesson),
            selectinload(HomeworkRecipient.homework).selectinload(Homework.attachments),
            selectinload(HomeworkRecipient.submissions).selectinload(HomeworkSubmission.attachments),
            selectinload(HomeworkRecipient.reviews),
        )
        .where(HomeworkRecipient.id == recipient_id, Homework.teacher_id == teacher_id)
    )


def student_recipient(db: Session, student_id: int, recipient_id: int) -> HomeworkRecipient | None:
    return db.scalar(
        select(HomeworkRecipient)
        .options(
            selectinload(HomeworkRecipient.student).selectinload(Student.user),
            selectinload(HomeworkRecipient.homework).selectinload(Homework.teacher),
            selectinload(HomeworkRecipient.homework).selectinload(Homework.lesson),
            selectinload(HomeworkRecipient.homework).selectinload(Homework.attachments),
            selectinload(HomeworkRecipient.submissions).selectinload(HomeworkSubmission.attachments),
            selectinload(HomeworkRecipient.reviews),
        )
        .where(HomeworkRecipient.id == recipient_id, HomeworkRecipient.student_id == student_id)
    )


def student_recipients(db: Session, student_id: int) -> list[HomeworkRecipient]:
    return list(
        db.scalars(
            select(HomeworkRecipient)
            .join(Homework)
            .options(
                selectinload(HomeworkRecipient.student),
                selectinload(HomeworkRecipient.homework).selectinload(Homework.teacher),
                selectinload(HomeworkRecipient.homework).selectinload(Homework.lesson),
                selectinload(HomeworkRecipient.homework).selectinload(Homework.attachments),
                selectinload(HomeworkRecipient.submissions).selectinload(HomeworkSubmission.attachments),
                selectinload(HomeworkRecipient.reviews),
            )
            .where(HomeworkRecipient.student_id == student_id)
            .order_by(Homework.due_at.asc(), Homework.id.desc())
        ).unique()
    )


def search_students(db: Session, teacher_id: int, query: str) -> list[Student]:
    needle = query.strip().casefold()
    students = list(db.scalars(select(Student).where(Student.teacher_id == teacher_id, Student.archived_at.is_(None))))
    if not needle:
        return sorted(students, key=lambda row: (row.first_name.casefold(), row.last_name.casefold()))[:20]

    def rank(item: Student) -> tuple[int, str, str] | None:
        first = item.first_name.casefold()
        last = item.last_name.casefold()
        full = f"{first} {last}".strip()
        if first.startswith(needle):
            score = 0
        elif last.startswith(needle):
            score = 1
        elif needle in full:
            score = 2
        else:
            return None
        return score, first, last

    ranked = [(rank(item), item) for item in students]
    return [item for item_rank, item in sorted((row for row in ranked if row[0] is not None), key=lambda row: row[0])][:20]


def create_homework(db: Session, teacher: User, data: HomeworkCreate) -> Homework:
    lesson = None
    if data.lesson_id is not None:
        lesson = db.scalar(select(Lesson).where(Lesson.id == data.lesson_id, Lesson.teacher_id == teacher.id))
        if not lesson:
            raise ValueError("Занятие не найдено")

    students = list(
        db.scalars(
            select(Student).where(Student.teacher_id == teacher.id, Student.archived_at.is_(None), Student.id.in_(data.recipient_ids))
        )
    )
    if len(students) != len(data.recipient_ids):
        raise ValueError("Один или несколько учеников не найдены")

    attachments = []
    if data.attachment_ids:
        attachments = list(
            db.scalars(
                select(FileResource).where(
                    FileResource.owner_id == teacher.id,
                    FileResource.id.in_(data.attachment_ids),
                )
            )
        )
        if len(attachments) != len(data.attachment_ids):
            raise ValueError("Один или несколько файлов не найдены")

    due_at = local_aware(data.due_at)
    item = Homework(
        teacher_id=teacher.id,
        lesson_id=lesson.id if lesson else None,
        title=data.title,
        description=data.description,
        due_at=due_at,
    )
    item.attachments.extend(attachments)
    item.recipients.extend(HomeworkRecipient(student=student, status="ASSIGNED") for student in students)
    db.add(item)
    db.commit()
    return teacher_homework(db, teacher.id, item.id)


def submit_homework(
    db: Session,
    student: Student,
    recipient: HomeworkRecipient,
    data: HomeworkSubmissionCreate,
) -> HomeworkRecipient:
    if recipient.student_id != student.id:
        raise PermissionError("Задание принадлежит другому ученику")
    if recipient.status not in {"ASSIGNED", "REVISION_REQUIRED"}:
        raise ValueError("Сейчас это задание нельзя отправить")
    if not student.user_id:
        raise ValueError("Профиль ученика не связан с аккаунтом")

    attachments = []
    if data.attachment_ids:
        attachments = list(
            db.scalars(
                select(FileResource).where(
                    FileResource.owner_id == student.user_id,
                    FileResource.id.in_(data.attachment_ids),
                )
            )
        )
        if len(attachments) != len(data.attachment_ids):
            raise ValueError("Один или несколько файлов не найдены")

    timestamp = now_utc()
    submission = HomeworkSubmission(comment=data.comment, created_at=timestamp, updated_at=timestamp)
    submission.attachments.extend(attachments)
    recipient.submissions.append(submission)
    recipient.status = "SUBMITTED"
    recipient.submitted_at = timestamp
    recipient.completed_at = None
    db.commit()
    return student_recipient(db, student.id, recipient.id)


def review_homework(
    db: Session,
    teacher: User,
    recipient: HomeworkRecipient,
    data: HomeworkReviewCreate,
) -> HomeworkRecipient:
    if recipient.homework.teacher_id != teacher.id:
        raise PermissionError("Задание принадлежит другому преподавателю")
    if recipient.status != "SUBMITTED":
        raise ValueError("Проверить можно только отправленную работу")
    timestamp = now_utc()
    recipient.reviews.append(
        HomeworkReview(action=data.action, teacher_comment=data.teacher_comment, created_at=timestamp)
    )
    recipient.status = data.action
    recipient.completed_at = timestamp if data.action == "COMPLETED" else None
    db.commit()
    return teacher_recipient(db, teacher.id, recipient.id)
