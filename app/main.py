import mimetypes

from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.web.router import router as web_router
from app.web.templating import STATIC_DIR

mimetypes.add_type("image/webp", ".webp")

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(web_router)


@app.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    return {"status": "ok"}
