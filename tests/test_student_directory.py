from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.usefixtures("legacy_cabinet_auth")

from app.main import app

client = TestClient(app)


def test_directory_search_filters_student_cards() -> None:
    response = client.get('/students', params={'q': 'Михаил'})
    assert response.status_code == 200
    visible = response.context.get('directory_students', response.context['students'])
    assert [row['id'] for row in visible] == [1]


def test_directory_renders_search_controls_and_only_matching_cards() -> None:
    response = client.get('/students', params={'q': 'Михаил'})
    assert 'data-student-directory-form' in response.text
    assert 'name="q"' in response.text
    assert 'name="subject"' in response.text
    assert f"Показано 1 из {response.context['directory_total']}" in response.text
    assert 'data-directory-student="1"' in response.text
    assert 'data-directory-student="2"' not in response.text


@pytest.mark.parametrize('query', ['  КОВАЛЕВ  ', 'михаил  ковалев', 'm.kovalev', '9 класс'])
def test_directory_search_normalizes_and_matches_contact_fields(query: str) -> None:
    response = client.get('/students', params={'q': query})
    assert response.status_code == 200
    assert [row['id'] for row in response.context['directory_students']] == [1]
    assert response.context['directory_query'] == query.strip()


def test_directory_subject_combines_with_search_without_filtering_modal_options() -> None:
    response = client.get('/students', params={'q': 'класс', 'subject': 'Физика'})
    assert [row['id'] for row in response.context['directory_students']] == [3]
    assert response.context['directory_subject'] == 'Физика'
    assert 'Математика' in response.context['directory_subjects']
    assert len(response.context['students']) == response.context['directory_total']
    assert '<option value="Физика" selected>' in response.text


def test_directory_no_results_keeps_controls_and_reset_link() -> None:
    response = client.get('/students', params={'q': 'нет-такого-ученика'})
    assert response.context['directory_students'] == []
    assert 'data-directory-no-results' in response.text
    assert 'Ученики не найдены' in response.text
    assert 'Учеников пока нет' not in response.text
    assert 'Сбросить' in response.text
    assert 'data-student-directory-form' in response.text


def test_directory_whitespace_returns_all_students() -> None:
    response = client.get('/students', params={'q': '   ', 'subject': '  '})
    assert len(response.context['directory_students']) == response.context['directory_total']
    assert response.context['directory_query'] == ''
    assert response.context['directory_subject'] == ''


def test_directory_query_is_escaped_in_html() -> None:
    query = '\"><script>alert(1)</script>'
    response = client.get('/students', params={'q': query})
    assert response.status_code == 200
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text


@pytest.mark.parametrize('params', [{'q': 'x' * 201}, {'subject': 'x' * 121}])
def test_directory_bounds_query_parameters(params: dict[str, str]) -> None:
    assert client.get('/students', params=params).status_code == 422


def test_directory_limits_students_and_subjects_to_current_teacher() -> None:
    from fastapi import Depends
    from app.core.auth import get_current_teacher
    from app.core.database import get_db
    from app.models import Student, User
    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        teacher = User(email='directory-teacher@example.test', password_hash='not-a-login', first_name='Другой', last_name='Учитель', role='teacher')
        db.add(teacher)
        db.flush()
        teacher_id = teacher.id
        student = Student(teacher_id=teacher_id, first_name='Другой', last_name='Ученик', subject='Химия', grade='8 класс')
        db.add(student)
        db.commit()
        student_id = student.id

    def current_teacher(db=Depends(get_db)):
        return db.get(User, teacher_id)

    app.dependency_overrides[get_current_teacher] = current_teacher
    try:
        response = client.get('/students')
        assert response.context['directory_total'] == 1
        assert response.context['directory_subjects'] == ['Химия']
        assert [row['id'] for row in response.context['directory_students']] == [student_id]
        assert client.get('/students?q=Михаил').context['directory_students'] == []
        with TestingSessionLocal() as db:
            db.delete(db.get(Student, student_id))
            db.commit()
        empty = client.get('/students')
        assert 'Учеников пока нет' in empty.text
        assert 'Ученики не найдены' not in empty.text
    finally:
        app.dependency_overrides.pop(get_current_teacher, None)
        with TestingSessionLocal() as db:
            teacher = db.get(User, teacher_id)
            if teacher:
                db.delete(teacher)
                db.commit()
