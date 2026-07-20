"""Persistence and projection for desktop-local task result synchronization."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.core import job_store
from backend.core.runtime_paths import default_job_db_path


SYNC_RESULT_RETENTION_DAYS = 7
VALID_SYNC_STATUSES = frozenset({"queued", "running", "completed", "failed", "cancelled"})
FORBIDDEN_SYNC_KEYS = frozenset({
    "artifacts",
    "artifact_url",
    "local_path",
    "playback_audio_url",
    "source_file_storage",
    "source_path",
    "source_url",
    "video_url",
})


class DesktopSyncError(ValueError):
    """A client-safe validation error for desktop synchronization."""


class DesktopSyncConflictError(DesktopSyncError):
    def __init__(self, task: dict[str, Any]):
        super().__init__("The desktop result is older than the cloud revision")
        self.task = task


class DesktopSyncPermissionError(DesktopSyncError):
    """The credential does not own the requested desktop task."""


def _db_path(db_path: Path | str | None = None) -> Path:
    return Path(db_path) if db_path is not None else default_job_db_path()


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def ensure_desktop_sync_db(db_path: Path | str | None = None) -> None:
    path = _db_path(db_path)
    job_store.ensure_job_db(path)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS desktop_sync_tasks (
                task_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                origin_device_id TEXT NOT NULL,
                origin_device_name TEXT NOT NULL,
                origin_device_platform TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                execution_location TEXT NOT NULL,
                source_availability TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                source_file_size_bytes INTEGER,
                source_duration_seconds REAL,
                status TEXT NOT NULL,
                stage TEXT,
                progress REAL,
                error_code TEXT,
                error_reason TEXT,
                result_revision INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                result_expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_user_id, origin_device_id, idempotency_key),
                FOREIGN KEY(task_id) REFERENCES jobs(task_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_tasks_owner_updated
                ON desktop_sync_tasks(owner_user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_tasks_device
                ON desktop_sync_tasks(origin_device_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_tasks_expiry
                ON desktop_sync_tasks(result_expires_at);

            CREATE TABLE IF NOT EXISTS desktop_sync_operations (
                operation_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                operation_kind TEXT NOT NULL,
                base_revision INTEGER NOT NULL,
                result_revision INTEGER NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES desktop_sync_tasks(task_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_operations_task
                ON desktop_sync_operations(task_id, created_at);
            """
        )


def _row_to_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "task_id": row["task_id"],
        "owner_user_id": row["owner_user_id"],
        "origin_device_id": row["origin_device_id"],
        "origin_device": {
            "display_name": row["origin_device_name"],
            "platform": row["origin_device_platform"],
        },
        "execution_location": row["execution_location"],
        "source_availability": row["source_availability"],
        "source": {
            "type": row["source_type"],
            "filename": row["source_filename"],
            "file_size_bytes": row["source_file_size_bytes"],
            "duration_seconds": row["source_duration_seconds"],
        },
        "status": row["status"],
        "stage": row["stage"],
        "progress": row["progress"],
        "error_code": row["error_code"],
        "error_reason": row["error_reason"],
        "result_revision": int(row["result_revision"] or 0),
        "completed_at": row["completed_at"],
        "result_expires_at": row["result_expires_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_task_row(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM desktop_sync_tasks WHERE task_id = ?", (task_id,)).fetchone()


def _validate_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 128:
        raise DesktopSyncError("idempotency_key is required and must be 128 characters or fewer")
    return key


def _validate_requested_task_id(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return uuid.UUID(str(value).strip()).hex
    except (AttributeError, ValueError) as exc:
        raise DesktopSyncError("task_id must be a UUID") from exc


def _validate_operation_id(value: Any) -> str:
    operation_id = str(value or "").strip()
    if not operation_id or len(operation_id) > 128:
        raise DesktopSyncError("operation_id is required and must be 128 characters or fewer")
    return operation_id


def _validate_filename(value: Any) -> str:
    filename = " ".join(str(value or "").split())
    if not filename or len(filename) > 255:
        raise DesktopSyncError("source.filename is required and must be 255 characters or fewer")
    if any(char in filename for char in ("/", "\\", "\r", "\n")):
        raise DesktopSyncError("source.filename must not contain a local file path")
    return filename


def _positive_number(value: Any, field: str, *, integer: bool = False) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise DesktopSyncError(f"{field} must be numeric") from exc
    if parsed < 0:
        raise DesktopSyncError(f"{field} must not be negative")
    return parsed


def _validate_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise DesktopSyncError("source is required")
    source_type = str(source.get("type") or "").strip().lower()
    if source_type not in {"video", "audio"}:
        raise DesktopSyncError("source.type must be video or audio")
    return {
        "type": source_type,
        "filename": _validate_filename(source.get("filename")),
        "file_size_bytes": _positive_number(source.get("file_size_bytes"), "source.file_size_bytes", integer=True),
        "duration_seconds": _positive_number(source.get("duration_seconds"), "source.duration_seconds"),
    }


def _validate_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status not in VALID_SYNC_STATUSES:
        raise DesktopSyncError("status must be queued, running, completed, failed, or cancelled")
    return status


def _validate_progress(value: Any) -> float | None:
    if value is None:
        return None
    try:
        progress = float(value)
    except (TypeError, ValueError) as exc:
        raise DesktopSyncError("progress must be numeric") from exc
    if not 0 <= progress <= 100:
        raise DesktopSyncError("progress must be between 0 and 100")
    return progress


def _validate_base_revision(value: Any) -> int:
    try:
        revision = int(value)
    except (TypeError, ValueError) as exc:
        raise DesktopSyncError("base_revision must be an integer") from exc
    if revision < 0:
        raise DesktopSyncError("base_revision must not be negative")
    return revision


def _validate_sync_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DesktopSyncError("result is required")

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                normalized = str(key).strip().lower()
                if normalized in FORBIDDEN_SYNC_KEYS or normalized.endswith("_path") or normalized.endswith("_url"):
                    raise DesktopSyncError(f"result.{key} is not allowed for desktop synchronization")
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    walk(value)
    return dict(value)


def _operation_response(task: dict[str, Any], operation_id: str) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "operation_id": operation_id,
        "status": task["status"],
        "stage": task["stage"],
        "progress": task["progress"],
        "result_revision": task["result_revision"],
        "result_expires_at": task["result_expires_at"],
    }


def _persist_operation(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    task_id: str,
    device_id: str,
    operation_kind: str,
    base_revision: int,
    response: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO desktop_sync_operations
            (operation_id, task_id, device_id, operation_kind, base_revision, result_revision, response_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            task_id,
            device_id,
            operation_kind,
            base_revision,
            response["result_revision"],
            _json_dumps(response),
            _now_iso(),
        ),
    )


def _existing_operation(conn: sqlite3.Connection, operation_id: str, task_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT task_id, response_json FROM desktop_sync_operations WHERE operation_id = ?",
        (operation_id,),
    ).fetchone()
    if row is None:
        return None
    if row["task_id"] != task_id:
        raise DesktopSyncError("operation_id is already bound to a different task")
    return _json_loads(row["response_json"])


def _desktop_metadata(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "desktop_sync": {
            "execution_location": task["execution_location"],
            "source_availability": task["source_availability"],
            "origin_device": task["origin_device"],
            "result_revision": task["result_revision"],
            "result_expires_at": task["result_expires_at"],
        }
    }


def _project_job(task: dict[str, Any], result: dict[str, Any] | None, db_path: Path) -> None:
    source = task["source"]
    projected_result = dict(result or {})
    if projected_result:
        projected_result.update({
            "task_id": task["task_id"],
            "status": task["status"],
            "filename": projected_result.get("filename") or source["filename"],
            "source_file_available": False,
            "playback_audio_available": False,
        })
    job_store.upsert_job(
        task_id=task["task_id"],
        status=task["status"],
        client_id=f"user:{task['owner_user_id']}",
        stage=task["stage"],
        progress=task["progress"],
        source_type=source["type"],
        source_filename=source["filename"],
        source_file_size_mb=(float(source["file_size_bytes"]) / (1024 * 1024)) if source["file_size_bytes"] is not None else None,
        summary_status=projected_result.get("summary_status") if projected_result else None,
        error_reason=task["error_reason"],
        result=projected_result or None,
        metadata=_desktop_metadata(task),
        db_path=db_path,
    )


def create_desktop_sync_task(
    *,
    device_auth: dict[str, Any],
    idempotency_key: Any,
    source: Any,
    task_id: Any = None,
    db_path: Path | str | None = None,
) -> tuple[dict[str, Any], bool]:
    account_id = str(device_auth.get("user_id") or "").strip()
    device_id = str(device_auth.get("device_id") or "").strip()
    if not account_id or not device_id:
        raise DesktopSyncPermissionError("A desktop device credential is required")
    key = _validate_idempotency_key(idempotency_key)
    source_data = _validate_source(source)
    requested_task_id = _validate_requested_task_id(task_id)
    path = _db_path(db_path)
    ensure_desktop_sync_db(path)

    task: dict[str, Any] | None = None
    created = False
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            """
            SELECT * FROM desktop_sync_tasks
            WHERE owner_user_id = ? AND origin_device_id = ? AND idempotency_key = ?
            """,
            (account_id, device_id, key),
        ).fetchone()
        if existing is not None:
            task = _row_to_task(existing)
            if not task:
                raise RuntimeError("desktop sync task is missing")
        else:
            now = _now_iso()
            task_id_value = requested_task_id or uuid.uuid4().hex
            if _get_task_row(conn, task_id_value) is not None:
                raise DesktopSyncError("task_id is already in use")
            conn.execute(
                """
                INSERT INTO desktop_sync_tasks (
                    task_id, owner_user_id, origin_device_id, origin_device_name, origin_device_platform,
                    idempotency_key, execution_location, source_availability, source_type, source_filename,
                    source_file_size_bytes, source_duration_seconds, status, stage, progress, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'local_desktop', 'local_only', ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?)
                """,
                (
                    task_id_value,
                    account_id,
                    device_id,
                    str(device_auth.get("display_name") or "Desktop"),
                    str(device_auth.get("platform") or "unknown"),
                    key,
                    source_data["type"],
                    source_data["filename"],
                    source_data["file_size_bytes"],
                    source_data["duration_seconds"],
                    now,
                    now,
                ),
            )
            task = _row_to_task(_get_task_row(conn, task_id_value))
            created = True
    if not task:
        raise RuntimeError("created desktop sync task is missing")
    _project_job(task, None, path)
    return task, created


def _owned_task(conn: sqlite3.Connection, task_id: str, device_auth: dict[str, Any]) -> dict[str, Any]:
    task = _row_to_task(_get_task_row(conn, task_id))
    if not task or task["owner_user_id"] != device_auth.get("user_id"):
        raise DesktopSyncPermissionError("Desktop sync task not found")
    if task["origin_device_id"] != device_auth.get("device_id"):
        raise DesktopSyncPermissionError("Only the originating desktop can synchronize this task")
    return task


def sync_desktop_task_status(
    *,
    task_id: str,
    device_auth: dict[str, Any],
    operation_id: Any,
    base_revision: Any,
    status: Any,
    stage: Any = None,
    progress: Any = None,
    error_code: Any = None,
    error_reason: Any = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    path = _db_path(db_path)
    ensure_desktop_sync_db(path)
    operation = _validate_operation_id(operation_id)
    revision = _validate_base_revision(base_revision)
    next_status = _validate_status(status)
    if next_status == "completed":
        raise DesktopSyncError("completed status must be synchronized with a result")
    next_progress = _validate_progress(progress)
    next_stage = str(stage or "").strip()[:80] or next_status
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        task = _owned_task(conn, task_id, device_auth)
        existing = _existing_operation(conn, operation, task_id)
        if existing is not None:
            return existing
        if task["result_revision"] != revision:
            raise DesktopSyncConflictError(task)
        if task["status"] in {"completed", "failed", "cancelled"}:
            raise DesktopSyncConflictError(task)
        now = _now_iso()
        conn.execute(
            """
            UPDATE desktop_sync_tasks
            SET status = ?, stage = ?, progress = ?, error_code = ?, error_reason = ?,
                result_revision = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                next_status,
                next_stage,
                next_progress if next_progress is not None else task["progress"],
                str(error_code or "").strip()[:80] or None,
                str(error_reason or "").strip()[:1000] or None,
                revision + 1,
                now,
                task_id,
            ),
        )
        updated = _row_to_task(_get_task_row(conn, task_id))
        if not updated:
            raise RuntimeError("updated desktop sync task is missing")
        response = _operation_response(updated, operation)
        _persist_operation(
            conn,
            operation_id=operation,
            task_id=task_id,
            device_id=str(device_auth["device_id"]),
            operation_kind="status",
            base_revision=revision,
            response=response,
        )
    _project_job(updated, None, path)
    return response


def sync_desktop_task_result(
    *,
    task_id: str,
    device_auth: dict[str, Any],
    operation_id: Any,
    base_revision: Any,
    result: Any,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    path = _db_path(db_path)
    ensure_desktop_sync_db(path)
    operation = _validate_operation_id(operation_id)
    revision = _validate_base_revision(base_revision)
    synced_result = _validate_sync_result(result)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        task = _owned_task(conn, task_id, device_auth)
        existing = _existing_operation(conn, operation, task_id)
        if existing is not None:
            return existing
        if task["result_revision"] != revision:
            raise DesktopSyncConflictError(task)
        if task["status"] in {"completed", "failed", "cancelled"}:
            raise DesktopSyncConflictError(task)
        now = _now()
        completed_at = task["completed_at"] or now.isoformat(timespec="seconds")
        expires_at = task["result_expires_at"] or (now + timedelta(days=SYNC_RESULT_RETENTION_DAYS)).isoformat(timespec="seconds")
        conn.execute(
            """
            UPDATE desktop_sync_tasks
            SET status = 'completed', stage = 'done', progress = 100, error_code = NULL, error_reason = NULL,
                result_revision = ?, completed_at = ?, result_expires_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (revision + 1, completed_at, expires_at, now.isoformat(timespec="seconds"), task_id),
        )
        updated = _row_to_task(_get_task_row(conn, task_id))
        if not updated:
            raise RuntimeError("completed desktop sync task is missing")
        response = _operation_response(updated, operation)
        _persist_operation(
            conn,
            operation_id=operation,
            task_id=task_id,
            device_id=str(device_auth["device_id"]),
            operation_kind="result",
            base_revision=revision,
            response=response,
        )
    _project_job(updated, synced_result, path)
    return response


def get_desktop_sync_task(
    task_id: str,
    *,
    user_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    path = _db_path(db_path)
    ensure_desktop_sync_db(path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        task = _row_to_task(_get_task_row(conn, task_id))
    if not task or task["owner_user_id"] != str(user_id or "").strip():
        return None
    return task


def get_desktop_sync_task_for_device(
    task_id: str,
    *,
    device_auth: dict[str, Any],
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return the latest revision only to the desktop that owns writes."""
    path = _db_path(db_path)
    ensure_desktop_sync_db(path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return _owned_task(conn, task_id, device_auth)
