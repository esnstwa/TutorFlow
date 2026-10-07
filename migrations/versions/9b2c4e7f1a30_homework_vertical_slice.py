"""replace per-student assignments with shared homework workflow

Revision ID: 9b2c4e7f1a30
Revises: 2cc15ffc8185
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9b2c4e7f1a30"
down_revision: str | Sequence[str] | None = "2cc15ffc8185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "homeworks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_homeworks_due_at", "homeworks", ["due_at"])
    op.create_index("ix_homeworks_lesson_id", "homeworks", ["lesson_id"])
    op.create_index("ix_homeworks_teacher_id", "homeworks", ["teacher_id"])

    op.create_table(
        "homework_recipients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("homework_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ASSIGNED', 'SUBMITTED', 'REVISION_REQUIRED', 'COMPLETED')",
            name="ck_homework_recipients_status",
        ),
        sa.ForeignKeyConstraint(["homework_id"], ["homeworks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("homework_id", "student_id", name="uq_homework_recipients_homework_student"),
    )
    op.create_index("ix_homework_recipients_homework_id", "homework_recipients", ["homework_id"])
    op.create_index("ix_homework_recipients_status", "homework_recipients", ["status"])
    op.create_index("ix_homework_recipients_student_id", "homework_recipients", ["student_id"])

    op.create_table(
        "homework_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("homework_recipient_id", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["homework_recipient_id"], ["homework_recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_homework_submissions_recipient_id", "homework_submissions", ["homework_recipient_id"])

    op.create_table(
        "homework_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("homework_recipient_id", sa.Integer(), nullable=False),
        sa.Column("teacher_comment", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('REVISION_REQUIRED', 'COMPLETED')", name="ck_homework_reviews_action"),
        sa.ForeignKeyConstraint(["homework_recipient_id"], ["homework_recipients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_homework_reviews_recipient_id", "homework_reviews", ["homework_recipient_id"])

    op.create_table(
        "homework_attachments",
        sa.Column("homework_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["homework_id"], ["homeworks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("homework_id", "file_id"),
    )
    op.create_table(
        "homework_submission_attachments",
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["homework_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("submission_id", "file_id"),
    )

    op.execute(
        """
        INSERT INTO homeworks (id, teacher_id, lesson_id, title, description, due_at, created_at, updated_at)
        SELECT id, teacher_id, NULL, title, description, due_at, created_at, updated_at
        FROM assignments
        """
    )
    op.execute(
        """
        INSERT INTO homework_recipients
            (id, homework_id, student_id, status, assigned_at, submitted_at, completed_at)
        SELECT
            a.id,
            a.id,
            a.student_id,
            CASE
                WHEN a.status IN ('submitted', 'under_review') THEN 'SUBMITTED'
                WHEN a.status = 'revision_requested' THEN 'REVISION_REQUIRED'
                WHEN a.status = 'reviewed' THEN 'COMPLETED'
                ELSE 'ASSIGNED'
            END,
            a.created_at,
            (SELECT MAX(s.submitted_at) FROM assignment_submissions s WHERE s.assignment_id = a.id),
            CASE WHEN a.status = 'reviewed' THEN a.updated_at ELSE NULL END
        FROM assignments a
        """
    )
    op.execute(
        """
        INSERT INTO homework_attachments (homework_id, file_id)
        SELECT assignment_id, file_id FROM assignment_materials
        """
    )
    op.execute(
        """
        INSERT INTO homework_submissions (id, homework_recipient_id, comment, created_at, updated_at)
        SELECT id, assignment_id, comment, submitted_at, updated_at
        FROM assignment_submissions
        """
    )
    op.execute(
        """
        INSERT INTO homework_submission_attachments (submission_id, file_id)
        SELECT submission_id, file_id FROM submission_files
        """
    )
    op.execute(
        """
        INSERT INTO homework_reviews (id, homework_recipient_id, teacher_comment, action, created_at)
        SELECT
            r.id,
            s.assignment_id,
            r.comment,
            CASE WHEN r.result = 'accepted' THEN 'COMPLETED' ELSE 'REVISION_REQUIRED' END,
            r.reviewed_at
        FROM assignment_reviews r
        JOIN assignment_submissions s ON s.id = r.submission_id
        """
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("homeworks", "homework_recipients", "homework_submissions", "homework_reviews"):
            op.execute(
                sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                )
            )

    op.drop_table("review_files")
    op.drop_table("assignment_reviews")
    op.drop_table("submission_files")
    op.drop_table("assignment_submissions")
    op.drop_table("assignment_materials")
    op.drop_table("assignments")


def downgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assignments_due_at", "assignments", ["due_at"])
    op.create_index("ix_assignments_student_id", "assignments", ["student_id"])
    op.create_index("ix_assignments_teacher_id", "assignments", ["teacher_id"])
    op.create_table(
        "assignment_materials",
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("assignment_id", "file_id"),
    )
    op.create_table(
        "assignment_submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "attempt_number", name="uq_submissions_assignment_attempt"),
    )
    op.create_index("ix_submissions_assignment_id", "assignment_submissions", ["assignment_id"])
    op.create_table(
        "submission_files",
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["assignment_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("submission_id", "file_id"),
    )
    op.create_table(
        "assignment_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["assignment_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assignment_reviews_submission_id", "assignment_reviews", ["submission_id"])
    op.create_table(
        "review_files",
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["review_id"], ["assignment_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id", "file_id"),
    )

    op.execute(
        """
        INSERT INTO assignments
            (id, teacher_id, student_id, title, description, subject, due_at, status, created_at, updated_at)
        SELECT
            r.id, h.teacher_id, r.student_id, h.title, h.description,
            COALESCE(l.subject, s.subject), COALESCE(h.due_at, h.created_at),
            CASE
                WHEN r.status = 'SUBMITTED' THEN 'under_review'
                WHEN r.status = 'REVISION_REQUIRED' THEN 'revision_requested'
                WHEN r.status = 'COMPLETED' THEN 'reviewed'
                ELSE 'assigned'
            END,
            h.created_at, h.updated_at
        FROM homework_recipients r
        JOIN homeworks h ON h.id = r.homework_id
        JOIN students s ON s.id = r.student_id
        LEFT JOIN lessons l ON l.id = h.lesson_id
        """
    )
    op.execute(
        """
        INSERT INTO assignment_materials (assignment_id, file_id)
        SELECT r.id, a.file_id
        FROM homework_attachments a
        JOIN homework_recipients r ON r.homework_id = a.homework_id
        """
    )
    op.execute(
        """
        INSERT INTO assignment_submissions
            (id, assignment_id, student_id, attempt_number, comment, status, submitted_at, created_at, updated_at)
        SELECT
            s.id, s.homework_recipient_id, r.student_id,
            (SELECT COUNT(*) FROM homework_submissions prior
             WHERE prior.homework_recipient_id = s.homework_recipient_id AND prior.id <= s.id),
            s.comment, 'submitted', s.created_at, s.created_at, s.updated_at
        FROM homework_submissions s
        JOIN homework_recipients r ON r.id = s.homework_recipient_id
        """
    )
    op.execute(
        """
        INSERT INTO submission_files (submission_id, file_id)
        SELECT submission_id, file_id FROM homework_submission_attachments
        """
    )
    op.execute(
        """
        INSERT INTO assignment_reviews
            (id, submission_id, teacher_id, result, score, max_score, comment, reviewed_at, created_at, updated_at)
        SELECT
            rv.id,
            (SELECT MAX(s.id) FROM homework_submissions s WHERE s.homework_recipient_id = rv.homework_recipient_id),
            h.teacher_id,
            CASE WHEN rv.action = 'COMPLETED' THEN 'accepted' ELSE 'revision_requested' END,
            NULL, NULL, rv.teacher_comment, rv.created_at, rv.created_at, rv.created_at
        FROM homework_reviews rv
        JOIN homework_recipients r ON r.id = rv.homework_recipient_id
        JOIN homeworks h ON h.id = r.homework_id
        WHERE EXISTS (SELECT 1 FROM homework_submissions s WHERE s.homework_recipient_id = rv.homework_recipient_id)
        """
    )

    op.drop_table("homework_submission_attachments")
    op.drop_table("homework_attachments")
    op.drop_index("ix_homework_reviews_recipient_id", table_name="homework_reviews")
    op.drop_table("homework_reviews")
    op.drop_index("ix_homework_submissions_recipient_id", table_name="homework_submissions")
    op.drop_table("homework_submissions")
    op.drop_index("ix_homework_recipients_student_id", table_name="homework_recipients")
    op.drop_index("ix_homework_recipients_status", table_name="homework_recipients")
    op.drop_index("ix_homework_recipients_homework_id", table_name="homework_recipients")
    op.drop_table("homework_recipients")
    op.drop_index("ix_homeworks_teacher_id", table_name="homeworks")
    op.drop_index("ix_homeworks_lesson_id", table_name="homeworks")
    op.drop_index("ix_homeworks_due_at", table_name="homeworks")
    op.drop_table("homeworks")
