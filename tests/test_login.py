from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_page() -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "С возвращением" in response.text
    assert 'placeholder="Email"' in response.text
    assert 'placeholder="Пароль"' in response.text
    assert "augustin-neutral.webp" in response.text
    assert "augustin-eyes-closed.webp" in response.text
    assert "augustin-peeking.webp" in response.text
    assert "/static/css/login.css" in response.text
    assert "/static/js/login.js" in response.text


def test_landing_links_to_login_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="http://testserver/login"' in response.text


def test_login_assets_are_served() -> None:
    for path, content_type in (
        ("/static/css/login.css", "text/css"),
        ("/static/js/login.js", "javascript"),
        ("/static/images/augustin/augustin-eyes-closed.webp", "image/webp"),
        ("/static/images/augustin/augustin-peeking.webp", "image/webp"),
    ):
        response = client.get(path)

        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
