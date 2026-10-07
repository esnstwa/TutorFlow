from fastapi import Request
from starlette.routing import NoMatchFound

_AUTH_ROUTE_NAMES = {
    "login": "auth_login",
    "register": "auth_register",
}

TEACHER_NAVIGATION = (
    ("dashboard", "home", "Главная"),
    ("schedule", "calendar", "Расписание"),
    ("students", "users", "Ученики"),
    ("assignments", "assignment", "Задания"),
    ("materials", "folder", "Материалы"),
)


def get_auth_navigation(request: Request) -> dict[str, str | None]:
    """Resolve optional auth links without exposing routes that do not exist yet."""
    navigation: dict[str, str | None] = {}

    for action, route_name in _AUTH_ROUTE_NAMES.items():
        try:
            navigation[action] = str(request.url_for(route_name))
        except NoMatchFound:
            navigation[action] = None

    return navigation
