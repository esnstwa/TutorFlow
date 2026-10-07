from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Table, Text, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


lesson_materials = Table(
    "lesson_materials",
    Base.metadata,
    Column("lesson_id", ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)

homework_attachments = Table(
    "homework_attachments",
    Base.metadata,
    Column("homework_id", ForeignKey("homeworks.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)

homework_submission_attachments = Table(
    "homework_submission_attachments",
    Base.metadata,
    Column("submission_id", ForeignKey("homework_submissions.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('teacher', 'student')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500))

    students: Mapped[list[Student]] = relationship(back_populates="teacher", foreign_keys="Student.teacher_id")
    student_profile: Mapped[Student | None] = relationship(back_populates="user", foreign_keys="Student.user_id")


class Student(TimestampMixin, Base):
    __tablename__ = "students"
    __table_args__ = (Index("ix_students_teacher_id", "teacher_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    avatar: Mapped[str | None] = mapped_column(String(500))
    grade: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(120), nullable=False)

    teacher: Mapped[User] = relationship(back_populates="students", foreign_keys=[teacher_id])
    user: Mapped[User | None] = relationship(back_populates="student_profile", foreign_keys=[user_id])
    lessons: Mapped[list[Lesson]] = relationship(back_populates="student", cascade="all, delete-orphan")
    homework_recipients: Mapped[list[HomeworkRecipient]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Lesson(TimestampMixin, Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'completed_unpaid', 'completed_paid', 'cancelled')", name="ck_lessons_status"),
        CheckConstraint("end_at > start_at", name="ck_lessons_time_order"),
        Index("ix_lessons_teacher_start", "teacher_id", "start_at"),
        Index("ix_lessons_student_start", "student_id", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    meeting_url: Mapped[str | None] = mapped_column(String(1000))
    teacher_note: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)

    teacher: Mapped[User] = relationship()
    student: Mapped[Student] = relationship(back_populates="lessons")
    materials: Mapped[list[FileResource]] = relationship(secondary=lesson_materials, back_populates="lessons")
    homeworks: Mapped[list[Homework]] = relationship(back_populates="lesson")


class Homework(TimestampMixin, Base):
    __tablename__ = "homeworks"
    __table_args__ = (
        Index("ix_homeworks_teacher_id", "teacher_id"),
        Index("ix_homeworks_lesson_id", "lesson_id"),
        Index("ix_homeworks_due_at", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    teacher: Mapped[User] = relationship()
    lesson: Mapped[Lesson | None] = relationship(back_populates="homeworks")
    recipients: Mapped[list[HomeworkRecipient]] = relationship(back_populates="homework", cascade="all, delete-orphan")
    attachments: Mapped[list[FileResource]] = relationship(secondary=homework_attachments, back_populates="homeworks")


class HomeworkRecipient(Base):
    __tablename__ = "homework_recipients"
    __table_args__ = (
        CheckConstraint("status IN ('ASSIGNED', 'SUBMITTED', 'REVISION_REQUIRED', 'COMPLETED')", name="ck_homework_recipients_status"),
        UniqueConstraint("homework_id", "student_id", name="uq_homework_recipients_homework_student"),
        Index("ix_homework_recipients_homework_id", "homework_id"),
        Index("ix_homework_recipients_student_id", "student_id"),
        Index("ix_homework_recipients_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    homework_id: Mapped[int] = mapped_column(ForeignKey("homeworks.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ASSIGNED", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    homework: Mapped[Homework] = relationship(back_populates="recipients")
    student: Mapped[Student] = relationship(back_populates="homework_recipients")
    submissions: Mapped[list[HomeworkSubmission]] = relationship(back_populates="recipient", cascade="all, delete-orphan", order_by="HomeworkSubmission.created_at")
    reviews: Mapped[list[HomeworkReview]] = relationship(back_populates="recipient", cascade="all, delete-orphan", order_by="HomeworkReview.created_at")


class HomeworkSubmission(TimestampMixin, Base):
    __tablename__ = "homework_submissions"
    __table_args__ = (
        Index("ix_homework_submissions_recipient_id", "homework_recipient_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    homework_recipient_id: Mapped[int] = mapped_column(ForeignKey("homework_recipients.id", ondelete="CASCADE"), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)

    recipient: Mapped[HomeworkRecipient] = relationship(back_populates="submissions")
    attachments: Mapped[list[FileResource]] = relationship(secondary=homework_submission_attachments, back_populates="homework_submissions")


class HomeworkReview(Base):
    __tablename__ = "homework_reviews"
    __table_args__ = (
        CheckConstraint("action IN ('REVISION_REQUIRED', 'COMPLETED')", name="ck_homework_reviews_action"),
        Index("ix_homework_reviews_recipient_id", "homework_recipient_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    homework_recipient_id: Mapped[int] = mapped_column(ForeignKey("homework_recipients.id", ondelete="CASCADE"), nullable=False)
    teacher_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    recipient: Mapped[HomeworkRecipient] = relationship(back_populates="reviews")


class FileResource(TimestampMixin, Base):
    __tablename__ = "files"
    __table_args__ = (CheckConstraint("size >= 0", name="ck_files_size_nonnegative"), Index("ix_files_owner_id", "owner_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str | None] = mapped_column(String(255))
    storage_path: Mapped[str | None] = mapped_column(String(1000))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), default="Файл", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000))

    owner: Mapped[User] = relationship()
    lessons: Mapped[list[Lesson]] = relationship(secondary=lesson_materials, back_populates="materials")
    homeworks: Mapped[list[Homework]] = relationship(secondary=homework_attachments, back_populates="attachments")
    homework_submissions: Mapped[list[HomeworkSubmission]] = relationship(secondary=homework_submission_attachments, back_populates="attachments")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    student: Mapped[Student] = relationship()


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (CheckConstraint("author_role IN ('teacher', 'student')", name="ck_messages_author_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
