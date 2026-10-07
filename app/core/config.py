from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TutorFlow"
    database_url: str = (
        "postgresql+psycopg://tutorflow:tutorflow@localhost:5432/tutorflow"
    )
    dev_teacher_email: str = "anna@tutorflow.local"
    enable_dev_teacher_fallback: bool = True
    file_storage_path: str = "var/uploads"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
