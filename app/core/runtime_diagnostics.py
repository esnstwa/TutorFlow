"""Сведения о сборке и проверка минимального запуска TutorFlow."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

logger = logging.getLogger("tutorflow.runtime")
_SHA_RE = re.compile(r"(?P<sha>[0-9a-f]{7,40})(?P<dirty>-dirty)?\Z", re.IGNORECASE)


def _normalise_revision(value: str) -> str:
    value = value.strip().lower()
    if value == "unknown":
        return value
    match = _SHA_RE.fullmatch(value)
    if not match:
        return "unknown"
    return match.group("sha")[:12] + (match.group("dirty") or "")


def _packaged_revision() -> str:
    try:
        metadata = json.loads(files("app").joinpath("build-info.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return "unknown"
    return _normalise_revision(str(metadata.get("git_sha", "unknown")))


def git_revision() -> str:
    """Вернуть сокращённый SHA и отметить незакоммиченное состояние."""
    supplied = os.getenv("TUTORFLOW_GIT_SHA") or os.getenv("GITHUB_SHA")
    if supplied:
        return _normalise_revision(supplied)

    repository = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip().lower()
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                "app",
                "pyproject.toml",
                "uv.lock",
                "scripts/build_component.py",
            ],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return _packaged_revision()

    if not re.fullmatch(r"[0-9a-f]{12}", commit):
        return _packaged_revision()
    return f"{commit}-dirty" if status.strip() else commit


def runtime_info(app_name: str, app_env: str) -> dict[str, str]:
    """Собрать безопасный для вывода минимум сведений о запуске."""
    try:
        app_version = version("tutorflow")
    except PackageNotFoundError:
        app_version = "unknown"

    return {
        "app_name": app_name,
        "environment": app_env,
        "version": app_version,
        "git_sha": git_revision(),
    }


def _configuration_error(error: ValidationError) -> str:
    messages: list[str] = []
    for item in error.errors(include_input=False):
        field = ".".join(str(part) for part in item["loc"])
        messages.append(f"{field}: {item['msg']}")
    return "; ".join(messages) or "не удалось проверить настройки"


def main() -> int:
    """Вывести диагностику; при неверной конфигурации вернуть код 2."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("component_start")

    try:
        # Импорт внутри try позволяет перехватить ошибку Settings при импорте.
        from app.core.config import settings

        info = runtime_info(settings.app_name, settings.app_env)
    except ValidationError as error:
        print(f"configuration_error: {_configuration_error(error)}", file=sys.stderr)
        logger.info("component_result status=error")
        return 2

    print(json.dumps({"status": "ok", **info}, ensure_ascii=False, sort_keys=True))
    logger.info(
        "component_result status=ok version=%s git_sha=%s",
        info["version"],
        info["git_sha"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
