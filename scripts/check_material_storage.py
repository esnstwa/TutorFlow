#!/usr/bin/env python
"""Audit storage; offline recovery only with --apply --quiescent.

Uses the existing DATABASE_URL and FILE_STORAGE_PATH settings. Exit 0 means
inspection/reconciliation completed (findings may remain); exit 2 means refused
or failed. No schema creation, file purge, or DB writes are performed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

# Direct script invocation works from the repository checkout without installs.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _hours(value: str) -> float:
    try:
        hours = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("hours must be a positive finite number") from None
    if not math.isfinite(hours) or hours <= 0:
        raise argparse.ArgumentTypeError("hours must be a positive finite number")
    return hours


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Permit non-destructive recovery renames")
    parser.add_argument("--quiescent", action="store_true",
                        help="Assert all application writers and other reconcilers are stopped")
    parser.add_argument("--older-than-hours", type=_hours, default=24,
                        help="Minimum file mtime age for recovery (default: 24)")
    args = parser.parse_args(argv)
    if args.apply and not args.quiescent:
        parser.error("--apply requires --quiescent; stop all writers before recovery")
    engine = None
    report = {"mode": "apply" if args.apply else "audit", "actions": [], "errors": []}
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        from sqlalchemy.orm import Session

        from app.core.config import settings

        url = make_url(settings.database_url)
        # SQLite must not create a missing DB even for a read-only audit. Force
        # read-only URI connections; reconciliation never needs writable SQL.
        if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
            database = url.database
            if not database.startswith("file:"):
                database = Path(database).absolute().as_uri()
            # mode=ro can still create/modify WAL/SHM sidecars. Inspect the
            # actual local file header without opening a SQLite connection.
            # Decode the SQLAlchemy-parsed file URI exactly once, as SQLite
            # does; url2pathname also handles Windows drive-letter paths.
            location = urlsplit(database)
            if location.netloc not in ("", "localhost"):
                raise ValueError("unsupported SQLite URI authority")
            source = Path(url2pathname(location.path)).resolve(strict=True)
            with source.open("rb") as stream:
                header = stream.read(100)
            if len(header) != 100 or header[:16] != b"SQLite format 3\x00":
                raise ValueError("invalid SQLite header")
            if 2 in header[18:20]:  # File-format write/read versions: WAL.
                report["errors"].append("sqlite_wal_unsupported")
            url = url.set(database=database, query={**url.query, "mode": "ro", "uri": "true"})
        if not report["errors"]:
            from app.material_storage_audit import reconcile_storage

            engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
            with Session(engine, autoflush=False, expire_on_commit=False) as db:
                report = reconcile_storage(db, apply=args.apply, quiescent=args.quiescent,
                                           older_than_hours=args.older_than_hours)
    except Exception:
        # Driver/settings errors can contain credentials or paths. Preserve any
        # completed renames even if session cleanup fails after reconciliation.
        report["errors"].append("audit_unavailable")
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                report["errors"].append("database_cleanup_failed")
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
