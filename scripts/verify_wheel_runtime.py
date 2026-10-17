"""Проверить установленный wheel вне checkout и постороннего Git-репозитория."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from zipfile import BadZipFile, ZipFile

_REVISION_PATTERN = re.compile(r"[0-9a-f]{12}(?:-dirty)?\Z")


def _clean_git_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("GIT_") or name.upper() in {
            "GITHUB_SHA",
            "TUTORFLOW_GIT_SHA",
            "TUTORFLOW_EXPECTED_SHA",
        }:
            environment.pop(name)
    return environment


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout.strip()


def _verify_wheel(wheel: Path, expected_revision: str) -> int:
    if not _REVISION_PATTERN.fullmatch(expected_revision):
        print("expected revision must be a 12-character SHA, optionally followed by -dirty", file=sys.stderr)
        return 2
    try:
        with ZipFile(wheel) as package:
            metadata = json.loads(package.read("app/build-info.json"))
    except (BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError, OSError) as error:
        print(f"cannot read app/build-info.json from wheel: {error}", file=sys.stderr)
        return 2

    packaged_revision = str(metadata.get("git_sha", "")) if isinstance(metadata, dict) else ""
    if packaged_revision != expected_revision:
        print(
            f"wheel revision mismatch: expected {expected_revision}, packaged {packaged_revision or 'unknown'}",
            file=sys.stderr,
        )
        return 1

    try:
        with tempfile.TemporaryDirectory(prefix="tutorflow-wheel-runtime-") as temporary:
            unrelated_repo = Path(temporary) / "unrelated-repository"
            unrelated_repo.mkdir()
            git_environment = _clean_git_environment()
            _run(["git", "init", "--quiet", str(unrelated_repo)], cwd=unrelated_repo, environment=git_environment)
            (unrelated_repo / "marker.txt").write_text("unrelated repository\n", encoding="utf-8")
            _run(["git", "add", "marker.txt"], cwd=unrelated_repo, environment=git_environment)
            _run(
                [
                    "git",
                    "-c",
                    "user.name=TutorFlow Verification",
                    "-c",
                    "user.email=tutorflow-verification@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "unrelated repository fixture",
                ],
                cwd=unrelated_repo,
                environment=git_environment,
            )
            foreign_revision = _run(
                ["git", "rev-parse", "--short=12", "HEAD"],
                cwd=unrelated_repo,
                environment=git_environment,
            ).lower()
            if foreign_revision == expected_revision.split("-", 1)[0]:
                print("test fixture unexpectedly has the same SHA as the wheel", file=sys.stderr)
                return 1

            site_packages = unrelated_repo / "runtime-env" / "site-packages"
            site_packages.mkdir(parents=True)
            _run(
                ["uv", "pip", "install", "--target", str(site_packages), "--no-deps", str(wheel)],
                cwd=unrelated_repo,
                environment=git_environment,
            )

            environment = os.environ.copy()
            for name in tuple(environment):
                if name.upper().startswith("GIT_") or name.upper() in {
                    "GITHUB_SHA",
                    "TUTORFLOW_GIT_SHA",
                    "TUTORFLOW_EXPECTED_SHA",
                }:
                    environment.pop(name)
            previous_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = str(site_packages) + (
                os.pathsep + previous_pythonpath if previous_pythonpath else ""
            )
            environment["APP_NAME"] = "TutorFlow-wheel-check"
            environment["APP_ENV"] = "test"

            diagnostic = subprocess.run(
                [sys.executable, "-m", "app.core.runtime_diagnostics"],
                cwd=unrelated_repo,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if diagnostic.returncode != 0:
                print(diagnostic.stderr, file=sys.stderr, end="")
                return 1
            report = json.loads(diagnostic.stdout)
            if report.get("git_sha") != expected_revision:
                print(
                    "installed wheel reported the wrong SHA: "
                    f"expected {expected_revision}, got {report.get('git_sha', 'unknown')}; "
                    f"unrelated repo is {foreign_revision}",
                    file=sys.stderr,
                )
                return 1

            module_path = Path(
                _run(
                    [sys.executable, "-c", "import app; from pathlib import Path; print(Path(app.__file__).resolve())"],
                    cwd=unrelated_repo,
                    environment=environment,
                )
            )
            if module_path != (site_packages / "app" / "__init__.py").resolve():
                print(f"application imported outside the installed wheel: {module_path}", file=sys.stderr)
                return 1

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]

            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=unrelated_repo,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    if server.poll() is not None:
                        logs = server.communicate(timeout=5)[0]
                        raise RuntimeError(f"Uvicorn exited before readiness:\n{logs}")
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                            health_status = response.status
                            health_json = json.loads(response.read())
                        with urlopen(f"http://127.0.0.1:{port}/static/css/schedule.css", timeout=5) as response:
                            static_status = response.status
                            css_bytes = len(response.read())
                        if health_status != 200 or health_json != {"status": "ok"}:
                            raise RuntimeError(f"unexpected /health response: {health_status} {health_json}")
                        if static_status != 200 or css_bytes == 0:
                            raise RuntimeError(f"unexpected schedule CSS response: {static_status}, {css_bytes} bytes")
                        break
                    except (URLError, TimeoutError, ConnectionError):
                        if time.monotonic() >= deadline:
                            logs = server.communicate(timeout=5)[0] if server.poll() is not None else ""
                            raise RuntimeError(f"Uvicorn did not become ready within 20 seconds:\n{logs}")
                        time.sleep(0.1)
            finally:
                if server.poll() is None:
                    server.terminate()
                try:
                    server.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.communicate(timeout=5)
            print(
                "WHEEL_RUNTIME PASS "
                f"git_sha={report['git_sha']} foreign_git_sha={foreign_revision} "
                f"health={health_status} static={static_status} css_bytes={css_bytes} "
                "import=installed-wheel"
            )
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError, KeyError) as error:
        print(f"wheel runtime verification failed: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expected-sha", required=True)
    arguments = parser.parse_args()
    return _verify_wheel(arguments.wheel.resolve(), arguments.expected_sha.strip().lower())


if __name__ == "__main__":
    raise SystemExit(main())
