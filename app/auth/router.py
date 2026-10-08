import secrets
from datetime import timedelta
from urllib.parse import parse_qs

from argon2.exceptions import InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.csrf import check_origin, require_csrf
from app.auth.models import AuthSession
from app.auth.schemas import FIELD_MESSAGES, LoginRequest, RegisterRequest
from app.auth.sessions import COOKIE_NAME, resolve_session, token_digest
from app.core.auth import get_current_user, optional_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password
from app.models import User, utc_now
from app.users.exceptions import UserAlreadyExistsError
from app.users.service import create_user

router = APIRouter()


async def validated_json(request: Request, schema):
    check_origin(request, auth=True)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="Требуется application/json")
    try:
        data = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"detail": "Некорректный JSON", "fields": {}}, status_code=422)
    try:
        return schema.model_validate(data)
    except ValidationError as error:
        fields = {str(item["loc"][0]): FIELD_MESSAGES.get(str(item["loc"][0]), "Некорректное значение")
                  for item in error.errors() if item["loc"]}
        # Do not serialize Pydantic input/context: they can contain passwords.
        return JSONResponse({"detail": "Проверьте введённые данные", "fields": fields}, status_code=422)


def public_user(user: User) -> dict:
    return {key: getattr(user, key) for key in ("id", "email", "role", "first_name", "last_name")}


def authenticated_response(request: Request, db: Session, user: User, status_code=200, remember=False):
    old_session = resolve_session(request, db)
    if old_session is not None:
        old_session.revoked_at = utc_now()
    lifetime = 2592000 if remember else 43200
    raw = secrets.token_urlsafe(32)
    session = AuthSession(user_id=user.id, token_hash=token_digest(raw),
                          csrf_token=secrets.token_urlsafe(32), expires_at=utc_now() + timedelta(seconds=lifetime))
    db.add(session)
    db.commit()
    response = JSONResponse({"ok": True, "user": public_user(user),
                             "redirect": "/dashboard" if user.role == "teacher" else "/student/homework",
                             "csrf_token": session.csrf_token}, status_code=status_code)
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/", max_age=lifetime if remember else None)
    return response


@router.post("/logout", name="auth_logout")
async def auth_logout(request: Request, db: Session = Depends(get_db)):
    user = optional_current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Требуется URLencoded-форма")
    try:
        form = parse_qs((await request.body()).decode("utf-8"), max_num_fields=10)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=403, detail="Недействительный CSRF-токен") from None
    tokens = form.get("csrf_token", [])
    require_csrf(request, request.state.csrf_token, tokens[0] if len(tokens) == 1 else "")
    session = resolve_session(request, db)
    session.revoked_at = utc_now()
    db.commit()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.session_cookie_secure, httponly=True, samesite="lax")
    return response


@router.post("/api/auth/logout")
async def logout(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="Требуется application/json")
    try:
        await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"detail": "Некорректный JSON", "fields": {}}, status_code=422)
    session = resolve_session(request, db)
    session.revoked_at = utc_now()
    db.commit()
    response = JSONResponse({"ok": True, "redirect": "/login"})
    response.delete_cookie(COOKIE_NAME, path="/", secure=settings.session_cookie_secure, httponly=True, samesite="lax")
    return response


@router.post("/api/auth/login")
async def login(request: Request, db: Session = Depends(get_db)):
    data = await validated_json(request, LoginRequest)
    if isinstance(data, JSONResponse):
        return data
    email = str(data.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    try:
        valid = user is not None and verify_password(data.password, user.password_hash)
    except InvalidHashError:
        valid = False
    if not valid:
        return JSONResponse({"detail": "Неверный email или пароль"}, status_code=401)
    return authenticated_response(request, db, user, remember=data.remember)


@router.get("/api/auth/me")
def me(request: Request, user=Depends(get_current_user)):
    return {"ok": True, "user": public_user(user), "csrf_token": request.state.csrf_token}


@router.post("/api/auth/register")
async def register(request: Request, db: Session = Depends(get_db)):
    data = await validated_json(request, RegisterRequest)
    if isinstance(data, JSONResponse):
        return data
    try:
        user = create_user(db, data)
    except UserAlreadyExistsError:
        return JSONResponse({"detail": "Этот email уже зарегистрирован", "fields": {"email": "Этот email уже зарегистрирован"}}, status_code=409)
    return authenticated_response(request, db, user, 201)
