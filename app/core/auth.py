from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.sessions import resolve_session
from app.auth.csrf import require_csrf
from app.core.database import get_db
from app.models import Student, User


def optional_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    session = resolve_session(request, db)
    user = db.get(User, session.user_id) if session else None
    request.state.csrf_token = session.csrf_token if user else None
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = optional_current_user(request, db)
    if user is None:
        if not request.url.path.startswith("/api/"):
            raise HTTPException(status_code=303, detail="Требуется авторизация", headers={"Location": "/login"})
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request, request.state.csrf_token)
    return user


def get_current_teacher(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Требуется роль преподавателя")
    return user


def get_current_student(request: Request, db: Session = Depends(get_db)) -> Student:
    user = get_current_user(request, db)
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Требуется роль ученика")
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise HTTPException(status_code=403, detail="Профиль ученика не найден")
    return student
