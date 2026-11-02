"""Regression boundaries between main's projection and teacher A-01–A-04."""
from datetime import date

import pytest

from app import services
from app.core.config import Settings
from app.schedule.sqlalchemy_source import SQLAlchemyCalendarEventSource
from tests.test_teacher_schedule import create, schedule_case


def test_session_lifetimes_and_file_quota_coexist():
    config = Settings(
        _env_file=None, app_env="test", database_url="sqlite+pysqlite:///:memory:",
        file_upload_max_bytes=4096, session_lifetime_seconds=3600,
        remember_session_lifetime_seconds=86400,
    )
    assert config.file_upload_max_bytes == 4096
    assert config.session_lifetime_seconds == 3600
    assert config.remember_session_lifetime_seconds == 86400


@pytest.mark.parametrize("end, included", [("00:00", False), ("01:00", True)])
def test_teacher_overlap_is_opt_in_without_changing_default_source(schedule_case, end, included):
    case = schedule_case
    lesson = create(case, start="23:30", end=end, end_date="2035-01-14")
    bounds = {"date_from": date(2035, 1, 14), "date_to": date(2035, 1, 14)}
    with case["sessions"]() as db:
        default = SQLAlchemyCalendarEventSource(db, services.lesson_dict)
        assert default.lessons_for_teacher(case["teacher_id"], **bounds) == []
        teacher = SQLAlchemyCalendarEventSource(
            db, services.lesson_dict, include_overlapping_lessons=True,
        )
        rows = teacher.lessons_for_teacher(case["teacher_id"], **bounds)
        assert [row.lesson_id for row in rows] == ([lesson["id"]] if included else [])
    result = case["client"].get("/api/lessons?date_from=2035-01-14&date_to=2035-01-14")
    assert result.status_code == 200, result.text
    assert [row["id"] for row in result.json()["lessons"]] == ([lesson["id"]] if included else [])


def test_http_fixture_keeps_production_defaults_secure(schedule_case, monkeypatch):
    from app.core.config import settings
    monkeypatch.delenv("APP_ENV", raising=False)
    assert settings.app_env == "test"
    assert Settings(_env_file=None).session_cookie_secure is True
    assert schedule_case["client"].get("/api/lessons").status_code == 200


def test_teacher_http_still_uses_neutral_projection(schedule_case, monkeypatch):
    case = schedule_case
    calls = []
    projector = services.CalendarEventService

    class ObservedProjection(projector):
        def list_events(self, **kwargs):
            calls.append(kwargs)
            return super().list_events(**kwargs)

    monkeypatch.setattr(services, "CalendarEventService", ObservedProjection)
    lesson = create(case, subject="Астрономия")
    response = case["client"].get("/api/lessons?date_from=2035-01-13&date_to=2035-01-13")
    assert response.status_code == 200, response.text
    assert calls == [{"teacher_id": case["teacher_id"], "date_from": date(2035, 1, 13), "date_to": date(2035, 1, 13)}]
    assert response.json()["lessons"][0]["id"] == lesson["id"]
