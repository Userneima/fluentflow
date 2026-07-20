"""Account retention and deletion lifecycle orchestration.

Deletion is intentionally split into a reversible account-state change and an
idempotent purge. The state change stops new access immediately; the purge only
runs after the server-time grace deadline.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core import account_store, api_key_store, desktop_device_store, desktop_sync_store
from backend.core import event_logger, job_store, quota_store


ACCOUNT_DELETION_GRACE_DAYS = 7


def request_deletion(
    user_id: str,
    *,
    grace_days: int = ACCOUNT_DELETION_GRACE_DAYS,
    account_db_path: Path | str | None = None,
) -> dict[str, Any]:
    request = account_store.request_account_deletion(
        user_id,
        grace_days=grace_days,
        db_path=account_db_path,
    )
    request["revoked_desktop_devices"] = desktop_device_store.revoke_desktop_devices_for_user(
        user_id,
        db_path=account_db_path,
    )
    request["revoked_api_keys"] = api_key_store.revoke_api_keys_for_user(user_id, db_path=account_db_path)
    return request


def cancel_deletion(user_id: str, *, account_db_path: Path | str | None = None) -> dict[str, Any]:
    return account_store.cancel_account_deletion(user_id, db_path=account_db_path)


def purge_due_deletions(
    *,
    cleanup_task_files: Callable[[str, dict[str, Any] | None], Any],
    now: datetime | None = None,
    account_db_path: Path | str | None = None,
    job_db_path: Path | str | None = None,
    event_db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Purge all product data for due deletion requests, safely on retries."""
    purged: list[dict[str, Any]] = []
    for request in account_store.list_due_account_deletions(now=now, db_path=account_db_path):
        user_id = str(request["user_id"])
        client_id = f"user:{user_id}"
        jobs = job_store.list_jobs_for_retention(db_path=job_db_path or job_store.DEFAULT_DB_PATH, client_id=client_id)
        task_ids = [str(job["task_id"]) for job in jobs if job.get("task_id")]
        for job in jobs:
            cleanup_task_files(str(job["task_id"]), job.get("metadata"))
        if task_ids:
            job_store.delete_jobs(task_ids, db_path=job_db_path or job_store.DEFAULT_DB_PATH, client_id=client_id)
            event_logger.delete_events_for_tasks(task_ids, db_path=event_db_path or event_logger.DEFAULT_DB_PATH)
        desktop_sync_store.purge_desktop_sync_tasks_for_user(user_id, db_path=job_db_path)
        quota_rows = quota_store.purge_account_quota(user_id, db_path=account_db_path)
        api_keys = api_key_store.purge_api_keys_for_user(user_id, db_path=account_db_path)
        devices = desktop_device_store.purge_desktop_devices_for_user(user_id, db_path=account_db_path)
        account_store.purge_account_identity(user_id, db_path=account_db_path)
        purged.append({
            "user_id": user_id,
            "task_count": len(task_ids),
            "quota_rows": quota_rows,
            "api_keys": api_keys,
            "desktop_devices": devices,
        })
    return purged
