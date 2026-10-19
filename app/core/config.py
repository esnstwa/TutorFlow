from datetime import datetime, timezone
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_SECONDS_PER_DAY = 24 * 60 * 60


def _datetime_safe_lifetime_seconds() -> int:
    """Return a technical bound that keeps session expiry representable."""
    remaining = datetime.max.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    remaining_seconds = remaining.days * _SECONDS_PER_DAY + remaining.seconds
    return max(1, remaining_seconds - _SECONDS_PER_DAY)


# This is a datetime representability limit, not a product lifetime policy.
# The one-day margin prevents a Settings instance from becoming invalid merely
# because the process runs between configuration loading and session creation.
MAX_SESSION_LIFETIME_SECONDS = _datetime_safe_lifetime_seconds()


class Settings(BaseSettings):
    app_name: str = "TutorFlow"
    app_env: Literal["production", "development", "local", "test"] = "production"

    database_url: str = (
        "postgresql+psycopg://tutorflow:tutorflow@localhost:5432/tutorflow"
    )
    dev_teacher_email: str = "anna@tutorflow.local"
    dev_student_email: str = "student@tutorflow.local"
    enable_dev_teacher_fallback: bool = False
    file_storage_path: str = "var/uploads"
    session_lifetime_seconds: int = Field(
        default=43200,
        gt=0,
        le=MAX_SESSION_LIFETIME_SECONDS,
        description=(
            "Lifetime of a regular authentication session in seconds; the "
            "upper bound keeps datetime expiry calculations representable."
        ),
    )
    remember_session_lifetime_seconds: int = Field(
        default=2592000,
        gt=0,
        le=MAX_SESSION_LIFETIME_SECONDS,
        description=(
            "Lifetime of a remember-me authentication session in seconds; the "
            "upper bound keeps datetime expiry calculations representable."
        ),
    )

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_env == "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
