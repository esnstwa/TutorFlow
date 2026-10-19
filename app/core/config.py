from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# This fixed ten-year bound is a technical configuration limit, not a product
# lifetime policy. It is well above the 30-day default and does not depend on
# when the process imported this module; runtime expiry calculation still
# checks the actual current datetime before creating a session.
MAX_SESSION_LIFETIME_SECONDS = 10 * 365 * 24 * 60 * 60


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
