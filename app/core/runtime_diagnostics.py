"""Сведения о сборке и проверка минимального запуска TutorFlow."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
from pathlib import Path

from pydantic import ValidationError

logger = logging.getLogger("tutorflow.runtime")
_SHA_RE = re.compile(r"(?P<sha>[0-9a-f]{12,40})(?P<dirty>-dirty)?\Z", re.IGNORECASE)


def _normalise_revision(value: str) -> str:
    value = value.strip().lower()
    if value == "unknown":
        return value
    match = _SHA_RE.fullmatch(value)
    if not match:
        return "unknown"
    return match.group("sha")[:12] + (match.group("dirty") or "")


def _packaged_revision() -> str | None:
    try:
        build_info = files("app").joinpath("build-info.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, TypeError, UnicodeDecodeError):
        return "unknown"

    try:
        metadata = json.loads(build_info)
    except json.JSONDecodeError:
        return "unknown"
    if not isinstance(metadata, dict):
        return "unknown"
    return _normalise_revision(str(metadata.get("git_sha", "unknown")))


def _source_repository() -> Path | None:
    module_path = Path(__file__).resolve()
    repository = module_path.parents[2]
    source_module = repository / "app" / "core" / "runtime_diagnostics.py"
    if (
        (repository / ".git").exists()
        and (repository / "pyproject.toml").is_file()
        and source_module.resolve() == module_path
    ):
        return repository
    return None


def _git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("GIT_") or name.upper() == "GITHUB_SHA":
            environment.pop(name)
    return environment


@lru_cache(maxsize=4)
def _source_revision(repository: Path) -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repository,
            env=_git_environment(),
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
            env=_git_environment(),
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    revision = _normalise_revision(commit)
    if revision == "unknown":
        return revision
    return f"{revision}-dirty" if status.strip() else revision


def git_revision() -> str:
    """Вернуть сокращённый SHA и отметить незакоммиченное состояние."""
    repository = _source_repository()
    if repository is not None:
        return _source_revision(repository)

    packaged = _packaged_revision()
    if packaged is not None:
        return packaged
    return _normalise_revision(os.getenv("TUTORFLOW_GIT_SHA", "unknown"))


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
