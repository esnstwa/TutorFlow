"""Offline storage audit: isolated SQLite and scratch files; use --noconftest."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import storage
from app.core.database import Base
from app.models import FileResource


@pytest.fixture
def audit_env(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    monkeypatch.setattr(storage.settings, "file_storage_path", str(root))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FileResource.__table__.create(engine)
    with Session(engine) as db:
        yield root, db
    engine.dispose()


def record(db, path, *, name=None):
    row = FileResource(owner_id=1, original_name="private.txt", title="private", size=7,
                       stored_name=name or Path(path).name, storage_path=str(path))
    db.add(row)
    db.commit()
    return row.id


def test_read_only_report_does_not_create_missing_root(audit_env):
    from app.material_storage_audit import audit_storage
    root, db = audit_env
    missing_id = record(db, root / f"{uuid4().hex}.txt")
    before = db.execute(select(FileResource.id)).all()
    report = audit_storage(db)
    assert report["missing_record_ids"] == [missing_id]
    assert report["root_exists"] is False
    assert report["errors"] == []
    assert not root.exists()
    assert db.execute(select(FileResource.id)).all() == before
    assert str(root) not in json.dumps(report)
    assert "private" not in json.dumps(report)


def test_inventory_classifies_managed_unmanaged_duplicate_and_external(audit_env):
    from app.material_storage_audit import audit_storage
    root, db = audit_env
    root.mkdir()
    live = root / f"{uuid4().hex}.txt"
    live.write_bytes(b"live")
    first = record(db, live)
    second = record(db, live)
    missing = record(db, root / f"{uuid4().hex}.pdf")
    unsafe = record(db, root.parent / "elsewhere" / f"{uuid4().hex}.txt")
    orphan = f"{uuid4().hex}.legacySuffix"
    upload = f".{uuid4().hex}.txt.uploading"
    stage = f".{uuid4().hex}.png.{uuid4().hex}.deleting"
    for name in (orphan, upload, stage, "do-not-touch.username.txt"):
        (root / name).write_bytes(b"bytes")
    (root / "folder").mkdir()
    db.add(FileResource(owner_id=1, title="link", original_name="link", size=0,
                        url="https://private.example/secret"))
    db.commit()
    before = {p.name: p.stat().st_mtime_ns for p in root.iterdir()}
    report = audit_storage(db)
    assert report["orphaned"] == [orphan]
    assert report["pending_uploads"] == [upload]
    assert report["staged_deletions"] == [stage]
    assert report["missing_record_ids"] == [missing]
    assert report["unsafe_record_ids"] == [unsafe]
    assert report["duplicate_references"] == [{"filename": live.name, "record_ids": [first, second]}]
    assert len(report["external_record_ids"]) == 1
    assert report["unmanaged_entry_count"] == 1
    assert report["unsafe_entry_count"] == 1
    assert {p.name: p.stat().st_mtime_ns for p in root.iterdir()} == before
    assert "username" not in json.dumps(report)
    assert "secret" not in json.dumps(report)


def test_metadata_only_records_are_not_storage_corruption(audit_env):
    from app.material_storage_audit import audit_storage

    root, db = audit_env
    note = FileResource(owner_id=1, original_name="Lesson notes", title="Notes", size=0)
    broken = FileResource(owner_id=1, original_name="lost.txt", title="Broken", size=4)
    db.add_all([note, broken])
    db.commit()
    report = audit_storage(db)
    assert report["unsafe_record_ids"] == [broken.id]
    assert report["metadata_record_ids"] == [note.id]
    assert report["missing_record_ids"] == []
    assert not root.exists()


def test_audit_never_autoflushes_pending_changes(audit_env):
    from app.material_storage_audit import audit_storage
    root, db = audit_env
    db.add(FileResource(owner_id=1, original_name="pending", title="pending", size=0))
    assert audit_storage(db)["unsafe_record_ids"] == []
    with db.no_autoflush:
        assert db.execute(select(FileResource.id)).all() == []


def aged_file(root, name, content=b"retained", hours=48):
    root.mkdir(exist_ok=True)
    path = root / name
    path.write_bytes(content)
    old = time.time() - hours * 3600
    os.utime(path, (old, old))
    return path


def test_offline_quarantine_retains_bytes_and_never_moves_live_files(audit_env):
    from app.material_storage_audit import reconcile_storage
    root, db = audit_env
    live = aged_file(root, f"{uuid4().hex}.txt", b"live")
    live_id = record(db, live)
    names = [f"{uuid4().hex}.unusual", f".{uuid4().hex}.txt.uploading",
             f".{uuid4().hex}.{uuid4().hex}.deleting"]
    for name in names:
        aged_file(root, name)
    recent = aged_file(root, f"{uuid4().hex}.txt", hours=1)
    unmanaged = aged_file(root, "human-file.txt")
    before = sorted(p.name for p in root.iterdir())
    assert reconcile_storage(db)["actions"] == []
    assert sorted(p.name for p in root.iterdir()) == before
    refused = reconcile_storage(db, apply=True)
    assert "quiescence_required" in refused["errors"]
    assert sorted(p.name for p in root.iterdir()) == before
    result = reconcile_storage(db, apply=True, quiescent=True, older_than_hours=24)
    assert result["errors"] == []
    assert len(result["actions"]) == 3
    for action in result["actions"]:
        assert action["action"] == "quarantine"
        assert action["source"] in names
        assert action["destination"].startswith(".quarantine.")
        assert (root / action["destination"]).read_bytes() == b"retained"
        assert not (root / action["source"]).exists()
    assert live.read_bytes() == b"live"
    assert recent.exists() and unmanaged.exists()
    assert db.execute(select(FileResource.id)).scalars().all() == [live_id]
    assert len(result["after"]["quarantined"]) == 3
    assert reconcile_storage(db, apply=True, quiescent=True)["actions"] == []


def test_restores_only_single_aged_staged_deletion_for_missing_record(audit_env):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    original = root / f"{uuid4().hex}.txt"
    row_id = record(db, original)
    stage = aged_file(root, f".{original.name}.{uuid4().hex}.deleting", b"restored")
    assert audit_storage(db)["missing_record_ids"] == [row_id]
    result = reconcile_storage(db, apply=True, quiescent=True)
    assert result["errors"] == []
    assert result["actions"] == [{"action": "restore", "source": stage.name,
                                   "destination": original.name}]
    assert original.read_bytes() == b"restored"
    assert not stage.exists()
    assert result["after"]["missing_record_ids"] == []
    assert db.get(FileResource, row_id).storage_path == str(original)


@pytest.mark.parametrize("duplicate_rows", [False, True])
def test_ambiguous_staged_deletion_requires_manual_attention(audit_env, duplicate_rows):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    original = root / f"{uuid4().hex}.txt"
    record(db, original)
    if duplicate_rows:
        record(db, original)
    aged_file(root, f".{original.name}.{uuid4().hex}.deleting")
    if not duplicate_rows:
        aged_file(root, f".{original.name}.{uuid4().hex}.deleting")
    before = sorted(p.name for p in root.iterdir())
    assert audit_storage(db)["manual_attention"]
    report = reconcile_storage(db, apply=True, quiescent=True)
    assert report["actions"] == []
    assert report["manual_attention"]
    assert sorted(p.name for p in root.iterdir()) == before


def test_referenced_temps_stages_and_recent_stage_are_never_quarantined(audit_env):
    from app.material_storage_audit import reconcile_storage
    root, db = audit_env
    live = aged_file(root, f"{uuid4().hex}.txt", b"live")
    record(db, live)
    aged_file(root, f".{live.name}.uploading")
    aged_file(root, f".{live.name}.{uuid4().hex}.deleting")
    missing = root / f"{uuid4().hex}.txt"
    record(db, missing)
    aged_file(root, f".{missing.name}.{uuid4().hex}.deleting", hours=1)
    before = sorted(p.name for p in root.iterdir())
    assert reconcile_storage(db, apply=True, quiescent=True)["actions"] == []
    assert sorted(p.name for p in root.iterdir()) == before


def run_cli(tmp_path, *args, database=None):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ, APP_ENV="test", PYTHONDONTWRITEBYTECODE="1",
               FILE_STORAGE_PATH=str(tmp_path / "uploads"),
               DATABASE_URL=f"sqlite+pysqlite:///{database or tmp_path / 'audit.sqlite'}")
    return subprocess.run([sys.executable, "-B", str(repo / "scripts/check_material_storage.py"), *args],
                          cwd=repo, env=env, capture_output=True, text=True, timeout=30)


def test_cli_real_sqlite_audit_apply_and_refuses_without_offline_flag(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'audit.sqlite'}")
    FileResource.__table__.create(engine)
    engine.dispose()
    original_db = (tmp_path / "audit.sqlite").read_bytes()
    orphan = aged_file(tmp_path / "uploads", f"{uuid4().hex}.txt", b"cli-bytes")
    audited = run_cli(tmp_path)
    assert audited.returncode == 0, audited.stderr
    assert json.loads(audited.stdout)["orphaned"] == [orphan.name]
    assert orphan.exists()
    refused = run_cli(tmp_path, "--apply")
    assert refused.returncode == 2
    assert orphan.exists()
    applied = run_cli(tmp_path, "--apply", "--quiescent", "--older-than-hours", "24")
    assert applied.returncode == 0, applied.stderr
    report = json.loads(applied.stdout)
    assert len(report["actions"]) == 1
    assert (orphan.parent / report["actions"][0]["destination"]).read_bytes() == b"cli-bytes"
    assert (tmp_path / "audit.sqlite").read_bytes() == original_db


@pytest.mark.parametrize("active", [False, True], ids=["closed", "active"])
@pytest.mark.parametrize("path_kind", ["path", "uri", "relative_uri", "localhost_uri"])
@pytest.mark.parametrize("args", [(), ("--apply", "--quiescent")], ids=["audit", "apply"])
def test_cli_refuses_wal_before_connect_without_changing_any_bytes(tmp_path, active, path_kind, args):
    from urllib.parse import quote

    database = tmp_path / "учёт material.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    connection = engine.connect()
    try:
        assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
        FileResource.__table__.create(connection)
        connection.commit()
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.commit()
        checkpointed = database.read_bytes()
        with Session(bind=connection) as db:
            db.add(FileResource(owner_id=1, original_name="private", title="private", size=0))
            db.commit()
        assert database.read_bytes() == checkpointed
        assert Path(f"{database}-wal").stat().st_size > 0
        # Confirm committed WAL data through a real read-only reader, and close
        # that engine before recording sidecar bytes (no mocked SQLite I/O).
        reader = create_engine(f"sqlite+pysqlite:///{database.as_uri()}?mode=ro&uri=true")
        try:
            with reader.connect() as readonly:
                assert readonly.execute(select(FileResource.id)).all() == [(1,)]
        finally:
            reader.dispose()
        if not active:
            connection.close()
            engine.dispose()
            assert sorted(p.name for p in tmp_path.iterdir()) == [database.name]
        assert database.read_bytes()[18:20] == b"\x02\x02"
        if path_kind == "uri":
            target = database.as_uri() + "?uri=true"
        elif path_kind == "relative_uri":
            repo = Path(__file__).resolve().parents[1]
            target = "file:" + quote(os.path.relpath(database, repo).replace(os.sep, "/"), safe="/:") + "?uri=true"
        elif path_kind == "localhost_uri":
            target = database.as_uri().replace("file://", "file://localhost", 1) + "?uri=true"
        else:
            target = database
        before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        result = run_cli(tmp_path, *args, database=target)
        after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
        assert after == before  # Includes DB, WAL, SHM and absence of storage root.
        assert result.returncode == 2, result.stdout + result.stderr
        assert json.loads(result.stdout) == {
            "mode": "apply" if args else "audit", "actions": [],
            "errors": ["sqlite_wal_unsupported"],
        }
        assert result.stderr == ""
        assert str(tmp_path) not in result.stdout
        assert "private" not in result.stdout
    finally:
        connection.close()
        engine.dispose()


@pytest.mark.parametrize("path_kind", ["uri", "relative_uri", "localhost_uri"])
def test_cli_rollback_journal_uri_remains_read_only(tmp_path, path_kind):
    from urllib.parse import quote

    database = tmp_path / "учёт material.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    try:
        FileResource.__table__.create(engine)
    finally:
        engine.dispose()
    assert database.read_bytes()[18:20] == b"\x01\x01"
    if path_kind == "relative_uri":
        repo = Path(__file__).resolve().parents[1]
        target = "file:" + quote(os.path.relpath(database, repo).replace(os.sep, "/"), safe="/:") + "?uri=true"
    elif path_kind == "localhost_uri":
        target = database.as_uri().replace("file://", "file://localhost", 1) + "?uri=true"
    else:
        target = database.as_uri() + "?uri=true"
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = run_cli(tmp_path, database=target)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["errors"] == []
    assert report["actions"] == []
    assert report["root_exists"] is False


def test_cli_missing_sqlite_database_and_root_are_not_created(tmp_path):
    result = run_cli(tmp_path)
    assert result.returncode == 2
    assert json.loads(result.stdout)["errors"]
    assert not (tmp_path / "audit.sqlite").exists()
    assert not (tmp_path / "uploads").exists()
    assert str(tmp_path) not in result.stdout + result.stderr


def test_unmanaged_record_is_reported_and_never_moved(audit_env):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    path = aged_file(root, "legacy-human-name.txt")
    row_id = record(db, path)
    assert audit_storage(db)["unmanaged_record_ids"] == [row_id]
    assert reconcile_storage(db, apply=True, quiescent=True)["actions"] == []
    assert path.read_bytes() == b"retained"


def test_quarantine_destination_referenced_by_db_is_never_used(audit_env, monkeypatch):
    from app import material_storage_audit as audit
    root, db = audit_env
    orphan = aged_file(root, f"{uuid4().hex}.txt")
    chosen = uuid4()
    destination = root / f".quarantine.{chosen.hex}"
    record(db, destination)
    monkeypatch.setattr(audit, "uuid4", lambda: chosen)
    report = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert report["actions"] == []
    assert orphan.exists()
    assert not destination.exists()


def test_rechecks_db_before_each_rename(audit_env, monkeypatch):
    from app import material_storage_audit as audit
    root, db = audit_env
    first = aged_file(root, "1" * 32 + ".txt")
    second = aged_file(root, "2" * 32 + ".txt")
    original = audit._rows
    calls = 0

    def fresh_rows(session):
        nonlocal calls
        calls += 1
        if calls == 3:  # Initial audit, first action, then second action.
            record(session, second)
        return original(session)

    monkeypatch.setattr(audit, "_rows", fresh_rows)
    result = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert result["errors"] == []
    assert len(result["actions"]) == 1
    assert result["actions"][0]["source"] == first.name
    assert second.read_bytes() == b"retained"
    assert calls >= 4  # Includes the read-back audit.


@pytest.mark.parametrize("fail_on", [1, 2])
def test_db_failure_stops_before_any_rename_without_secrets(audit_env, monkeypatch, fail_on):
    from app import material_storage_audit as audit
    from sqlalchemy.exc import SQLAlchemyError
    root, db = audit_env
    path = aged_file(root, f"{uuid4().hex}.txt")
    original = audit._rows
    calls = 0

    def broken(session):
        nonlocal calls
        calls += 1
        if calls >= fail_on:
            raise SQLAlchemyError(f"postgres://username:password@private {root}")
        return original(session)

    monkeypatch.setattr(audit, "_rows", broken)
    result = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert result["actions"] == []
    assert "database_unavailable" in result["errors"]
    assert path.read_bytes() == b"retained"
    assert "username" not in json.dumps(result)
    assert "password" not in json.dumps(result)
    assert str(root) not in json.dumps(result)


@pytest.mark.parametrize("restore", [False, True])
def test_rename_failure_preserves_source_bytes_and_db(audit_env, monkeypatch, restore):
    from app import material_storage_audit as audit
    root, db = audit_env
    base = f"{uuid4().hex}.txt"
    if restore:
        record(db, root / base)
        name = f".{base}.{uuid4().hex}.deleting"
    else:
        name = base
    source = aged_file(root, name)
    rows_before = db.execute(select(FileResource.id, FileResource.storage_path)).all()

    def denied(*args):
        raise PermissionError(f"private filesystem path {root}")

    monkeypatch.setattr(audit.os, "rename", denied)
    result = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert result["actions"] == []
    assert result["errors"] == ["reconciliation_stopped"]
    assert source.read_bytes() == b"retained"
    assert db.execute(select(FileResource.id, FileResource.storage_path)).all() == rows_before
    assert str(root) not in json.dumps(result)


def test_cross_root_and_mismatched_rows_protect_both_names(audit_env):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    local = aged_file(root, f"{uuid4().hex}.txt")
    other = aged_file(root, f"{uuid4().hex}.txt")
    cross_id = record(db, root.parent / "other" / local.name)
    mismatch_id = record(db, local, name=other.name)
    report = audit_storage(db)
    assert report["unsafe_record_ids"] == [cross_id, mismatch_id]
    assert reconcile_storage(db, apply=True, quiescent=True)["actions"] == []
    assert local.exists() and other.exists()


@pytest.mark.parametrize("hours", [0, -1, float("nan"), float("inf"), True, "24"])
def test_invalid_age_refuses_all_mutations(audit_env, hours):
    from app.material_storage_audit import reconcile_storage
    root, db = audit_env
    path = aged_file(root, f"{uuid4().hex}.txt")
    result = reconcile_storage(db, apply=True, quiescent=True, older_than_hours=hours)
    assert "invalid_age_threshold" in result["errors"]
    assert result["actions"] == []
    assert path.exists()


def test_bound_connection_transaction_and_pending_orm_state_are_preserved(audit_env):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    path = aged_file(root, f"{uuid4().hex}.txt")
    with db.get_bind().connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as bound:
            assert audit_storage(bound)["orphaned"] == [path.name]
            bound.add(FileResource(owner_id=1, title="pending", original_name="pending", size=0))
            result = reconcile_storage(bound, apply=True, quiescent=True)
            assert "pending_session_changes" in result["errors"]
            assert result["actions"] == []
            assert transaction.is_active
        transaction.rollback()
    assert path.exists()


@pytest.mark.parametrize("root_kind", ["static", "traversal"])
def test_unsafe_root_is_rejected_without_creating_it(audit_env, monkeypatch, root_kind):
    from app import material_storage_audit as audit
    root, db = audit_env
    candidate = storage._PUBLIC_STATIC_ROOT / "never-create" if root_kind == "static" else root / ".." / "never-create"
    monkeypatch.setattr(storage.settings, "file_storage_path", str(candidate))
    report = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert report["errors"] == ["unsafe_storage_root"]
    assert report["actions"] == []
    assert not candidate.exists()


def test_symlink_entries_and_symlink_root_are_never_followed(audit_env, monkeypatch):
    from app import material_storage_audit as audit
    root, db = audit_env
    root.mkdir()
    outside = root.parent / "private.txt"
    outside.write_bytes(b"outside")
    link = root / f"{uuid4().hex}.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"OS disallows symlink creation: {type(error).__name__}")
    row_id = record(db, link)
    report = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert report["actions"] == []
    assert report["unsafe_record_ids"] == [row_id]
    assert report["unsafe_entry_count"] == 1
    assert outside.read_bytes() == b"outside" and link.is_symlink()
    linked_root = root.parent / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    monkeypatch.setattr(storage.settings, "file_storage_path", str(linked_root))
    assert audit.audit_storage(db)["errors"] == ["unsafe_storage_root"]


def test_windows_junction_root_is_rejected(audit_env, monkeypatch):
    from app.material_storage_audit import audit_storage
    if os.name != "nt":
        pytest.skip("Windows junction check")
    root, db = audit_env
    root.mkdir()
    link = root.parent / "junction"
    created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(root)],
                             capture_output=True, timeout=10)
    if created.returncode:
        pytest.skip("OS disallows junction creation")
    monkeypatch.setattr(storage.settings, "file_storage_path", str(link))
    assert audit_storage(db)["errors"] == ["unsafe_storage_root"]


def test_legacy_suffix_case_is_preserved_in_reports_and_restore(audit_env):
    from app.material_storage_audit import audit_storage, reconcile_storage
    root, db = audit_env
    base = f"{uuid4().hex}.LEGaCy"
    row_id = record(db, root / base)
    stage = aged_file(root, f".{base}.{uuid4().hex}.deleting")
    assert audit_storage(db)["manual_attention"] == []
    result = reconcile_storage(db, apply=True, quiescent=True)
    assert result["actions"] == [{"action": "restore", "source": stage.name, "destination": base}]
    record(db, root / base)
    assert audit_storage(db)["duplicate_references"] == [{"filename": base, "record_ids": [row_id, row_id + 1]}]


def test_multiple_unreferenced_stages_are_left_for_manual_review(audit_env):
    from app.material_storage_audit import reconcile_storage
    root, db = audit_env
    base = f"{uuid4().hex}.txt"
    first = aged_file(root, f".{base}.{uuid4().hex}.deleting")
    second = aged_file(root, f".{base}.{uuid4().hex}.deleting")
    result = reconcile_storage(db, apply=True, quiescent=True)
    assert result["actions"] == []
    assert result["manual_attention"][0]["reason"] == "ambiguous_staged_deletion"
    assert first.exists() and second.exists()


def test_directory_candidate_makes_staged_restore_ambiguous(audit_env):
    from app.material_storage_audit import reconcile_storage
    root, db = audit_env
    base = f"{uuid4().hex}.txt"
    record(db, root / base)
    stage = aged_file(root, f".{base}.{uuid4().hex}.deleting")
    (root / f".{base}.{uuid4().hex}.deleting").mkdir()
    result = reconcile_storage(db, apply=True, quiescent=True)
    assert result["actions"] == []
    assert result["manual_attention"][0]["reason"] == "ambiguous_staged_deletion"
    assert stage.exists() and not (root / base).exists()


def test_filesystem_failure_after_first_rename_keeps_both_payloads(audit_env, monkeypatch):
    from app import material_storage_audit as audit
    root, db = audit_env
    first = aged_file(root, "1" * 32 + ".txt", b"first")
    second = aged_file(root, "2" * 32 + ".txt", b"second")
    rename = audit.os.rename
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("do not expose private paths")
        return rename(*args)

    monkeypatch.setattr(audit.os, "rename", fail_second)
    report = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert len(report["actions"]) == 1
    assert report["errors"] == ["reconciliation_stopped"]
    assert (root / report["actions"][0]["destination"]).read_bytes() == b"first"
    assert not first.exists() and second.read_bytes() == b"second"
    assert report["after"]["orphaned"] == [second.name]


def test_changed_source_is_not_moved(audit_env, monkeypatch):
    from app import material_storage_audit as audit
    root, db = audit_env
    source = aged_file(root, f"{uuid4().hex}.txt")
    original = audit._rows
    calls = 0

    def alter_before_action(session):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.write_bytes(b"changed since inventory")
        return original(session)

    monkeypatch.setattr(audit, "_rows", alter_before_action)
    result = audit.reconcile_storage(db, apply=True, quiescent=True)
    assert result["errors"] == ["reconciliation_stopped"]
    assert result["actions"] == []
    assert source.read_bytes() == b"changed since inventory"


@pytest.mark.parametrize("hours", ["0", "-1", "nan", "inf", "not-number"])
def test_cli_invalid_hours_refuses_before_touching_db(tmp_path, hours):
    result = run_cli(tmp_path, "--apply", "--quiescent", "--older-than-hours", hours)
    assert result.returncode == 2
    assert not (tmp_path / "audit.sqlite").exists()
    assert not (tmp_path / "uploads").exists()


def test_cli_cleanup_errors_preserve_completed_action_report(audit_env, monkeypatch, capsys):
    import importlib.util
    import sqlalchemy
    import sqlalchemy.orm
    from sqlalchemy.exc import SQLAlchemyError
    root, db = audit_env
    source = aged_file(root, f"{uuid4().hex}.txt")
    script = Path(__file__).resolve().parents[1] / "scripts/check_material_storage.py"
    spec = importlib.util.spec_from_file_location("material_audit_cli_test", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    engine = db.get_bind()
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *args, **kwargs: engine)

    class CloseFailureSession(Session):
        def close(self):
            super().close()
            raise SQLAlchemyError("private database URL and password")

    monkeypatch.setattr(sqlalchemy.orm, "Session", CloseFailureSession)
    code = cli.main(["--apply", "--quiescent"])
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert code == 2
    assert len(report["actions"]) == 1
    assert (root / report["actions"][0]["destination"]).read_bytes() == b"retained"
    assert not source.exists()
    assert "private" not in output.out + output.err
