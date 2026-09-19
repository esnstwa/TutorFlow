from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_landing_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TutorFlow" in response.text


def test_design_tokens_are_served() -> None:
    response = client.get("/static/css/tokens.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_health_still_works() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
