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
    assert "Как к вам " in response.text
    assert "<em>обращаться?</em>" in response.text
    assert "Это имя будут видеть ваши ученики и преподаватели." in response.text
    assert 'placeholder="Ваше имя"' in response.text
    assert 'id="register-name-error"' in response.text
    assert 'aria-describedby="register-name-error"' in response.text
    assert 'data-name-success' not in response.text
    assert 'data-name-success-text' not in response.text
    assert "Продолжить" in response.text
    assert response.text.count('class="register-continue__arrow"') == 5
    assert 'data-register-step="2" hidden' in response.text
    assert 'data-register-step="3" hidden' in response.text
    assert "Теперь ваша " in response.text
    assert "<em>почта.</em>" in response.text
    assert "Она понадобится для входа и важных уведомлений TutorFlow." in response.text
    assert 'aria-label="Email"' in response.text
    assert 'placeholder="Ваша почта"' in response.text
    assert 'id="register-email-error"' in response.text
    assert 'aria-describedby="register-email-error"' in response.text
    assert "email-form__valid-icon" not in response.text
    assert 'data-register-step="4" hidden' in response.text
    assert "Остался " in response.text
    assert "<em>пароль.</em>" in response.text
    assert "Придумайте пароль для своего аккаунта." in response.text
    assert 'placeholder="Пароль"' in response.text
    assert 'placeholder="Повторите пароль"' in response.text
    assert 'id="register-password"' in response.text
    assert 'name="password"' in response.text
    assert 'id="register-password-confirmation"' in response.text
    assert 'name="password_confirmation"' in response.text
    assert 'autocomplete="off"' in response.text
    assert response.text.count("data-password-toggle") == 2
    assert 'data-password-requirement="length"' in response.text
    assert 'data-password-requirement="letter"' in response.text
    assert 'data-password-requirement="digit"' in response.text
    assert "8+ символов" in response.text
    assert "буквы" in response.text
    assert "цифры" in response.text
    assert "Завершить" in response.text
    assert 'type="submit" disabled' in response.text
    assert 'data-register-step="5" hidden' in response.text
    assert "Всё " in response.text
    assert "<em>готово</em>" in response.text
    assert "ваш аккаунт TutorFlow создан." in response.text
    assert "Перейти в TutorFlow" in response.text
    assert 'data-register-complete-name' in response.text
    assert 'data-register-complete-description' in response.text
    assert 'data-register-complete-character' in response.text
    assert 'class="register-complete__stage"' in response.text
    assert "register-complete__spark" not in response.text
    assert "augustin-teacher-complete.webp" in response.text
    assert "augustin-student-complete.webp" in response.text
    assert 'value="teacher" checked' in response.text
    assert "augustin-teacher-role.webp" in response.text
    assert "augustin-student-role.webp" in response.text
    assert response.text.count('d="m6.5 12.5 3.4 3.4 7.7-8"') == 5
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
        ("/static/images/registration/augustin-student-role.webp", "image/webp"),
        ("/static/images/registration/augustin-teacher-role.webp", "image/webp"),
        ("/static/images/registration/augustin-student-complete.webp", "image/webp"),
        ("/static/images/registration/augustin-teacher-complete.webp", "image/webp"),
    ):
        response = client.get(path)

        assert response.status_code == 200
        assert content_type in response.headers["content-type"]


def test_route_character_uses_two_lossless_preloaded_moods() -> None:
    page = client.get("/register").text
    assert 'data-route-character-idle=' in page
    assert 'data-route-character-happy=' in page
    assert page.index('/js/register-route.js') < page.index('/js/register.js')
    assert client.get('/static/js/register-route.js').status_code == 200
    assert 'jump-01.webp' not in page
    assert 'success.webp' not in page
    for mood in ('idle', 'happy'):
        path = f'/static/images/registration/route/augustin-{mood}.webp'
        assert path in page
        response = client.get(path)
        assert response.status_code == 200
        data = response.content
        assert data[:4] == b'RIFF' and data[8:12] == b'WEBP'
        # VP8L identifies lossless WebP; its packed header stores canvas and alpha.
        assert data[12:16] == b'VP8L'
        header = int.from_bytes(data[21:25], 'little')
        assert (header & 0x3FFF) + 1 == 221
        assert ((header >> 14) & 0x3FFF) + 1 == 210
        assert (header >> 28) & 1


def test_route_character_uses_one_precomputed_waapi_animation() -> None:
    script = client.get('/static/js/register-route.js').text
    assert 'this.layer.animate(' in script
    assert 'offsetPath' in script
    assert 'offsetDistance' in script
    assert 'requestAnimationFrame' not in script
    assert 'translate3d' not in script
    assert 'devicePixelRatio' not in script
    assert 'willChange' not in script
    assert 'const segments' not in script
    assert script.count("document.createElement('img')") == 1
