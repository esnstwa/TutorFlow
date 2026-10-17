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
_SHA_PATTERN = re.compile(r"[0-9a-f]{12,40}\Z", re.IGNORECASE)


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


def _checkout_sha() -> str:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        env=_clean_git_environment(),
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("git rev-parse не вернул полный SHA коммита")
    return commit


def _expected_sha(argument: str | None) -> str | None:
    candidate = argument or os.getenv("TUTORFLOW_EXPECTED_SHA")
    if not candidate:
        return None
    candidate = candidate.strip().lower()
    if not _SHA_PATTERN.fullmatch(candidate):
        raise ValueError("ожидался Git SHA длиной от 12 до 40 шестнадцатеричных символов")
    return candidate


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
        checkout_sha = _checkout_sha()
        expected_sha = _expected_sha(arguments.expected_sha)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"component_check ERROR: {error}", file=sys.stderr)
        return 2

    if expected_sha and not checkout_sha.startswith(expected_sha):
        print(
            f"component_check ERROR: SHA не совпал; ожидался {expected_sha[:12]}, "
            f"получен {checkout_sha[:12]}",
            file=sys.stderr,
        )
        return 1
    expected_sha = checkout_sha[:12]

    environment = _clean_git_environment()
    environment["APP_NAME"] = "TutorFlow-Quality-Check"
    environment["APP_ENV"] = "test"

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
