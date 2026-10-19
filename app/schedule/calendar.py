"""Storage-independent schedule projection contract.

This module produces neutral event snapshots. HTTP and presentation fields are
added by the existing application compatibility layer, not here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Mapping, Protocol
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True, slots=True)
class CalendarLesson:
    """Read-only lesson data needed for a neutral calendar projection."""

    teacher_id: int
    lesson_id: int
    start_at: datetime
    end_at: datetime
    status: str
    lesson: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CalendarSubmission:
    """Read-only snapshot of one submitted homework recipient."""

    teacher_id: int
    recipient_id: int
    status: str
    submitted_at: datetime | None


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """Interface-neutral time interval projected from a schedule record."""

    kind: Literal["lesson", "review"]
    entity_id: int
    start_at: datetime
    end_at: datetime
    status: str | None = None
    details: Mapping[str, Any] | None = None


class CalendarEventSource(Protocol):
    """Storage boundary for the calendar projection.

    Implementations return snapshots in their documented order and do not
    mutate persistent state. The caller owns records returned by each call.
    """

    def lessons_for_teacher(
        self,
        teacher_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Sequence[CalendarLesson]:
        """Return the teacher's lessons in the requested start-date range."""
        ...

    def submissions_for_teacher(self, teacher_id: int) -> Sequence[CalendarSubmission]:
        """Return submitted homework recipients for the teacher."""
        ...


def localize(value: datetime) -> datetime:
    """Interpret naive stored datetimes as Moscow time; convert aware values."""
    if value.tzinfo is None:
        # SQLite used by tests drops tzinfo; app datetimes are authored in Moscow.
        return value.replace(tzinfo=MOSCOW)
    return value.astimezone(MOSCOW)


class CalendarEventService:
    """Build calendar events from an injected source.

    Args:
        source: A :class:`CalendarEventSource` implementation.

    The public operation is :meth:`list_events`. It queries lessons first,
    then submitted work, preserving the order: lessons sorted by start time
    followed by reviews in source order. It returns neutral data rather than
    HTTP routes, titles, or other presentation fields. Errors from the source
    or malformed snapshots propagate unchanged; no writes are performed.

    Example:
        >>> source = InMemoryCalendarEventSource(lessons=[], submissions=[])
        >>> CalendarEventService(source).list_events(teacher_id=12)
        []
    """

    def __init__(self, source: CalendarEventSource) -> None:
        self._source = source

    def list_events(
        self,
        *,
        teacher_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[CalendarEvent]:
        """Return neutral schedule events for one teacher.

        ``date_from`` and ``date_to`` constrain lessons by their local start
        date; both endpoints are inclusive. Submitted-work review events remain
        unfiltered by this range, matching the existing application behavior.
        All lesson statuses, including ``cancelled``, are included because the
        current calendar query does not exclude any status.

        Args:
            teacher_id: Persisted teacher identifier used by the source.
            date_from: Optional inclusive lower bound for lesson start dates.
            date_to: Optional inclusive upper bound for lesson start dates.

        Returns:
            Newly assembled neutral events. Lesson detail mappings are
            snapshots owned by this result; presentation mapping belongs to
            the application boundary.

        Raises:
            Exception: Any source/database error or malformed snapshot error;
                exceptions are intentionally not translated at this boundary.

        The method does not validate a reversed date range. Its source returns
        no lessons for such a range, while review events retain their existing
        unfiltered behavior. It does not mutate the source or persist data.
        """
        lessons = self._source.lessons_for_teacher(
            teacher_id,
            date_from=date_from,
            date_to=date_to,
        )
        events: list[CalendarEvent] = []
        for item in lessons:
            events.append(
                CalendarEvent(
                    kind="lesson",
                    entity_id=item.lesson_id,
                    start_at=localize(item.start_at),
                    end_at=localize(item.end_at),
                    status=item.status,
                    details=item.lesson,
                )
            )

        submissions = self._source.submissions_for_teacher(teacher_id)
        for item in submissions:
            submitted = localize(item.submitted_at)  # type: ignore[arg-type]
            start_at = submitted.replace(minute=0, second=0, microsecond=0)
            events.append(
                CalendarEvent(
                    kind="review",
                    entity_id=item.recipient_id,
                    start_at=start_at,
                    end_at=start_at + timedelta(hours=1),
                )
            )
        return events


class InMemoryCalendarEventSource:
    """Deterministic, read-only source for contract tests and local scenarios.

    Input snapshots are copied on construction and on each read. Lesson order
    is normalized by start time; review order follows the supplied sequence.
    This source models the calendar query only and does not emulate a database,
    authorization, transaction isolation, or concurrent writes.
    """

    def __init__(
        self,
        *,
        lessons: Iterable[CalendarLesson],
        submissions: Iterable[CalendarSubmission],
    ) -> None:
        self._lessons = tuple(deepcopy(tuple(lessons)))
        self._submissions = tuple(deepcopy(tuple(submissions)))

    def lessons_for_teacher(
        self,
        teacher_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Sequence[CalendarLesson]:
        lower = (
            datetime.combine(date_from, time.min, tzinfo=MOSCOW)
            if date_from is not None
            else None
        )
        upper = (
            datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW)
            if date_to is not None
            else None
        )
        selected = [
            item
            for item in self._lessons
            if item.teacher_id == teacher_id
            and (lower is None or localize(item.start_at) >= lower)
            and (upper is None or localize(item.start_at) < upper)
        ]
        selected.sort(key=lambda item: localize(item.start_at))
        return deepcopy(tuple(selected))

    def submissions_for_teacher(self, teacher_id: int) -> Sequence[CalendarSubmission]:
        selected = [
            item
            for item in self._submissions
            if item.teacher_id == teacher_id and item.status == "SUBMITTED"
        ]
        return deepcopy(tuple(selected))
