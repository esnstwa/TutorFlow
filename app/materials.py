"""Material access and public metadata over the existing file model."""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from urllib.parse import quote, unquote

from fastapi.responses import StreamingResponse
from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import FileResource, Homework, Lesson, Student, User
from app.storage import (FileStorageError, StoredUpload, finish_staged_deletion, inspect_file,
                         restore_staged_file, safe_storage_file, stage_deletion, validate_filename)

PREVIEW_TYPES = frozenset({"image/png", "image/jpeg", "text/plain"})
logger = logging.getLogger(__name__)


def accessible_file(db: Session, user: User, file_id: int) -> FileResource:
    if user.role not in {"teacher", "student"}:
        raise HTTPException(status_code=403, detail="Недоступная роль")
    item = db.scalar(select(FileResource).where(FileResource.id == file_id))
    if item is not None:
        if item.owner_id == user.id:
            return item
        if user.role == "student":
            student = db.scalar(select(Student).where(Student.user_id == user.id))
            if student is not None and item.owner_id == student.teacher_id:
                if any(lesson.student_id == student.id and lesson.teacher_id == student.teacher_id for lesson in item.lessons):
                    return item
                if any(homework.teacher_id == student.teacher_id and any(recipient.student_id == student.id for recipient in homework.recipients) for homework in item.homeworks):
                    return item
        elif any(submission.recipient.homework.teacher_id == user.id and submission.recipient.student.user_id == item.owner_id for submission in item.homework_submissions):
            return item
    raise HTTPException(status_code=404, detail="Материал не найден")


def upload_headers(request: Request) -> tuple[str, str, str, int | None]:
    def decode(value):
        try:
            if re.search(r"%(?![0-9A-Fa-f]{2})", value):
                raise ValueError("invalid escape")
            return unquote(value, errors="strict")
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=422, detail="Некорректная UTF-8 кодировка заголовка файла") from None

    original_name = decode(request.headers.get("X-Filename", ""))
    try:
        validate_filename(original_name)
    except FileStorageError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    title = decode(request.headers["X-Title"]) if "X-Title" in request.headers else original_name[:200]
    kind = decode(request.headers["X-File-Kind"]) if "X-File-Kind" in request.headers else "Файл"
    for value, limit in ((title, 200), (kind, 80)):
        if not value.strip() or len(value) > limit or any(unicodedata.category(char).startswith("C") for char in value):
            raise HTTPException(status_code=422, detail="Некорректное название или тип материала")
    if request.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise HTTPException(status_code=415, detail="Сжатое тело загрузки не поддерживается")
    raw_length = request.headers.get("Content-Length")
    if raw_length is not None and not re.fullmatch(r"[0-9]+", raw_length):
        raise HTTPException(status_code=422, detail="Некорректный Content-Length")
    length = int(raw_length) if raw_length is not None else None
    if length is not None and length > settings.file_upload_max_bytes:
        raise HTTPException(status_code=413, detail="Файл превышает допустимый размер")
    return original_name, title, kind, length


def upload_targets(db: Session, owner_id: int, lesson_id: int | None, homework_id: int | None):
    targets = []
    for model, identifier, attribute in ((Lesson, lesson_id, "materials"), (Homework, homework_id, "attachments")):
        if identifier is None:
            continue
        item = db.scalar(select(model).where(model.id == identifier, model.teacher_id == owner_id).execution_options(populate_existing=True))
        if item is None:
            raise HTTPException(status_code=404, detail="Занятие или задание не найдено")
        targets.append((item, attribute))
    return targets


def _discard_uncommitted_upload(db: Session, upload: StoredUpload):
    try:
        db.rollback()
    except Exception:
        logger.warning("Material transaction rollback requires reconciliation")
    try:
        # A commit error may mean an unknown outcome, not a guaranteed rollback.
        with Session(bind=db.get_bind()) as verification:
            referenced = verification.scalar(select(FileResource.id).where(FileResource.stored_name == upload.stored_name).limit(1))
    except Exception:
        logger.warning("Material cleanup deferred until database recovery")
        return
    if referenced is None:
        try:
            target = safe_storage_file(upload.storage_path)
            if target is not None:
                target.unlink(missing_ok=True)
        except (OSError, FileStorageError):
            logger.warning("Material cleanup deferred until storage recovery")


def persist_upload(db: Session, owner_id: int, upload: StoredUpload, *, title: str, kind: str,
                   lesson_id: int | None = None, homework_id: int | None = None,
                   expected_size: int | None = None) -> FileResource:
    try:
        if expected_size is not None and upload.size != expected_size:
            raise HTTPException(status_code=422, detail="Размер тела не совпадает с Content-Length")
        targets = upload_targets(db, owner_id, lesson_id, homework_id)
        item = FileResource(owner_id=owner_id, original_name=upload.original_name,
                            stored_name=upload.stored_name, storage_path=upload.storage_path,
                            mime_type=upload.mime_type, size=upload.size, title=title, kind=kind)
        db.add(item)
        for target, attribute in targets:
            getattr(target, attribute).append(item)
        db.commit()
        return item
    except HTTPException:
        _discard_uncommitted_upload(db, upload)
        raise
    except Exception:
        _discard_uncommitted_upload(db, upload)
        raise HTTPException(status_code=503, detail="Не удалось подтвердить сохранение. Проверьте список материалов перед повтором.") from None


def delete_stored_material(db: Session, item: FileResource) -> bool:
    staged = None
    reference = None
    try:
        # Match the existing student mutation pattern: a no-op write serializes
        # DELETEs on this row before touching bytes (also on SQLite).
        locked = db.execute(update(FileResource).where(
            FileResource.id == item.id, FileResource.owner_id == item.owner_id,
        ).values(updated_at=FileResource.updated_at).execution_options(synchronize_session=False))
        if locked.rowcount != 1:
            raise HTTPException(status_code=404, detail="Материал не найден")
        db.refresh(item)
        # Keep scalar identity before rollback expires the ORM object.
        reference = (item.id, item.owner_id, item.stored_name, item.storage_path)
        try:
            staged = stage_deletion(item.storage_path)
        except (OSError, FileStorageError):
            raise HTTPException(status_code=503, detail="Не удалось подготовить удаление файла") from None
        db.delete(item)
        db.commit()
    except Exception as error:
        try:
            db.rollback()
        except Exception:
            # Do not open another writer while the original lock may be held.
            logger.warning("Material deletion rollback requires reconciliation")
        else:
            if staged is not None and reference is not None:
                try:
                    # Rollback released the lock. Reacquire it with fresh DB
                    # reference proof and hold it THROUGH filesystem recovery.
                    # A commit exception is not proof that the row survived.
                    with Session(bind=db.get_bind()) as recovery:
                        retained = recovery.execute(update(FileResource).where(
                            FileResource.id == reference[0], FileResource.owner_id == reference[1],
                            FileResource.stored_name == reference[2], FileResource.storage_path == reference[3],
                        ).values(updated_at=FileResource.updated_at).execution_options(synchronize_session=False))
                        if retained.rowcount == 1:
                            restore_staged_file(staged)
                        else:
                            logger.warning("Material deletion outcome requires storage reconciliation")
                except Exception:
                    # Unknown DB/FS outcome: preserve the hidden stage for the
                    # existing quiescent reconciliation, never guess or purge.
                    logger.warning("Material deletion recovery requires reconciliation")
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="Не удалось подтвердить удаление. Проверьте список материалов.") from None
    try:
        finish_staged_deletion(staged)
    except OSError:
        logger.warning("Deleted material bytes require storage reconciliation")
        return True
    return False


def file_metadata(item: FileResource) -> dict:
    has_file = bool(item.stored_name and item.storage_path)
    target = safe_storage_file(item.storage_path) if has_file else None
    try:
        missing = has_file and (target is None or not target.is_file())
    except OSError:
        missing = has_file
    previewable = has_file and not missing and item.mime_type in PREVIEW_TYPES
    return {
        "id": item.id, "title": item.title, "kind": item.kind,
        "description": item.description, "original_name": item.original_name,
        "mime_type": item.mime_type or "application/octet-stream", "size": item.size,
        "has_file": has_file, "missing_file": missing, "previewable": previewable,
        "download_url": f"/api/files/{item.id}/download" if has_file else None,
        "preview_url": f"/api/files/{item.id}/preview" if previewable else None,
    }


class _ClosingFileResponse(StreamingResponse):
    def __init__(self, handle, *, media_type: str, headers: dict):
        self._handle = handle

        def chunks():
            while chunk := handle.read(64 * 1024):
                yield chunk

        super().__init__(chunks(), media_type=media_type, headers=headers)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._handle.close()


def download_response(item: FileResource, *, preview: bool = False):
    try:
        target = safe_storage_file(item.storage_path)
        if target is None or not target.is_file():
            raise HTTPException(status_code=404, detail="Файл отсутствует в хранилище")
        media_type = "application/octet-stream"
        if preview:
            media_type, previewable = inspect_file(target, item.original_name, item.mime_type)
            if not previewable:
                raise HTTPException(status_code=415, detail="Для этого формата доступно только скачивание")
        handle = target.open("rb")
    except FileStorageError as error:
        raise HTTPException(status_code=503 if error.status_code >= 500 else error.status_code, detail=error.detail) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл отсутствует в хранилище") from None
    except OSError:
        raise HTTPException(status_code=503, detail="Хранилище временно недоступно") from None
    try:
        headers = {
            "Content-Disposition": f"{'inline' if preview else 'attachment'}; filename*=UTF-8''{quote(item.original_name, safe='')}",
            "Content-Length": str(os.fstat(handle.fileno()).st_size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox; frame-ancestors 'none'",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Accept-Ranges": "none",
        }
        return _ClosingFileResponse(handle, media_type=media_type, headers=headers)
    except BaseException:
        handle.close()
        raise
