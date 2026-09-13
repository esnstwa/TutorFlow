from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TutorFlow"
    database_url: str = (
        "postgresql+psycopg://tutorflow:tutorflow@localhost:5432/tutorflow"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
