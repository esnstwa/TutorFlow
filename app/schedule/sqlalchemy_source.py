"""SQLAlchemy adapter for the storage-independent calendar contract."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Homework, HomeworkRecipient, Lesson, Student
from app.schedule.calendar import MOSCOW, CalendarLesson, CalendarSubmission

LessonSerializer = Callable[[Lesson], dict[str, Any]]


class SQLAlchemyCalendarEventSource:
    """Read calendar snapshots from the caller-owned SQLAlchemy session.

    Both read paths execute their ORM work inside ``session.no_autoflush`` so
    SQLAlchemy queries in that scope do not implicitly flush caller-owned
    pending changes. This is not a general write barrier: an explicit flush or
    side effects in a serializer are outside that guarantee. The adapter
    itself never calls ``flush``, ``commit``, ``rollback``, or ``close``;
    session ownership remains with the caller. The current production
    serializer is a read-only projection, but the adapter does not enforce
    callback purity. A serializer is supplied by the composition point so the
    adapter does not depend on the legacy application service module.
    """

    def __init__(self, session: Session, lesson_serializer: LessonSerializer) -> None:
        self._session = session
        self._lesson_serializer = lesson_serializer

    def lessons_for_teacher(
        self,
        teacher_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Sequence[CalendarLesson]:
        statement = select(Lesson).options(
            selectinload(Lesson.student).selectinload(Student.user),
            selectinload(Lesson.materials),
            selectinload(Lesson.homeworks).selectinload(Homework.attachments),
            selectinload(Lesson.homeworks)
            .selectinload(Homework.recipients)
            .selectinload(HomeworkRecipient.student),
            selectinload(Lesson.homeworks)
            .selectinload(Homework.recipients)
            .selectinload(HomeworkRecipient.submissions),
            selectinload(Lesson.homeworks)
            .selectinload(Homework.recipients)
            .selectinload(HomeworkRecipient.reviews),
        ).where(Lesson.teacher_id == teacher_id)
        if date_from is not None:
            statement = statement.where(
                Lesson.start_at
                >= datetime.combine(date_from, time.min, tzinfo=MOSCOW)
            )
        if date_to is not None:
            statement = statement.where(
                Lesson.start_at
                < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW)
            )

        with self._session.no_autoflush:
            lessons = self._session.scalars(statement.order_by(Lesson.start_at))
            return [
                CalendarLesson(
                    teacher_id=item.teacher_id,
                    lesson_id=item.id,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    status=item.status,
                    lesson=self._lesson_serializer(item),
                )
                for item in lessons
            ]

    def submissions_for_teacher(self, teacher_id: int) -> Sequence[CalendarSubmission]:
        statement = (
            select(HomeworkRecipient)
            .join(Homework)
            .where(
                Homework.teacher_id == teacher_id,
                HomeworkRecipient.status == "SUBMITTED",
            )
        )
        with self._session.no_autoflush:
            return [
                CalendarSubmission(
                    teacher_id=teacher_id,
                    recipient_id=item.id,
                    status=item.status,
                    submitted_at=item.submitted_at,
                )
                for item in self._session.scalars(statement)
            ]
