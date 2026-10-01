from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_register_page() -> None:
    response = client.get("/register")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Давайте " in response.text
    assert "<em>знакомиться</em>" in response.text
    assert "01" in response.text
    assert "Я преподаватель" in response.text
    assert "Я ученик" in response.text
    assert 'value="teacher" checked' in response.text
    assert "teacher.png" in response.text
    assert "student.png" in response.text
    assert response.text.count('d="m6.5 12.5 3.4 3.4 7.7-8"') == 2
    assert "/static/css/register.css" in response.text
    assert "/static/js/register.js" in response.text


def test_login_links_to_register_page() -> None:
    response = client.get("/login")

    assert response.status_code == 200
    assert 'href="http://testserver/register"' in response.text


def test_register_assets_are_served() -> None:
    for path, content_type in (
        ("/static/css/register.css", "text/css"),
        ("/static/js/register.js", "application/javascript"),
        ("/static/images/registration/student.png", "image/png"),
        ("/static/images/registration/teacher.png", "image/png"),
    ):
        response = client.get(path)

        assert response.status_code == 200
        assert content_type in response.headers["content-type"]
