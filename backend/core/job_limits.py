"""Submission, active-job, and daily usage limits."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from backend.core.account_store import get_user_by_id
from backend.core.job_store import list_jobs

SUBMISSION_RATE_EVENTS: dict[str, list[float]] = {}
SUBMISSION_RATE_LOCK = threading.Lock()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(float(raw), minimum)
    except ValueError:
        return default


def max_active_jobs_per_client(*, public_mode: bool) -> int:
    return _env_int("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT", 2 if public_mode else 0)


def max_active_jobs_global(*, public_mode: bool) -> int:
    return _env_int("FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL", 6 if public_mode else 0)


def daily_job_limit_per_client(*, public_mode: bool) -> int:
    return _env_int("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", 10 if public_mode else 0)


def daily_job_limit_global(*, public_mode: bool) -> int:
    return _env_int("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL", 80 if public_mode else 0)


def daily_upload_mb_per_client(*, public_mode: bool) -> float:
    return _env_float("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", 4096.0 if public_mode else 0.0)


def daily_upload_mb_global(*, public_mode: bool) -> float:
    return _env_float("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL", 32768.0 if public_mode else 0.0)


def submission_rate_limit_per_ip(*, public_mode: bool) -> int:
    return _env_int("FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP", 12 if public_mode else 0)


def submission_rate_limit_window_seconds() -> float:
    return _env_float("FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS", 60.0, minimum=1.0)


def active_job_count(client_id: str | None, exclude_task_id: str | None = None) -> int:
    return sum(
        1
        for job in list_jobs(limit=200, client_id=client_id)
        if job.get("status") in {"queued", "running"} and job.get("task_id") != exclude_task_id
    )


def global_active_job_count(exclude_task_id: str | None = None) -> int:
    return sum(
        1
        for job in list_jobs(limit=200)
        if job.get("status") in {"queued", "running"} and job.get("task_id") != exclude_task_id
    )


def enforce_active_job_limit(
    client_id: str | None,
    *,
    public_mode: bool,
    incoming: int = 1,
    exclude_task_id: str | None = None,
) -> None:
    limit = max_active_jobs_per_client(public_mode=public_mode)
    if limit <= 0:
        return
    active = active_job_count(client_id, exclude_task_id=exclude_task_id)
    if active + max(incoming, 1) > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"当前仍有 {active} 个后台任务未完成。"
                f"封闭测试阶段每个设备最多同时运行 {limit} 个任务，请稍后再提交。"
            ),
        )


def enforce_global_active_job_limit(
    *,
    public_mode: bool,
    incoming: int = 1,
    exclude_task_id: str | None = None,
) -> None:
    limit = max_active_jobs_global(public_mode=public_mode)
    if limit <= 0:
        return
    active = global_active_job_count(exclude_task_id=exclude_task_id)
    if active + max(incoming, 1) > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"当前服务器已有 {active} 个后台任务未完成。"
                f"公开试用阶段全站最多同时运行 {limit} 个任务，请稍后再提交。"
            ),
        )


def _account_id_from_client_scope(client_id: str | None) -> str | None:
    text = (client_id or "").strip()
    if text and text.startswith("user:"):
        return text.split(":", 1)[1] or None
    return None


def client_scope_is_admin(client_id: str | None) -> bool:
    account_id = _account_id_from_client_scope(client_id)
    if not account_id:
        return False
    try:
        user = get_user_by_id(account_id)
    except Exception:
        return False
    return bool(user and user.get("role") == "admin")


def job_created_today(job: dict[str, Any]) -> bool:
    raw = job.get("created_at") or job.get("updated_at")
    if not raw:
        return False
    try:
        created = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone().date() == datetime.now(timezone.utc).astimezone().date()


def job_is_imported_history(job: dict[str, Any]) -> bool:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return bool(
        metadata.get("imported_by_account_id")
        or metadata.get("source_type") == "imported_local_history"
        or result.get("imported_from_local_history")
        or job.get("source_type") == "imported_local_history"
    )


def job_counts_toward_daily_submission(job: dict[str, Any]) -> bool:
    return job_created_today(job) and not job_is_imported_history(job)


def daily_usage_for_client(client_id: str | None, exclude_task_id: str | None = None) -> dict[str, float]:
    jobs = [
        job for job in list_jobs(limit=200, client_id=client_id)
        if job.get("task_id") != exclude_task_id and job_counts_toward_daily_submission(job)
    ]
    upload_mb = 0.0
    for job in jobs:
        try:
            upload_mb += float(job.get("source_file_size_mb") or 0)
        except (TypeError, ValueError):
            continue
    return {"jobs": float(len(jobs)), "upload_mb": round(upload_mb, 3)}


def daily_usage_global(exclude_task_id: str | None = None) -> dict[str, float]:
    jobs = [
        job for job in list_jobs(limit=200)
        if job.get("task_id") != exclude_task_id and job_counts_toward_daily_submission(job)
    ]
    upload_mb = 0.0
    for job in jobs:
        try:
            upload_mb += float(job.get("source_file_size_mb") or 0)
        except (TypeError, ValueError):
            continue
    return {"jobs": float(len(jobs)), "upload_mb": round(upload_mb, 3)}


def enforce_daily_quota(
    client_id: str | None,
    *,
    public_mode: bool,
    incoming_jobs: int = 1,
    incoming_upload_mb: float | None = None,
    exclude_task_id: str | None = None,
) -> None:
    if client_scope_is_admin(client_id):
        return
    job_limit = daily_job_limit_per_client(public_mode=public_mode)
    upload_limit = daily_upload_mb_per_client(public_mode=public_mode)
    if job_limit <= 0 and upload_limit <= 0:
        return
    usage = daily_usage_for_client(client_id, exclude_task_id=exclude_task_id)
    next_jobs = int(usage["jobs"]) + max(int(incoming_jobs or 0), 0)
    next_upload_mb = usage["upload_mb"] + max(float(incoming_upload_mb or 0), 0.0)
    if job_limit > 0 and next_jobs > job_limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"今天这个设备已经提交 {int(usage['jobs'])} 个任务。"
                f"当前每日上限为 {job_limit} 个任务，请明天再试或联系维护者调高额度。"
            ),
        )
    if upload_limit > 0 and next_upload_mb > upload_limit:
        remaining = max(upload_limit - usage["upload_mb"], 0.0)
        raise HTTPException(
            status_code=429,
            detail=(
                f"今天这个设备已使用约 {usage['upload_mb']:.1f} MB 上传额度。"
                f"当前每日上限为 {upload_limit:g} MB，剩余额度约 {remaining:.1f} MB。"
            ),
        )


def enforce_global_daily_quota(
    *,
    public_mode: bool,
    client_id: str | None = None,
    incoming_jobs: int = 1,
    incoming_upload_mb: float | None = None,
    exclude_task_id: str | None = None,
) -> None:
    if client_scope_is_admin(client_id):
        return
    job_limit = daily_job_limit_global(public_mode=public_mode)
    upload_limit = daily_upload_mb_global(public_mode=public_mode)
    if job_limit <= 0 and upload_limit <= 0:
        return
    usage = daily_usage_global(exclude_task_id=exclude_task_id)
    next_jobs = int(usage["jobs"]) + max(int(incoming_jobs or 0), 0)
    next_upload_mb = usage["upload_mb"] + max(float(incoming_upload_mb or 0), 0.0)
    if job_limit > 0 and next_jobs > job_limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"今天全站已经提交 {int(usage['jobs'])} 个任务。"
                f"公开试用阶段每日全站上限为 {job_limit} 个任务，请明天再试。"
            ),
        )
    if upload_limit > 0 and next_upload_mb > upload_limit:
        remaining = max(upload_limit - usage["upload_mb"], 0.0)
        raise HTTPException(
            status_code=429,
            detail=(
                f"今天全站已使用约 {usage['upload_mb']:.1f} MB 上传额度。"
                f"当前每日全站上限为 {upload_limit:g} MB，剩余额度约 {remaining:.1f} MB。"
            ),
        )


def request_ip_key(request: Request, *, trusted_proxy: bool = False) -> str:
    if trusted_proxy:
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:128]
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host or "unknown")[:128]


def enforce_submission_rate_limit(
    request: Request,
    *,
    public_mode: bool,
    trusted_proxy: bool = False,
    incoming: int = 1,
) -> None:
    limit = submission_rate_limit_per_ip(public_mode=public_mode)
    if limit <= 0:
        return
    window_seconds = submission_rate_limit_window_seconds()
    now = time.time()
    cutoff = now - window_seconds
    ip_key = request_ip_key(request, trusted_proxy=trusted_proxy)
    with SUBMISSION_RATE_LOCK:
        events = [stamp for stamp in SUBMISSION_RATE_EVENTS.get(ip_key, []) if stamp >= cutoff]
        if len(events) + max(int(incoming or 1), 1) > limit:
            SUBMISSION_RATE_EVENTS[ip_key] = events
            raise HTTPException(
                status_code=429,
                detail=(
                    f"提交过于频繁。公开试用阶段同一网络在 {int(window_seconds)} 秒内"
                    f"最多提交 {limit} 个任务，请稍后再试。"
                ),
            )
        events.extend([now] * max(int(incoming or 1), 1))
        SUBMISSION_RATE_EVENTS[ip_key] = events
