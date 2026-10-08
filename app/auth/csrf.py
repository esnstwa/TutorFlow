import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException


def origin_tuple(value):
    try:
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            return None
        if url.path not in {"", "/"} or url.query or url.fragment:
            return None
        return url.scheme, url.hostname, url.port or (443 if url.scheme == "https" else 80)
    except ValueError:
        return None


def require_csrf(request, expected, supplied=None):
    check_origin(request)
    token = request.headers.get("x-csrf-token") if supplied is None else supplied
    if not isinstance(token, str) or not expected or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Недействительный CSRF-токен")


def check_origin(request, *, auth=False):
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in {"same-origin", "none"}:
        raise HTTPException(status_code=403, detail="Недопустимый источник запроса")
    origin = request.headers.get("origin")
    expected = origin_tuple(str(request.base_url))
    if origin is not None:
        actual = origin_tuple(origin)
        if actual is None or actual != expected:
            raise HTTPException(status_code=403, detail="Недопустимый источник запроса")
    elif auth and request.headers.get("x-tutorflow-request") != "auth":
        raise HTTPException(status_code=403, detail="Недопустимый источник запроса")
