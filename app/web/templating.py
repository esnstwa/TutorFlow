from pathlib import Path

from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def static_version(path: str) -> str:
    """Return a cache-busting version that changes whenever a static file is saved."""
    asset = STATIC_DIR / path.lstrip("/")
    try:
        return str(asset.stat().st_mtime_ns)
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version
