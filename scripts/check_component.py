"""Содержательная проверка запуска минимального компонента TutorFlow."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SHA_PATTERN = re.compile(r"[0-9a-f]{7,40}\Z", re.IGNORECASE)


def _expected_sha(argument: str | None) -> str:
    candidate = argument or os.getenv("TUTORFLOW_EXPECTED_SHA") or os.getenv("GITHUB_SHA")
    if not candidate:
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    candidate = candidate.strip().lower()
    if not _SHA_PATTERN.fullmatch(candidate):
        raise ValueError("ожидался Git SHA длиной от 7 до 40 шестнадцатеричных символов")
    return candidate[:12]


def _run_component(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.core.runtime_diagnostics"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", help="SHA исходного состояния для проверки")
    arguments = parser.parse_args()

    try:
        expected_sha = _expected_sha(arguments.expected_sha)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"component_check ERROR: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["APP_NAME"] = "TutorFlow-Quality-Check"
    environment["APP_ENV"] = "test"
    environment.pop("TUTORFLOW_GIT_SHA", None)

    result = _run_component(environment)
    if result.returncode != 0:
        print("component_check ERROR: допустимая конфигурация не запустилась", file=sys.stderr)
        print(result.stderr, file=sys.stderr, end="")
        return 1

    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("component_check ERROR: вывод компонента не является JSON", file=sys.stderr)
        return 1

    actual_sha = str(report.get("git_sha", "")).removesuffix("-dirty")
    if report.get("status") != "ok":
        print("component_check ERROR: статус компонента не ok", file=sys.stderr)
        return 1
    if report.get("app_name") != "TutorFlow-Quality-Check":
        print("component_check ERROR: APP_NAME не повлиял на результат", file=sys.stderr)
        return 1
    if report.get("version") in {None, "", "unknown"}:
        print("component_check ERROR: версия приложения не определена", file=sys.stderr)
        return 1
    if actual_sha != expected_sha:
        print(
            f"component_check ERROR: SHA не совпал; ожидался {expected_sha}, получен {actual_sha or 'пусто'}",
            file=sys.stderr,
        )
        return 1

    invalid_environment = environment.copy()
    invalid_environment["APP_ENV"] = "invalid-pz01-value"
    invalid_result = _run_component(invalid_environment)
    if (
        invalid_result.returncode != 2
        or "configuration_error" not in invalid_result.stderr
        or "app_env" not in invalid_result.stderr
    ):
        print("component_check ERROR: неверная конфигурация не была отклонена", file=sys.stderr)
        return 1

    print(
        "component_check PASS "
        f"version={report['version']} git_sha={report['git_sha']} "
        "valid_config=0 invalid_config=2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
