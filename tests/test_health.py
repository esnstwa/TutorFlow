import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.main import app

client = TestClient(app)


def test_health_preserves_the_minimal_response_contract() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_schedule_stylesheet_is_available_in_source_runtime() -> None:
    response = client.get("/static/css/schedule.css")

    assert response.status_code == 200
    assert response.content


def test_health_does_not_recompute_runtime_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_runtime_lookup(*_args: str) -> dict[str, str]:
        pytest.fail("/health must not run runtime diagnostics on every request")

    monkeypatch.setattr(app_main, "runtime_info", unexpected_runtime_lookup)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
