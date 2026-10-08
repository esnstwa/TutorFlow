import hashlib
from datetime import timezone

from sqlalchemy import select

from app.auth.models import AuthSession
from app.models import utc_now

COOKIE_NAME = "tutorflow_session"


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve_session(request, db):
    raw = request.cookies.get(COOKIE_NAME)
    if not raw or len(raw) > 128:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(raw)))
    if session is None or session.revoked_at is not None:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:  # SQLite loses timezone information.
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= utc_now():
        return None
    return session
