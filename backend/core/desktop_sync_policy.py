"""Read/write boundary for cloud projections of desktop-local tasks."""

from __future__ import annotations

from typing import Any


def is_local_desktop_sync_job(job: dict[str, Any] | None) -> bool:
    metadata = job.get("metadata") if isinstance(job, dict) else None
    desktop_sync = metadata.get("desktop_sync") if isinstance(metadata, dict) else None
    return isinstance(desktop_sync, dict) and desktop_sync.get("execution_location") == "local_desktop"


def desktop_sync_read_only_detail(job: dict[str, Any] | None) -> str:
    metadata = job.get("metadata") if isinstance(job, dict) else None
    desktop_sync = metadata.get("desktop_sync") if isinstance(metadata, dict) else {}
    origin_device = desktop_sync.get("origin_device") if isinstance(desktop_sync, dict) else {}
    label = str(origin_device.get("display_name") or "the originating desktop").strip()
    return f"This desktop-synced result is read-only here. Edit it on {label}."
