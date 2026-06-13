"""SQLite-backed task and result persistence for FluentFlow."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = Path(os.environ.get("FLUENTFLOW_JOB_DB_PATH") or PROJECT_ROOT / "data" / "fluentflow_jobs.sqlite").expanduser()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    task_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    client_id TEXT,
    stage TEXT,
    progress REAL,
    source_type TEXT,
    source_filename TEXT,
    source_file_size_mb REAL,
    summary_status TEXT,
    error_reason TEXT,
    result_json TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def ensure_job_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "client_id" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN client_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_client_updated_at ON jobs(client_id, updated_at)")


def upsert_job(
    *,
    task_id: str,
    status: str,
    client_id: str | None = None,
    stage: str | None = None,
    progress: float | None = None,
    source_type: str | None = None,
    source_filename: str | None = None,
    source_file_size_mb: float | None = None,
    summary_status: str | None = None,
    error_reason: str | None = None,
    result: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    if not task_id:
        return
    try:
        ensure_job_db(db_path)
        now = _now_iso()
        with sqlite3.connect(Path(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    task_id, created_at, updated_at, status, client_id, stage, progress,
                    source_type, source_filename, source_file_size_mb, summary_status,
                    error_reason, result_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    client_id=COALESCE(excluded.client_id, jobs.client_id),
                    stage=COALESCE(excluded.stage, jobs.stage),
                    progress=COALESCE(excluded.progress, jobs.progress),
                    source_type=COALESCE(excluded.source_type, jobs.source_type),
                    source_filename=COALESCE(excluded.source_filename, jobs.source_filename),
                    source_file_size_mb=COALESCE(excluded.source_file_size_mb, jobs.source_file_size_mb),
                    summary_status=COALESCE(excluded.summary_status, jobs.summary_status),
                    error_reason=COALESCE(excluded.error_reason, jobs.error_reason),
                    result_json=COALESCE(excluded.result_json, jobs.result_json),
                    metadata_json=COALESCE(excluded.metadata_json, jobs.metadata_json)
                """,
                (
                    task_id,
                    now,
                    now,
                    status,
                    client_id,
                    stage,
                    progress,
                    source_type,
                    source_filename,
                    source_file_size_mb,
                    summary_status,
                    error_reason,
                    _json_dumps(result),
                    _json_dumps(metadata),
                ),
            )
    except Exception as exc:  # pragma: no cover - persistence must not break processing
        logger.warning("Job store update failed for %s: %s", task_id, exc)


def get_job(
    task_id: str,
    db_path: Path | str = DEFAULT_DB_PATH,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    ensure_job_db(db_path)
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if client_id is not None:
            row = conn.execute(
                "SELECT * FROM jobs WHERE task_id = ? AND client_id = ?",
                (task_id, client_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_jobs(
    limit: int = 50,
    db_path: Path | str = DEFAULT_DB_PATH,
    client_id: str | None = None,
) -> list[dict[str, Any]]:
    ensure_job_db(db_path)
    safe_limit = max(1, min(int(limit or 50), 200))
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if client_id is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE client_id = ? ORDER BY updated_at DESC LIMIT ?",
                (client_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_jobs_for_retention(
    db_path: Path | str = DEFAULT_DB_PATH,
    client_id: str | None = None,
) -> list[dict[str, Any]]:
    ensure_job_db(db_path)
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if client_id is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE client_id = ? ORDER BY updated_at DESC",
                (client_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
    return [_row_to_dict(row) for row in rows]


def update_job_result(
    task_id: str,
    result: dict[str, Any],
    db_path: Path | str = DEFAULT_DB_PATH,
    client_id: str | None = None,
) -> dict[str, Any] | None:
    if not task_id:
        return None
    ensure_job_db(db_path)
    now = _now_iso()
    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if client_id is not None:
            row = conn.execute(
                "SELECT * FROM jobs WHERE task_id = ? AND client_id = ?",
                (task_id, client_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE jobs SET updated_at = ?, result_json = ? WHERE task_id = ?",
            (now, _json_dumps(result), task_id),
        )
        updated = conn.execute("SELECT * FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
    return _row_to_dict(updated) if updated else None


def delete_jobs(
    task_ids: list[str] | tuple[str, ...],
    db_path: Path | str = DEFAULT_DB_PATH,
    client_id: str | None = None,
) -> int:
    ids = [str(task_id).strip() for task_id in task_ids if str(task_id).strip()]
    if not ids:
        return 0
    ensure_job_db(db_path)
    placeholders = ",".join("?" for _ in ids)
    params: list[Any] = list(ids)
    where = f"task_id IN ({placeholders})"
    if client_id is not None:
        where += " AND client_id = ?"
        params.append(client_id)
    with sqlite3.connect(Path(db_path)) as conn:
        cursor = conn.execute(f"DELETE FROM jobs WHERE {where}", params)
        return int(cursor.rowcount or 0)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
        "client_id": row["client_id"],
        "stage": row["stage"],
        "progress": row["progress"],
        "source_type": row["source_type"],
        "source_filename": row["source_filename"],
        "source_file_size_mb": row["source_file_size_mb"],
        "summary_status": row["summary_status"],
        "error_reason": row["error_reason"],
        "result": _json_loads(row["result_json"]),
        "metadata": _json_loads(row["metadata_json"]),
    }
