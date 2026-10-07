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

assignment_materials = Table(
    "assignment_materials",
    Base.metadata,
    Column("assignment_id", ForeignKey("assignments.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)

submission_files = Table(
    "submission_files",
    Base.metadata,
    Column("submission_id", ForeignKey("assignment_submissions.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)

review_files = Table(
    "review_files",
    Base.metadata,
    Column("review_id", ForeignKey("assignment_reviews.id", ondelete="CASCADE"), primary_key=True),
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
    assignments: Mapped[list[Assignment]] = relationship(back_populates="student", cascade="all, delete-orphan")
    submissions: Mapped[list[AssignmentSubmission]] = relationship(back_populates="student", cascade="all, delete-orphan")


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


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'assigned', 'submitted', 'under_review', 'revision_requested', 'reviewed')", name="ck_assignments_status"),
        Index("ix_assignments_teacher_id", "teacher_id"),
        Index("ix_assignments_student_id", "student_id"),
        Index("ix_assignments_due_at", "due_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(120), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="assigned", nullable=False)

    teacher: Mapped[User] = relationship()
    student: Mapped[Student] = relationship(back_populates="assignments")
    materials: Mapped[list[FileResource]] = relationship(secondary=assignment_materials, back_populates="assignments")
    submissions: Mapped[list[AssignmentSubmission]] = relationship(back_populates="assignment", cascade="all, delete-orphan")


class AssignmentSubmission(TimestampMixin, Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_submissions_attempt_positive"),
        CheckConstraint("status IN ('submitted', 'under_review', 'revision_requested', 'reviewed')", name="ck_submissions_status"),
        UniqueConstraint("assignment_id", "attempt_number", name="uq_submissions_assignment_attempt"),
        Index("ix_submissions_assignment_id", "assignment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    student: Mapped[Student] = relationship(back_populates="submissions")
    files: Mapped[list[FileResource]] = relationship(secondary=submission_files, back_populates="submissions")
    reviews: Mapped[list[AssignmentReview]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class AssignmentReview(TimestampMixin, Base):
    __tablename__ = "assignment_reviews"
    __table_args__ = (
        CheckConstraint("result IN ('accepted', 'revision_requested')", name="ck_reviews_result"),
        CheckConstraint("score IS NULL OR score >= 0", name="ck_reviews_score_nonnegative"),
        CheckConstraint("max_score IS NULL OR max_score > 0", name="ck_reviews_max_score_positive"),
        CheckConstraint("score IS NULL OR max_score IS NULL OR score <= max_score", name="ck_reviews_score_lte_max"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[int | None]
    max_score: Mapped[int | None]
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    submission: Mapped[AssignmentSubmission] = relationship(back_populates="reviews")
    teacher: Mapped[User] = relationship()
    files: Mapped[list[FileResource]] = relationship(secondary=review_files, back_populates="reviews")


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
    assignments: Mapped[list[Assignment]] = relationship(secondary=assignment_materials, back_populates="materials")
    submissions: Mapped[list[AssignmentSubmission]] = relationship(secondary=submission_files, back_populates="files")
    reviews: Mapped[list[AssignmentReview]] = relationship(secondary=review_files, back_populates="files")


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
