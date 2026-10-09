"""Add soft archive and hashed one-use student invitations.

Revision ID: d2b3c4d5e6f7
Revises: c1a2b3c4d5e6
"""
from alembic import op
import sqlalchemy as sa

revision = "d2b3c4d5e6f7"
down_revision = "c1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("students", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "student_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("target_email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_student_invitations_student_id", "student_invitations", ["student_id"])


def downgrade():
    # Explicit rollback only; upgrade never drops or rewrites existing history.
    op.drop_index("ix_student_invitations_student_id", table_name="student_invitations")
    op.drop_table("student_invitations")
    op.drop_column("students", "archived_at")
