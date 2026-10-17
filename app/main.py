import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.runtime_diagnostics import runtime_info
from app.students.router import router as students_router
from app.web.router import router as web_router
from app.web.templating import STATIC_DIR

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

logger = logging.getLogger("tutorflow.runtime")
logger.setLevel(logging.INFO)

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("application/javascript", ".js")

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    info = runtime_info(settings.app_name, settings.app_env)
    logger.info(
        "application_start environment=%s version=%s git_sha=%s",
        info["environment"],
        info["version"],
        info["git_sha"],
    )
    try:
        yield
    finally:
        logger.info(
            "application_stop version=%s git_sha=%s",
            info["version"],
            info["git_sha"],
        )


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router)
app.include_router(students_router)
app.include_router(web_router)


@app.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict[str, str]:
    return {"status": "ok", **runtime_info(settings.app_name, settings.app_env)}
