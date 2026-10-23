from datetime import date, datetime, timedelta

import pytest

from app.schedule.calendar import (
    CalendarEventService,
    CalendarLesson,
    CalendarSubmission,
    InMemoryCalendarEventSource,
)


def test_in_memory_source_builds_calendar_event_for_the_shared_consumer() -> None:
    lesson = {
        "id": 17,
        "student": {"name": "Анна Иванова", "subject": "Математика", "initials": "АИ"},
        "topic": "Дроби",
        "date_iso": "2026-11-10",
        "start": "10:00",
        "end": "11:00",
    }
    source = InMemoryCalendarEventSource(
        lessons=[
            CalendarLesson(
                teacher_id=3,
                lesson_id=17,
                start_at=datetime.fromisoformat("2026-11-10T10:00:00+03:00"),
                end_at=datetime.fromisoformat("2026-11-10T11:00:00+03:00"),
                status="scheduled",
                lesson=lesson,
            )
        ],
        submissions=[],
    )

    result = CalendarEventService(source).list_events(
        teacher_id=3,
        date_from=date(2026, 11, 10),
        date_to=date(2026, 11, 10),
    )

    assert len(result) == 1
    event = result[0]
    assert event.kind == "lesson"
    assert event.entity_id == 17
    assert event.start_at == datetime.fromisoformat("2026-11-10T10:00:00+03:00")
    assert event.end_at == datetime.fromisoformat("2026-11-10T11:00:00+03:00")
    assert event.status == "scheduled"
    assert event.details == lesson
    assert not hasattr(event, "url")
    assert not hasattr(event, "title")


def _calendar_lesson(
    lesson_id: int,
    start_at: datetime,
    *,
    teacher_id: int = 3,
    status: str = "scheduled",
) -> CalendarLesson:
    local_start = start_at.isoformat()
    local_date, clock = local_start[:10], local_start[11:16]
    hour = int(clock[:2])
    end = f"{(hour + 1) % 24:02d}:{clock[3:]}"
    detail = {
        "id": lesson_id,
        "student": {"name": f"Ученик {lesson_id}", "subject": "Математика", "initials": "У"},
        "topic": "Тема",
        "date_iso": local_date,
        "start": clock,
        "end": end,
    }
    return CalendarLesson(
        teacher_id=teacher_id,
        lesson_id=lesson_id,
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        status=status,
        lesson=detail,
    )


def test_in_memory_source_matches_teacher_and_inclusive_local_date_bounds() -> None:
    source = InMemoryCalendarEventSource(
        lessons=[
            _calendar_lesson(1, datetime.fromisoformat("2026-11-09T23:59:00+03:00")),
            _calendar_lesson(2, datetime.fromisoformat("2026-11-10T00:00:00+03:00")),
            _calendar_lesson(
                3,
                datetime.fromisoformat("2026-11-10T23:59:00+03:00"),
                status="cancelled",
            ),
            _calendar_lesson(4, datetime.fromisoformat("2026-11-11T00:00:00+03:00")),
            _calendar_lesson(
                5,
                datetime.fromisoformat("2026-11-10T10:00:00+03:00"),
                teacher_id=99,
            ),
        ],
        submissions=[
            CalendarSubmission(
                teacher_id=3,
                recipient_id=41,
                status="SUBMITTED",
                submitted_at=datetime.fromisoformat("2026-11-09T23:30:00+03:00"),
            ),
            CalendarSubmission(
                teacher_id=3,
                recipient_id=42,
                status="SUBMITTED",
                submitted_at=datetime.fromisoformat("2026-11-12T12:30:00+03:00"),
            ),
            CalendarSubmission(
                teacher_id=3,
                recipient_id=43,
                status="ASSIGNED",
                submitted_at=None,
            ),
            CalendarSubmission(
                teacher_id=99,
                recipient_id=44,
                status="SUBMITTED",
                submitted_at=datetime.fromisoformat("2026-11-10T12:30:00+03:00"),
            ),
        ],
    )

    selected = source.lessons_for_teacher(
        3,
        date_from=date(2026, 11, 10),
        date_to=date(2026, 11, 10),
    )
    events = CalendarEventService(source).list_events(
        teacher_id=3,
        date_from=date(2026, 11, 10),
        date_to=date(2026, 11, 10),
    )

    assert [item.lesson_id for item in selected] == [2, 3]
    assert selected[1].status == "cancelled"
    assert [(item.kind, item.entity_id) for item in events] == [
        ("lesson", 2),
        ("lesson", 3),
        ("review", 41),
        ("review", 42),
    ]
    assert events[-2].start_at.date().isoformat() == "2026-11-09"
    assert events[-1].start_at.date().isoformat() == "2026-11-12"
    assert events[-2].start_at.strftime("%H:%M") == "23:00"
    assert events[-2].end_at.strftime("%H:%M") == "00:00"


def test_reversed_range_has_no_lessons_but_keeps_legacy_unfiltered_reviews() -> None:
    source = InMemoryCalendarEventSource(
        lessons=[
            _calendar_lesson(1, datetime.fromisoformat("2026-11-10T10:00:00+03:00"))
        ],
        submissions=[
            CalendarSubmission(
                teacher_id=3,
                recipient_id=41,
                status="SUBMITTED",
                submitted_at=datetime.fromisoformat("2026-11-10T12:00:00+03:00"),
            )
        ],
    )

    events = CalendarEventService(source).list_events(
        teacher_id=3,
        date_from=date(2026, 11, 11),
        date_to=date(2026, 11, 10),
    )

    assert [(item.kind, item.entity_id) for item in events] == [("review", 41)]


def test_in_memory_source_returns_independent_snapshots() -> None:
    lesson = _calendar_lesson(17, datetime.fromisoformat("2026-11-10T10:00:00+03:00"))
    source = InMemoryCalendarEventSource(lessons=[lesson], submissions=[])
    lesson.lesson["student"]["name"] = "Изменено после создания источника"

    first = CalendarEventService(source).list_events(teacher_id=3)
    first[0].details["student"]["name"] = "Изменено вызывающим кодом"
    second = CalendarEventService(source).list_events(teacher_id=3)

    assert second[0].details["student"]["name"] == "Ученик 17"


def test_lesson_source_error_precedes_submission_read() -> None:
    calls: list[str] = []

    class FailingSource:
        def lessons_for_teacher(self, teacher_id: int, **kwargs):
            calls.append("lessons")
            raise RuntimeError("lesson read failed")

        def submissions_for_teacher(self, teacher_id: int):
            calls.append("submissions")
            raise RuntimeError("submission read failed")

    with pytest.raises(RuntimeError, match="lesson read failed"):
        CalendarEventService(FailingSource()).list_events(teacher_id=3)

    assert calls == ["lessons"]


def test_submitted_record_without_timestamp_propagates_data_error() -> None:
    source = InMemoryCalendarEventSource(
        lessons=[],
        submissions=[
            CalendarSubmission(
                teacher_id=3,
                recipient_id=41,
                status="SUBMITTED",
                submitted_at=None,
            )
        ],
    )

    with pytest.raises(AttributeError):
        CalendarEventService(source).list_events(teacher_id=3)
