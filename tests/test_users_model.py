from sqlalchemy import UniqueConstraint

from app.core.database import Base
from app.users.models import User


def test_users_table_is_registered_in_metadata() -> None:
    assert User.__tablename__ in Base.metadata.tables


def test_users_table_has_expected_columns() -> None:
    users_table = Base.metadata.tables[User.__tablename__]

    assert set(users_table.columns.keys()) == {
        "id",
        "email",
        "first_name",
        "last_name",
        "role",
        "created_at",
        "updated_at",
    }


def test_users_email_is_unique() -> None:
    users_table = Base.metadata.tables[User.__tablename__]
    email_column = users_table.c.email
    has_email_unique_constraint = any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"email"}
        for constraint in users_table.constraints
    )

    assert email_column.unique or has_email_unique_constraint
