from __future__ import annotations

from threading import Lock
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.models import WebLeadSubmission

_lock = Lock()
_initialized = False
_backup_engine = None
_BackupSessionLocal: sessionmaker[Session] | None = None


def _ensure_backup_sessionmaker() -> sessionmaker[Session] | None:
    """
    Lazily initialize backup DB engine/session for web-form mirroring.
    """

    global _initialized, _backup_engine, _BackupSessionLocal
    if _initialized:
        return _BackupSessionLocal

    with _lock:
        if _initialized:
            return _BackupSessionLocal

        if not settings.forms_backup_enabled:
            _initialized = True
            return None

        backup_url = (settings.forms_backup_database_url or "").strip()
        primary_url = settings.sqlalchemy_database_url.strip()
        if not backup_url or backup_url == primary_url:
            _initialized = True
            return None

        connect_args = {"check_same_thread": False} if backup_url.startswith("sqlite") else {}
        _backup_engine = create_engine(backup_url, future=True, pool_pre_ping=True, connect_args=connect_args)

        # Only materialize the table needed for mirrored lead submissions.
        Base.metadata.create_all(bind=_backup_engine, tables=[WebLeadSubmission.__table__])

        _BackupSessionLocal = sessionmaker(bind=_backup_engine, autoflush=False, autocommit=False, future=True)
        _initialized = True
        return _BackupSessionLocal


def mirror_web_form_submission(payload: dict[str, Any]) -> bool:
    """
    Best-effort mirror of a web lead submission into the configured local backup DB.

    Returns True when mirrored successfully; False when backup is disabled/unavailable
    or when the mirror write fails.
    """

    backup_sessionmaker = _ensure_backup_sessionmaker()
    if backup_sessionmaker is None:
        return False

    try:
        with backup_sessionmaker() as db:
            row = WebLeadSubmission(**payload)
            db.add(row)
            db.commit()
        return True
    except Exception:
        return False
