import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import runtime_diagnostics


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REVISION_PATHS = ["app", "pyproject.toml", "uv.lock", "scripts/build_component.py"]


def _expected_checkout_revision() -> tuple[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if name.upper().startswith("GIT_") or name.upper() in {
            "GITHUB_SHA",
            "TUTORFLOW_GIT_SHA",
            "TUTORFLOW_EXPECTED_SHA",
        }:
            environment.pop(name)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout.strip().lower()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *REVISION_PATHS],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
    ).stdout
    revision = head[:12] + ("-dirty" if status.strip() else "")
    return head, revision


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
    _, expected_revision = _expected_checkout_revision()
    result = _run_diagnostic(
        {
            "APP_NAME": "TutorFlow-Practice",
            "APP_ENV": "test",
            "TUTORFLOW_GIT_SHA": "0000000000000000000000000000000000000000",
            "GITHUB_SHA": "0000000000000000000000000000000000000000",
            "DATABASE_URL": "diagnostic-marker-not-output",
        }
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report == {
        "app_name": "TutorFlow-Practice",
        "environment": "test",
        "git_sha": expected_revision,
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


@pytest.mark.parametrize(
    "revision",
    ["012345", "0123456", "01234567890", "01234567890-dirty", "0" * 41, "g" * 12],
)
def test_normalise_revision_rejects_invalid_revision_boundaries(revision: str) -> None:
    assert runtime_diagnostics._normalise_revision(revision) == "unknown"


@pytest.mark.parametrize(
    ("revision", "expected"),
    [
        ("0123456789ab", "0123456789ab"),
        ("0123456789abcdef0123456789abcdef01234567", "0123456789ab"),
        ("ABCDEF012345-dirty", "abcdef012345-dirty"),
    ],
)
def test_normalise_revision_preserves_the_twelve_character_contract(
    revision: str, expected: str
) -> None:
    assert runtime_diagnostics._normalise_revision(revision) == expected


def test_installed_wheel_prefers_packaged_sha_inside_an_unrelated_git_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unrelated_repo = tmp_path / "unrelated-repository"
    unrelated_repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(unrelated_repo)], check=True)
    (unrelated_repo / "marker.txt").write_text("unrelated\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(unrelated_repo), "add", "marker.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(unrelated_repo),
            "-c",
            "user.name=TutorFlow Test",
            "-c",
            "user.email=tutorflow-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "unrelated test repository",
        ],
        check=True,
    )

    package = unrelated_repo / "runtime-env" / "Lib" / "site-packages" / "app"
    (package / "core").mkdir(parents=True)
    (package / "core" / "runtime_diagnostics.py").write_text("# installed module\n", encoding="utf-8")
    packaged_sha = "abcdef0123456789abcdef0123456789abcdef01"
    (package / "build-info.json").write_text(
        json.dumps({"git_sha": packaged_sha}), encoding="utf-8"
    )

    monkeypatch.setattr(
        runtime_diagnostics,
        "__file__",
        str(package / "core" / "runtime_diagnostics.py"),
    )
    monkeypatch.setattr(runtime_diagnostics, "files", lambda _name: package)
    monkeypatch.delenv("TUTORFLOW_GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    assert runtime_diagnostics.git_revision() == packaged_sha[:12]


def test_source_checkout_prefers_git_sha_over_stale_packaged_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "source-repository"
    module = repository / "app" / "core" / "runtime_diagnostics.py"
    module.parent.mkdir(parents=True)
    module.write_text("# source module\n", encoding="utf-8")
    (repository / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (repository / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    build_script = repository / "scripts" / "build_component.py"
    build_script.parent.mkdir()
    build_script.write_text("# build script\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "app", "pyproject.toml", "uv.lock", "scripts"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=TutorFlow Test",
            "-c",
            "user.email=tutorflow-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "source repository fixture",
        ],
        check=True,
    )
    head = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--short=12", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    package = repository / "app"
    (package / "build-info.json").write_text(
        json.dumps({"git_sha": "abcdef0123456789abcdef0123456789abcdef01"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(runtime_diagnostics, "__file__", str(module))
    monkeypatch.setattr(runtime_diagnostics, "files", lambda _name: package)
    monkeypatch.delenv("TUTORFLOW_GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    assert runtime_diagnostics.git_revision() == f"{head}-dirty"


def test_container_sha_is_used_only_when_package_and_source_metadata_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "container" / "app"
    module = package / "core" / "runtime_diagnostics.py"
    module.parent.mkdir(parents=True)
    module.write_text("# container module\n", encoding="utf-8")
    monkeypatch.setattr(runtime_diagnostics, "__file__", str(module))
    monkeypatch.setattr(runtime_diagnostics, "files", lambda _name: package)
    monkeypatch.setenv("TUTORFLOW_GIT_SHA", "1234567890abcdef1234567890abcdef12345678")
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)

    assert runtime_diagnostics.git_revision() == "1234567890ab"


def test_packaged_revision_returns_unknown_for_invalid_utf8_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "app"
    package.mkdir()
    (package / "build-info.json").write_bytes(b"\xff")
    monkeypatch.setattr(runtime_diagnostics, "files", lambda _name: package)

    assert runtime_diagnostics._packaged_revision() == "unknown"


def test_source_revision_runs_git_only_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    original_run = subprocess.run
    git_commands: list[list[str]] = []

    def track_git(command: list[str], *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command and command[0] == "git":
            git_commands.append(command)
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", track_git)
    first = runtime_diagnostics.git_revision()
    second = runtime_diagnostics.git_revision()

    assert first == second
    assert len(git_commands) <= 2


def _run_component_check(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(overrides)
    return subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "check_component.py")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def test_component_check_uses_checkout_sha_not_environment_overrides() -> None:
    actual_sha, expected_revision = _expected_checkout_revision()
    result = _run_component_check(
        {
            "TUTORFLOW_EXPECTED_SHA": actual_sha,
            "TUTORFLOW_GIT_SHA": "0" * 40,
            "GITHUB_SHA": "0" * 40,
        }
    )

    assert result.returncode == 0, result.stderr
    assert f"git_sha={expected_revision}" in result.stdout


def test_component_check_rejects_matching_but_false_environment_sha() -> None:
    false_sha = "0" * 40
    result = _run_component_check(
        {
            "TUTORFLOW_EXPECTED_SHA": false_sha,
            "TUTORFLOW_GIT_SHA": false_sha,
            "GITHUB_SHA": false_sha,
        }
    )

    assert result.returncode == 1
    assert "SHA не совпал" in result.stderr
