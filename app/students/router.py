from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_current_teacher, get_current_user as current_user
from app.core.database import get_db
from app.models import User, Student
from app.services import scoped_student, student_dict, teacher_dict
from app.students.service import issue_invitation, invitation_for_token, accept_invitation

router = APIRouter()


@router.post('/api/students/{student_id}/archive')
def archive(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    from app.students.service import archive_student
    student = scoped_student(db, teacher.id, student_id)
    if not student:
        raise HTTPException(404, 'Ученик не найден')
    return {'ok': True, 'student': student_dict(archive_student(db, student))}


@router.post('/api/students/{student_id}/restore')
def restore(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    student = scoped_student(db, teacher.id, student_id)
    if not student:
        raise HTTPException(404, 'Ученик не найден')
    student.archived_at = None
    db.commit()
    return {'ok': True, 'student': student_dict(student)}


class TokenBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(min_length=1, max_length=128)


@router.post('/api/students/{student_id}/invite')
def invite(student_id: int, db: Session = Depends(get_db), teacher: User = Depends(get_current_teacher)):
    student = scoped_student(db, teacher.id, student_id)
    if not student:
        raise HTTPException(404, 'Ученик не найден')
    try:
        raw, invitation = issue_invitation(db, student)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return {'ok': True, 'student': student_dict(student), 'invitation': {'url': '/invite#' + raw, 'expires_at': invitation.expires_at.isoformat()}}


@router.post('/api/student/invitations/preview')
def preview(data: TokenBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != 'student':
        raise HTTPException(403, 'Требуется роль ученика')
    try:
        invitation = invitation_for_token(db, data.token)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    student = db.get(Student, invitation.student_id)
    return {'ok': True, 'student': {'name': student_dict(student)['name']}, 'teacher': {'name': teacher_dict(student.teacher)['name']}}


@router.post('/api/student/invitations/accept')
def accept(data: TokenBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        student = accept_invitation(db, data.token, user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return {'ok': True, 'student': student_dict(student)}
