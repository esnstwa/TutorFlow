from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import User


def get_current_teacher(request: Request, db: Session = Depends(get_db)) -> User:
    """Use an upstream authenticated user when present, with a dev-only seed fallback.

    The project has no authentication routes yet. This dependency is the single
    integration point for the future auth module and avoids inventing a second
    login/session implementation in the teacher cabinet.
    """
    principal = getattr(request.state, "user", None)
    if isinstance(principal, User):
        teacher = db.get(User, principal.id)
    elif getattr(principal, "id", None):
        teacher = db.get(User, int(principal.id))
    elif settings.enable_dev_teacher_fallback:
        teacher = db.scalar(select(User).where(User.email == settings.dev_teacher_email))
    else:
        teacher = None
    if not teacher or teacher.role != "teacher":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация преподавателя")
    return teacher
