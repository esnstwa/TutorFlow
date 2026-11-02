"""Read-only storage inventory and explicitly offline, non-destructive recovery.

No startup hooks, schema writes, permanent deletion, or storage_root() calls.
Reports contain record IDs and managed filenames, never configured paths or URLs.
"""
from __future__ import annotations

import math
import os
import re
import stat
import time
from uuid import uuid4
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import storage
from app.models import FileResource


def _root() -> Path:
    root = Path(storage.settings.file_storage_path).absolute()
    if ".." in root.parts:
        raise ValueError("unsafe_root")
    for part in (root, *root.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or part.is_junction():
            raise ValueError("unsafe_root")
    public = storage._PUBLIC_STATIC_ROOT.resolve()
    if root.is_relative_to(public) or public.is_relative_to(root):
        raise ValueError("unsafe_root")
    if root.exists() and not root.is_dir():
        raise ValueError("unsafe_root")
    return root


def _rows(db: Session):
    # Scalar column reads bypass the ORM identity map; never flush pending work.
    with db.no_autoflush:
        return db.execute(select(FileResource.id, FileResource.stored_name,
                                 FileResource.storage_path, FileResource.url, FileResource.size)).all()


def _record_name(row, root: Path) -> str | None:
    if not row.storage_path:
        return None
    target = Path(row.storage_path)
    storage.validate_filename(target.name)
    if ".." in target.parts or target.absolute().parent != root or row.stored_name != target.name:
        raise ValueError("unsafe_record")
    return target.name


def _managed(name: str) -> bool:
    if not re.fullmatch(r"[0-9a-f]{32}(?:\.[^.]{1,15})?", name):
        return False
    try:
        storage.validate_filename(name)
    except storage.FileStorageError:
        return False
    return True


def _kind(name: str) -> tuple[str, str] | None:
    if _managed(name):
        return "orphaned", name
    if name.startswith(".") and name.endswith(".uploading") and _managed(name[1:-10]):
        return "pending_uploads", name[1:-10]
    if name.startswith(".") and name.endswith(".deleting"):
        parts = name[1:-9].rsplit(".", 1)
        if len(parts) == 2 and _managed(parts[0]) and re.fullmatch(r"[0-9a-f]{32}", parts[1]):
            return "staged_deletions", parts[0]
    if re.fullmatch(r"\.quarantine\.[0-9a-f]{32}", name):
        return "quarantined", name
    return None


def _references(rows) -> dict[str, set[int]]:
    # Even malformed/cross-root rows conservatively protect matching leaf names.
    references = defaultdict(set)
    for row in rows:
        for name in (row.stored_name, Path(row.storage_path).name if row.storage_path else None):
            if name:
                references[name.casefold()].add(row.id)
    return references


def _entries(root: Path) -> dict[str, tuple[os.stat_result, tuple[str, str] | None]]:
    entries = {}
    if not root.exists():
        return entries
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        info = path.lstat()
        safe = stat.S_ISREG(info.st_mode) and not path.is_junction()
        entries[path.name] = (info, _kind(path.name) if safe else None)
    return entries


def _stage_groups(entries) -> dict[str, list[str]]:
    groups = defaultdict(list)
    # Count even unsafe directory/link candidates: never choose around one.
    for name in entries:
        kind = _kind(name)
        if kind and kind[0] == "staged_deletions":
            groups[kind[1].casefold()].append(name)
    return groups


def _stage_decision(base: str, root: Path, rows, references, entries) -> tuple[str | None, str | None]:
    candidates = _stage_groups(entries).get(base.casefold(), [])
    if len(candidates) != 1:
        return None, "ambiguous_staged_deletion"
    ids = references.get(base.casefold(), set())
    if len(ids) > 1:
        return None, "ambiguous_database_references"
    if not ids or _present(root / base):
        return None, None
    candidate = candidates[0]
    if references.get(candidate.casefold()):
        return None, "referenced_staged_file"
    info, kind = entries[candidate]
    if not kind or not stat.S_ISREG(info.st_mode):
        return None, "unsafe_staged_deletion"
    row = next(row for row in rows if row.id in ids)
    try:
        if _record_name(row, root) != base:
            return None, "unsafe_staged_reference"
    except (ValueError, storage.FileStorageError):
        return None, "unsafe_staged_reference"
    return base, None


def audit_storage(db: Session) -> dict:
    """Inspect configured storage without creating roots or mutating DB/files."""
    report = {"root_exists": False, "missing_record_ids": [], "unsafe_record_ids": [],
              "external_record_ids": [], "metadata_record_ids": [], "orphaned": [], "pending_uploads": [],
              "staged_deletions": [], "duplicate_references": [], "manual_attention": [],
              "unmanaged_entry_count": 0, "unsafe_entry_count": 0, "quarantined": [],
              "unmanaged_record_ids": [], "errors": []}
    try:
        root = _root()
        report["root_exists"] = root.exists()
        rows = _rows(db)
        references = _references(rows)
        entries = _entries(root)
        for base, candidates in sorted(_stage_groups(entries).items()):
            parsed = _kind(candidates[0])
            assert parsed is not None
            _, reason = _stage_decision(parsed[1], root, rows, references, entries)
            if reason:
                report["manual_attention"].append({"reason": reason, "filenames": candidates,
                                                   "record_ids": sorted(references.get(base, set()))})
        for name, (info, kind) in entries.items():
            if not stat.S_ISREG(info.st_mode) or (root / name).is_junction():
                report["unsafe_entry_count"] += 1
            elif not kind:
                report["unmanaged_entry_count"] += 1
            elif kind[0] != "orphaned" or name.casefold() not in references:
                report[kind[0]].append(name)
        for name, ids in sorted(references.items()):
            if len(ids) > 1:
                duplicate: dict = {"record_ids": sorted(ids)}
                actual = next((candidate for row in rows
                               for candidate in (row.stored_name, Path(row.storage_path).name if row.storage_path else None)
                               if candidate and candidate.casefold() == name and _managed(candidate)), None)
                if actual:
                    duplicate["filename"] = actual
                report["duplicate_references"].append(duplicate)
        for row in rows:
            if not row.storage_path and row.url:
                report["external_record_ids"].append(row.id)
                continue
            if not row.storage_path and not row.stored_name and row.size == 0:
                report["metadata_record_ids"].append(row.id)
                continue
            try:
                name = _record_name(row, root)
                if not name:
                    raise ValueError("unsafe_record")
                if not _managed(name):
                    report["unmanaged_record_ids"].append(row.id)
                target = root / name
                if target.is_symlink() or target.is_junction() or (target.exists() and not target.is_file()):
                    raise ValueError("unsafe_record")
                if not target.exists():
                    report["missing_record_ids"].append(row.id)
            except (ValueError, storage.FileStorageError):
                report["unsafe_record_ids"].append(row.id)
    except SQLAlchemyError:
        report["errors"].append("database_unavailable")
    except ValueError:
        report["errors"].append("unsafe_storage_root")
    except OSError:
        report["errors"].append("filesystem_unavailable")
    for key in ("missing_record_ids", "unsafe_record_ids", "external_record_ids", "metadata_record_ids"):
        report[key].sort()
    return report


def _present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _identity(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns


def _move(root: Path, source: str, destination: str, info: os.stat_result, actions: list,
          *, action: str = "quarantine") -> None:
    target = root / destination
    if _present(target):
        raise OSError("destination_exists")
    os.rename(root / source, target)  # Same directory/volume; bytes are never deleted.
    actions.append({"action": action, "source": source, "destination": destination})
    if _present(root / source) or _identity(target.lstat()) != _identity(info):
        raise OSError("rename_verification_failed")


def reconcile_storage(db: Session, *, apply: bool = False, quiescent: bool = False,
                      older_than_hours: float = 24) -> dict:
    """Audit by default; --apply AND an offline/quiescent assertion permit renames.

    Age uses file mtime. The caller must stop all writers (including student
    uploads) and other reconcilers; this function cannot enforce that externally.
    Existing transactions/connections are respected; DB rows are never changed.
    """
    report = audit_storage(db)
    report.update(mode="apply" if apply else "audit", actions=[])
    if not apply:
        return report
    if not quiescent:
        report["errors"].append("quiescence_required")
    if (isinstance(older_than_hours, bool) or not isinstance(older_than_hours, (int, float))
            or not math.isfinite(older_than_hours) or older_than_hours <= 0):
        report["errors"].append("invalid_age_threshold")
    if db.new or db.dirty or db.deleted:
        report["errors"].append("pending_session_changes")
    if report["errors"]:
        return report
    try:
        root = _root()
        cutoff = time.time() - older_than_hours * 3600
        for name, (initial, kind) in _entries(root).items():
            if not kind or kind[0] == "quarantined" or initial.st_mtime > cutoff:
                continue
            if _root() != root:
                raise ValueError("root_changed")
            rows = _rows(db)  # Fresh DB SELECT before EVERY action.
            references = _references(rows)
            destination = None
            action = "quarantine"
            if kind[0] == "staged_deletions":
                destination, reason = _stage_decision(kind[1], root, rows, references, _entries(root))
                if reason:
                    continue
                if destination:
                    action = "restore"
            if name.casefold() in references:
                continue
            if not destination and kind[1].casefold() in references:
                continue
            source = root / name
            current = source.lstat()
            if (source.is_junction() or not stat.S_ISREG(current.st_mode)
                    or _identity(initial) != _identity(current) or current.st_mtime > cutoff):
                raise OSError("source_changed")
            destination = destination or f".quarantine.{uuid4().hex}"
            if action == "quarantine" and destination.casefold() in references:
                raise OSError("destination_referenced")
            _move(root, name, destination, current, report["actions"], action=action)
    except SQLAlchemyError:
        report["errors"].append("database_unavailable")
    except (OSError, ValueError):
        report["errors"].append("reconciliation_stopped")
    report["after"] = audit_storage(db)
    if report["after"]["errors"] and not report["errors"]:
        report["errors"].append("post_audit_failed")
    return report
