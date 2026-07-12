"""Guest-trial config getters (env-backed), extracted from server_helpers.py.
Depend only on _env + os — re-imported by server_helpers so H._guest_* work."""

from __future__ import annotations

import os

from backend.core._env import _env_truthy


def _guest_trial_enabled() -> bool:
    raw = os.environ.get("FLUENTFLOW_GUEST_TRIAL_ENABLED")
    if raw is None:
        return True
    return _env_truthy("FLUENTFLOW_GUEST_TRIAL_ENABLED")


def _guest_file_limit_mb() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_GUEST_FILE_LIMIT_MB", "150")), 1.0)
    except ValueError:
        return 150.0


def _guest_duration_limit_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_GUEST_DURATION_LIMIT_SECONDS", "900")), 1.0)
    except ValueError:
        return 900.0


def _guest_active_processing_slots() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_GUEST_ACTIVE_PROCESSING_SLOTS", "1")), 1)
    except ValueError:
        return 1


def _guest_waiting_queue_limit() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_GUEST_WAITING_QUEUE_LIMIT", "5")), 0)
    except ValueError:
        return 5


def _guest_daily_trials_per_ip() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_GUEST_DAILY_TRIALS_PER_IP", "2")), 0)
    except ValueError:
        return 2


def _guest_result_retention_hours() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_GUEST_RESULT_RETENTION_HOURS", "24")), 1.0)
    except ValueError:
        return 24.0


def _guest_wait_estimate_per_task_minutes() -> tuple[int, int]:
    raw = (os.environ.get("FLUENTFLOW_GUEST_WAIT_ESTIMATE_PER_TASK_MINUTES") or "8-12").strip()
    try:
        if "-" in raw:
            lo, hi = raw.split("-", 1)
            low = max(int(float(lo)), 1)
            high = max(int(float(hi)), low)
            return low, high
        value = max(int(float(raw)), 1)
        return value, value
    except ValueError:
        return 8, 12
