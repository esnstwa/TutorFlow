"""Сборка воспроизводимого wheel-пакета или Docker-образа TutorFlow."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
REVISION_PATTERN = re.compile(r"[0-9a-f]{12}(?:-dirty)?\Z")
REQUIRED_WHEEL_FILES = {
    "app/main.py",
    "app/core/runtime_diagnostics.py",
    "app/build-info.json",
    "app/web/templates/pages/schedule.html",
    "app/web/static/css/schedule.css",
}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def source_revision() -> str:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("GIT_"):
            environment.pop(name)
    commit = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{12}", commit):
        raise ValueError("Git не вернул ожидаемый сокращённый SHA")

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
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout
    return f"{commit}-dirty" if status.strip() else commit


def copy_project_config(destination: Path) -> None:
    root = ROOT.resolve()
    source = ROOT / "pyproject.toml"
    if source.is_symlink():
        raise ValueError("Символическая ссылка не допускается: pyproject.toml")
    resolved_source = source.resolve()
    if not _inside(resolved_source, root):
        raise ValueError("pyproject.toml находится вне репозитория")
    if not resolved_source.is_file():
        raise ValueError("pyproject.toml не является файлом")
    shutil.copy2(resolved_source, destination / "pyproject.toml")


def copy_tracked_app(destination: Path) -> None:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("GIT_"):
            environment.pop(name)
    result = subprocess.run(
        ["git", "ls-files", "--cached", "-z", "--", "app"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        timeout=3,
    )
    root = ROOT.resolve()
    for entry in result.stdout.decode("utf-8").split("\0"):
        if not entry:
            continue
        relative_path = Path(entry)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Git вернул небезопасный путь файла приложения")
        if "__pycache__" in relative_path.parts or relative_path.suffix == ".pyc":
            continue
        source = root
        for part in relative_path.parts:
            source /= part
            if source.is_symlink():
                raise ValueError(f"Символическая ссылка не допускается: {relative_path}")
        if not source.is_file():
            continue
        resolved_source = source.resolve()
        if not _inside(resolved_source, root):
            raise ValueError(f"Файл приложения находится вне репозитория: {relative_path}")
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved_source, target)


def verify_wheel(path: Path, expected_revision: str) -> str:
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            missing = sorted(REQUIRED_WHEEL_FILES - names)
            if missing:
                raise ValueError("в wheel отсутствуют файлы: " + ", ".join(missing))

            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            metadata = package.read(metadata_name).decode("utf-8")
            version_lines = [line for line in metadata.splitlines() if line.startswith("Version: ")]
            if len(version_lines) != 1:
                raise ValueError("в METADATA не найдена единственная версия пакета")
            package_version = version_lines[0].split(": ", 1)[1].strip()

            build_info = json.loads(package.read("app/build-info.json"))
            if not isinstance(build_info, dict):
                raise ValueError("app/build-info.json должен содержать JSON-объект")
            packaged_revision = str(build_info.get("git_sha", ""))
    except (BadZipFile, KeyError, StopIteration, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"не удалось проверить wheel: {error}") from error

    if packaged_revision != expected_revision or not REVISION_PATTERN.fullmatch(packaged_revision):
        raise ValueError("в wheel записан неверный Git SHA")
    return package_version


def build_wheel(output_directory: Path, work_directory: Path) -> int:
    root = ROOT.resolve()
    output = output_directory.resolve()
    work = work_directory.resolve()
    if _inside(output, root) or _inside(work, root):
        print("Пути сборки должны находиться вне каталога репозитория.", file=sys.stderr)
        return 2
    if not work.is_dir():
        print(f"Временный каталог не найден: {work}", file=sys.stderr)
        return 2

    output.mkdir(parents=True, exist_ok=True)
    if any(output.glob("tutorflow-*.whl")):
        print("В каталоге уже есть wheel; выбери новый каталог, чтобы ничего не перезаписать.", file=sys.stderr)
        return 2

    try:
        revision = source_revision()
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"Не удалось определить исходное состояние Git: {error}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="tutorflow-wheel-", dir=work) as temporary:
        staging = Path(temporary)
        try:
            copy_project_config(staging)
            copy_tracked_app(staging)
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError, ValueError) as error:
            print(f"Не удалось собрать безопасный staging: {error}", file=sys.stderr)
            return 2
        (staging / "app").mkdir(parents=True, exist_ok=True)
        (staging / "app" / "build-info.json").write_text(
            json.dumps({"git_sha": revision}, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        build = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(output)],
            cwd=staging,
            check=False,
        )
        if build.returncode:
            return build.returncode

    wheels = list(output.glob("tutorflow-*.whl"))
    if len(wheels) != 1:
        print("Сборка не создала ровно один wheel.", file=sys.stderr)
        return 1
    try:
        package_version = verify_wheel(wheels[0], revision)
    except ValueError as error:
        print(f"Проверка поставочного пакета завершилась ошибкой: {error}", file=sys.stderr)
        return 1

    print(
        f"BUILD_OK artifact={wheels[0]} version={package_version} "
        f"git_sha={revision} packaged_files={len(REQUIRED_WHEEL_FILES)}"
    )
    return 0


def build_image(dry_run: bool) -> int:
    try:
        revision = source_revision()
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"Не удалось определить исходное состояние Git: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["TUTORFLOW_GIT_SHA"] = revision
    command = ["docker", "compose", "build", "web"]
    if dry_run:
        print(f"IMAGE_BUILD_PLAN git_sha={revision} command={' '.join(command)}")
        return 0
    return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="target", required=True)

    wheel_parser = subcommands.add_parser("wheel", help="собрать wheel во внешнем каталоге")
    wheel_parser.add_argument("--out-dir", type=Path, required=True)
    wheel_parser.add_argument("--work-dir", type=Path, default=Path(tempfile.gettempdir()))

    image_parser = subcommands.add_parser("image", help="собрать Docker-образ с Git SHA")
    image_parser.add_argument("--dry-run", action="store_true")

    arguments = parser.parse_args()
    if arguments.target == "wheel":
        return build_wheel(arguments.out_dir, arguments.work_dir)
    return build_image(arguments.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
