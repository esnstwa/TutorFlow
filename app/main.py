from fastapi import FastAPI, status

from app.core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    return {"status": "ok"}
