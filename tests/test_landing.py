from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_landing_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TutorFlow" in response.text
    assert "augustin-neutral.png" in response.text
    assert "Мы собрали то, что обычно разбросано" in response.text
    assert "Теперь это один маршрут." in response.text
    assert "Прокрутите, чтобы узнать больше" in response.text


def test_design_tokens_are_served() -> None:
    response = client.get("/static/css/tokens.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_augustin_neutral_asset_is_served() -> None:
    response = client.get("/static/images/augustin/augustin-neutral.png")

    assert response.status_code == 200
    assert "image/png" in response.headers["content-type"]


def test_local_gsap_assets_are_served() -> None:
    for path in ("gsap.min.js", "ScrollTrigger.min.js"):
        response = client.get(f"/static/vendor/gsap/{path}")

        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "3.15.0" in response.text[:200]


def test_health_still_works() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
