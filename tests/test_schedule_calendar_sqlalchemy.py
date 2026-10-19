from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Homework, HomeworkRecipient, Lesson, Student, User
from app.services import lesson_dict


@pytest.fixture
def calendar_db() -> Generator[dict, None, None]:
    import app.students.models  # Register invitation tables used by lesson_dict.

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        teacher = User(
            email="calendar-owner@example.test",
            password_hash="test-hash",
            first_name="Репетитор",
            role="teacher",
        )
        other_teacher = User(
            email="calendar-other@example.test",
            password_hash="test-hash",
            first_name="Другой",
            role="teacher",
        )
        db.add_all([teacher, other_teacher])
        db.flush()

        student = Student(
            teacher_id=teacher.id,
            first_name="Анна",
            last_name="Иванова",
            grade="8",
            subject="Математика",
        )
        other_student = Student(
            teacher_id=other_teacher.id,
            first_name="Борис",
            last_name="Петров",
            grade="9",
            subject="Физика",
        )
        db.add_all([student, other_student])
        db.flush()

        early = Lesson(
            teacher_id=teacher.id,
            student_id=student.id,
            subject="Математика",
            topic="Дроби",
            start_at=datetime.fromisoformat("2026-11-10T09:00:00+03:00"),
            end_at=datetime.fromisoformat("2026-11-10T10:00:00+03:00"),
        )
        cancelled = Lesson(
            teacher_id=teacher.id,
            student_id=student.id,
            subject="Математика",
            topic="Уравнения",
            start_at=datetime.fromisoformat("2026-11-10T11:00:00+03:00"),
            end_at=datetime.fromisoformat("2026-11-10T12:00:00+03:00"),
            status="cancelled",
        )
        outside_range = Lesson(
            teacher_id=teacher.id,
            student_id=student.id,
            subject="Математика",
            topic="Следующий день",
            start_at=datetime.fromisoformat("2026-11-11T00:00:00+03:00"),
            end_at=datetime.fromisoformat("2026-11-11T01:00:00+03:00"),
        )
        foreign_lesson = Lesson(
            teacher_id=other_teacher.id,
            student_id=other_student.id,
            subject="Физика",
            topic="Чужое занятие",
            start_at=datetime.fromisoformat("2026-11-10T10:00:00+03:00"),
            end_at=datetime.fromisoformat("2026-11-10T11:00:00+03:00"),
        )
        db.add_all([early, cancelled, outside_range, foreign_lesson])
        db.flush()

        submitted_homework = Homework(
            teacher_id=teacher.id,
            title="Проверить",
            description="Работа",
        )
        assigned_homework = Homework(
            teacher_id=teacher.id,
            title="Выполняется",
            description="Ещё не отправлено",
        )
        foreign_homework = Homework(
            teacher_id=other_teacher.id,
            title="Чужое",
            description="Другой преподаватель",
        )
        db.add_all([submitted_homework, assigned_homework, foreign_homework])
        db.flush()
        submitted = HomeworkRecipient(
            homework_id=submitted_homework.id,
            student_id=student.id,
            status="SUBMITTED",
            submitted_at=datetime.fromisoformat("2026-11-10T12:34:00+03:00"),
        )
        assigned = HomeworkRecipient(
            homework_id=assigned_homework.id,
            student_id=student.id,
            status="ASSIGNED",
        )
        foreign_submission = HomeworkRecipient(
            homework_id=foreign_homework.id,
            student_id=other_student.id,
            status="SUBMITTED",
            submitted_at=datetime.fromisoformat("2026-11-10T13:00:00+03:00"),
        )
        db.add_all([submitted, assigned, foreign_submission])
        db.commit()

        yield {
            "db": db,
            "teacher_id": teacher.id,
            "other_teacher_id": other_teacher.id,
            "lesson_ids": (early.id, cancelled.id, outside_range.id, foreign_lesson.id),
            "recipient_ids": (submitted.id, assigned.id, foreign_submission.id),
        }
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_sqlalchemy_source_scopes_orders_and_preserves_calendar_rows(calendar_db: dict) -> None:
    from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource

    case = calendar_db
    source = SQLAlchemyCalendarEventSource(case["db"], lesson_dict)

    lessons = source.lessons_for_teacher(
        case["teacher_id"],
        date_from=datetime.fromisoformat("2026-11-10").date(),
        date_to=datetime.fromisoformat("2026-11-10").date(),
    )
    submissions = source.submissions_for_teacher(case["teacher_id"])

    assert [item.lesson_id for item in lessons] == list(case["lesson_ids"][:2])
    assert [item.status for item in lessons] == ["scheduled", "cancelled"]
    assert lessons[0].end_at == datetime.fromisoformat("2026-11-10T10:00:00+03:00")
    assert [item.recipient_id for item in submissions] == [case["recipient_ids"][0]]
    assert submissions[0].submitted_at == datetime.fromisoformat("2026-11-10T12:34:00+03:00")


def test_shared_consumer_returns_same_calendar_for_both_sources(calendar_db: dict) -> None:
    from app.schedule.calendar import CalendarEventService, InMemoryCalendarEventSource
    from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource

    case = calendar_db
    lower = datetime.fromisoformat("2026-11-10").date()
    upper = lower
    sql_source = SQLAlchemyCalendarEventSource(case["db"], lesson_dict)
    sql_events = CalendarEventService(sql_source).list_events(
        teacher_id=case["teacher_id"],
        date_from=lower,
        date_to=upper,
    )
    memory_source = InMemoryCalendarEventSource(
        lessons=sql_source.lessons_for_teacher(
            case["teacher_id"], date_from=lower, date_to=upper
        ),
        submissions=sql_source.submissions_for_teacher(case["teacher_id"]),
    )
    memory_events = CalendarEventService(memory_source).list_events(
        teacher_id=case["teacher_id"],
        date_from=lower,
        date_to=upper,
    )

    assert memory_events == sql_events
    assert [(item.kind, item.entity_id) for item in sql_events] == [
        ("lesson", case["lesson_ids"][0]),
        ("lesson", case["lesson_ids"][1]),
        ("review", case["recipient_ids"][0]),
    ]


def test_sqlalchemy_source_preserves_missing_submission_time_error(calendar_db: dict) -> None:
    from app.schedule.calendar import CalendarEventService
    from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource

    case = calendar_db
    db: Session = case["db"]
    homework = Homework(
        teacher_id=case["teacher_id"],
        title="Без времени отправки",
        description="Синтетическая ошибочная запись",
    )
    db.add(homework)
    db.flush()
    db.add(
        HomeworkRecipient(
            homework_id=homework.id,
            student_id=1,
            status="SUBMITTED",
            submitted_at=None,
        )
    )
    db.commit()
    source = SQLAlchemyCalendarEventSource(db, lesson_dict)

    with pytest.raises(AttributeError):
        CalendarEventService(source).list_events(teacher_id=case["teacher_id"])


@pytest.mark.parametrize("read_method", ["lessons_for_teacher", "submissions_for_teacher"])
def test_sqlalchemy_source_does_not_autoflush_caller_pending_writes(
    calendar_db: dict, read_method: str
) -> None:
    from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource

    case = calendar_db
    db: Session = case["db"]
    db.autoflush = True
    persisted_lesson = db.get(Lesson, case["lesson_ids"][0])
    assert persisted_lesson is not None
    pending = Lesson(
        teacher_id=case["teacher_id"],
        student_id=persisted_lesson.student_id,
        subject="Математика",
        topic="Не сохранять при чтении календаря",
        start_at=datetime.fromisoformat("2026-11-10T15:00:00+03:00"),
        end_at=datetime.fromisoformat("2026-11-10T16:00:00+03:00"),
    )
    db.add(pending)
    assert pending in db.new

    source = SQLAlchemyCalendarEventSource(db, lesson_dict)
    if read_method == "lessons_for_teacher":
        result = source.lessons_for_teacher(case["teacher_id"])
        assert all(item.lesson_id != pending.id for item in result)
    else:
        source.submissions_for_teacher(case["teacher_id"])

    assert pending in db.new
