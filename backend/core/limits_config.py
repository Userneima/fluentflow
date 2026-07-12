"""Upload / queue / quota / rate-limit config getters (env-backed),
extracted from server_helpers.py. Depend only on _env + os — re-imported
by server_helpers so H._max_* / H._daily_* keep working."""

from __future__ import annotations

import os
from typing import Any

from backend.core._env import _public_mode_enabled


def _max_upload_mb() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_MAX_UPLOAD_MB", "2048")), 1.0)
    except ValueError:
        return 2048.0


def _max_queue_files() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_MAX_QUEUE_FILES", "5")), 1)
    except ValueError:
        return 5


def _max_active_jobs_per_client() -> int:
    raw = os.environ.get("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT")
    if raw is None:
        return 2 if _public_mode_enabled() else 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 2 if _public_mode_enabled() else 0


def _max_active_jobs_global() -> int:
    raw = os.environ.get("FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL")
    if raw is None:
        return 6 if _public_mode_enabled() else 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 6 if _public_mode_enabled() else 0


def _daily_job_limit_per_client() -> int:
    raw = os.environ.get("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT")
    if raw is None:
        return 10 if _public_mode_enabled() else 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 10 if _public_mode_enabled() else 0


def _daily_job_limit_global() -> int:
    raw = os.environ.get("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL")
    if raw is None:
        return 80 if _public_mode_enabled() else 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 80 if _public_mode_enabled() else 0


def _daily_upload_mb_per_client() -> float:
    raw = os.environ.get("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT")
    if raw is None:
        return 4096.0 if _public_mode_enabled() else 0.0
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 4096.0 if _public_mode_enabled() else 0.0


def _daily_upload_mb_global() -> float:
    raw = os.environ.get("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL")
    if raw is None:
        return 32768.0 if _public_mode_enabled() else 0.0
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 32768.0 if _public_mode_enabled() else 0.0


def _submission_rate_limit_per_ip() -> int:
    raw = os.environ.get("FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP")
    if raw is None:
        return 12 if _public_mode_enabled() else 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 12 if _public_mode_enabled() else 0


def _submission_rate_limit_window_seconds() -> float:
    raw = os.environ.get("FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS")
    if raw is None:
        return 60.0
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return 60.0


def _max_media_duration_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS", "14400")), 0.0)
    except ValueError:
        return 14400.0
