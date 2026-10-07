from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def storage_root() -> Path:
    root = Path(settings.file_storage_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_bytes(original_name: str, content: bytes) -> tuple[str, str]:
    suffix = Path(original_name).suffix[:16]
    stored_name = f"{uuid4().hex}{suffix}"
    root = storage_root()
    final_path = root / stored_name
    temporary_path = root / f".{stored_name}.uploading"
    try:
        temporary_path.write_bytes(content)
        os.replace(temporary_path, final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    return stored_name, str(final_path)


def safe_storage_file(path: str | None) -> Path | None:
    if not path:
        return None
    root = storage_root()
    target = Path(path).resolve()
    return target if target.is_relative_to(root) else None


def stage_deletion(path: str | None) -> tuple[Path, Path] | None:
    target = safe_storage_file(path)
    if not target or not target.is_file():
        return None
    staged = target.with_name(f".{target.name}.{uuid4().hex}.deleting")
    os.replace(target, staged)
    return target, staged


def restore_staged_file(staged: tuple[Path, Path] | None) -> None:
    if staged and staged[1].exists():
        os.replace(staged[1], staged[0])


def finish_staged_deletion(staged: tuple[Path, Path] | None) -> None:
    if staged:
        staged[1].unlink(missing_ok=True)
