"""Durable local outbox for paired desktop result synchronization.

The outbox is deliberately local-only. It stores safe task metadata, status
updates, and canonical text results, but never source paths, media bytes, or
desktop credentials. Credentials remain in the 0600 local config file.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.core.desktop_pairing import SYNC_CONFIG_KEY, desktop_sync_status
from backend.core.local_config import load_config
from backend.core.result_schema import canonical_display_segments, canonical_raw_segments
from backend.core.runtime_paths import default_desktop_sync_outbox_db_path


SYNC_API_PREFIX = "/desktop-sync/v1"
SYNC_CREDENTIAL_HEADER = "X-FluentFlow-Desktop-Credential"
RETRY_SECONDS = 15
MAX_FLUSH_ACTIONS = 40


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _outbox_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else default_desktop_sync_outbox_db_path()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def ensure_desktop_sync_outbox(path: Path | str | None = None) -> None:
    db_path = _outbox_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS desktop_sync_local_tasks (
                task_id TEXT PRIMARY KEY,
                cloud_url TEXT NOT NULL,
                device_id TEXT NOT NULL,
                remote_revision INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desktop_sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                operation_kind TEXT NOT NULL,
                operation_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(operation_id),
                FOREIGN KEY(task_id) REFERENCES desktop_sync_local_tasks(task_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_outbox_pending
                ON desktop_sync_outbox(completed_at, next_attempt_at, id);
            CREATE INDEX IF NOT EXISTS idx_desktop_sync_outbox_task
                ON desktop_sync_outbox(task_id, id);
            """
        )


def _connection(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = _outbox_path(path)
    ensure_desktop_sync_outbox(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _sync_config(config_path: Path | str | None = None) -> dict[str, str] | None:
    status = desktop_sync_status(config_path)
    if not status["connected"]:
        return None
    raw = load_config(config_path).get(SYNC_CONFIG_KEY)
    sync = dict(raw) if isinstance(raw, dict) else {}
    credential = str(sync.get("device_credential") or "").strip()
    cloud_url = str(sync.get("cloud_url") or "").strip().rstrip("/")
    device_id = str(sync.get("device_id") or "").strip()
    if not credential or not cloud_url or not device_id:
        return None
    return {"credential": credential, "cloud_url": cloud_url, "device_id": device_id}


def desktop_sync_connected(config_path: Path | str | None = None) -> bool:
    return _sync_config(config_path) is not None


def desktop_sync_outbox_status(outbox_path: Path | str | None = None) -> dict[str, Any]:
    """Return safe local retry metadata for the desktop settings surface."""
    with _connection(outbox_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS pending_count, MIN(next_attempt_at) AS next_attempt_at
            FROM desktop_sync_outbox
            WHERE completed_at IS NULL
            """
        ).fetchone()
        latest_error = conn.execute(
            """
            SELECT last_error FROM desktop_sync_outbox
            WHERE completed_at IS NULL AND last_error IS NOT NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    return {
        "pending_count": int(row["pending_count"] or 0),
        "next_attempt_at": row["next_attempt_at"],
        "last_error": latest_error["last_error"] if latest_error else None,
    }


def _safe_source(source: dict[str, Any]) -> dict[str, Any]:
    source_type = str(source.get("type") or "").strip().lower()
    filename = " ".join(str(source.get("filename") or "").split())
    if source_type not in {"video", "audio"} or not filename or any(char in filename for char in ("/", "\\", "\r", "\n")):
        raise ValueError("desktop sync source must contain a safe audio or video filename")
    safe: dict[str, Any] = {"type": source_type, "filename": filename}
    for key in ("file_size_bytes", "duration_seconds"):
        value = source.get(key)
        if value is not None:
            safe[key] = value
    return safe


def _enqueue(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    operation_kind: str,
    operation_id: str,
    payload: dict[str, Any],
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO desktop_sync_outbox
            (task_id, operation_kind, operation_id, payload_json, next_attempt_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, operation_kind, operation_id, _json_dumps(payload), now, now, now),
    )


def queue_desktop_task(
    *,
    task_id: str,
    source: dict[str, Any],
    config_path: Path | str | None = None,
    outbox_path: Path | str | None = None,
) -> bool:
    """Persist remote registration before any local processing can finish."""
    config = _sync_config(config_path)
    if config is None:
        return False
    try:
        normalized_task_id = uuid.UUID(str(task_id)).hex
    except (AttributeError, ValueError) as exc:
        raise ValueError("desktop sync task_id must be a UUID") from exc
    safe_source = _safe_source(source)
    with _connection(outbox_path) as conn:
        now = _now_iso()
        existing = conn.execute(
            "SELECT task_id FROM desktop_sync_local_tasks WHERE task_id = ?", (normalized_task_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO desktop_sync_local_tasks (task_id, cloud_url, device_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_task_id, config["cloud_url"], config["device_id"], now, now),
            )
        _enqueue(
            conn,
            task_id=normalized_task_id,
            operation_kind="create",
            operation_id=f"create:{normalized_task_id}",
            payload={
                "task_id": normalized_task_id,
                "idempotency_key": normalized_task_id,
                "source": safe_source,
            },
        )
        _enqueue(
            conn,
            task_id=normalized_task_id,
            operation_kind="status",
            operation_id=f"queued:{normalized_task_id}",
            payload={"status": "queued", "stage": "queued", "progress": 0},
        )
    return True


def _task_exists(conn: sqlite3.Connection, task_id: str) -> bool:
    return conn.execute("SELECT 1 FROM desktop_sync_local_tasks WHERE task_id = ?", (task_id,)).fetchone() is not None


def queue_desktop_status(
    *,
    task_id: str,
    status: str,
    stage: str | None = None,
    progress: float | None = None,
    error_code: str | None = None,
    error_reason: str | None = None,
    outbox_path: Path | str | None = None,
) -> bool:
    if status not in {"queued", "running", "failed", "cancelled"}:
        raise ValueError("desktop status must be queued, running, failed, or cancelled")
    with _connection(outbox_path) as conn:
        if not _task_exists(conn, task_id):
            return False
        payload = {
            "status": status,
            "stage": stage,
            "progress": progress,
            "error_code": error_code,
            "error_reason": error_reason,
        }
        _enqueue(
            conn,
            task_id=task_id,
            operation_kind="status",
            operation_id=f"{status}:{task_id}:{uuid.uuid4().hex}",
            payload={key: value for key, value in payload.items() if value is not None},
        )
    return True


def _safe_result(result: dict[str, Any]) -> dict[str, Any]:
    """Keep only portable transcript/note fields; artifacts and paths never leave disk."""
    safe: dict[str, Any] = {}
    raw = canonical_raw_segments(result)
    display = canonical_display_segments(result)
    if raw:
        safe["raw_segments"] = raw
    if display:
        safe["display_segments"] = display
    allowed = {
        "transcript_text", "raw_transcript_text", "cleaned_transcript_text", "summary_markdown",
        "summary_status", "summary_skipped", "audio_duration_seconds",
        "stt_elapsed_seconds", "stt_realtime_factor", "stt_provider", "stt_provider_label",
        "stt_model", "stt_speed", "stt_language", "detected_language", "source_language",
        "subtitle_mode", "translation_status", "speaker_diarization",
        "requested_note_mode", "resolved_note_mode", "note_generation_transcript_source",
        "prompt_preset", "prompt_preset_label", "status", "filename", "raw_title", "display_title",
    }
    for key in allowed:
        value = result.get(key)
        if value is not None:
            safe[key] = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value) if key == "summary_markdown" else value
    return safe


def queue_desktop_result(
    *,
    task_id: str,
    result: dict[str, Any],
    outbox_path: Path | str | None = None,
) -> bool:
    with _connection(outbox_path) as conn:
        if not _task_exists(conn, task_id):
            return False
        _enqueue(
            conn,
            task_id=task_id,
            operation_kind="result",
            operation_id=f"result:{task_id}:{uuid.uuid4().hex}",
            payload={"result": _safe_result(result)},
        )
    return True


def _ready_actions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    now = _now_iso()
    rows = conn.execute(
        """
        SELECT o.*, t.cloud_url, t.device_id, t.remote_revision
        FROM desktop_sync_outbox o
        JOIN desktop_sync_local_tasks t ON t.task_id = o.task_id
        WHERE o.completed_at IS NULL AND o.next_attempt_at <= ?
        ORDER BY o.id ASC
        LIMIT ?
        """,
        (now, MAX_FLUSH_ACTIONS),
    ).fetchall()
    return [dict(row) for row in rows]


def _update_retry(conn: sqlite3.Connection, action_id: int, error: str) -> None:
    retry_at = (_now() + timedelta(seconds=RETRY_SECONDS)).isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE desktop_sync_outbox
        SET attempt_count = attempt_count + 1, next_attempt_at = ?, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (retry_at, error[:800], _now_iso(), action_id),
    )


def _complete_action(conn: sqlite3.Connection, action_id: int, revision: int) -> None:
    now = _now_iso()
    conn.execute(
        "UPDATE desktop_sync_outbox SET completed_at = ?, last_error = NULL, updated_at = ? WHERE id = ?",
        (now, now, action_id),
    )
    conn.execute(
        "UPDATE desktop_sync_local_tasks SET remote_revision = ?, updated_at = ? WHERE task_id = (SELECT task_id FROM desktop_sync_outbox WHERE id = ?)",
        (revision, now, action_id),
    )


def _refresh_revision(client: httpx.Client, base_url: str, task_id: str, headers: dict[str, str]) -> int | None:
    response = client.get(f"{base_url}{SYNC_API_PREFIX}/tasks/{task_id}", headers=headers)
    if response.is_error:
        return None
    task = response.json().get("task") if isinstance(response.json(), dict) else None
    return int(task.get("result_revision")) if isinstance(task, dict) else None


def flush_desktop_sync_outbox(
    *,
    config_path: Path | str | None = None,
    outbox_path: Path | str | None = None,
) -> dict[str, int]:
    """Make one non-blocking retry pass. Errors remain durable for the next pass."""
    config = _sync_config(config_path)
    if config is None:
        return {"sent": 0, "pending": 0, "skipped": 1}
    sent = 0
    with _connection(outbox_path) as conn, httpx.Client(timeout=10.0) as client:
        actions = _ready_actions(conn)
        for action in actions:
            if action["cloud_url"] != config["cloud_url"] or action["device_id"] != config["device_id"]:
                continue
            if action["operation_kind"] != "create":
                registration_pending = conn.execute(
                    """
                    SELECT 1 FROM desktop_sync_outbox
                    WHERE task_id = ? AND operation_kind = 'create' AND completed_at IS NULL
                    """,
                    (action["task_id"],),
                ).fetchone()
                if registration_pending is not None:
                    continue
            revision_row = conn.execute(
                "SELECT remote_revision FROM desktop_sync_local_tasks WHERE task_id = ?", (action["task_id"],)
            ).fetchone()
            if revision_row is None:
                _update_retry(conn, int(action["id"]), "Desktop sync task is missing from the local outbox")
                continue
            remote_revision = int(revision_row["remote_revision"])
            headers = {SYNC_CREDENTIAL_HEADER: config["credential"]}
            payload = _json_loads(action["payload_json"])
            try:
                if action["operation_kind"] == "create":
                    response = client.post(f"{config['cloud_url']}{SYNC_API_PREFIX}/tasks", headers=headers, json=payload)
                elif action["operation_kind"] == "status":
                    request_body = {**payload, "operation_id": action["operation_id"], "base_revision": remote_revision}
                    response = client.patch(
                        f"{config['cloud_url']}{SYNC_API_PREFIX}/tasks/{action['task_id']}/status",
                        headers=headers,
                        json=request_body,
                    )
                elif action["operation_kind"] == "result":
                    request_body = {**payload, "operation_id": action["operation_id"], "base_revision": remote_revision}
                    response = client.put(
                        f"{config['cloud_url']}{SYNC_API_PREFIX}/tasks/{action['task_id']}/result",
                        headers=headers,
                        json=request_body,
                    )
                else:
                    _update_retry(conn, int(action["id"]), "Unknown desktop sync operation")
                    continue
            except httpx.RequestError as exc:
                _update_retry(conn, int(action["id"]), f"Network error: {exc}")
                continue

            if response.status_code == 409:
                revision = _refresh_revision(client, config["cloud_url"], action["task_id"], headers)
                if revision is None:
                    _update_retry(conn, int(action["id"]), "Cloud revision conflict could not be refreshed")
                else:
                    conn.execute(
                        "UPDATE desktop_sync_local_tasks SET remote_revision = ?, updated_at = ? WHERE task_id = ?",
                        (revision, _now_iso(), action["task_id"]),
                    )
                continue
            if response.is_error:
                _update_retry(conn, int(action["id"]), f"Cloud returned HTTP {response.status_code}")
                continue
            body = response.json()
            task = body.get("task") if isinstance(body, dict) else None
            revision_value = body.get("result_revision") if isinstance(body, dict) else None
            if revision_value is None and isinstance(task, dict):
                revision_value = task.get("result_revision")
            try:
                revision = int(revision_value)
            except (TypeError, ValueError):
                _update_retry(conn, int(action["id"]), "Cloud response did not include result_revision")
                continue
            _complete_action(conn, int(action["id"]), revision)
            sent += 1
    with _connection(outbox_path) as conn:
        pending = conn.execute("SELECT COUNT(*) FROM desktop_sync_outbox WHERE completed_at IS NULL").fetchone()[0]
    return {"sent": sent, "pending": int(pending), "skipped": 0}


def sync_terminal_local_job(
    job: dict[str, Any],
    *,
    config_path: Path | str | None = None,
    outbox_path: Path | str | None = None,
) -> dict[str, int] | None:
    """Queue the final local task state and attempt one safe delivery pass."""
    task_id = str(job.get("task_id") or "")
    status = str(job.get("status") or "")
    if not task_id or status not in {"completed", "failed", "cancelled"}:
        return None
    if status == "completed":
        if not queue_desktop_result(task_id=task_id, result=job.get("result") or {}, outbox_path=outbox_path):
            return None
    else:
        if not queue_desktop_status(
            task_id=task_id,
            status=status,
            stage=str(job.get("stage") or status),
            progress=job.get("progress"),
            error_code="local_processing_failed",
            error_reason="本地处理未完成，请在原设备查看详情后重试。",
            outbox_path=outbox_path,
        ):
            return None
    return flush_desktop_sync_outbox(config_path=config_path, outbox_path=outbox_path)
