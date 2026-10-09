import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Student, User, utc_now
from app.students.models import StudentInvitation


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_invitation(db: Session, student: Student) -> tuple[str, StudentInvitation]:
    # A no-op conditional write serializes issue/archive/accept on this row.
    eligible = db.execute(update(Student).where(Student.id == student.id, Student.user_id.is_(None), Student.archived_at.is_(None), Student.email == student.email).values(updated_at=utc_now()))
    if eligible.rowcount != 1 or not student.email:
        db.rollback()
        raise ValueError('Ученик архивирован, связан или не имеет email')
    db.execute(update(StudentInvitation).where(StudentInvitation.student_id == student.id, StudentInvitation.consumed_at.is_(None), StudentInvitation.revoked_at.is_(None)).values(revoked_at=utc_now()))
    raw = secrets.token_urlsafe(32)
    invitation = StudentInvitation(student_id=student.id, target_email=student.email, token_hash=token_hash(raw), expires_at=utc_now() + timedelta(days=7))
    db.add(invitation)
    db.commit()
    return raw, invitation


def invitation_for_token(db: Session, token: str) -> StudentInvitation:
    item = db.scalar(select(StudentInvitation).where(StudentInvitation.token_hash == token_hash(token), StudentInvitation.revoked_at.is_(None), StudentInvitation.consumed_at.is_(None), StudentInvitation.expires_at > utc_now()))
    student = db.get(Student, item.student_id) if item else None
    if not item or not student or student.archived_at is not None or student.user_id is not None or (student.email or '').casefold() != item.target_email.casefold():
        raise ValueError("Приглашение недействительно")
    return item


def accept_invitation(db: Session, token: str, user: User) -> Student:
    from sqlalchemy.exc import IntegrityError
    if user.role != 'student':
        raise ValueError('Требуется аккаунт ученика')
    invitation = invitation_for_token(db, token)
    student = db.get(Student, invitation.student_id)
    if user.email.casefold() != invitation.target_email.casefold():
        raise ValueError('Приглашение предназначено другому аккаунту')
    if db.scalar(select(Student.id).where(Student.user_id == user.id)):
        raise ValueError('Аккаунт уже связан с учеником')
    try:
        # Match issue/archive/email-change lock order: Student, then invitation.
        linked = db.execute(update(Student).where(Student.id == student.id, Student.user_id.is_(None), Student.archived_at.is_(None), Student.email == student.email).values(user_id=user.id))
        # Acquiring the Student write lock may wait past the invitation expiry.
        now = utc_now()
        consumed = db.execute(update(StudentInvitation).where(StudentInvitation.id == invitation.id, StudentInvitation.consumed_at.is_(None), StudentInvitation.revoked_at.is_(None), StudentInvitation.expires_at > now).values(consumed_at=now).execution_options(synchronize_session=False))
        if consumed.rowcount != 1 or linked.rowcount != 1:
            raise ValueError('Приглашение уже использовано или изменено')
        db.commit()
        db.refresh(student)
    except (IntegrityError, ValueError) as exc:
        db.rollback()
        raise ValueError('Аккаунт или приглашение уже связано') from exc
    return student


def archive_student(db: Session, student: Student) -> Student:
    now = utc_now()
    db.execute(update(Student).where(Student.id == student.id).values(archived_at=student.archived_at or now))
    db.execute(update(StudentInvitation).where(StudentInvitation.student_id == student.id, StudentInvitation.consumed_at.is_(None), StudentInvitation.revoked_at.is_(None)).values(revoked_at=now))
    db.commit()
    db.refresh(student)
    return student


def lifecycle(db: Session | None, student: Student) -> str:
    if student.user_id is not None:
        return 'linked'
    if db and db.scalar(select(StudentInvitation.id).where(StudentInvitation.student_id == student.id, StudentInvitation.revoked_at.is_(None), StudentInvitation.consumed_at.is_(None), StudentInvitation.expires_at > utc_now())):
        return 'invited'
    return 'unlinked'
