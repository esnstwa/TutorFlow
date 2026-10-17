import json
import logging
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run_diagnostic(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(overrides)
    return subprocess.run(
        [sys.executable, "-m", "app.core.runtime_diagnostics"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_diagnostic_reports_config_version_revision_and_safe_logs() -> None:
    result = _run_diagnostic(
        {
            "APP_NAME": "TutorFlow-Practice",
            "APP_ENV": "test",
            "TUTORFLOW_GIT_SHA": "0123456789abcdef0123456789abcdef01234567",
            "DATABASE_URL": "diagnostic-marker-not-output",
        }
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report == {
        "app_name": "TutorFlow-Practice",
        "environment": "test",
        "git_sha": "0123456789ab",
        "status": "ok",
        "version": "0.1.0",
    }
    assert "component_start" in result.stderr
    assert "component_result status=ok" in result.stderr
    assert "diagnostic-marker-not-output" not in result.stdout + result.stderr


def test_invalid_environment_fails_without_printing_database_secret() -> None:
    result = _run_diagnostic(
        {
            "APP_ENV": "not-a-valid-environment",
            "DATABASE_URL": "diagnostic-marker-not-output",
        }
    )

    assert result.returncode == 2
    assert "configuration_error" in result.stderr
    assert "app_env" in result.stderr
    assert "diagnostic-marker-not-output" not in result.stdout + result.stderr
    assert "component_result status=error" in result.stderr


def test_application_runtime_logger_accepts_info_records() -> None:
    from app.main import logger as runtime_logger

    assert runtime_logger.getEffectiveLevel() == logging.INFO
