from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.users.exceptions import UserAlreadyExistsError
from app.users.models import User
from app.users.schemas import UserCreate


def create_user(db: Session, user_data: UserCreate) -> User:
    normalized_email = user_data.email.strip().lower()

    existing_user = db.scalar(select(User).where(User.email == normalized_email))
    if existing_user is not None:
        raise UserAlreadyExistsError("User with this email already exists.")

    user = User(
        email=normalized_email,
        password_hash=hash_password(user_data.password),
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=user_data.role,
    )

    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise UserAlreadyExistsError("User with this email already exists.") from error

    db.refresh(user)
    return user
