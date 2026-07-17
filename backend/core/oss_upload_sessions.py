"""Persistent metadata for the disabled-by-default OSS multipart upload flow."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.runtime_paths import default_oss_upload_session_db_path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS oss_upload_sessions (
    session_id TEXT PRIMARY KEY,
    owner_scope TEXT NOT NULL,
    object_key TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    content_type TEXT,
    content_length INTEGER NOT NULL,
    part_size_bytes INTEGER NOT NULL,
    upload_id TEXT,
    task_id TEXT,
    status TEXT NOT NULL,
    error_reason TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    completed_at REAL,
    aborted_at REAL
);
CREATE INDEX IF NOT EXISTS idx_oss_upload_sessions_owner_status
    ON oss_upload_sessions(owner_scope, status, expires_at);
"""

class OssUploadSessionCapacityError(RuntimeError):
    """Raised when an owner already has the allowed number of open sessions."""


def _db_path(db_path: Path | str | None) -> Path:
    return Path(db_path) if db_path else default_oss_upload_session_db_path()


def _timestamp_to_iso(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "owner_scope": row["owner_scope"],
        "object_key": row["object_key"],
        "source_filename": row["source_filename"],
        "content_type": row["content_type"],
        "content_length": int(row["content_length"]),
        "part_size_bytes": int(row["part_size_bytes"]),
        "upload_id": row["upload_id"],
        "task_id": row["task_id"],
        "status": row["status"],
        "error_reason": row["error_reason"],
        "created_at": _timestamp_to_iso(row["created_at"]),
        "updated_at": _timestamp_to_iso(row["updated_at"]),
        "expires_at": _timestamp_to_iso(row["expires_at"]),
        "completed_at": _timestamp_to_iso(row["completed_at"]),
        "aborted_at": _timestamp_to_iso(row["aborted_at"]),
        "expired": float(row["expires_at"]) <= time.time(),
    }


def ensure_oss_upload_session_db(db_path: Path | str | None = None) -> None:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(oss_upload_sessions)").fetchall()}
        if "task_id" not in columns:
            conn.execute("ALTER TABLE oss_upload_sessions ADD COLUMN task_id TEXT")


def _expire_open_sessions(conn: sqlite3.Connection, now: float) -> None:
    conn.execute(
        """
        UPDATE oss_upload_sessions
        SET status = 'expired', updated_at = ?
        WHERE status IN ('creating', 'initiated') AND expires_at <= ?
        """,
        (now, now),
    )


def reserve_oss_upload_session(
    *,
    session_id: str,
    owner_scope: str,
    object_key: str,
    source_filename: str,
    content_type: str | None,
    content_length: int,
    part_size_bytes: int,
    expires_at: float,
    max_open_sessions: int,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Reserve capacity before initiating an OSS multipart upload."""

    ensure_oss_upload_session_db(db_path)
    path = _db_path(db_path)
    now = time.time()
    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        _expire_open_sessions(conn, now)
        active_count = conn.execute(
            """
            SELECT COUNT(*) FROM oss_upload_sessions
            WHERE owner_scope = ? AND status IN ('creating', 'initiated') AND expires_at > ?
            """,
            (owner_scope, now),
        ).fetchone()[0]
        if int(active_count) >= max_open_sessions:
            raise OssUploadSessionCapacityError("too_many_open_upload_sessions")
        conn.execute(
            """
            INSERT INTO oss_upload_sessions (
                session_id, owner_scope, object_key, source_filename, content_type,
                content_length, part_size_bytes, status, created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'creating', ?, ?, ?)
            """,
            (
                session_id,
                owner_scope,
                object_key,
                source_filename,
                content_type,
                content_length,
                part_size_bytes,
                now,
                now,
                expires_at,
            ),
        )
        row = conn.execute("SELECT * FROM oss_upload_sessions WHERE session_id = ?", (session_id,)).fetchone()
    return _row_to_dict(row)


def get_oss_upload_session(
    session_id: str,
    *,
    owner_scope: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    ensure_oss_upload_session_db(db_path)
    path = _db_path(db_path)
    now = time.time()
    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        _expire_open_sessions(conn, now)
        row = conn.execute(
            "SELECT * FROM oss_upload_sessions WHERE session_id = ? AND owner_scope = ?",
            (session_id, owner_scope),
        ).fetchone()
    return _row_to_dict(row) if row else None


def activate_oss_upload_session(
    session_id: str,
    *,
    upload_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    return _update_oss_upload_session(session_id, status="initiated", upload_id=upload_id, db_path=db_path)


def fail_oss_upload_session(
    session_id: str,
    *,
    reason: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    return _update_oss_upload_session(session_id, status="failed", error_reason=reason, db_path=db_path)


def complete_oss_upload_session(
    session_id: str,
    *,
    task_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    return _update_oss_upload_session(
        session_id,
        status="completed",
        task_id=task_id,
        completed_at=time.time(),
        db_path=db_path,
    )


def abort_oss_upload_session(session_id: str, *, db_path: Path | str | None = None) -> dict[str, Any] | None:
    return _update_oss_upload_session(session_id, status="aborted", aborted_at=time.time(), db_path=db_path)


def _update_oss_upload_session(
    session_id: str,
    *,
    status: str,
    upload_id: str | None = None,
    task_id: str | None = None,
    error_reason: str | None = None,
    completed_at: float | None = None,
    aborted_at: float | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    ensure_oss_upload_session_db(db_path)
    path = _db_path(db_path)
    now = time.time()
    with sqlite3.connect(path, timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            UPDATE oss_upload_sessions
            SET status = ?, upload_id = COALESCE(?, upload_id), task_id = COALESCE(?, task_id),
                error_reason = COALESCE(?, error_reason),
                completed_at = COALESCE(?, completed_at), aborted_at = COALESCE(?, aborted_at), updated_at = ?
            WHERE session_id = ?
            """,
            (status, upload_id, task_id, error_reason, completed_at, aborted_at, now, session_id),
        )
        row = conn.execute("SELECT * FROM oss_upload_sessions WHERE session_id = ?", (session_id,)).fetchone()
    return _row_to_dict(row) if row else None


__all__ = [
    "OssUploadSessionCapacityError",
    "abort_oss_upload_session",
    "activate_oss_upload_session",
    "complete_oss_upload_session",
    "fail_oss_upload_session",
    "get_oss_upload_session",
    "reserve_oss_upload_session",
]
