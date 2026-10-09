"""Idempotent development seed. Run explicitly with ``python -m app.seed``."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    Conversation,
    FileResource,
    Homework,
    HomeworkRecipient,
    HomeworkSubmission,
    Lesson,
    Message,
    Student,
    User,
)

MOSCOW = ZoneInfo("Europe/Moscow")


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=MOSCOW)


def seed_dev_data(db: Session) -> User:
    teacher = db.scalar(select(User).where(User.email == "anna@tutorflow.local"))
    if not teacher:
        teacher = User(id=1, email="anna@tutorflow.local", password_hash="dev-only-not-a-login", first_name="Анна", last_name="Иванова", role="teacher")
        db.add(teacher)
        db.flush()

    student_user = db.scalar(select(User).where(User.email == "student@tutorflow.local"))
    if not student_user:
        student_user = User(id=2, email="student@tutorflow.local", password_hash="dev-only-not-a-login", first_name="Михаил", last_name="Ковалёв", role="student")
        db.add(student_user)
        db.flush()

    students_data = [
        (1, "Михаил", "Ковалёв", "m.kovalev@example.test", "Математика", "9 класс"),
        (2, "София", "Смирнова", "s.smirnova@example.test", "Математика", "7 класс"),
        (3, "Александр", "Петров", "a.petrov@example.test", "Физика", "10 класс"),
    ]
    for item_id, first, last, email, subject, grade in students_data:
        if not db.get(Student, item_id):
            db.add(Student(id=item_id, teacher_id=teacher.id, user_id=student_user.id if item_id == 1 else None, first_name=first, last_name=last, email=email, subject=subject, grade=grade))
    first_student = db.get(Student, 1)
    if first_student and first_student.user_id is None:
        first_student.user_id = student_user.id
    db.flush()

    materials_data = [
        (301, "Формулы сокращённого умножения", "PDF"),
        (302, "Графики линейных функций", "Презентация"),
    ]
    for item_id, title, kind in materials_data:
        if not db.get(FileResource, item_id):
            db.add(FileResource(id=item_id, owner_id=teacher.id, original_name=title, title=title, kind=kind, size=0))
    db.flush()

    lessons_data = [
        (101, 1, "Математика", "Квадратные уравнения", "2026-09-29T14:00:00", "2026-09-29T15:00:00"),
        (102, 2, "Математика", "Линейные функции", "2026-09-29T16:00:00", "2026-09-29T17:00:00"),
        (103, 3, "Физика", "Законы Ньютона", "2026-09-29T18:00:00", "2026-09-29T19:00:00"),
        (104, 2, "Математика", "Повторение дробей", "2026-09-28T09:00:00", "2026-09-28T10:00:00"),
        (105, 1, "Математика", "Системы уравнений", "2026-09-30T09:00:00", "2026-09-30T10:00:00"),
        (106, 3, "Физика", "Равномерное движение", "2026-09-30T14:00:00", "2026-09-30T15:00:00"),
        (107, 1, "Математика", "Теорема Виета", "2026-10-01T11:00:00", "2026-10-01T12:00:00"),
        (108, 3, "Физика", "Силы в природе", "2026-10-02T10:00:00", "2026-10-02T11:00:00"),
        (109, 2, "Математика", "Пропорции", "2026-10-02T15:00:00", "2026-10-02T16:00:00"),
    ]
    for item_id, student_id, subject, topic, start, end in lessons_data:
        if not db.get(Lesson, item_id):
            lesson = Lesson(id=item_id, teacher_id=teacher.id, student_id=student_id, subject=subject, topic=topic, start_at=dt(start), end_at=dt(end), location="Онлайн · TutorFlow", status="scheduled")
            if item_id == 101:
                lesson.location = "Онлайн · Google Meet"
                lesson.teacher_note = "Повторить формулу дискриминанта в начале занятия."
                lesson.materials.append(db.get(FileResource, 301))
            db.add(lesson)

    homeworks_data = [
        (201, 101, "Квадратные уравнения", "Решите упражнения 1–5 из приложенного материала.", "2026-09-30T23:59:00"),
        (202, 103, "Законы Ньютона", "Подготовьте краткие ответы на вопросы после параграфа.", "2026-09-28T23:59:00"),
        (203, 102, "Линейные функции", "Постройте графики трёх функций.", "2026-10-12T23:59:00"),
    ]
    for item_id, lesson_id, title, description, due in homeworks_data:
        if not db.get(Homework, item_id):
            homework = Homework(id=item_id, teacher_id=teacher.id, lesson_id=lesson_id, title=title, description=description, due_at=dt(due))
            if item_id == 201:
                homework.attachments.append(db.get(FileResource, 301))
            db.add(homework)
    db.flush()

    recipients_data = [
        (201, 201, 1, "SUBMITTED", "2026-09-29T12:18:00"),
        (202, 202, 3, "ASSIGNED", None),
        (203, 203, 1, "ASSIGNED", None),
        (204, 203, 2, "ASSIGNED", None),
    ]
    for recipient_id, homework_id, student_id, status, submitted in recipients_data:
        existing = db.scalar(select(HomeworkRecipient).where(HomeworkRecipient.homework_id == homework_id, HomeworkRecipient.student_id == student_id))
        if not existing and not db.get(HomeworkRecipient, recipient_id):
            db.add(HomeworkRecipient(id=recipient_id, homework_id=homework_id, student_id=student_id, status=status, assigned_at=dt("2026-09-28T12:00:00"), submitted_at=dt(submitted) if submitted else None))
    db.flush()

    if not db.get(HomeworkSubmission, 501):
        db.add(HomeworkSubmission(id=501, homework_recipient_id=201, comment="Решение задания", created_at=dt("2026-09-29T12:18:00"), updated_at=dt("2026-09-29T12:18:00")))

    if not db.get(Conversation, 601):
        conversation = Conversation(id=601, teacher_id=teacher.id, student_id=2)
        conversation.messages.extend([
            Message(author_role="student", body="Спасибо, теперь всё понятно!", sent_at=dt("2026-09-29T13:05:00")),
            Message(author_role="teacher", body="Отлично! Тогда на занятии закрепим тему.", sent_at=dt("2026-09-29T13:08:00")),
        ])
        db.add(conversation)

    db.flush()
    if db.bind and db.bind.dialect.name == "postgresql":
        for table_name in ("users", "students", "lessons", "homeworks", "homework_recipients", "homework_submissions", "files", "conversations", "messages"):
            db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE(MAX(id), 1), true) FROM {table_name}"))
    db.commit()
    return teacher


def main() -> None:
    with SessionLocal() as db:
        teacher = seed_dev_data(db)
        print(f"Development seed is ready for {teacher.email}")


if __name__ == "__main__":
    main()
