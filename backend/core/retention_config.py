"""Retention config getters + job-time parsing, extracted from
server_helpers.py. Leaf helpers (os/datetime only) — re-imported by
server_helpers so H._*_retention_* / H._parse_job_time keep working."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any


def _history_retention_per_client() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT", "20")), 0)
    except ValueError:
        return 20


def _artifact_retention_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_ARTIFACT_RETENTION_DAYS", "30")), 0)
    except ValueError:
        return 30


def _source_retention_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_SOURCE_RETENTION_DAYS", "7")), 0)
    except ValueError:
        return 7


def _parse_job_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _source_retention_expiry(days: int) -> str:
    return (
        datetime.now(timezone.utc).astimezone() + timedelta(days=days)
    ).isoformat(timespec="seconds")
