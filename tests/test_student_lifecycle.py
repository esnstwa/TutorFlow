"""Isolated HTTP lifecycle tests: no demo-auth or running database."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_current_teacher
from app.core.database import Base, get_db
from app.models import Student, User, Lesson, Homework, HomeworkRecipient, HomeworkSubmission
from app.web.router import router as web_router
from app.students.models import StudentInvitation


def real_client(ctx, user):
    import secrets
    from app.students.router import router
    from app.auth.models import AuthSession
    from app.auth.sessions import token_digest
    from app.models import utc_now
    db = ctx['db']
    raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(raw), csrf_token=csrf, expires_at=utc_now()+timedelta(days=1)))
    db.commit()
    api = FastAPI(); api.include_router(web_router); api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api, base_url='https://testserver', headers={'X-CSRF-Token': csrf, 'Origin': 'https://testserver'})
    client.cookies.set('tutorflow_session', raw)
    return client


@pytest.fixture
def ctx():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    db = factory()
    teacher = User(email='teacher@example.com', password_hash='unused', first_name='Teacher', role='teacher')
    user = User(email='child@example.com', password_hash='unused', first_name='Child', role='student')
    other = User(email='other@example.com', password_hash='unused', first_name='Other', role='teacher')
    db.add_all([teacher, user, other]); db.flush()
    student = Student(teacher_id=teacher.id, first_name='Child', last_name='Name', email=user.email, grade='9 класс', subject='Math')
    db.add(student); db.commit()
    api = FastAPI(); api.include_router(web_router)
    api.dependency_overrides[get_db] = lambda: db
    api.dependency_overrides[get_current_teacher] = lambda: teacher
    state = {'db': db, 'teacher': teacher, 'user': user, 'other': other, 'student': student, 'api': api}
    try:
        from app.students.router import router, current_user
        api.include_router(router)
        api.dependency_overrides[current_user] = lambda: state['user']
    except ModuleNotFoundError:
        pass
    state['client'] = TestClient(api)
    yield state
    db.close(); Base.metadata.drop_all(engine); engine.dispose()


def test_delete_archives_without_deleting_history(ctx):
    db, s, c = ctx['db'], ctx['student'], ctx['client']
    s.user_id = ctx['user'].id
    lesson = Lesson(teacher_id=s.teacher_id, student_id=s.id, subject='Math', topic='History', start_at=datetime(2027, 1, 1, 10), end_at=datetime(2027, 1, 1, 11))
    hw = Homework(teacher_id=s.teacher_id, title='History', description='Keep')
    recipient = HomeworkRecipient(student=s, homework=hw)
    submission = HomeworkSubmission(recipient=recipient, comment='Keep answer')
    db.add_all([lesson, hw, recipient, submission]); db.commit()
    assert c.delete(f'/api/students/{s.id}').status_code == 200
    db.expire_all()
    preserved = db.get(Student, s.id)
    assert preserved is not None
    assert preserved.archived_at is not None
    assert preserved.user_id == ctx['user'].id
    assert db.get(Lesson, lesson.id) is not None
    assert db.get(HomeworkSubmission, submission.id).comment == 'Keep answer'


def test_invitation_requires_explicit_token_consent(ctx):
    c, s, db = ctx['client'], ctx['student'], ctx['db']
    issued = c.post(f'/api/students/{s.id}/invite')
    assert issued.status_code == 200
    body = issued.json()
    assert body['student']['lifecycle'] == 'invited'
    token = body['invitation']['url'].split('#')[1]
    assert db.get(Student, s.id).user_id is None
    preview = c.post('/api/student/invitations/preview', json={'token': token})
    assert preview.status_code == 200
    assert preview.json()['student']['name'] == 'Child Name'
    accepted = c.post('/api/student/invitations/accept', json={'token': token})
    assert accepted.status_code == 200
    assert accepted.json()['student']['lifecycle'] == 'linked'
    assert db.get(Student, s.id).user_id == ctx['user'].id
    from app.students.models import StudentInvitation
    inv = db.scalar(select(StudentInvitation))
    assert inv.token_hash != token
    assert len(inv.token_hash) == 64
    assert inv.consumed_at is not None


@pytest.mark.parametrize('invalid', ['expired', 'reused', 'revoked', 'archived', 'wrong_role', 'wrong_email', 'linked_elsewhere', 'student_linked', 'changed_email'])
def test_invitation_rejects_invalid_acceptance_without_stealing_links(ctx, invalid):
    c, s, db = ctx['client'], ctx['student'], ctx['db']
    token = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    inv = db.scalar(select(StudentInvitation))
    if invalid == 'expired': inv.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if invalid == 'reused': inv.consumed_at = datetime.now(timezone.utc)
    if invalid == 'revoked': inv.revoked_at = datetime.now(timezone.utc)
    if invalid == 'archived': s.archived_at = datetime.now(timezone.utc)
    if invalid == 'wrong_role': ctx['user'] = ctx['teacher']
    if invalid == 'wrong_email': ctx['user'].email = 'wrong@example.com'
    if invalid == 'changed_email': s.email = 'changed@example.com'
    if invalid == 'linked_elsewhere':
        db.add(Student(teacher_id=ctx['other'].id, user_id=ctx['user'].id, first_name='Existing', grade='1', subject='Other'))
    if invalid == 'student_linked': s.user_id = ctx['other'].id
    db.commit()
    before = s.user_id
    authenticated = real_client(ctx, ctx['user'])
    response = authenticated.post('/api/student/invitations/accept', json={'token': token})
    assert response.status_code in (403, 409, 422)
    db.expire_all()
    assert db.get(Student, s.id).user_id == before


@pytest.mark.parametrize('invalid', ['archived', 'linked', 'no_email'])
def test_issue_invitation_rejects_ineligible_student(ctx, invalid):
    s = ctx['student']
    if invalid == 'archived': s.archived_at = datetime.now(timezone.utc)
    if invalid == 'linked': s.user_id = ctx['user'].id
    if invalid == 'no_email': s.email = None
    ctx['db'].commit()
    assert ctx['client'].post(f'/api/students/{s.id}/invite').status_code == 422


def test_reissue_revokes_old_token(ctx):
    c, s = ctx['client'], ctx['student']
    old = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    new = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    assert old != new
    assert c.post('/api/student/invitations/preview', json={'token': old}).status_code == 422
    assert c.post('/api/student/invitations/accept', json={'token': new}).status_code == 200


def test_archive_restore_revokes_outstanding_invitation(ctx):
    c, s, db = ctx['client'], ctx['student'], ctx['db']
    token = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    response = c.post(f'/api/students/{s.id}/archive')
    assert response.status_code == 200
    assert response.json()['student']['archived'] is True
    assert c.post(f'/api/students/{s.id}/restore').json()['student']['archived'] is False
    assert c.post('/api/student/invitations/accept', json={'token': token}).status_code == 422


@pytest.mark.parametrize('method, suffix', [('post', '/invite'), ('post', '/archive'), ('post', '/restore'), ('patch', ''), ('delete', '')])
def test_student_mutations_are_owner_scoped(ctx, method, suffix):
    client = real_client(ctx, ctx['other'])
    response = getattr(client, method)(f"/api/students/{ctx['student'].id}{suffix}")
    assert response.status_code == 404


@pytest.mark.parametrize('method', ['post', 'patch'])
@pytest.mark.parametrize('payload', [{'user_id': 2}, {'name': ''}, {'name': 'a'*101}, {'name': 'A '+'b'*101}, {'email': 'not-email'}, {'subject': 'a'*121}, {'grade': 'a'*51}, {'subject': ''}, {'grade': ''}, {'email': 'a'*321}])
def test_student_input_is_bounded_and_rejects_user_link_assignment(ctx, method, payload):
    data = {'name': 'Valid Name', 'email': 'valid@example.com', 'subject': 'Math', 'grade': '9'} if method == 'post' else {}
    data.update(payload)
    path = '/api/students' if method == 'post' else f"/api/students/{ctx['student'].id}"
    assert getattr(ctx['client'], method)(path, json=data).status_code == 422


def test_create_same_email_never_autolinks_and_update_keeps_history(ctx):
    c, s, db = ctx['client'], ctx['student'], ctx['db']
    response = c.post('/api/students', json={'name': 'Same Email', 'email': ctx['user'].email, 'subject': 'Math', 'grade': '9'})
    assert response.status_code == 200
    new = db.get(Student, response.json()['student']['id'])
    assert new.user_id is None
    assert response.json()['student']['lifecycle'] == 'unlinked'
    updated = c.patch(f'/api/students/{s.id}', json={'name': 'New Name', 'email': 'demo@example.test', 'grade': '10', 'subject': 'Physics'})
    assert updated.status_code == 200
    assert updated.json()['student']['name'] == 'New Name'
    assert s.teacher_id == ctx['teacher'].id


def test_archived_students_excluded_from_roster_search_and_directory(ctx):
    from app.services import cabinet_data, student_directory
    from app.homework.service import search_students
    s, db = ctx['student'], ctx['db']
    s.archived_at = datetime.now(timezone.utc); db.commit()
    assert cabinet_data(db, ctx['teacher'])['students'] == []
    assert search_students(db, ctx['teacher'].id, '') == []
    assert student_directory(db, ctx['teacher'])['directory_students'] == []
    rows = student_directory(db, ctx['teacher'], query='child', subject='Math', archived='archived')['directory_students']
    assert [row['id'] for row in rows] == [s.id]
    assert student_directory(db, ctx['teacher'], archived='all')['directory_total'] == 1


@pytest.mark.parametrize('path, payload', [
    ('/api/lessons', {'student_id': 1, 'date': '2027-02-01', 'start': '10:00', 'end': '11:00', 'topic': 'New'}),
    ('/api/mock/lesson', {'student_id': 1, 'date': '2027-02-01', 'start': '10:00', 'end': '11:00', 'topic': 'New'}),
    ('/api/homework', {'title': 'New', 'description': 'New', 'recipient_ids': [1]}),
    ('/api/assignments', {'title': 'New', 'description': 'New', 'recipient_ids': [1]}),
    ('/api/mock/assignment', {'student_id': 1, 'due': '2027-02-01', 'title': 'New'})])
def test_archived_students_cannot_receive_new_work(ctx, path, payload):
    ctx['student'].archived_at = datetime.now(timezone.utc); ctx['db'].commit()
    assert ctx['client'].post(path, json=payload).status_code == 422


@pytest.mark.parametrize('authenticated, role, expected', [(False, 'student', 401), (True, 'teacher', 403), (True, 'student', 200)])
def test_preview_requires_real_student_session(ctx, authenticated, role, expected):
    from app.students.router import router
    from app.auth.models import AuthSession
    from app.auth.sessions import token_digest
    from app.models import utc_now
    db = ctx['db']
    raw = 'session-token-for-test'
    principal = ctx['user'] if role == 'student' else ctx['teacher']
    db.add(AuthSession(user_id=principal.id, token_hash=token_digest(raw), csrf_token='csrf-test', expires_at=utc_now()+timedelta(days=1)))
    db.commit()
    token = ctx['client'].post(f"/api/students/{ctx['student'].id}/invite").json()['invitation']['url'].split('#')[1]
    api = FastAPI(); api.include_router(router)
    api.dependency_overrides[get_db] = lambda: db  # Only database is replaced; real session/role/CSRF.
    client = TestClient(api, base_url='https://testserver')
    if authenticated: client.cookies.set('tutorflow_session', raw)
    response = client.post('/api/student/invitations/preview', json={'token': token}, headers={'X-CSRF-Token': 'csrf-test', 'Origin': 'https://testserver'})
    assert response.status_code == expected


def test_accept_rejects_real_session_without_csrf(ctx):
    from app.students.router import router
    from app.auth.models import AuthSession
    from app.auth.sessions import token_digest
    from app.models import utc_now
    db = ctx['db']
    db.add(AuthSession(user_id=ctx['user'].id, token_hash=token_digest('session-test'), csrf_token='csrf-test', expires_at=utc_now()+timedelta(days=1)))
    db.commit()
    token = ctx['client'].post(f"/api/students/{ctx['student'].id}/invite").json()['invitation']['url'].split('#')[1]
    api = FastAPI(); api.include_router(router); api.dependency_overrides[get_db] = lambda: db
    client = TestClient(api, base_url='https://testserver'); client.cookies.set('tutorflow_session', 'session-test')
    assert client.post('/api/student/invitations/accept', json={'token': token}).status_code == 403
    assert ctx['student'].user_id is None


def test_email_change_permanently_revokes_invitation(ctx):
    c, s = ctx['client'], ctx['student']
    token = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    assert c.patch(f'/api/students/{s.id}', json={'email': 'changed@example.com'}).status_code == 200
    assert c.patch(f'/api/students/{s.id}', json={'email': ctx['user'].email}).json()['student']['lifecycle'] == 'unlinked'
    assert c.post('/api/student/invitations/accept', json={'token': token}).status_code == 422


@pytest.mark.parametrize('payload', [[], None, 'text'])
def test_create_rejects_non_object_payload(ctx, payload):
    assert ctx['client'].post('/api/students', json=payload).status_code == 422


def test_additive_migration_preserves_existing_student_data():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text, inspect
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/d2b3c4d5e6f7_student_lifecycle.py'
    assert path.is_file()
    spec = importlib.util.spec_from_file_location('student_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    assert migration.revision == 'd2b3c4d5e6f7'
    assert migration.down_revision == 'c1a2b3c4d5e6'
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE students (id INTEGER PRIMARY KEY, first_name VARCHAR(100))'))
        connection.execute(text("INSERT INTO students VALUES (1, 'Preserved')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text('SELECT first_name, archived_at FROM students')).one() == ('Preserved', None)
        assert 'student_invitations' in inspect(connection).get_table_names()
    engine.dispose()


def test_archived_linked_student_still_reads_submission_history(ctx):
    s, db = ctx['student'], ctx['db']
    s.user_id = ctx['user'].id
    homework = Homework(teacher_id=s.teacher_id, title='Historic homework', description='Keep')
    recipient = HomeworkRecipient(student=s, homework=homework, status='SUBMITTED')
    submission = HomeworkSubmission(recipient=recipient, comment='Historic answer')
    db.add_all([homework, recipient, submission]); db.commit()
    assert ctx['client'].patch(f'/api/students/{s.id}', json={'name': 'Updated Name'}).status_code == 200
    assert ctx['client'].delete(f'/api/students/{s.id}').status_code == 200
    student_client = real_client(ctx, ctx['user'])
    response = student_client.get(f'/api/student/homework/{recipient.id}')
    assert response.status_code == 200
    assert response.json()['recipient']['submissions'][0]['comment'] == 'Historic answer'
    assert ctx['client'].get(f'/api/students/{s.id}').json()['student']['archived'] is True


def test_invitation_lifetime_is_seven_days_and_expiry_changes_lifecycle(ctx):
    s, db, c = ctx['student'], ctx['db'], ctx['client']
    c.post(f'/api/students/{s.id}/invite')
    invitation = db.scalar(select(StudentInvitation))
    assert abs((invitation.expires_at-invitation.created_at).total_seconds() - timedelta(days=7).total_seconds()) < 1
    invitation.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1); db.commit()
    assert c.get(f'/api/students/{s.id}').json()['student']['lifecycle'] == 'unlinked'


def test_invitation_expiring_while_acquiring_student_lock_is_rejected(ctx, monkeypatch):
    from sqlalchemy import event
    import app.students.service as service
    c, s, db = ctx['client'], ctx['student'], ctx['db']
    token = c.post(f'/api/students/{s.id}/invite').json()['invitation']['url'].split('#')[1]
    clock = [datetime.now(timezone.utc)]
    invitation = db.scalar(select(StudentInvitation))
    invitation.expires_at = clock[0]+timedelta(seconds=1); db.commit()
    monkeypatch.setattr(service, 'utc_now', lambda: clock[0])
    def acquired(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith('UPDATE students SET user_id'):
            clock[0] += timedelta(seconds=2)
    engine = db.get_bind()
    event.listen(engine, 'after_cursor_execute', acquired)
    try:
        assert c.post('/api/student/invitations/accept', json={'token': token}).status_code == 422
        db.expire_all()
        assert db.get(Student, s.id).user_id is None
        assert db.get(StudentInvitation, invitation.id).consumed_at is None
    finally:
        event.remove(engine, 'after_cursor_execute', acquired)


def test_concurrent_accept_has_exactly_one_winner(ctx):
    import os
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.students.service import accept_invitation, issue_invitation
    with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
        engine = create_engine('sqlite:///' + directory.replace('\\', '/') + '/invites.sqlite', connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory() as db:
            teacher = User(email='concurrent.teacher@example.com', password_hash='unused', first_name='T', role='teacher')
            user = User(email='concurrent.student@example.com', password_hash='unused', first_name='S', role='student')
            db.add_all([teacher, user]); db.flush()
            student = Student(teacher_id=teacher.id, email=user.email, first_name='S', grade='1', subject='Math')
            db.add(student); db.commit()
            token, invitation = issue_invitation(db, student)
            uid, sid, iid = user.id, student.id, invitation.id
        barrier = Barrier(2)
        def attempt():
            with factory() as db:
                user = db.get(User, uid)
                db.get(Student, sid); db.get(StudentInvitation, iid)
                barrier.wait(timeout=10)
                try:
                    accept_invitation(db, token, user)
                    return 'accepted'
                except ValueError:
                    return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: attempt(), range(2)))
        assert sorted(results) == ['accepted', 'rejected']
        with factory() as db:
            assert db.get(Student, sid).user_id == uid
            assert db.get(StudentInvitation, iid).consumed_at is not None
        engine.dispose()
