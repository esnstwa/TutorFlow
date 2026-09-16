"""add password hash to users

Revision ID: 20260916_0002
Revises: 20260916_0001
Create Date: 2026-09-16

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260916_0002"
down_revision: str | Sequence[str] | None = "20260916_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.String(length=255),
            server_default="",
            nullable=False,
        ),
    )
    op.alter_column("users", "password_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "password_hash")
