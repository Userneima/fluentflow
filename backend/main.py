"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes:
  GET  /health   – liveness check
  POST /process  – upload video/audio, run STT + summarize, optional Lark export
                   returns Server-Sent Events for real-time progress
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from http.cookies import SimpleCookie
import importlib.metadata
import json
import logging
import math
import mimetypes
import os
import platform
import queue as thread_queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import wave
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
import urllib.error
import urllib.request

import httpx
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(title="FluentFlow")

EVENT_SCHEMA_VERSION = "1.3"
APP_VERSION = "local"
INTERNAL_QUEUE_TOKEN = uuid.uuid4().hex
GUEST_TRIAL_TOKEN_HEADER = "x-fluentflow-guest-token"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_SOURCE_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "sources"


def _video_source_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_VIDEO_SOURCE_DIR")
    return Path(override).expanduser() if override else _project_root() / "视频文件"


def _edited_transcript_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_EDITED_TRANSCRIPT_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "edited_transcripts"


def _artifact_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_ARTIFACT_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "artifacts"


def _transcript_edit_records_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "transcript_edit_records"


class JobEventHub:
    """In-memory fan-out for live job progress events.

    Durable completion state lives in the SQLite job store. This hub only keeps
    recent live events so clients can disconnect and resubscribe without
    cancelling the underlying processing task.
    """

    def __init__(self, max_events_per_job: int = 500) -> None:
        self.max_events_per_job = max_events_per_job
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        if not task_id:
            return
        async with self._lock:
            history = self._events.setdefault(task_id, [])
            payload = dict(event)
            payload["event_index"] = len(history)
            history.append(payload)
            if len(history) > self.max_events_per_job:
                del history[: len(history) - self.max_events_per_job]
                for index, item in enumerate(history):
                    item["event_index"] = index
            subscribers = list(self._subscribers.get(task_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def start(self, task_id: str, runner: Any) -> None:
        async with self._lock:
            existing = self._tasks.get(task_id)
            if existing and not existing.done():
                return
            self._tasks[task_id] = asyncio.create_task(runner())

    async def subscribe(self, task_id: str, since: int = 0) -> AsyncGenerator[str, None]:
        cached = await self.cached_events(task_id)
        start = max(0, int(since or 0))
        for event in cached[start:]:
            yield _sse(event)
            if self.is_terminal(event):
                return

        job = get_job(task_id)
        if job and job.get("status") in {"completed", "failed", "cancelled"}:
            terminal = self.event_from_job(job)
            await self.publish(task_id, terminal)
            yield _sse(terminal)
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(queue)
        try:
            while True:
                event = await queue.get()
                yield _sse(event)
                if self.is_terminal(event):
                    return
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(task_id)
                if subscribers:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(task_id, None)

    async def cached_events(self, task_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._events.get(task_id, []))

    async def has_running_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and not task.done())

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
        if not task or task.done():
            return False
        task.cancel()
        return True

    @staticmethod
    def is_terminal(event: dict[str, Any]) -> bool:
        return event.get("stage") in {"done", "error"}

    @staticmethod
    def event_from_job(job: dict[str, Any]) -> dict[str, Any]:
        status = job.get("status")
        result = job.get("result")
        if status == "completed" or result:
            return {"stage": "done", "progress": 100, "result": result or {}}
        return {
            "stage": "error",
            "progress": job.get("progress") or 0,
            "error": job.get("error_reason") or f"Job {status or 'failed'}",
        }


JOB_EVENTS = JobEventHub()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5185",
        "http://localhost:5185",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _configured_access_tokens() -> tuple[str, ...]:
    raw = os.environ.get("FLUENTFLOW_ACCESS_TOKENS") or os.environ.get("FLUENTFLOW_ACCESS_TOKEN") or ""
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _access_control_enabled() -> bool:
    return bool(_configured_access_tokens())


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _account_auth_enabled() -> bool:
    mode = (os.environ.get("FLUENTFLOW_AUTH_MODE") or "").strip().lower()
    return mode in {"account", "accounts"} or _env_truthy("FLUENTFLOW_ACCOUNT_AUTH")


def _account_signups_enabled() -> bool:
    return _env_truthy("FLUENTFLOW_ALLOW_SIGNUPS")


def _cookie_secure_enabled() -> bool:
    return _env_truthy("FLUENTFLOW_COOKIE_SECURE")


def _public_mode_enabled() -> bool:
    return _env_truthy("FLUENTFLOW_PUBLIC_MODE")


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


def _cloud_workspace_url() -> str:
    return (os.environ.get("FLUENTFLOW_CLOUD_WORKSPACE_URL") or "").strip().rstrip("/")


def _cloud_workspace_enabled() -> bool:
    return bool(_cloud_workspace_url())


LOCAL_CLOUD_WORKSPACE_PATHS = {
    "/health",
    "/runtime-config",
    "/credentials/status",
    "/speaker-diarization/status",
    "/local-history/candidates",
}


def _request_prefers_local_execution(request: Request) -> bool:
    return (request.headers.get("x-fluentflow-execution-target") or "").strip().lower() == "local"


def _should_proxy_cloud_workspace(request: Request) -> bool:
    if not _cloud_workspace_enabled():
        return False
    path = request.url.path
    if path == "/" or path.startswith("/assets/"):
        return False
    if path in LOCAL_CLOUD_WORKSPACE_PATHS:
        return False
    if path == "/process" and _request_prefers_local_execution(request):
        return False
    first_segment = (path.lstrip("/").split("/", 1)[0] or "")
    return path in {"/auth/status", "/auth/login", "/auth/register", "/auth/logout"} or first_segment in API_ROUTE_PREFIXES


def _request_is_internal_queue(request: Request) -> bool:
    supplied = request.headers.get("x-fluentflow-internal-queue-token") or ""
    return bool(supplied and hmac.compare_digest(supplied, INTERNAL_QUEUE_TOKEN))


def _proxy_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {
        "connection",
        "content-encoding",
        "content-length",
        "set-cookie",
        "transfer-encoding",
        "www-authenticate",
    }
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def _apply_remote_session_cookie(response: Response, request: Request, remote_headers: httpx.Headers) -> None:
    path = request.url.path
    if path == "/auth/logout":
        response.delete_cookie(SESSION_COOKIE_NAME, samesite="lax")
        response.delete_cookie("fluentflow_access_token", samesite="lax")
        return
    if path not in {"/auth/login", "/auth/register"}:
        return
    for header in remote_headers.get_list("set-cookie"):
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except Exception:
            continue
        morsel = cookie.get(SESSION_COOKIE_NAME)
        if not morsel:
            continue
        max_age_text = morsel.get("max-age")
        try:
            max_age = int(max_age_text) if max_age_text else _session_days() * 24 * 60 * 60
        except ValueError:
            max_age = _session_days() * 24 * 60 * 60
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=morsel.value,
            max_age=max_age,
            httponly=True,
            secure=_cookie_secure_enabled(),
            samesite="lax",
        )
        break


async def _proxy_cloud_workspace_request(request: Request) -> StreamingResponse:
    base_url = _cloud_workspace_url()
    target = f"{base_url}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    blocked_headers = {
        "connection",
        "content-length",
        "cookie",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    headers = {key: value for key, value in request.headers.items() if key.lower() not in blocked_headers}
    session_token = _request_account_session_token(request)
    if session_token:
        headers["X-FluentFlow-Session"] = session_token

    async def body_iter() -> AsyncGenerator[bytes, None]:
        async for chunk in request.stream():
            if chunk:
                yield chunk

    client = httpx.AsyncClient(timeout=None, follow_redirects=False)
    stream = client.stream(request.method, target, headers=headers, content=body_iter())
    try:
        remote = await stream.__aenter__()
    except Exception as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Cloud workspace unavailable: {exc}") from exc

    async def response_iter() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in remote.aiter_raw():
                if chunk:
                    yield chunk
        finally:
            await stream.__aexit__(None, None, None)
            await client.aclose()

    response = StreamingResponse(
        response_iter(),
        status_code=remote.status_code,
        headers=_proxy_response_headers(remote.headers),
    )
    _apply_remote_session_cookie(response, request, remote.headers)
    return response


def _request_access_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = request.headers.get("x-fluentflow-access-token") or ""
    if header_token.strip():
        return header_token.strip()
    return (request.cookies.get("fluentflow_access_token") or "").strip()


def _request_has_access(request: Request) -> bool:
    tokens = _configured_access_tokens()
    if not tokens:
        return True
    supplied = _request_access_token(request)
    return bool(supplied and any(hmac.compare_digest(supplied, token) for token in tokens))


def _normalize_client_id(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    safe = "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"})
    return safe[:96] or None


def _request_client_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return _normalize_client_id(
        request.headers.get("x-fluentflow-client-id")
        or request.cookies.get("fluentflow_client_id")
    )


def _request_client_scope(request: Request | None) -> str:
    if request is not None and _account_auth_enabled():
        user = _request_account_user(request)
        if user and user.get("id"):
            return f"user:{user['id']}"
    return _request_client_id(request) or "anonymous"


def _is_public_request(request: Request) -> bool:
    if request.method.upper() == "OPTIONS":
        return True
    path = request.url.path
    if path.startswith("/guest-trial"):
        return True
    if path in {"/", "/health", "/auth/status", "/auth/login", "/auth/register", "/auth/logout", "/runtime-config"}:
        return True
    if path.startswith("/assets/"):
        return True
    first_segment = (path.lstrip("/").split("/", 1)[0] or "")
    return first_segment not in API_ROUTE_PREFIXES


@app.middleware("http")
async def beta_access_middleware(request: Request, call_next):
    if _should_proxy_cloud_workspace(request):
        return await _proxy_cloud_workspace_request(request)
    if _request_is_internal_queue(request):
        return await call_next(request)
    if _account_auth_enabled():
        if _is_public_request(request):
            return await call_next(request)
        user = _request_account_user(request)
        if user:
            request.state.account_user = user
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={
                "detail": "FluentFlow account login is required.",
                "auth_mode": "accounts",
                "account_required": True,
            },
        )
    if not _access_control_enabled() or _is_public_request(request) or _request_has_access(request):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={
            "detail": "FluentFlow beta access code is required.",
            "access_required": True,
        },
    )

try:
    from backend.core.audio_handler import extract_compressed_mp3, extract_stt_wav
    from backend.core.local_stt import transcribe_audio, get_or_load_model
    from backend.core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
    from backend.core.stt_process import drain_queue, start_transcription_process, terminate_process
    from backend.core.ai_summarizer import summarize_transcript_to_markdown, summarize_transcript_with_metadata
    from backend.core.lark_exporter import export_markdown_to_lark
    from backend.core.lark_cli_exporter import export_markdown_via_lark_cli
    from backend.core.note_title import resolve_lark_doc_title
    from backend.core.transcript_parser import parse_transcript_file
    from backend.core.transcript_cleaner import clean_repeated_transcript
    from backend.core.event_logger import log_event
    from backend.core.job_store import delete_jobs, get_job, list_job_summaries, list_jobs, list_jobs_for_retention, update_job_result, upsert_job
    from backend.core.local_config import credential_status, resolve_secret, save_sensitive_settings
    from backend.core.account_store import (
        authenticate_user,
        count_users,
        create_session,
        create_user,
        get_user_by_id,
        get_user_by_session_token,
        list_users,
        revoke_session,
    )
    from backend.core.quota_store import (
        InsufficientBalanceError,
        account_quota_summary,
        add_admin_adjustment,
        finalize_task_charge,
        grant_starter_balance,
        release_reservation,
        reserve_units,
    )
    from backend.core.speaker_diarization import assign_speakers_to_segments, diarization_status, diarize_audio
    from backend.core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source
except ImportError:
    from core.audio_handler import extract_compressed_mp3, extract_stt_wav
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
    from core.stt_process import drain_queue, start_transcription_process, terminate_process
    from core.ai_summarizer import summarize_transcript_to_markdown, summarize_transcript_with_metadata
    from core.lark_exporter import export_markdown_to_lark
    from core.lark_cli_exporter import export_markdown_via_lark_cli
    from core.note_title import resolve_lark_doc_title
    from core.transcript_parser import parse_transcript_file
    from core.transcript_cleaner import clean_repeated_transcript
    from core.event_logger import log_event
    from core.job_store import delete_jobs, get_job, list_job_summaries, list_jobs, list_jobs_for_retention, update_job_result, upsert_job
    from core.local_config import credential_status, resolve_secret, save_sensitive_settings
    from core.account_store import (
        authenticate_user,
        count_users,
        create_session,
        create_user,
        get_user_by_id,
        get_user_by_session_token,
        list_users,
        revoke_session,
    )
    from core.quota_store import (
        InsufficientBalanceError,
        account_quota_summary,
        add_admin_adjustment,
        finalize_task_charge,
        grant_starter_balance,
        release_reservation,
        reserve_units,
    )
    from core.speaker_diarization import assign_speakers_to_segments, diarization_status, diarize_audio
    from core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source


SESSION_COOKIE_NAME = "fluentflow_session"


def _session_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_SESSION_DAYS", "30")), 1)
    except ValueError:
        return 30


def _request_account_session_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = (request.headers.get("x-fluentflow-session") or "").strip()
    if header_token:
        return header_token
    return (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()


def _public_account_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "role": user.get("role"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }


def _account_quota_payload(user: dict[str, Any] | None) -> dict[str, Any]:
    if not user or not user.get("id"):
        return {"balance_units": 0, "recent_transactions": [], "unlimited": False, "quota_exempt": False}
    summary = account_quota_summary(str(user["id"]))
    is_admin = user.get("role") == "admin"
    summary["unlimited"] = bool(is_admin)
    summary["quota_exempt"] = bool(is_admin)
    return summary


def _starter_balance_units() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_STARTER_BALANCE_UNITS", "100")), 0)
    except ValueError:
        return 100


def _public_account_payload(user: dict[str, Any] | None) -> dict[str, Any] | None:
    public = _public_account_user(user)
    if not public:
        return None
    try:
        public["quota"] = _account_quota_payload(user)
    except Exception as exc:
        logger.warning("Failed to load account quota summary for %s: %s", public.get("id"), exc)
        public["quota"] = {"balance_units": 0, "recent_transactions": [], "unlimited": False, "quota_exempt": False}
    return public


def _grant_starter_balance_if_needed(user: dict[str, Any] | None) -> None:
    if not user or not user.get("id"):
        return
    units = _starter_balance_units()
    if units <= 0:
        return
    try:
        grant_starter_balance(str(user["id"]), units=units)
    except Exception as exc:
        logger.warning("Failed to grant starter balance to %s: %s", user.get("id"), exc)


def _account_id_from_client_scope(client_id: str | None) -> str | None:
    text = (client_id or "").strip()
    if text and text.startswith("user:"):
        return text.split(":", 1)[1] or None
    return None


def _normalize_client_scope(value: str | None) -> str | None:
    text = (value or "").strip()
    if text.startswith("user:") and text.split(":", 1)[1]:
        return text
    return _normalize_client_id(text)


def _quota_account_for_client(client_id: str | None) -> dict[str, Any] | None:
    account_id = _account_id_from_client_scope(client_id)
    if not account_id:
        return None
    try:
        user = get_user_by_id(account_id)
    except Exception:
        return None
    if not user or user.get("role") == "admin":
        return None
    return user


def _quota_number(name: str, default: float) -> float:
    try:
        return max(float(os.environ.get(name, str(default))), 0.0)
    except ValueError:
        return default


def _estimate_processing_units(
    *,
    duration_seconds: float | None = None,
    transcript_text: str | None = None,
    summary_text: str | None = None,
    skip_summary: bool = False,
    estimate_only: bool = False,
) -> dict[str, Any]:
    duration_minutes = max(float(duration_seconds or 0), 0.0) / 60.0
    transcription_rate = _quota_number("FLUENTFLOW_TRANSCRIPTION_UNITS_PER_MINUTE", 1.0)
    transcription_units = int(math.ceil(duration_minutes * transcription_rate)) if duration_minutes > 0 else 0

    transcript_len = len(transcript_text or "")
    summary_len = len(summary_text or "")
    ai_units = 0
    if not skip_summary:
        if transcript_len > 0 or summary_len > 0:
            chars_per_unit = max(_quota_number("FLUENTFLOW_AI_CHARS_PER_UNIT", 4000.0), 1.0)
            weighted_chars = transcript_len + summary_len * 2
            ai_units = int(math.ceil(weighted_chars / chars_per_unit))
        elif estimate_only and duration_minutes > 0:
            ai_units = int(math.ceil(duration_minutes * _quota_number("FLUENTFLOW_AI_ESTIMATE_UNITS_PER_MINUTE", 0.5)))

    default_units = int(_quota_number("FLUENTFLOW_DEFAULT_TASK_ESTIMATE_UNITS", 20.0))
    total_units = transcription_units + ai_units
    if estimate_only and total_units <= 0:
        total_units = default_units
    elif duration_minutes > 0 or transcript_len > 0:
        total_units = max(total_units, 1)

    return {
        "total_units": max(int(total_units), 0),
        "transcription_units": max(int(transcription_units), 0),
        "ai_note_units": max(int(ai_units), 0),
        "duration_seconds": round(float(duration_seconds or 0), 3) if duration_seconds else None,
        "transcript_chars": transcript_len,
        "summary_chars": summary_len,
        "rate_card_version": "quota-v0",
        "estimate_only": bool(estimate_only),
        "skip_summary": bool(skip_summary),
    }


def _reserve_task_quota(
    *,
    client_id: str | None,
    task_id: str,
    estimate: dict[str, Any],
    reason: str = "Task processing reservation",
) -> dict[str, Any] | None:
    user = _quota_account_for_client(client_id)
    if not user:
        return None
    units = int(estimate.get("total_units") or 0)
    if units <= 0:
        return None
    try:
        tx = reserve_units(
            str(user["id"]),
            task_id=task_id,
            units=units,
            reason=reason,
            metadata={"estimate": estimate},
        )
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "message": "当前账号处理额度不足，请充值或联系维护者增加额度。",
                "required_units": exc.required_units,
                "balance_units": exc.balance_units,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "account_id": user["id"],
        "reserved_units": units,
        "transaction": tx,
        "estimate": estimate,
    }


def _release_task_quota(
    *,
    client_id: str | None,
    task_id: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    user = _quota_account_for_client(client_id)
    if not user:
        return
    try:
        release_reservation(str(user["id"]), task_id=task_id, reason=reason, metadata=metadata)
    except Exception as exc:
        logger.warning("Failed to release quota reservation for %s: %s", task_id, exc)


def _finalize_task_quota(
    *,
    client_id: str | None,
    task_id: str,
    final_usage: dict[str, Any],
    reason: str = "Finalize task charge",
) -> dict[str, Any] | None:
    user = _quota_account_for_client(client_id)
    if not user:
        return None
    try:
        tx = finalize_task_charge(
            str(user["id"]),
            task_id=task_id,
            final_units=int(final_usage.get("total_units") or 0),
            reason=reason,
            metadata={"final_usage": final_usage},
        )
        return {
            "account_id": user["id"],
            "charged_units": int(final_usage.get("total_units") or 0),
            "transaction": tx,
            "final_usage": final_usage,
            "balance": account_quota_summary(str(user["id"])),
        }
    except Exception as exc:
        logger.warning("Failed to finalize quota charge for %s: %s", task_id, exc)
        return None


def _request_account_user(request: Request) -> dict[str, Any] | None:
    cached = getattr(request.state, "account_user", None)
    if cached:
        return cached
    token = _request_account_session_token(request)
    user = get_user_by_session_token(token)
    if user:
        request.state.account_user = user
    return user


def _require_account_user(request: Request) -> dict[str, Any]:
    user = _request_account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="FluentFlow account login is required.")
    return user


def _require_admin_user(request: Request) -> dict[str, Any]:
    user = _require_account_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permission is required.")
    return user


def _account_registration_allowed() -> bool:
    return _account_signups_enabled() or count_users() == 0


def _validate_account_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if len(normalized) > 254 or "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise HTTPException(status_code=400, detail="请输入有效邮箱")
    return normalized


def _validate_account_password(password: str) -> str:
    text = password or ""
    if len(text) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要 8 位")
    if len(text) > 256:
        raise HTTPException(status_code=400, detail="密码过长")
    return text


def _set_session_cookie(response: Response, token: str) -> None:
    max_age = _session_days() * 24 * 60 * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure_enabled(),
        samesite="lax",
    )


def _truthy_form(val: Optional[str]) -> bool:
    return bool(val and val.strip().lower() in ("true", "1", "yes", "on"))


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_from_sse_chunk(chunk: str) -> dict[str, Any] | None:
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
}

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt", ".md"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_SUFFIXES = ALLOWED_SUFFIXES - AUDIO_SUFFIXES


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


def _runtime_limits() -> dict[str, Any]:
    return _runtime_limits_for_request()


def _runtime_limits_for_request(request: Request | None = None) -> dict[str, Any]:
    duration_limit = _max_media_duration_seconds()
    return {
        "max_upload_mb": _max_upload_mb(),
        "max_queue_files": _max_queue_files(),
        "max_active_jobs_per_client": _max_active_jobs_per_client() or None,
        "max_active_jobs_global": _max_active_jobs_global() or None,
        "daily_job_limit_per_client": _daily_job_limit_per_client() or None,
        "daily_job_limit_global": _daily_job_limit_global() or None,
        "daily_upload_mb_per_client": _daily_upload_mb_per_client() or None,
        "daily_upload_mb_global": _daily_upload_mb_global() or None,
        "submission_rate_limit_per_ip": _submission_rate_limit_per_ip() or None,
        "submission_rate_limit_window_seconds": _submission_rate_limit_window_seconds(),
        "max_media_duration_seconds": duration_limit if duration_limit > 0 else None,
        "access_control_enabled": _access_control_enabled(),
        "account_auth_enabled": _account_auth_enabled(),
        "public_mode": _public_mode_enabled(),
        "allowed_stt_providers": list(_allowed_stt_providers(request)),
        "default_stt_provider": _default_stt_provider(request),
        "guest_trial": _guest_trial_config(),
    }


def _guest_trial_config() -> dict[str, Any]:
    low, high = _guest_wait_estimate_per_task_minutes()
    return {
        "enabled": _guest_trial_enabled(),
        "file_limit_mb": _guest_file_limit_mb(),
        "duration_limit_seconds": _guest_duration_limit_seconds(),
        "active_processing_slots": _guest_active_processing_slots(),
        "waiting_queue_limit": _guest_waiting_queue_limit(),
        "daily_trials_per_ip": _guest_daily_trials_per_ip(),
        "result_retention_hours": _guest_result_retention_hours(),
        "wait_estimate_per_task_minutes": [low, high],
    }


def _duration_limit_error(
    duration_seconds: float,
    filename: str | None = None,
    limit_override_seconds: float | None = None,
) -> str | None:
    limit = _max_media_duration_seconds()
    if limit_override_seconds and limit_override_seconds > 0:
        limit = min(limit, limit_override_seconds) if limit > 0 else limit_override_seconds
    if limit <= 0 or duration_seconds <= limit:
        return None
    name = f"「{filename}」" if filename else "当前媒体"
    return (
        f"{name}时长过长：约 {duration_seconds / 60:.1f} 分钟，"
        f"当前限制为 {limit / 60:.1f} 分钟。"
    )


def _new_task_id() -> str:
    return uuid.uuid4().hex


def _source_type_for_suffix(suffix: str) -> str:
    if suffix in TRANSCRIPT_SUFFIXES:
        return "transcript_file"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return "unknown"


def _file_size_mb(byte_count: int | None) -> float | None:
    if byte_count is None:
        return None
    return round(byte_count / (1024 * 1024), 3)


def _upload_size_mb(upload: UploadFile) -> float | None:
    file_obj = getattr(upload, "file", None)
    if file_obj is None:
        return None
    try:
        pos = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(pos, os.SEEK_SET)
        return _file_size_mb(size)
    except Exception:
        return None


def _friendly_error_message(error: Any) -> str:
    """Convert infrastructure errors into user-facing Chinese copy."""

    raw = str(error or "").strip()
    if not raw:
        return "处理失败，但没有返回具体原因。请重试一次。"
    lowered = raw.lower()

    if "cloud transcription backend configuration is incomplete" in lowered:
        return "云端转录暂不可用：后端 Azure Speech 配置不完整。请联系产品维护者检查 Speech endpoint 和 key。"
    if "cloud transcription storage is not configured" in lowered:
        return "云端转录暂不可用：后端 Blob/SAS 存储配置缺失。请联系产品维护者检查 Azure 存储设置。"
    if "only \"standard\" subscriptions" in lowered or 'only \\"standard\\" subscriptions' in lowered or "invalidsubscription" in lowered:
        return "云端转录提交失败：当前区域的 Speech 资源不是 Batch 支持的 Standard 订阅。请检查 Azure Speech 区域和定价层。"
    if "invalidlocale" in lowered or "specified locale is not supported" in lowered:
        return "云端转录提交失败：当前音频语言不被 Azure 支持。请切换为中文/英文，或改用本地转录。"
    if "invalidmodel" in lowered or "specified model is not supported" in lowered:
        return "云端转录提交失败：当前 Azure 资源不支持所选模型。请切换云端 Batch 默认模型或改用本地转录。"
    if "diarization is currently not supported" in lowered:
        return "云端转录提交失败：当前 Azure 路线不支持说话人区分。请关闭说话人区分后重试。"
    if "eof occurred in violation of protocol" in lowered or "broken pipe" in lowered:
        return "云端上传中断：通常是网络或 Azure 边缘服务断开连接。请重试；如果文件很大，优先使用 Azure Batch 或减小音频体积。"
    if "azure blob upload failed" in lowered:
        return "云端上传到 Blob 失败。请检查 SAS URL 是否仍有效、是否允许写入，以及网络是否稳定。"
    if "queued processing request failed" in lowered:
        return "后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务并检查上传大小限制。"
    if "no position encodings are defined" in lowered:
        return "本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。"
    if "downloaded video is too large" in lowered or "file is too large" in lowered:
        return "文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。"
    if "unsupported transcript file type" in lowered:
        return "不支持这个字幕/转录文件格式。请上传 SRT、VTT、TXT 或 Markdown 文件。"
    if "unsupported file type" in lowered:
        return "不支持这个文件格式。请上传视频或音频文件。"
    if "no file uploaded" in lowered:
        return "没有收到上传文件。请重新选择文件后再试。"
    if "queued source file is missing" in lowered:
        return "后台任务找不到原始文件。文件可能已被清理，请重新上传。"
    if "暂时无法自动解析这个视频链接" in raw:
        return "暂时无法自动解析这个视频链接。请换一个分享链接，或直接上传视频文件。"
    if "没有识别到视频链接" in raw:
        return "没有识别到视频链接。请粘贴完整的分享文本或视频 URL。"
    if "视频下载失败" in raw or "视频文件过大" in raw:
        return raw
    return raw


def _active_job_count(client_id: str | None, exclude_task_id: str | None = None) -> int:
    return sum(
        1
        for job in list_jobs(limit=200, client_id=client_id)
        if job.get("status") in {"queued", "running"} and job.get("task_id") != exclude_task_id
    )


def _global_active_job_count(exclude_task_id: str | None = None) -> int:
    return sum(
        1
        for job in list_jobs(limit=200)
        if job.get("status") in {"queued", "running"} and job.get("task_id") != exclude_task_id
    )


def _enforce_active_job_limit(
    client_id: str | None,
    incoming: int = 1,
    exclude_task_id: str | None = None,
) -> None:
    limit = _max_active_jobs_per_client()
    if limit <= 0:
        return
    active = _active_job_count(client_id, exclude_task_id=exclude_task_id)
    if active + max(incoming, 1) > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"当前仍有 {active} 个后台任务未完成。"
                f"封闭测试阶段每个设备最多同时运行 {limit} 个任务，请稍后再提交。"
            ),
        )


def _enforce_global_active_job_limit(
    incoming: int = 1,
    exclude_task_id: str | None = None,
) -> None:
    limit = _max_active_jobs_global()
    if limit <= 0:
        return
    active = _global_active_job_count(exclude_task_id=exclude_task_id)
    if active + max(incoming, 1) > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"当前服务器已有 {active} 个后台任务未完成。"
                f"公开试用阶段全站最多同时运行 {limit} 个任务，请稍后再提交。"
            ),
        )


def _job_created_today(job: dict[str, Any]) -> bool:
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


def _job_is_imported_history(job: dict[str, Any]) -> bool:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return bool(
        metadata.get("imported_by_account_id")
        or metadata.get("source_type") == "imported_local_history"
        or result.get("imported_from_local_history")
        or job.get("source_type") == "imported_local_history"
    )


def _job_counts_toward_daily_submission(job: dict[str, Any]) -> bool:
    return _job_created_today(job) and not _job_is_imported_history(job)


def _client_scope_is_admin(client_id: str | None) -> bool:
    account_id = _account_id_from_client_scope(client_id)
    if not account_id:
        return False
    try:
        user = get_user_by_id(account_id)
    except Exception:
        return False
    return bool(user and user.get("role") == "admin")


def _daily_usage_for_client(
    client_id: str | None,
    exclude_task_id: str | None = None,
) -> dict[str, float]:
    jobs = [
        job for job in list_jobs(limit=200, client_id=client_id)
        if job.get("task_id") != exclude_task_id and _job_counts_toward_daily_submission(job)
    ]
    upload_mb = 0.0
    for job in jobs:
        try:
            upload_mb += float(job.get("source_file_size_mb") or 0)
        except (TypeError, ValueError):
            continue
    return {"jobs": float(len(jobs)), "upload_mb": round(upload_mb, 3)}


def _daily_usage_global(exclude_task_id: str | None = None) -> dict[str, float]:
    jobs = [
        job for job in list_jobs(limit=200)
        if job.get("task_id") != exclude_task_id and _job_counts_toward_daily_submission(job)
    ]
    upload_mb = 0.0
    for job in jobs:
        try:
            upload_mb += float(job.get("source_file_size_mb") or 0)
        except (TypeError, ValueError):
            continue
    return {"jobs": float(len(jobs)), "upload_mb": round(upload_mb, 3)}


def _enforce_daily_quota(
    client_id: str | None,
    *,
    incoming_jobs: int = 1,
    incoming_upload_mb: float | None = None,
    exclude_task_id: str | None = None,
) -> None:
    if _client_scope_is_admin(client_id):
        return
    job_limit = _daily_job_limit_per_client()
    upload_limit = _daily_upload_mb_per_client()
    if job_limit <= 0 and upload_limit <= 0:
        return
    usage = _daily_usage_for_client(client_id, exclude_task_id=exclude_task_id)
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


def _enforce_global_daily_quota(
    *,
    client_id: str | None = None,
    incoming_jobs: int = 1,
    incoming_upload_mb: float | None = None,
    exclude_task_id: str | None = None,
) -> None:
    if _client_scope_is_admin(client_id):
        return
    job_limit = _daily_job_limit_global()
    upload_limit = _daily_upload_mb_global()
    if job_limit <= 0 and upload_limit <= 0:
        return
    usage = _daily_usage_global(exclude_task_id=exclude_task_id)
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


_SUBMISSION_RATE_EVENTS: dict[str, list[float]] = {}
_SUBMISSION_RATE_LOCK = threading.Lock()


def _request_ip_key(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:128]
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host or "unknown")[:128]


def _enforce_submission_rate_limit(request: Request, incoming: int = 1) -> None:
    limit = _submission_rate_limit_per_ip()
    if limit <= 0:
        return
    window_seconds = _submission_rate_limit_window_seconds()
    now = time.time()
    cutoff = now - window_seconds
    ip_key = _request_ip_key(request)
    with _SUBMISSION_RATE_LOCK:
        events = [stamp for stamp in _SUBMISSION_RATE_EVENTS.get(ip_key, []) if stamp >= cutoff]
        if len(events) + max(int(incoming or 1), 1) > limit:
            _SUBMISSION_RATE_EVENTS[ip_key] = events
            raise HTTPException(
                status_code=429,
                detail=(
                    f"提交过于频繁。公开试用阶段同一网络在 {int(window_seconds)} 秒内"
                    f"最多提交 {limit} 个任务，请稍后再试。"
                ),
            )
        events.extend([now] * max(int(incoming or 1), 1))
        _SUBMISSION_RATE_EVENTS[ip_key] = events


def _path_size_mb(path: Path | str) -> float | None:
    try:
        return _file_size_mb(Path(path).stat().st_size)
    except OSError:
        return None


def _source_fingerprint(content: bytes, filename: str | None = None) -> dict[str, Any]:
    """Return a content fingerprint for comparing reruns without storing content."""
    return {
        "algorithm": "sha256",
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_filename": filename,
        "source_size_bytes": len(content),
    }


def _source_fingerprint_for_path(path: Path | str, filename: str | None = None) -> dict[str, Any]:
    hasher = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    return {
        "algorithm": "sha256",
        "sha256": hasher.hexdigest(),
        "source_filename": filename,
        "source_size_bytes": size,
    }


def _persist_source_file(task_id: str, suffix: str, content: bytes) -> Path:
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix or '.bin'}"
    target.write_bytes(content)
    return target


def _new_guest_trial_token() -> str:
    return uuid.uuid4().hex


def _guest_client_id(token: str) -> str:
    return f"guest_{_normalize_client_id(token) or _new_guest_trial_token()}"


def _request_guest_token(request: Request) -> str:
    return (
        request.headers.get(GUEST_TRIAL_TOKEN_HEADER)
        or request.query_params.get("guest_token")
        or ""
    ).strip()


def _is_guest_trial_job(job: dict[str, Any] | None) -> bool:
    metadata = job.get("metadata") if job else None
    return bool(isinstance(metadata, dict) and isinstance(metadata.get("guest_trial"), dict))


def _guest_metadata(job: dict[str, Any] | None) -> dict[str, Any]:
    metadata = job.get("metadata") if job else None
    guest = metadata.get("guest_trial") if isinstance(metadata, dict) else None
    return guest if isinstance(guest, dict) else {}


def _guest_trial_jobs(statuses: set[str] | None = None) -> list[dict[str, Any]]:
    jobs = [job for job in list_jobs(limit=200) if _is_guest_trial_job(job)]
    if statuses is not None:
        jobs = [job for job in jobs if str(job.get("status") or "") in statuses]
    return sorted(jobs, key=lambda item: str(item.get("created_at") or item.get("updated_at") or ""))


def _guest_active_jobs() -> list[dict[str, Any]]:
    return _guest_trial_jobs({"queued", "running"})


def _guest_wait_estimate(people_ahead: int) -> dict[str, int]:
    low, high = _guest_wait_estimate_per_task_minutes()
    ahead = max(int(people_ahead or 0), 0)
    return {"min_minutes": ahead * low, "max_minutes": ahead * high}


def _guest_queue_snapshot(task_id: str | None = None) -> dict[str, Any]:
    active = _guest_active_jobs()
    total_capacity = _guest_active_processing_slots() + _guest_waiting_queue_limit()
    position = None
    people_ahead = len(active)
    if task_id:
        for index, job in enumerate(active):
            if job.get("task_id") == task_id:
                position = index + 1
                people_ahead = index
                break
    return {
        "active_count": len(active),
        "capacity": total_capacity,
        "active_processing_slots": _guest_active_processing_slots(),
        "waiting_queue_limit": _guest_waiting_queue_limit(),
        "queue_full": len(active) >= total_capacity,
        "position": position,
        "people_ahead": people_ahead,
        "estimated_wait": _guest_wait_estimate(people_ahead),
    }


def _guest_trial_status_payload(job: dict[str, Any] | None = None) -> dict[str, Any]:
    result = dict(job.get("result") or {}) if job else None
    return {
        "enabled": _guest_trial_enabled(),
        "config": _guest_trial_config(),
        "queue": _guest_queue_snapshot(job.get("task_id") if job else None),
        "job": job,
        "result": result,
    }


def _enforce_guest_trial_enabled() -> None:
    if not _guest_trial_enabled():
        raise HTTPException(status_code=403, detail="访客试用暂未开放。")


def _enforce_guest_queue_capacity() -> None:
    snapshot = _guest_queue_snapshot()
    if snapshot["queue_full"]:
        raise HTTPException(
            status_code=429,
            detail="当前试用人数较多。为了保证生成质量，访客队列暂时已满，请稍后再试。",
        )


def _guest_daily_usage_for_ip(ip_key: str) -> int:
    count = 0
    for job in _guest_trial_jobs():
        guest = _guest_metadata(job)
        if guest.get("ip_key") != ip_key:
            continue
        if _job_created_today(job):
            count += 1
    return count


def _enforce_guest_daily_ip_limit(request: Request) -> None:
    limit = _guest_daily_trials_per_ip()
    if limit <= 0:
        return
    ip_key = _request_ip_key(request)
    used = _guest_daily_usage_for_ip(ip_key)
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"今天这个网络已使用 {used} 次访客试用额度。当前每日上限为 {limit} 次，请明天再试。",
        )


def _guest_job_for_request(request: Request, task_id: str) -> dict[str, Any]:
    token = _request_guest_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing guest trial token")
    job = get_job(task_id, client_id=_guest_client_id(token))
    if not job or _guest_metadata(job).get("token") != token:
        raise HTTPException(status_code=404, detail="Guest trial job not found")
    return job


def _copy_source_file(task_id: str, suffix: str, source_path: Path | str) -> Path:
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix or '.mp4'}"
    tmp = target_dir / f".source.{uuid.uuid4().hex}.tmp"
    shutil.copyfile(str(source_path), tmp)
    tmp.replace(target)
    return target


def _find_source_file(task_id: str) -> Path | None:
    if not task_id:
        return None
    target_dir = _source_storage_dir() / task_id
    if not target_dir.is_dir():
        return None
    candidates = sorted(path for path in target_dir.glob("source.*") if path.is_file())
    return candidates[0] if candidates else None


def _remove_tree(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return True
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def _cleanup_task_source_files(task_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    removed: list[str] = []
    source_dir = _source_storage_dir() / task_id
    if _remove_tree(source_dir):
        removed.append(str(source_dir))

    video_source = (metadata or {}).get("video_source")
    if isinstance(video_source, dict):
        for key in ("file_path", "metadata_path"):
            raw_path = str(video_source.get(key) or "").strip()
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if _remove_tree(path):
                removed.append(str(path))
    return {
        "source_retention_status": "deleted" if removed else "not_found",
        "source_retention_removed_paths": removed,
        "source_retention_cleaned_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _cleanup_task_all_files(task_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    cleanup = _cleanup_task_source_files(task_id, metadata)
    removed = list(cleanup.get("source_retention_removed_paths") or [])
    for path in (
        _artifact_storage_dir() / task_id,
    ):
        if _remove_tree(path):
            removed.append(str(path))
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    for folder, pattern in (
        (_edited_transcript_dir(), f"*__{task_suffix}_edited.txt"),
        (_transcript_edit_records_dir(), f"*__{task_suffix}_edit_records.json"),
    ):
        if folder.is_dir():
            for path in folder.glob(pattern):
                if _remove_tree(path):
                    removed.append(str(path))
    cleanup["source_retention_removed_paths"] = removed
    cleanup["history_retention_status"] = "deleted" if removed else "not_found"
    return cleanup


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


def _enforce_history_retention(client_id: str | None) -> dict[str, Any]:
    if not client_id:
        return {"pruned_count": 0, "task_ids": []}
    keep_count = _history_retention_per_client()
    retention_days = _artifact_retention_days()
    if keep_count <= 0 and retention_days <= 0:
        return {"pruned_count": 0, "task_ids": []}

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
        if retention_days > 0
        else None
    )
    jobs = list_jobs_for_retention(client_id=client_id)
    pruned_task_ids: list[str] = []
    for index, job in enumerate(jobs):
        task_id = str(job.get("task_id") or "")
        if not task_id or job.get("status") not in {"completed", "failed", "cancelled"}:
            continue
        too_many = keep_count > 0 and index >= keep_count
        updated_at = _parse_job_time(job.get("updated_at") or job.get("created_at"))
        too_old = cutoff is not None and updated_at is not None and updated_at < cutoff
        if too_many or too_old:
            _cleanup_task_all_files(task_id, job.get("metadata"))
            pruned_task_ids.append(task_id)

    if pruned_task_ids:
        delete_jobs(pruned_task_ids, client_id=client_id)
    return {"pruned_count": len(pruned_task_ids), "task_ids": pruned_task_ids}


def _import_text(value: Any, max_chars: int) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > max_chars:
        raise HTTPException(status_code=413, detail="Imported history entry is too large.")
    return text


def _import_segments(value: Any, max_segments: int = 5000) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    clean: list[dict[str, Any]] = []
    for item in value[:max_segments]:
        if not isinstance(item, dict):
            continue
        segment: dict[str, Any] = {}
        for key in ("start", "end"):
            try:
                segment[key] = float(item[key])
            except Exception:
                pass
        text = str(item.get("text") or "").strip()
        if text:
            segment["text"] = text[:5000]
        if segment:
            clean.append(segment)
    return clean


def _import_number(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalize_import_entry(entry: dict[str, Any], max_chars: int) -> dict[str, Any] | None:
    raw_result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
    original_task_id = str(
        raw_result.get("task_id") or entry.get("task_id") or entry.get("taskId") or ""
    ).strip()
    filename = str(
        raw_result.get("filename")
        or raw_result.get("source_filename")
        or entry.get("name")
        or entry.get("source_filename")
        or "Imported transcript"
    ).strip()[:240]
    transcript_text = _import_text(
        raw_result.get("transcript_text")
        or raw_result.get("cleaned_transcript_text")
        or entry.get("transcriptText")
        or "",
        max_chars,
    )
    summary_markdown = _import_text(
        raw_result.get("summary_markdown") or entry.get("summary") or "",
        max_chars,
    )
    segments = _import_segments(raw_result.get("segments") or entry.get("segments"))
    if not transcript_text and segments:
        transcript_text = "\n".join(str(seg.get("text") or "") for seg in segments if seg.get("text"))[:max_chars]
    if not transcript_text and not summary_markdown:
        return None

    source_fingerprint = str(
        raw_result.get("source_fingerprint") or entry.get("sourceFingerprint") or ""
    ).strip()[:128] or None
    audio_duration = _import_number(raw_result.get("audio_duration_seconds") or entry.get("audioDurationSec"))
    stt_elapsed = _import_number(raw_result.get("stt_elapsed_seconds") or entry.get("sttElapsedSec"))
    timestamp_raw = entry.get("timestamp") or raw_result.get("timestamp")
    try:
        imported_timestamp = int(float(timestamp_raw)) if timestamp_raw else None
    except Exception:
        imported_timestamp = None

    result: dict[str, Any] = {
        "status": "completed",
        "filename": filename,
        "source": raw_result.get("source") or entry.get("source") or "imported_local_history",
        "transcript_text": transcript_text,
        "segments": segments,
        "summary_markdown": summary_markdown,
        "summary_skipped": bool(raw_result.get("summary_skipped") or entry.get("summarySkipped")),
        "summary_status": raw_result.get("summary_status") or entry.get("summaryStatus") or ("completed" if summary_markdown else "skipped"),
        "audio_duration_seconds": audio_duration or 0,
        "stt_elapsed_seconds": stt_elapsed or 0,
        "stt_provider": raw_result.get("stt_provider") or entry.get("sttProvider"),
        "stt_provider_label": raw_result.get("stt_provider_label") or entry.get("sttProviderLabel"),
        "stt_model": raw_result.get("stt_model") or entry.get("sttModel"),
        "stt_speed": raw_result.get("stt_speed") or entry.get("sttSpeed"),
        "stt_language": raw_result.get("stt_language") or entry.get("sttLanguage"),
        "detected_language": raw_result.get("detected_language") or entry.get("detectedLanguage"),
        "source_fingerprint": source_fingerprint,
        "source_file_available": False,
        "playback_audio_available": False,
        "imported_from_local_history": True,
        "original_task_id": original_task_id or None,
    }
    if raw_result.get("transcript_edited") or entry.get("transcriptEdited"):
        result["transcript_edited"] = True
        result["transcript_edited_at"] = raw_result.get("transcript_edited_at") or entry.get("transcriptEditedAt")
        result["transcript_edit_records"] = raw_result.get("transcript_edit_records") or entry.get("transcriptEditRecords") or []
    return {
        "original_task_id": original_task_id or None,
        "source_fingerprint": source_fingerprint,
        "filename": filename,
        "imported_timestamp": imported_timestamp,
        "source": result["source"],
        "result": {k: v for k, v in result.items() if v is not None},
        "source_file_size_mb": _import_number(entry.get("source_file_size_mb") or entry.get("sourceFileSizeMb")),
    }


def _existing_import_keys(client_id: str) -> set[str]:
    keys: set[str] = set()
    for job in list_jobs_for_retention(client_id=client_id):
        task_id = str(job.get("task_id") or "")
        metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        for value in (
            task_id,
            metadata.get("original_task_id"),
            metadata.get("source_fingerprint"),
            result.get("original_task_id"),
            result.get("source_fingerprint"),
        ):
            if value:
                keys.add(str(value))
    return keys


def _import_task_id(account_id: str, entry: dict[str, Any]) -> str:
    source = "|".join(
        str(value or "")
        for value in (
            account_id,
            entry.get("original_task_id"),
            entry.get("source_fingerprint"),
            entry.get("filename"),
            entry.get("imported_timestamp"),
        )
    )
    return f"imported_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:24]}"


def _local_history_export_allowed(request: Request) -> bool:
    if not _cloud_workspace_enabled():
        return False
    client_host = (request.client.host if request.client else "") or ""
    url_host = request.url.hostname or ""
    allowed = {"127.0.0.1", "localhost", "::1", "testclient"}
    return client_host in allowed or url_host in allowed


def _finalize_completed_result_storage(task_id: str, result: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    next_result = dict(result)
    artifacts = dict(next_result.get("artifacts") or {})
    if artifacts.get("playback_audio"):
        next_result["playback_audio_available"] = True
    cleanup = _cleanup_task_source_files(task_id, metadata)
    next_result["source_file_available"] = False
    next_result.update({
        key: value
        for key, value in cleanup.items()
        if key != "source_retention_removed_paths"
    })
    return next_result


def _safe_filename_stem(value: str | None, fallback: str = "transcript") -> str:
    raw_stem = Path(value or fallback).stem or fallback
    safe_stem = "".join(
        ch if ch.isalnum() or ch in {" ", "-", "_", "."} else "_"
        for ch in raw_stem
    ).strip(" ._")
    return (safe_stem or fallback)[:96]


def _format_backup_timestamp(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_edited_transcript_backup(transcript: str, segments: list[dict[str, Any]]) -> str:
    usable_segments = [
        segment for segment in segments
        if isinstance(segment, dict) and str(segment.get("text") or "").strip()
    ]
    if not usable_segments:
        return transcript.rstrip() + "\n"
    lines = [
        f"[{_format_backup_timestamp(segment.get('start'))}] {str(segment.get('text') or '').strip()}"
        for segment in usable_segments
    ]
    return "\n".join(lines).rstrip() + "\n"


def _artifact_url(task_id: str, kind: str) -> str:
    return f"/jobs/{task_id}/artifacts/{kind}"


def _artifact_filename(result: dict[str, Any], suffix: str) -> str:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback="transcript")
    return f"{stem}{suffix}"


def _format_subtitle_timestamp(seconds: Any, *, separator: str) -> str:
    try:
        value = max(0.0, float(seconds))
    except (TypeError, ValueError):
        value = 0.0
    total = int(value)
    millis = int(round((value - total) * 1000))
    if millis >= 1000:
        total += 1
        millis -= 1000
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _format_srt(segments: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_subtitle_timestamp(segment.get("start"), separator=",")
        end = _format_subtitle_timestamp(segment.get("end"), separator=",")
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks).rstrip() + ("\n" if blocks else "")


def _format_vtt(segments: list[dict[str, Any]]) -> str:
    blocks = ["WEBVTT\n"]
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_subtitle_timestamp(segment.get("start"), separator=".")
        end = _format_subtitle_timestamp(segment.get("end"), separator=".")
        blocks.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(blocks).rstrip() + "\n"


def _write_text_artifact(task_id: str, kind: str, filename: str, content: str) -> dict[str, Any]:
    target_dir = _artifact_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    tmp = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {
        "kind": kind,
        "filename": filename,
        "url": _artifact_url(task_id, kind),
        "size_bytes": path.stat().st_size,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _write_file_artifact(task_id: str, kind: str, filename: str, source_path: Path | str) -> dict[str, Any]:
    target_dir = _artifact_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    tmp = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(str(source_path), tmp)
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {
        "kind": kind,
        "filename": filename,
        "url": _artifact_url(task_id, kind),
        "size_bytes": path.stat().st_size,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _attach_playback_audio_artifact(task_id: str, result: dict[str, Any], audio_path: Path | str) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.is_file():
        return result
    try:
        artifact = _write_file_artifact(
            task_id,
            "playback_audio",
            _artifact_filename(result, "_audio.mp3"),
            path,
        )
    except Exception as exc:
        logger.warning("Playback audio artifact write failed for %s: %s", task_id, exc)
        return result
    next_result = dict(result)
    artifacts = dict(next_result.get("artifacts") or {})
    artifacts["playback_audio"] = artifact
    next_result["artifacts"] = artifacts
    next_result["playback_audio_available"] = True
    return next_result


def _write_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    transcript = str(result.get("transcript_text") or "").strip()
    segments = _sanitize_edit_segments(result.get("segments"))
    if transcript:
        artifacts["transcript_txt"] = _write_text_artifact(
            task_id,
            "transcript_txt",
            _artifact_filename(result, ".txt"),
            transcript.rstrip() + "\n",
        )
    if segments:
        artifacts["transcript_srt"] = _write_text_artifact(
            task_id,
            "transcript_srt",
            _artifact_filename(result, ".srt"),
            _format_srt(segments),
        )
        artifacts["transcript_vtt"] = _write_text_artifact(
            task_id,
            "transcript_vtt",
            _artifact_filename(result, ".vtt"),
            _format_vtt(segments),
        )
    summary = str(result.get("summary_markdown") or "").strip()
    if summary:
        artifacts["summary_md"] = _write_text_artifact(
            task_id,
            "summary_md",
            _artifact_filename(result, "_summary.md"),
            summary.rstrip() + "\n",
        )
    return artifacts


def _attach_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        artifacts = _write_result_artifacts(task_id, result)
    except Exception as exc:
        logger.warning("Result artifact write failed for %s: %s", task_id, exc)
        return result
    if not artifacts:
        return result
    next_result = dict(result)
    next_result["artifacts"] = {**dict(result.get("artifacts") or {}), **artifacts}
    return next_result


def _write_edited_transcript_backup(task_id: str, result: dict[str, Any]) -> Path:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback=task_id or "transcript")
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _edited_transcript_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edited.txt"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    content = _format_edited_transcript_backup(
        str(result.get("transcript_text") or ""),
        _sanitize_edit_segments(result.get("segments")),
    )
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def _sanitize_edit_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    allowed_keys = {
        "index",
        "start",
        "end",
        "before",
        "after",
        "previous_before",
        "next_before",
        "previous_after",
        "next_after",
        "created_at",
    }
    for item in value[:500]:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for key in allowed_keys:
            if key not in item:
                continue
            raw = item.get(key)
            if key in {"index"}:
                try:
                    record[key] = int(raw)
                except (TypeError, ValueError):
                    record[key] = 0
            elif key in {"start", "end"}:
                try:
                    record[key] = float(raw)
                except (TypeError, ValueError):
                    record[key] = 0.0
            else:
                record[key] = str(raw or "")[:4000]
        if str(record.get("before") or "").strip() != str(record.get("after") or "").strip():
            records.append(record)
    return records


def _write_transcript_edit_records_backup(task_id: str, result: dict[str, Any], records: list[dict[str, Any]]) -> Path:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback=task_id or "transcript")
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _transcript_edit_records_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edit_records.json"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "task_id": task_id,
        "source_filename": result.get("filename") or result.get("source_filename"),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "record_count": len(records),
        "records": records,
    }
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def _wav_duration_seconds(path: Path | str) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return None
            return wav.getnframes() / frame_rate
    except Exception:
        return None


def _media_duration_seconds(path: Path | str) -> float | None:
    wav_duration = _wav_duration_seconds(path)
    if wav_duration is not None:
        return wav_duration
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = float((result.stdout or "").strip())
        return value if value > 0 else None
    except Exception:
        return None


def _text_len(value: str | None) -> int:
    return len(value or "")


def _sanitize_edit_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    segments: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        segment: dict[str, Any] = {"text": text}
        for key in ("start", "end"):
            try:
                segment[key] = float(item.get(key) or 0)
            except (TypeError, ValueError):
                segment[key] = 0.0
        if item.get("speaker"):
            segment["speaker"] = str(item.get("speaker"))
        segments.append(segment)
    return segments


def _metadata(**values: Any) -> dict[str, Any]:
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        **{k: v for k, v in values.items() if v is not None},
    }


def _job_metadata_for_update(task_id: str, client_id: str | None, **values: Any) -> dict[str, Any]:
    existing = get_job(task_id, client_id=client_id) if task_id else None
    current = existing.get("metadata") if existing else None
    base = current if isinstance(current, dict) else {}
    return {**base, **_metadata(**values)}


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


@lru_cache(maxsize=1)
def _ffmpeg_version() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        completed = subprocess.run(
            [ffmpeg, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    first_line = (completed.stdout or completed.stderr or "").splitlines()
    return first_line[0][:160] if first_line else None


@lru_cache(maxsize=1)
def _runtime_context_metadata() -> dict[str, Any]:
    return _metadata(
        runtime_os=platform.system(),
        runtime_machine=platform.machine(),
        runtime_cpu_count=os.cpu_count(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        faster_whisper_version=_package_version("faster-whisper"),
        ctranslate2_version=_package_version("ctranslate2"),
        ffmpeg_version=_ffmpeg_version(),
    )


def _stt_realtime_factor(stt_elapsed_seconds: float | None, duration_seconds: float | None) -> float | None:
    if not stt_elapsed_seconds or not duration_seconds or duration_seconds <= 0:
        return None
    return max(round(stt_elapsed_seconds / duration_seconds, 4), 0.0001)


def _canonical_stt_provider(value: str | None) -> str:
    provider = (value or "").strip().lower().replace("-", "_")
    if provider in {"azure", "azure_batch", "azure_blob", "azure_speech_batch", "azure_fast", "azure_speech"}:
        return "azure_batch"
    if provider in {"local", "faster_whisper", "faster-whisper", "whisper"}:
        return "local"
    return "local"


def _request_can_use_local_stt(request: Request | None = None) -> bool:
    if not _public_mode_enabled():
        return True
    if request is None:
        return False
    if _request_is_internal_queue(request):
        return True
    url_host = (request.url.hostname or "").strip().lower()
    return url_host in {"127.0.0.1", "localhost", "::1", "testclient"}


def _allowed_stt_providers(request: Request | None = None) -> tuple[str, ...]:
    raw = os.environ.get("FLUENTFLOW_ALLOWED_STT_PROVIDERS")
    if raw is None or not raw.strip():
        return ("azure_batch", "local") if _request_can_use_local_stt(request) else ("azure_batch",)
    providers: list[str] = []
    for item in raw.split(","):
        provider = _canonical_stt_provider(item)
        if provider in {"azure_batch", "local"} and provider not in providers:
            providers.append(provider)
    if _public_mode_enabled() and not _request_can_use_local_stt(request):
        providers = [provider for provider in providers if provider != "local"]
    return tuple(providers) or (("azure_batch", "local") if _request_can_use_local_stt(request) else ("azure_batch",))


def _default_stt_provider(request: Request | None = None) -> str:
    requested = _canonical_stt_provider(os.environ.get("FLUENTFLOW_DEFAULT_STT_PROVIDER") or "azure_batch")
    allowed = _allowed_stt_providers(request)
    return requested if requested in allowed else allowed[0]


def _normalize_stt_provider(value: str | None, request: Request | None = None) -> str:
    provider = _canonical_stt_provider(value) if value else _default_stt_provider(request)
    allowed = _allowed_stt_providers(request)
    return provider if provider in allowed else _default_stt_provider(request)


def _stt_provider_label(provider: str) -> str:
    if provider == "azure_batch":
        return "Cloud Transcription"
    return "faster-whisper"


def _lark_export_target(lark_via_cli: Optional[str]) -> str:
    return "lark_cli" if _truthy_form(lark_via_cli) else "lark_openapi"


def _pipeline_mode(source_type: str | None) -> str | None:
    if source_type == "transcript_file":
        return "transcript_file"
    if source_type in {"audio", "video"}:
        return "audio_video"
    return None


def _elapsed_since(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def _log_task_completed(
    *,
    task_id: str,
    started_at: float,
    final_status: str,
    source_type: str | None = None,
    source_filename: str | None = None,
    source_duration_seconds: float | None = None,
    source_file_size_mb: float | None = None,
    transcript_length: int | None = None,
    summary_length: int | None = None,
    summary_status: str | None = None,
    lark_requested: bool | None = None,
    lark_success: bool | None = None,
    stt_provider: str | None = None,
    completion_reason: str | None = None,
) -> None:
    total_duration = _elapsed_since(started_at)
    log_event(
        task_id=task_id,
        event_name="task_completed",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        source_file_size_mb=source_file_size_mb,
        transcript_length=transcript_length,
        summary_length=summary_length,
        stage="done" if final_status == "completed" else final_status,
        duration_seconds=total_duration,
        success=final_status == "completed",
        metadata=_metadata(
            **_runtime_context_metadata(),
            final_status=final_status,
            total_duration_seconds=total_duration,
            summary_status=summary_status,
            lark_requested=lark_requested,
            lark_success=lark_success,
            stt_provider=stt_provider,
            stt_provider_label=_stt_provider_label(stt_provider) if stt_provider else None,
            source_type=source_type,
            pipeline_mode=_pipeline_mode(source_type),
            completion_reason=completion_reason,
        ),
    )


CLIENT_EVENT_NAMES = {
    "summary_downloaded",
    "transcript_downloaded",
    "task_cancelled",
}


def _ai_kwargs(
    *,
    deepseek_api_key: Optional[str],
    openai_api_key: Optional[str],
    ai_provider: Optional[str],
    ai_model: Optional[str],
    system_prompt: Optional[str],
    note_mode: Optional[str] = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    provider_name = (ai_provider or "").strip()
    resolved_openai_key = resolve_secret(openai_api_key, "openai_api_key")
    resolved_deepseek_key = resolve_secret(deepseek_api_key, "deepseek_api_key")
    if not provider_name and resolved_openai_key:
        provider_name = "openai"
    if provider_name:
        kwargs["provider"] = provider_name
    if resolved_deepseek_key:
        k = resolved_deepseek_key
        kwargs["api_key"] = k
    if resolved_openai_key and provider_name.lower() == "openai":
        k = resolved_openai_key
        kwargs["api_key"] = k
    if (m := (ai_model or "").strip()):
        kwargs["model"] = m
    if (sp := (system_prompt or "").strip()):
        kwargs["system_prompt"] = sp
    if (nm := (note_mode or "").strip()):
        kwargs["note_mode"] = nm
    return kwargs


def _cleanup_payload(cleanup_result: Any) -> dict[str, Any]:
    return {
        "applied_count": cleanup_result.applied_count,
        "removed_segment_count": cleanup_result.removed_segment_count,
        "raw_length": cleanup_result.raw_length,
        "cleaned_length": cleanup_result.cleaned_length,
        "issues": [asdict(item) for item in cleanup_result.issues[:20]],
        "issue_count": len(cleanup_result.issues),
    }


_TRANSCRIPTION_QUEUE: thread_queue.Queue[dict[str, Any]] = thread_queue.Queue()
_QUEUE_THREAD: threading.Thread | None = None
_QUEUE_LOCK = threading.Lock()
_QUEUED_TASK_IDS: set[str] = set()
_QUEUE_EVENT_LOOP: asyncio.AbstractEventLoop | None = None


def _queue_timeout_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_QUEUE_PROCESS_TIMEOUT_SECONDS", "86400")), 60.0)
    except ValueError:
        return 86400.0


def _stale_job_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_STALE_JOB_SECONDS", "90000")), 60.0)
    except ValueError:
        return 90000.0


def _queue_base_url_from_request(request: Request | None = None) -> str:
    configured = (os.environ.get("FLUENTFLOW_SELF_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8000"


def _publish_job_event_from_thread(task_id: str, event: dict[str, Any]) -> None:
    loop = _QUEUE_EVENT_LOOP
    if not loop or loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(JOB_EVENTS.publish(task_id, event), loop)
    except Exception:
        logger.debug("Queue event publish failed for %s", task_id, exc_info=True)


def _multipart_process_body(
    *,
    fields: dict[str, Any],
    file_path: Path,
    filename: str,
) -> tuple[bytes, str]:
    boundary = f"----FluentFlowQueue{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value)
        if text == "":
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
            text.encode("utf-8"),
            b"\r\n",
        ])
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="file"; filename="{Path(filename).name}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _enqueue_transcription_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    if not task_id:
        return
    with _QUEUE_LOCK:
        if task_id in _QUEUED_TASK_IDS:
            return
        _QUEUED_TASK_IDS.add(task_id)
        _TRANSCRIPTION_QUEUE.put(dict(item))
        _ensure_queue_worker_started_locked()


def _queue_status_snapshot() -> dict[str, Any]:
    with _QUEUE_LOCK:
        queued_task_ids = sorted(_QUEUED_TASK_IDS)
    return {
        "worker_alive": bool(_QUEUE_THREAD and _QUEUE_THREAD.is_alive()),
        "queue_depth": int(_TRANSCRIPTION_QUEUE.qsize()),
        "tracked_task_count": len(queued_task_ids),
        "tracked_task_ids": queued_task_ids[:20],
    }


def _ensure_queue_worker_started_locked() -> None:
    global _QUEUE_THREAD
    if _QUEUE_THREAD and _QUEUE_THREAD.is_alive():
        return
    _QUEUE_THREAD = threading.Thread(
        target=_queue_worker_loop,
        name="fluentflow-transcription-queue",
        daemon=True,
    )
    _QUEUE_THREAD.start()


def _queue_worker_loop() -> None:
    while True:
        item = _TRANSCRIPTION_QUEUE.get()
        task_id = str(item.get("task_id") or "")
        try:
            _run_queued_transcription(item)
        except Exception as exc:
            logger.exception("Queued transcription failed for %s", task_id)
            if task_id:
                _release_task_quota(
                    client_id=_normalize_client_scope(str(item.get("client_id") or "")),
                    task_id=task_id,
                    reason="Queued processing failed before completion",
                    metadata={"route": "/queue/process", "stage": "queued", "raw_error": str(exc)},
                )
                friendly_error = _friendly_error_message(exc)
                upsert_job(
                    task_id=task_id,
                    status="failed",
                    client_id=_normalize_client_id(str(item.get("client_id") or "")),
                    stage="queued",
                    progress=0,
                    error_reason=friendly_error,
                )
                _publish_job_event_from_thread(
                    task_id,
                    {"stage": "error", "progress": 0, "error": friendly_error},
                )
        finally:
            if task_id:
                with _QUEUE_LOCK:
                    _QUEUED_TASK_IDS.discard(task_id)
            _TRANSCRIPTION_QUEUE.task_done()


def _run_queued_transcription(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    source_path = Path(str(item.get("source_path") or ""))
    filename = str(item.get("filename") or source_path.name or "source")
    base_url = str(item.get("base_url") or _queue_base_url_from_request()).rstrip("/")
    options = dict(item.get("options") or {})
    client_id = _normalize_client_scope(str(item.get("client_id") or ""))
    if not task_id:
        raise RuntimeError("Queued task is missing task_id")
    if not source_path.is_file():
        raise RuntimeError("Queued source file is missing")

    job = get_job(task_id)
    if job and job.get("status") in {"completed", "failed", "cancelled"}:
        return

    fields = {
        **options,
        "task_id": task_id,
        "title": options.get("title") or Path(filename).stem,
    }
    body, content_type = _multipart_process_body(fields=fields, file_path=source_path, filename=filename)
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Accept": "text/event-stream",
    }
    if client_id:
        headers["X-FluentFlow-Client-Id"] = client_id
    headers["X-FluentFlow-Internal-Queue-Token"] = INTERNAL_QUEUE_TOKEN
    tokens = _configured_access_tokens()
    if tokens:
        headers["X-FluentFlow-Access-Token"] = tokens[0]
    request = urllib.request.Request(
        f"{base_url}/process",
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=_queue_timeout_seconds()) as response:
            while response.read(64 * 1024):
                pass
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Queued processing request failed: HTTP {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Queued processing request failed: {exc.reason}") from exc


def _queue_options_from_form(
    *,
    export_to_lark: Optional[str],
    lark_via_cli: Optional[str],
    title: Optional[str],
    folder_token: Optional[str],
    deepseek_api_key: Optional[str],
    openai_api_key: Optional[str],
    ai_provider: Optional[str],
    ai_model: Optional[str],
    note_mode: Optional[str],
    skip_summary: Optional[str],
    stt_model: Optional[str],
    stt_speed: Optional[str],
    stt_language: Optional[str],
    stt_provider: Optional[str],
    azure_speech_key: Optional[str],
    azure_speech_endpoint: Optional[str],
    azure_blob_container_sas_url: Optional[str],
    speaker_diarization: Optional[str],
    lark_app_id: Optional[str],
    lark_app_secret: Optional[str],
    system_prompt: Optional[str],
) -> dict[str, str]:
    raw: dict[str, Optional[str]] = {
        "export_to_lark": export_to_lark,
        "lark_via_cli": lark_via_cli,
        "title": title,
        "folder_token": folder_token,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "note_mode": note_mode,
        "skip_summary": skip_summary,
        "stt_model": stt_model,
        "stt_speed": stt_speed,
        "stt_language": stt_language,
        "stt_provider": stt_provider,
        "azure_speech_endpoint": azure_speech_endpoint,
        "speaker_diarization": speaker_diarization,
        "system_prompt": system_prompt,
    }
    return {key: value.strip() for key, value in raw.items() if isinstance(value, str) and value.strip()}


def _queue_options_from_mapping(payload: dict[str, Any] | None) -> dict[str, str]:
    allowed = {
        "export_to_lark",
        "lark_via_cli",
        "title",
        "folder_token",
        "ai_provider",
        "ai_model",
        "note_mode",
        "skip_summary",
        "stt_model",
        "stt_speed",
        "stt_language",
        "stt_provider",
        "azure_speech_endpoint",
        "speaker_diarization",
        "system_prompt",
        "duration_limit_seconds",
    }
    result: dict[str, str] = {}
    for key, value in (payload or {}).items():
        if key not in allowed or value is None:
            continue
        text = str(value).strip()
        if text:
            result[key] = text
    return result


def _public_video_source_metadata(saved: SavedVideoSource) -> dict[str, Any]:
    return {
        "provider": saved.provider,
        "source_url": saved.source_url,
        "video_id": saved.video_id,
        "title": saved.title,
        "filename": saved.filename,
        "file_path": saved.file_path,
        "file_url": saved.file_url,
        "metadata_path": saved.metadata_path,
        "size_bytes": saved.size_bytes,
        "downloaded_at": saved.downloaded_at,
    }


def _video_source_progress_value(progress: VideoSourceProgress) -> float:
    if progress.stage == "resolving":
        return float(progress.percent or 8)
    if progress.stage == "downloading":
        pct = progress.percent if progress.percent is not None else 0
        return 10 + max(0, min(100, float(pct))) * 0.45
    if progress.stage == "saving":
        return 58
    return 0


def _run_video_source_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    input_text = str(item.get("input") or "")
    title = str(item.get("title") or "").strip() or None
    options = dict(item.get("options") or {})
    base_url = str(item.get("base_url") or _queue_base_url_from_request())
    client_id = _normalize_client_scope(str(item.get("client_id") or ""))
    if not task_id:
        return

    def on_progress(progress: VideoSourceProgress) -> None:
        upsert_job(
            task_id=task_id,
            status="running",
            client_id=client_id,
            stage=progress.stage,
            progress=_video_source_progress_value(progress),
            summary_status=progress.message,
            metadata=_metadata(
                route="/video-sources/jobs",
                queue_options=options,
                video_source_progress={
                    "message": progress.message,
                    "loaded_bytes": progress.loaded_bytes,
                    "total_bytes": progress.total_bytes,
                },
            ),
        )

    try:
        saved = download_video_source(
            input_text,
            title=title,
            video_dir=_video_source_storage_dir(),
            on_progress=on_progress,
        )
        saved_size_mb = _file_size_mb(saved.size_bytes)
        max_upload_mb = _max_upload_mb()
        if saved_size_mb is not None and saved_size_mb > max_upload_mb:
            raise RuntimeError(
                f"Downloaded video is too large: {saved_size_mb} MB. Limit is {max_upload_mb:g} MB."
            )
        _enforce_daily_quota(
            client_id,
            incoming_jobs=1,
            incoming_upload_mb=saved_size_mb,
            exclude_task_id=task_id,
        )
        _enforce_global_daily_quota(
            client_id=client_id,
            incoming_jobs=1,
            incoming_upload_mb=saved_size_mb,
            exclude_task_id=task_id,
        )
        source_path = Path(saved.file_path)
        target_path = _copy_source_file(task_id, ".mp4", source_path)
        source_fingerprint = _source_fingerprint_for_path(target_path, saved.filename)
        source_file_size_mb = _path_size_mb(target_path)
        duration_estimate_sec = _media_duration_seconds(target_path)
        quota_estimate = _estimate_processing_units(
            duration_seconds=duration_estimate_sec,
            skip_summary=_truthy_form(options.get("skip_summary")),
            estimate_only=True,
        )
        metadata = _metadata(
            route="/video-sources/jobs",
            queue_options=options,
            source_path=str(target_path),
            source_fingerprint=source_fingerprint,
            video_source=_public_video_source_metadata(saved),
        )
        quota_reservation = _reserve_task_quota(
            client_id=client_id,
            task_id=task_id,
            estimate=quota_estimate,
            reason="Video source task processing reservation",
        )
        if quota_reservation:
            metadata["quota"] = quota_reservation
        log_event(
            task_id=task_id,
            event_name="video_source_downloaded",
            source_type="video",
            source_filename=saved.filename,
            source_file_size_mb=source_file_size_mb,
            stage="queued",
            success=True,
            metadata=metadata,
        )
        upsert_job(
            task_id=task_id,
            status="queued",
            client_id=client_id,
            stage="queued",
            progress=0,
            source_type="video",
            source_filename=saved.filename,
            source_file_size_mb=source_file_size_mb,
            metadata=metadata,
        )
        enqueue_item = {
            "task_id": task_id,
            "source_path": str(target_path),
            "filename": saved.filename,
            "options": options,
            "base_url": base_url,
        }
        if client_id:
            enqueue_item["client_id"] = client_id
        _enqueue_transcription_job(enqueue_item)
    except Exception as exc:
        logger.exception("Video source job failed for %s", task_id)
        friendly_error = _friendly_error_message(exc)
        _release_task_quota(
            client_id=client_id,
            task_id=task_id,
            reason="Video source job failed",
            metadata={"route": "/video-sources/jobs", "raw_error": str(exc)},
        )
        upsert_job(
            task_id=task_id,
            status="failed",
            client_id=client_id,
            stage="failed",
            progress=100,
            source_type="video_link",
            source_filename=title or (input_text[:80] if input_text else "video link"),
            error_reason=friendly_error,
            metadata=_metadata(
                route="/video-sources/jobs",
                queue_options=options,
                raw_error=str(exc),
            ),
        )


def _start_video_source_job(item: dict[str, Any]) -> None:
    threading.Thread(
        target=_run_video_source_job,
        args=(dict(item),),
        name=f"fluentflow-video-source-{item.get('task_id') or 'job'}",
        daemon=True,
    ).start()


def _resume_queued_transcription_jobs(base_url: str | None = None) -> None:
    recovered = 0
    failed = 0
    for job in list_jobs(limit=200):
        status = job.get("status")
        raw_metadata = job.get("metadata") or {}
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        if status not in {"queued", "running"}:
            continue
        task_id = str(job.get("task_id") or "")
        source_path = Path(str(metadata.get("source_path") or ""))
        if not task_id:
            continue
        if not metadata.get("queue_options") or not metadata.get("source_path") or not source_path.is_file():
            upsert_job(
                task_id=task_id,
                status="failed",
                client_id=job.get("client_id"),
                stage="recovery",
                progress=0,
                error_reason="服务重启后无法恢复任务：原始文件已不存在，请重新上传。",
                metadata={
                    **metadata,
                    "recovery_status": "failed_missing_source",
                    "recovered_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                },
            )
            failed += 1
            continue
        upsert_job(
            task_id=task_id,
            status="queued",
            client_id=job.get("client_id"),
            stage="queued",
            progress=0,
            metadata={
                **metadata,
                "recovery_status": "requeued_after_startup",
                "recovered_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            },
        )
        _enqueue_transcription_job({
            "task_id": task_id,
            "source_path": str(source_path),
            "filename": job.get("source_filename") or source_path.name,
            "options": metadata.get("queue_options") or {},
            "base_url": base_url or _queue_base_url_from_request(),
            "client_id": job.get("client_id"),
        })
        recovered += 1
    if recovered or failed:
        logger.info("Startup queue recovery finished: recovered=%s failed=%s", recovered, failed)


@app.on_event("startup")
async def _startup_resume_queue() -> None:
    global _QUEUE_EVENT_LOOP
    _QUEUE_EVENT_LOOP = asyncio.get_running_loop()
    _resume_queued_transcription_jobs()


def _directory_usage(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path if path.exists() else path.parent)
        return {
            "path": str(path),
            "exists": path.exists(),
            "total_mb": round(usage.total / (1024 * 1024), 1),
            "used_mb": round(usage.used / (1024 * 1024), 1),
            "free_mb": round(usage.free / (1024 * 1024), 1),
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else None,
        }
    except Exception as exc:
        return {"path": str(path), "exists": path.exists(), "error": str(exc)}


def _job_monitor_snapshot() -> dict[str, Any]:
    jobs = list_jobs(limit=200)
    counts: dict[str, int] = {}
    stale_cutoff = datetime.now(timezone.utc) - timedelta(seconds=_stale_job_seconds())
    stale_jobs: list[dict[str, Any]] = []
    for job in jobs:
        status = str(job.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
        if status not in {"queued", "running"}:
            continue
        updated_at = _parse_job_time(job.get("updated_at") or job.get("created_at"))
        if updated_at is not None and updated_at < stale_cutoff:
            stale_jobs.append({
                "task_id": job.get("task_id"),
                "status": status,
                "stage": job.get("stage"),
                "updated_at": job.get("updated_at"),
                "source_filename": job.get("source_filename"),
            })
    return {
        "recent_count": len(jobs),
        "status_counts": counts,
        "active_count": counts.get("queued", 0) + counts.get("running", 0),
        "stale_after_seconds": _stale_job_seconds(),
        "stale_count": len(stale_jobs),
        "stale_jobs": stale_jobs[:20],
    }


def _ops_status_payload() -> dict[str, Any]:
    credentials = credential_status()
    queue_snapshot = _queue_status_snapshot()
    job_snapshot = _job_monitor_snapshot()
    storage = {
        "sources": _directory_usage(_source_storage_dir()),
        "artifacts": _directory_usage(_artifact_storage_dir()),
        "edited_transcripts": _directory_usage(_edited_transcript_dir()),
        "transcript_edit_records": _directory_usage(_transcript_edit_records_dir()),
        "video_sources": _directory_usage(_video_source_storage_dir()),
    }
    warnings: list[str] = []
    failures: list[str] = []
    if job_snapshot["stale_count"]:
        warnings.append(f"{job_snapshot['stale_count']} 个任务长时间未更新")
    for name, item in storage.items():
        used_percent = item.get("used_percent")
        if isinstance(used_percent, (int, float)):
            if used_percent >= 95:
                failures.append(f"{name} 所在磁盘使用率 {used_percent}%")
            elif used_percent >= 85:
                warnings.append(f"{name} 所在磁盘使用率 {used_percent}%")
    if _public_mode_enabled():
        for key, label in (
            ("azure_speech_endpoint_configured", "Azure Speech endpoint"),
            ("azure_speech_key_configured", "Azure Speech key"),
            ("azure_blob_container_sas_url_configured", "Azure Blob SAS"),
        ):
            if not credentials.get(key):
                failures.append(f"缺少 {label}")
        if not (credentials.get("deepseek_api_key_configured") or credentials.get("openai_api_key_configured")):
            failures.append("缺少摘要模型 Key")
    user_count: int | None = None
    if _account_auth_enabled():
        try:
            user_count = count_users()
        except Exception as exc:
            failures.append(f"账号数据库不可读：{exc}")
    status = "fail" if failures else ("warn" if warnings else "ok")
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "public_mode": _public_mode_enabled(),
        "account_auth_enabled": _account_auth_enabled(),
        "user_count": user_count,
        "queue": queue_snapshot,
        "jobs": job_snapshot,
        "storage": storage,
        "credentials": credentials,
        "warnings": warnings,
        "failures": failures,
    }


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "runtime": _runtime_context_metadata(),
        "limits": _runtime_limits_for_request(request),
    }


@app.get("/ops/status")
def ops_status() -> dict[str, Any]:
    return _ops_status_payload()


@app.get("/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    if _account_auth_enabled():
        user = _request_account_user(request)
        return {
            "auth_mode": "accounts",
            "account_required": True,
            "authenticated": bool(user),
            "allow_signups": _account_registration_allowed(),
            "bootstrap_required": count_users() == 0,
            "user": _public_account_payload(user),
            "guest_trial": _guest_trial_config(),
        }
    return {
        "access_required": _access_control_enabled(),
        "authenticated": (not _access_control_enabled()) or _request_has_access(request),
        "guest_trial": _guest_trial_config(),
    }


@app.post("/auth/login")
def auth_login(
    request: Request,
    response: Response,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    if _account_auth_enabled():
        email = _validate_account_email(str(payload.get("email") or ""))
        password = str(payload.get("password") or "")
        user = authenticate_user(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="邮箱或密码不正确")
        token = create_session(
            str(user["id"]),
            days=_session_days(),
            user_agent=request.headers.get("user-agent"),
            ip_address=_request_ip_key(request),
        )
        _set_session_cookie(response, token)
        return {
            "ok": True,
            "auth_mode": "accounts",
            "account_required": True,
            "user": _public_account_payload(user),
        }

    token = str(payload.get("access_token") or payload.get("token") or "").strip()
    if not _access_control_enabled():
        return {"ok": True, "access_required": False}
    if not token or not any(hmac.compare_digest(token, configured) for configured in _configured_access_tokens()):
        raise HTTPException(status_code=401, detail="Invalid access code")
    response.set_cookie(
        key="fluentflow_access_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=_cookie_secure_enabled(),
        samesite="lax",
    )
    return {"ok": True, "access_required": True}


@app.post("/auth/register")
def auth_register(
    request: Request,
    response: Response,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    if not _account_auth_enabled():
        raise HTTPException(status_code=404, detail="Account auth is not enabled")
    if not _account_registration_allowed():
        raise HTTPException(status_code=403, detail="当前未开放注册，请联系产品维护者创建账号")
    email = _validate_account_email(str(payload.get("email") or ""))
    password = _validate_account_password(str(payload.get("password") or ""))
    first_user = count_users() == 0
    try:
        user = create_user(email, password, role="admin" if first_user else "user")
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="这个邮箱已经注册") from exc
        raise
    _grant_starter_balance_if_needed(user)
    token = create_session(
        str(user["id"]),
        days=_session_days(),
        user_agent=request.headers.get("user-agent"),
        ip_address=_request_ip_key(request),
    )
    _set_session_cookie(response, token)
    return {
        "ok": True,
        "auth_mode": "accounts",
        "account_required": True,
        "user": _public_account_payload(user),
        "bootstrap_admin": first_user,
    }


@app.post("/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    if _account_auth_enabled():
        revoke_session(_request_account_session_token(request))
        response.delete_cookie(SESSION_COOKIE_NAME, samesite="lax")
    response.delete_cookie("fluentflow_access_token", samesite="lax")
    return {"ok": True}


@app.get("/account/quota")
def account_quota(request: Request) -> dict[str, Any]:
    user = _require_account_user(request)
    return _account_quota_payload(user)


@app.post("/account/import-history")
def import_account_history(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    user = _require_account_user(request)
    client_id = _request_client_scope(request)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="entries must be a list")

    max_entries = max(1, min(int(os.environ.get("FLUENTFLOW_IMPORT_HISTORY_MAX_ENTRIES", "100")), 300))
    max_chars = max(1000, int(os.environ.get("FLUENTFLOW_IMPORT_HISTORY_MAX_CHARS", "1000000")))
    existing_keys = _existing_import_keys(client_id)
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for raw_entry in entries[:max_entries]:
        if not isinstance(raw_entry, dict):
            skipped.append({"reason": "invalid_entry"})
            continue
        normalized = _normalize_import_entry(raw_entry, max_chars=max_chars)
        if not normalized:
            skipped.append({"reason": "empty_result"})
            continue
        dedupe_keys = {
            str(value)
            for value in (normalized.get("original_task_id"), normalized.get("source_fingerprint"))
            if value
        }
        if dedupe_keys & existing_keys:
            skipped.append({
                "reason": "duplicate",
                "original_task_id": normalized.get("original_task_id"),
                "filename": normalized.get("filename"),
            })
            continue

        task_id_value = _import_task_id(str(user["id"]), normalized)
        if task_id_value in existing_keys or get_job(task_id_value, client_id=client_id):
            skipped.append({
                "reason": "duplicate",
                "original_task_id": normalized.get("original_task_id"),
                "filename": normalized.get("filename"),
            })
            continue

        result = dict(normalized["result"])
        result["task_id"] = task_id_value
        result = _attach_result_artifacts(task_id_value, result)
        metadata = _metadata(
            source_type="imported_local_history",
            original_task_id=normalized.get("original_task_id"),
            source_fingerprint=normalized.get("source_fingerprint"),
            imported_by_account_id=str(user["id"]),
            imported_timestamp=normalized.get("imported_timestamp"),
        )
        upsert_job(
            task_id=task_id_value,
            status="completed",
            client_id=client_id,
            stage="done",
            progress=100,
            source_type=str(normalized.get("source") or "imported_local_history"),
            source_filename=str(normalized.get("filename") or "Imported transcript"),
            source_file_size_mb=normalized.get("source_file_size_mb"),
            summary_status=result.get("summary_status") or "completed",
            result=result,
            metadata=metadata,
        )
        job = get_job(task_id_value, client_id=client_id)
        if job:
            imported.append(job)
        existing_keys.add(task_id_value)
        existing_keys.update(dedupe_keys)

    return {
        "ok": True,
        "imported_count": len(imported),
        "skipped_count": len(skipped),
        "imported": imported,
        "skipped": skipped,
    }


@app.get("/admin/users")
def admin_list_users(request: Request, limit: int = 100) -> dict[str, Any]:
    _require_admin_user(request)
    users = []
    for user in list_users(limit=limit):
        public = _public_account_payload(user)
        if public:
            users.append(public)
    return {"users": users}


@app.post("/admin/users/{user_id}/balance-adjustments")
def admin_adjust_user_balance(
    request: Request,
    user_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    admin = _require_admin_user(request)
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        units = int(payload.get("units") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="units must be an integer") from None
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    provider_reference = str(payload.get("provider_reference") or "").strip() or None
    try:
        tx = add_admin_adjustment(
            user_id,
            units=units,
            reason=reason,
            admin_account_id=str(admin["id"]),
            provider_reference=provider_reference,
            metadata={"route": "/admin/users/{user_id}/balance-adjustments"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "transaction": tx,
        "user": _public_account_payload(target),
    }


@app.get("/credentials/status")
def get_credentials_status() -> dict[str, Any]:
    return credential_status()


@app.get("/runtime-config")
def runtime_config(request: Request) -> dict[str, Any]:
    allowed = list(_allowed_stt_providers(request))
    return {
        "public_mode": _public_mode_enabled(),
        "auth_mode": "accounts" if _account_auth_enabled() else ("access_code" if _access_control_enabled() else "open"),
        "allowed_stt_providers": allowed,
        "default_stt_provider": _default_stt_provider(request),
        "show_maintainer_settings": not _public_mode_enabled(),
        "limits": _runtime_limits_for_request(request),
        "guest_trial": _guest_trial_config(),
    }


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/speaker-diarization/status")
def get_speaker_diarization_status() -> dict[str, Any]:
    return diarization_status()


@app.get("/guest-trial/status")
def guest_trial_status(request: Request, task_id: Optional[str] = None) -> dict[str, Any]:
    _enforce_guest_trial_enabled()
    if task_id:
        job = _guest_job_for_request(request, task_id)
        return _guest_trial_status_payload(job)
    return _guest_trial_status_payload()


@app.post("/guest-trial/heartbeat")
def guest_trial_heartbeat(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _enforce_guest_trial_enabled()
    task_id = str(payload.get("task_id") or request.query_params.get("task_id") or "").strip()
    if task_id:
        job = _guest_job_for_request(request, task_id)
        return _guest_trial_status_payload(job)
    return _guest_trial_status_payload()


@app.post("/guest-trial/process")
async def guest_trial_process(
    request: Request,
    file: UploadFile = File(...),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    stt_provider: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
) -> dict[str, Any]:
    _enforce_guest_trial_enabled()
    _enforce_guest_queue_capacity()
    _enforce_guest_daily_ip_limit(request)
    _enforce_submission_rate_limit(request, incoming=1)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in ALLOWED_SUFFIXES or suffix in TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    source_file_size_mb = _upload_size_mb(file)
    effective_limit_mb = min(_max_upload_mb(), _guest_file_limit_mb())
    if source_file_size_mb is not None and source_file_size_mb > effective_limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"访客试用支持 {effective_limit_mb:g} MB 以内的单个音视频文件。",
        )

    content = await file.read()
    source_file_size_mb = _file_size_mb(len(content))
    if source_file_size_mb is not None and source_file_size_mb > effective_limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"访客试用支持 {effective_limit_mb:g} MB 以内的单个音视频文件。",
        )

    token = _new_guest_trial_token()
    client_id = _guest_client_id(token)
    task_id_value = _new_task_id()
    source_type = _source_type_for_suffix(suffix)
    source_fingerprint = _source_fingerprint(content, file.filename)
    source_path = _persist_source_file(task_id_value, suffix, content)
    expires_at = (
        datetime.now(timezone.utc).astimezone() + timedelta(hours=_guest_result_retention_hours())
    ).isoformat(timespec="seconds")

    options = _queue_options_from_mapping({
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "note_mode": note_mode,
        "skip_summary": "false",
        "stt_model": stt_model,
        "stt_language": stt_language,
        "stt_provider": stt_provider or _default_stt_provider(),
        "speaker_diarization": speaker_diarization,
        "system_prompt": system_prompt,
        "duration_limit_seconds": str(_guest_duration_limit_seconds()),
    })
    metadata = _metadata(
        route="/guest-trial/process",
        queue_options=options,
        source_path=str(source_path),
        source_fingerprint=source_fingerprint,
        guest_trial={
            "token": token,
            "ip_key": _request_ip_key(request),
            "expires_at": expires_at,
            "file_limit_mb": effective_limit_mb,
            "duration_limit_seconds": _guest_duration_limit_seconds(),
        },
    )
    log_event(
        task_id=task_id_value,
        event_name="guest_trial_queued",
        source_type=source_type,
        source_filename=file.filename,
        source_file_size_mb=source_file_size_mb,
        stage="queued",
        success=True,
        metadata=metadata,
    )
    upsert_job(
        task_id=task_id_value,
        status="queued",
        client_id=client_id,
        stage="queued",
        progress=0,
        source_type=source_type,
        source_filename=file.filename,
        source_file_size_mb=source_file_size_mb,
        metadata=metadata,
    )
    _enqueue_transcription_job({
        "task_id": task_id_value,
        "source_path": str(source_path),
        "filename": file.filename,
        "options": options,
        "base_url": _queue_base_url_from_request(request),
        "client_id": client_id,
    })
    job = get_job(task_id_value, client_id=client_id)
    return {
        "ok": True,
        "guest_token": token,
        "task_id": task_id_value,
        "job": job,
        "queue": _guest_queue_snapshot(task_id_value),
        "config": _guest_trial_config(),
    }


@app.get("/guest-trial/jobs/{task_id}")
def get_guest_trial_job(request: Request, task_id: str) -> dict[str, Any]:
    _enforce_guest_trial_enabled()
    return _guest_job_for_request(request, task_id)


@app.get("/guest-trial/jobs/{task_id}/events")
async def stream_guest_trial_job_events(request: Request, task_id: str, since: int = 0) -> StreamingResponse:
    _enforce_guest_trial_enabled()
    _guest_job_for_request(request, task_id)
    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/guest-trial/jobs/{task_id}/cancel")
async def cancel_guest_trial_job(request: Request, task_id: str) -> dict[str, Any]:
    _enforce_guest_trial_enabled()
    job = _guest_job_for_request(request, task_id)
    if job.get("status") not in {"queued", "running"}:
        return {"ok": True, "status": job.get("status")}
    await JOB_EVENTS.cancel(task_id)
    upsert_job(
        task_id=task_id,
        status="cancelled",
        client_id=job.get("client_id"),
        stage="cancelled",
        progress=0,
        error_reason="guest_cancelled",
    )
    return {"ok": True, "status": "cancelled"}


@app.get("/guest-trial/jobs/{task_id}/artifacts/{kind}")
def download_guest_trial_artifact(request: Request, task_id: str, kind: str) -> FileResponse:
    _enforce_guest_trial_enabled()
    _guest_job_for_request(request, task_id)
    allowed = {
        "transcript_txt": ".txt",
        "transcript_srt": ".srt",
        "transcript_vtt": ".vtt",
        "summary_md": ".md",
        "playback_audio": ".mp3",
    }
    suffix = allowed.get(kind)
    if not suffix:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target_dir = _artifact_storage_dir() / task_id
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Artifact not found")
    matches = sorted(path for path in target_dir.glob(f"*{suffix}") if path.is_file())
    if kind == "summary_md":
        matches = [path for path in matches if path.name.endswith("_summary.md")]
    elif kind == "transcript_txt":
        matches = [path for path in matches if not path.name.endswith("_summary.md")]
    if not matches:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target = matches[0]
    return FileResponse(path=str(target), filename=target.name)


@app.post("/credentials")
def update_credentials(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    allowed = {
        "deepseek_api_key",
        "openai_api_key",
        "lark_app_id",
        "lark_app_secret",
        "pyannote_auth_token",
        "azure_speech_key",
        "azure_speech_endpoint",
        "azure_blob_container_sas_url",
    }
    return save_sensitive_settings({k: v for k, v in payload.items() if k in allowed})


@app.post("/azure-speech/smoke-test")
def azure_speech_smoke_test(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    endpoint = resolve_secret(payload.get("azure_speech_endpoint"), "azure_speech_endpoint")
    api_key = resolve_secret(payload.get("azure_speech_key"), "azure_speech_key")
    if not endpoint or not api_key:
        missing = []
        if not endpoint:
            missing.append("Speech address")
        if not api_key:
            missing.append("Speech key")
        raise HTTPException(status_code=400, detail="Azure Speech smoke test is missing " + " and ".join(missing))
    try:
        return run_short_audio_smoke_test(
            endpoint=endpoint,
            api_key=api_key,
            language=(payload.get("language") or "en-US"),
            phrase=payload.get("phrase"),
            timeout=float(payload.get("timeout") or 60),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/jobs")
def get_jobs(request: Request, limit: int = 50, include_result: bool = False) -> dict[str, Any]:
    client_id = _request_client_scope(request)
    jobs = (
        list_jobs(limit=limit, client_id=client_id)
        if include_result
        else list_job_summaries(limit=limit, client_id=client_id)
    )
    return {"jobs": jobs}


@app.get("/local-history/candidates")
def local_history_candidates(request: Request, limit: int = 100) -> dict[str, Any]:
    if not _local_history_export_allowed(request):
        return {"jobs": [], "count": 0, "available": False}
    safe_limit = max(1, min(int(limit or 100), 200))
    candidates = [
        job
        for job in list_jobs(limit=safe_limit)
        if job.get("status") == "completed" and isinstance(job.get("result"), dict)
    ]
    return {"jobs": candidates, "count": len(candidates), "available": True}


@app.get("/jobs/{task_id}")
def get_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    job = get_job(task_id, client_id=_request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _delete_job_for_request(request: Request, task_id: str) -> dict[str, Any]:
    client_id = _request_client_scope(request)
    job = get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be deleted")
    _cleanup_task_all_files(task_id, job.get("metadata"))
    deleted = delete_jobs([task_id], client_id=client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "task_id": task_id, "deleted": True}


@app.delete("/jobs/{task_id}")
def delete_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    return _delete_job_for_request(request, task_id)


@app.post("/jobs/{task_id}/delete")
def delete_job_detail_fallback(request: Request, task_id: str) -> dict[str, Any]:
    return _delete_job_for_request(request, task_id)


@app.patch("/jobs/{task_id}/transcript")
def update_job_transcript(request: Request, task_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    client_id = _request_client_scope(request)
    job = get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = dict(job.get("result") or {})
    transcript = payload.get("transcript_text")
    if not isinstance(transcript, str):
        raise HTTPException(status_code=400, detail="transcript_text is required")
    max_chars = int(os.environ.get("FLUENTFLOW_MAX_TRANSCRIPT_EDIT_CHARS", "1000000"))
    if len(transcript) > max_chars:
        raise HTTPException(status_code=413, detail=f"Transcript edit is too large: {len(transcript)} chars")

    segments = _sanitize_edit_segments(payload.get("segments"))
    edit_records = _sanitize_edit_records(payload.get("edit_records"))
    edited_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    result.update({
        "task_id": result.get("task_id") or task_id,
        "transcript_text": transcript,
        "transcript_text_preview": transcript[:200],
        "segments": segments,
        "transcript_edit_records": edit_records,
        "transcript_edit_record_count": len(edit_records),
        "transcript_edited": True,
        "transcript_edited_at": edited_at,
    })
    try:
        backup_path = _write_edited_transcript_backup(task_id, result)
        edit_records_path = _write_transcript_edit_records_backup(task_id, result, edit_records)
    except Exception as exc:
        logger.warning("Edited transcript backup failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Edited transcript backup failed") from exc

    result.update({
        "edited_transcript_path": str(backup_path),
        "edited_transcript_saved_at": edited_at,
        "transcript_edit_records_path": str(edit_records_path),
    })
    result = _attach_result_artifacts(task_id, result)
    updated = update_job_result(task_id, result, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": updated, "result": updated.get("result")}


@app.get("/jobs/{task_id}/events")
async def stream_job_events(request: Request, task_id: str, since: int = 0) -> StreamingResponse:
    job = get_job(task_id, client_id=_request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/jobs/{task_id}/source")
def download_job_source(request: Request, task_id: str) -> FileResponse:
    if not get_job(task_id, client_id=_request_client_scope(request)):
        raise HTTPException(status_code=404, detail="Source file not found")
    source = _find_source_file(task_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path=str(source), filename=source.name)


@app.get("/jobs/{task_id}/artifacts/{kind}")
def download_job_artifact(request: Request, task_id: str, kind: str) -> FileResponse:
    if not get_job(task_id, client_id=_request_client_scope(request)):
        raise HTTPException(status_code=404, detail="Artifact not found")
    allowed = {
        "transcript_txt": ".txt",
        "transcript_srt": ".srt",
        "transcript_vtt": ".vtt",
        "summary_md": ".md",
        "playback_audio": ".mp3",
    }
    suffix = allowed.get(kind)
    if not suffix:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target_dir = _artifact_storage_dir() / task_id
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Artifact not found")
    matches = sorted(path for path in target_dir.glob(f"*{suffix}") if path.is_file())
    if kind == "summary_md":
        matches = [path for path in matches if path.name.endswith("_summary.md")]
    elif kind == "transcript_txt":
        matches = [path for path in matches if not path.name.endswith("_summary.md")]
    if not matches:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target = matches[0]
    return FileResponse(path=str(target), filename=target.name)


@app.get("/hotword-libraries", include_in_schema=False)
def removed_hotword_libraries() -> None:
    """Legacy endpoint kept only to avoid the SPA fallback masking removal."""
    raise HTTPException(status_code=410, detail="Built-in hotword libraries have been removed")


@app.post("/video-sources/jobs")
async def create_video_source_job(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    input_text = str(payload.get("input") or "").strip()
    title = str(payload.get("title") or "").strip()
    client_id = _request_client_scope(request)
    if not input_text:
        raise HTTPException(status_code=400, detail="缺少视频分享文本或视频链接")
    if len(input_text) > 4000:
        raise HTTPException(status_code=400, detail="分享文本过长")
    _enforce_submission_rate_limit(request, incoming=1)
    _enforce_active_job_limit(client_id, incoming=1)
    _enforce_global_active_job_limit(incoming=1)
    _enforce_daily_quota(client_id, incoming_jobs=1)
    _enforce_global_daily_quota(client_id=client_id, incoming_jobs=1)

    options = _queue_options_from_mapping(payload.get("options") if isinstance(payload.get("options"), dict) else {})
    task_id_value = _new_task_id()
    display_name = title or input_text[:80]
    metadata = _metadata(
        route="/video-sources/jobs",
        queue_options=options,
        video_source_input_preview=input_text[:200],
    )
    log_event(
        task_id=task_id_value,
        event_name="video_source_submitted",
        source_type="video_link",
        source_filename=display_name,
        stage="resolving",
        success=True,
        metadata=metadata,
    )
    upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="resolving",
        progress=2,
        source_type="video_link",
        source_filename=display_name,
        metadata=metadata,
    )
    _start_video_source_job({
        "task_id": task_id_value,
        "input": input_text,
        "title": title or None,
        "options": options,
        "base_url": _queue_base_url_from_request(request),
        "client_id": client_id,
    })
    return {
        "ok": True,
        "job": {
            "task_id": task_id_value,
            "status": "running",
            "stage": "resolving",
            "source_type": "video_link",
            "source_filename": display_name,
        },
    }


@app.get("/video-sources/jobs")
def list_video_source_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    jobs = [
        job for job in list_jobs(limit=200, client_id=_request_client_scope(request))
        if (job.get("metadata") or {}).get("route") == "/video-sources/jobs"
    ][:safe_limit]
    return {"jobs": jobs}


@app.post("/queue/process")
async def queue_process(
    request: Request,
    files: list[UploadFile] = File(...),
    export_to_lark: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    stt_provider: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
) -> dict[str, Any]:
    """Persist multiple media files and process them sequentially in the backend."""
    client_id = _request_client_scope(request)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    max_queue_files = _max_queue_files()
    if len(files) > max_queue_files:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files uploaded: {len(files)}. Limit is {max_queue_files}.",
        )
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower() or ".mp4"
        if not upload.filename:
            raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")
        if suffix not in ALLOWED_SUFFIXES or suffix in TRANSCRIPT_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    _enforce_submission_rate_limit(request, incoming=len(files))
    _enforce_active_job_limit(client_id, incoming=len(files))
    _enforce_global_active_job_limit(incoming=len(files))
    max_upload_mb = _max_upload_mb()
    total_upload_mb = 0.0
    for upload in files:
        source_file_size_mb = _upload_size_mb(upload)
        if source_file_size_mb is None:
            continue
        total_upload_mb += source_file_size_mb
        if source_file_size_mb > max_upload_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
            )
    _enforce_daily_quota(client_id, incoming_jobs=len(files), incoming_upload_mb=total_upload_mb)
    _enforce_global_daily_quota(client_id=client_id, incoming_jobs=len(files), incoming_upload_mb=total_upload_mb)

    base_options = _queue_options_from_form(
        export_to_lark=export_to_lark,
        lark_via_cli=lark_via_cli,
        title=title if len(files) == 1 else None,
        folder_token=folder_token,
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        note_mode=note_mode,
        skip_summary=skip_summary,
        stt_model=stt_model,
        stt_speed=stt_speed,
        stt_language=stt_language,
        stt_provider=stt_provider,
        azure_speech_key=azure_speech_key,
        azure_speech_endpoint=azure_speech_endpoint,
        azure_blob_container_sas_url=azure_blob_container_sas_url,
        speaker_diarization=speaker_diarization,
        lark_app_id=lark_app_id,
        lark_app_secret=lark_app_secret,
        system_prompt=system_prompt,
    )
    base_url = _queue_base_url_from_request(request)
    queued: list[dict[str, Any]] = []
    total = len(files)
    for index, upload in enumerate(files, start=1):
        filename = upload.filename or f"source-{index}"
        suffix = Path(filename).suffix.lower() or ".mp4"
        content = await upload.read()
        source_file_size_mb = _file_size_mb(len(content))
        if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
            )
        task_id_value = _new_task_id()
        source_type = _source_type_for_suffix(suffix)
        source_fingerprint = _source_fingerprint(content, filename)
        source_path = _persist_source_file(task_id_value, suffix, content)
        metadata = _metadata(
            route="/queue/process",
            queue_options=base_options,
            queue_position=index,
            queue_total=total,
            source_path=str(source_path),
            source_fingerprint=source_fingerprint,
        )
        duration_estimate_sec = _media_duration_seconds(source_path)
        quota_estimate = _estimate_processing_units(
            duration_seconds=duration_estimate_sec,
            skip_summary=_truthy_form(base_options.get("skip_summary")),
            estimate_only=True,
        )
        quota_reservation = _reserve_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            estimate=quota_estimate,
        )
        if quota_reservation:
            metadata["quota"] = quota_reservation
        log_event(
            task_id=task_id_value,
            event_name="source_queued",
            source_type=source_type,
            source_filename=filename,
            source_file_size_mb=source_file_size_mb,
            stage="queued",
            success=True,
            metadata=metadata,
        )
        upsert_job(
            task_id=task_id_value,
            status="queued",
            client_id=client_id,
            stage="queued",
            progress=0,
            source_type=source_type,
            source_filename=filename,
            source_file_size_mb=source_file_size_mb,
            metadata=metadata,
        )
        _enqueue_transcription_job({
            "task_id": task_id_value,
            "source_path": str(source_path),
            "filename": filename,
            "options": base_options,
            "base_url": base_url,
            "client_id": client_id,
        })
        queued.append({
            "task_id": task_id_value,
            "filename": filename,
            "source_type": source_type,
            "source_file_size_mb": source_file_size_mb,
            "status": "queued",
            "queue_position": index,
            "queue_total": total,
        })
    return {"ok": True, "queued": queued, "count": len(queued)}


@app.post("/process")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    export_to_lark: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    stt_provider: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    duration_limit_seconds: Optional[float] = Form(None),
    task_id: Optional[str] = Form(None),
    source_last_modified_ms: Optional[str] = Form(None),
) -> StreamingResponse:
    """Upload a file and stream processing progress via SSE."""

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    do_lark = _truthy_form(export_to_lark)
    summary_disabled = _truthy_form(skip_summary)
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    _enforce_submission_rate_limit(request, incoming=1)
    _enforce_active_job_limit(client_id, incoming=1, exclude_task_id=task_id_value)
    _enforce_global_active_job_limit(incoming=1, exclude_task_id=task_id_value)
    source_filename = file.filename
    source_type = _source_type_for_suffix(suffix)
    td = tempfile.mkdtemp()
    content = await file.read()
    source_file_size_mb = _file_size_mb(len(content))
    max_upload_mb = _max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
    _enforce_daily_quota(
        client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    _enforce_global_daily_quota(
        client_id=client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    source_fingerprint = _source_fingerprint(content, source_filename)
    in_path = _persist_source_file(task_id_value, suffix, content)
    duration_preflight_sec = _media_duration_seconds(in_path)
    quota_estimate = _estimate_processing_units(
        duration_seconds=duration_preflight_sec,
        skip_summary=summary_disabled,
        estimate_only=True,
    )
    try:
        quota_reservation = None if _request_is_internal_queue(request) else _reserve_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            estimate=quota_estimate,
        )
    except HTTPException:
        try:
            in_path.unlink(missing_ok=True)
        except Exception:
            pass
        shutil.rmtree(td, ignore_errors=True)
        raise

    log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=_metadata(
            route="/process",
            source_fingerprint=source_fingerprint,
            source_last_modified_ms=source_last_modified_ms,
            quota=quota_reservation,
            quota_estimate=quota_estimate,
        ),
    )
    upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="import",
        progress=0,
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        metadata=_job_metadata_for_update(
            task_id_value,
            client_id,
            route="/process",
            source_fingerprint=source_fingerprint,
            source_last_modified_ms=source_last_modified_ms,
            quota=quota_reservation,
            quota_estimate=quota_estimate,
        ),
    )

    loop = asyncio.get_event_loop()
    model_size = (stt_model or "").strip() or "medium"
    if model_size in {"tiny", "base", "small"}:
        model_size = "medium"
    speed_profile = (stt_speed or "").strip() or "balanced"
    language = (stt_language or "").strip() or "auto"
    stt_provider_value = _normalize_stt_provider(stt_provider, request)
    azure_cloud_provider = stt_provider_value == "azure_batch"
    diarization_requested = _truthy_form(speaker_diarization)
    azure_endpoint_value: str | None = None
    azure_key_value: str | None = None
    azure_blob_container_sas_value: str | None = None
    if azure_cloud_provider:
        azure_endpoint_value = resolve_secret(azure_speech_endpoint, "azure_speech_endpoint")
        azure_key_value = resolve_secret(azure_speech_key, "azure_speech_key")
    if stt_provider_value == "azure_batch":
        azure_blob_container_sas_value = resolve_secret(
            azure_blob_container_sas_url,
            "azure_blob_container_sas_url",
        )

    async def event_stream() -> AsyncGenerator[str, None]:
        current_stage = "import"
        duration_sec: float | None = None
        duration_estimate_sec: float | None = None
        transcript_text = ""
        summary_md = ""
        summary_status: str | None = None
        lark_success: bool | None = None
        stt_process = None
        stt_queue = None
        playback_audio_path: Path | None = None
        try:
            if azure_cloud_provider and (not azure_endpoint_value or not azure_key_value):
                raise RuntimeError(
                    "Cloud transcription backend configuration is incomplete. "
                    "Please contact the product maintainer."
                )
            if stt_provider_value == "azure_batch" and not azure_blob_container_sas_value:
                raise RuntimeError(
                    "Cloud transcription storage is not configured. "
                    "Please contact the product maintainer."
                )

            # ── Stage 1: Audio extraction ──────────────────────
            current_stage = "audio"
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=5)
            yield _sse({"stage": "audio", "progress": 5})
            audio_started_at = time.perf_counter()
            if azure_cloud_provider:
                audio_output_format = "mp3"
                out_audio = await loop.run_in_executor(
                    None, lambda: extract_compressed_mp3(in_path, output_path=Path(td) / "azure_stt.mp3")
                )
                playback_audio_path = out_audio
            else:
                audio_output_format = "wav"
                out_audio = await loop.run_in_executor(
                    None, lambda: extract_stt_wav(in_path, output_path=Path(td) / "stt.wav")
                )
                playback_audio_path = await loop.run_in_executor(
                    None, lambda: extract_compressed_mp3(in_path, output_path=Path(td) / "playback.mp3")
                )
            audio_elapsed_sec = time.perf_counter() - audio_started_at
            log_event(
                task_id=task_id_value,
                event_name="audio_extracted",
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                stage="audio",
                duration_seconds=round(audio_elapsed_sec, 3),
                success=True,
                metadata=_metadata(
                    route="/process",
                    stt_provider=stt_provider_value,
                    stt_provider_label=_stt_provider_label(stt_provider_value),
                    audio_output_format=audio_output_format,
                    audio_output_size_mb=_path_size_mb(out_audio),
                ),
            )
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=20)
            yield _sse({"stage": "audio", "progress": 20})

            # ── Stage 2: STT transcription ─────────────────────
            current_stage = "stt"
            upsert_job(task_id=task_id_value, status="running", stage="stt", progress=22)
            yield _sse({"stage": "stt", "progress": 22, "stt_progress": 0, "stt_status": "starting"})

            duration_estimate_sec = _media_duration_seconds(out_audio)
            if duration_estimate_sec:
                duration_error = _duration_limit_error(duration_estimate_sec, source_filename, duration_limit_seconds)
                if duration_error:
                    raise RuntimeError(duration_error)
            status_progress_floor = {
                "starting": 22.0,
                "loading_model": 23.0,
                "chunking_audio": 24.0,
                "preparing_audio": 24.0,
                "waiting_first_segment": 25.0,
                "transcribing_chunks": 25.0,
                "transcribing_segments": 25.0,
            }
            progress_state: dict[str, Any] = {
                "latest": 22.0,
                "stt_progress": 0.0,
                "transcribed_seconds": 0.0,
                "duration_seconds": duration_estimate_sec,
                "stt_status": "starting",
            }

            azure_inline_limits: dict[str, Any] = {}
            stt_started_at = time.perf_counter()
            if stt_provider_value == "azure_batch":
                azure_inline_limits = {
                    "azure_batch_audio_size_mb": _path_size_mb(out_audio),
                    "azure_batch_duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                }

                def on_azure_batch_progress(status: str, metadata: dict[str, Any] | None = None) -> None:
                    progress_state["stt_status"] = status
                    if metadata:
                        azure_inline_limits.update(metadata)

                progress_state["stt_status"] = "azure_batch_uploading"
                azure_task = loop.run_in_executor(
                    None,
                    lambda: transcribe_audio_batch(
                        out_audio,
                        endpoint=azure_endpoint_value,
                        api_key=azure_key_value,
                        container_sas_url=azure_blob_container_sas_value,
                        locale=language,
                        diarization_enabled=diarization_requested,
                        display_name=f"FluentFlow {Path(file.filename).stem}",
                        progress_callback=on_azure_batch_progress,
                    ),
                )
                last_emit_at = time.perf_counter()
                while not azure_task.done():
                    await asyncio.sleep(1)
                    now = time.perf_counter()
                    if now - last_emit_at < 2:
                        continue
                    last_emit_at = now
                    upsert_job(
                        task_id=task_id_value,
                        status="running",
                        stage="stt",
                        progress=25,
                        metadata={
                            "stt_provider": stt_provider_value,
                            "stt_provider_label": _stt_provider_label(stt_provider_value),
                            **azure_inline_limits,
                            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                            "stt_elapsed_seconds": round(now - stt_started_at, 1),
                            "stt_status": progress_state.get("stt_status"),
                        },
                    )
                    yield _sse({
                        "stage": "stt",
                        "progress": 25,
                        **azure_inline_limits,
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                        "stt_provider": stt_provider_value,
                    })
                tr = azure_task.result()
            else:
                stt_process, stt_queue = start_transcription_process(
                    out_audio,
                    model_size=model_size,
                    speed_profile=speed_profile,
                    language=language,
                )
                stt_result = None
                stt_error: str | None = None
                last_sent_progress = 22.0
                last_emit_at = time.perf_counter()
                while True:
                    for message in drain_queue(stt_queue):
                        message_type = message.get("type")
                        if message_type == "progress":
                            safe_frac = max(0.0, min(float(message.get("value") or 0), 1.0))
                            progress_state["stt_progress"] = safe_frac
                            progress_state["latest"] = max(
                                float(progress_state.get("latest") or 22.0),
                                22 + safe_frac * 38,  # 22–60 range
                            )
                            if duration_estimate_sec:
                                progress_state["transcribed_seconds"] = safe_frac * duration_estimate_sec
                        elif message_type == "status":
                            status = message.get("status") or progress_state["stt_status"]
                            progress_state["stt_status"] = status
                            progress_state["latest"] = max(
                                float(progress_state.get("latest") or 22.0),
                                status_progress_floor.get(str(status), 22.0),
                            )
                        elif message_type == "result":
                            stt_result = message.get("result")
                        elif message_type == "error":
                            stt_error = message.get("error") or "STT worker failed"

                    if stt_result is not None:
                        break
                    if stt_error:
                        raise RuntimeError(stt_error)
                    if stt_process is not None and not stt_process.is_alive():
                        for message in drain_queue(stt_queue):
                            if message.get("type") == "result":
                                stt_result = message.get("result")
                            elif message.get("type") == "error":
                                stt_error = message.get("error") or "STT worker failed"
                        if stt_result is not None:
                            break
                        if stt_error:
                            raise RuntimeError(stt_error)
                        raise RuntimeError(f"STT worker exited unexpectedly with code {stt_process.exitcode}")

                    await asyncio.sleep(0.5)
                    latest_progress = float(progress_state.get("latest") or 22.0)
                    now = time.perf_counter()
                    if latest_progress >= last_sent_progress + 1 or now - last_emit_at >= 2:
                        last_sent_progress = max(last_sent_progress, latest_progress)
                        last_emit_at = now
                        upsert_job(
                            task_id=task_id_value,
                            status="running",
                            stage="stt",
                            progress=round(latest_progress, 1),
                            metadata={
                                "stt_provider": stt_provider_value,
                                "stt_provider_label": _stt_provider_label(stt_provider_value),
                                "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                                "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                                "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                                "stt_elapsed_seconds": round(now - stt_started_at, 1),
                                "stt_status": progress_state.get("stt_status"),
                            },
                        )
                        yield _sse({
                            "stage": "stt",
                            "progress": round(latest_progress, 1),
                            "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                            "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                            "stt_elapsed_seconds": round(now - stt_started_at, 1),
                            "stt_status": progress_state.get("stt_status"),
                            "stt_provider": stt_provider_value,
                        })
                if stt_process is not None:
                    stt_process.join(timeout=2)
                tr = stt_result
            stt_elapsed_sec = time.perf_counter() - stt_started_at
            upsert_job(
                task_id=task_id_value,
                status="running",
                stage="stt",
                progress=60,
                metadata={
                    "stt_provider": stt_provider_value,
                    "stt_provider_label": _stt_provider_label(stt_provider_value),
                    **azure_inline_limits,
                    "stt_progress": 1,
                    "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                },
            )
            yield _sse({
                "stage": "stt",
                "progress": 60,
                "stt_progress": 1,
                **azure_inline_limits,
                "transcribed_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                "stt_provider": stt_provider_value,
            })

            duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
            stt_realtime_factor = _stt_realtime_factor(stt_elapsed_sec, duration_sec)
            transcript_text = tr.text
            if stt_provider_value == "azure_batch":
                stt_model_for_result = "azure-batch-transcription"
            else:
                stt_model_for_result = model_size
            log_event(
                task_id=task_id_value,
                event_name="stt_completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                stage="stt",
                duration_seconds=round(stt_elapsed_sec, 3),
                success=True,
                metadata=_metadata(
                    **_runtime_context_metadata(),
                    route="/process",
                    source_fingerprint=source_fingerprint,
                    stt_provider=stt_provider_value,
                    stt_provider_label=_stt_provider_label(stt_provider_value),
                    stt_model=stt_model_for_result,
                    stt_speed=speed_profile,
                    stt_language=language,
                    **azure_inline_limits,
                    device_requested=getattr(tr, "device_requested", None) or "auto",
                    device_resolved=getattr(tr, "device_resolved", None),
                    vad_filter=getattr(tr, "vad_filter", None),
                    cpu_threads=getattr(tr, "cpu_threads", None),
                    num_workers=getattr(tr, "num_workers", None),
                    detected_language=tr.language,
                    language_probability=tr.language_probability,
                    segment_count=len(tr.segments),
                    stt_realtime_factor=stt_realtime_factor,
                    model_cache_hit=getattr(tr, "model_cache_hit", None),
                    model_load_seconds=getattr(tr, "model_load_seconds", None),
                    model_source=getattr(tr, "model_source", None),
                    compute_type=getattr(tr, "compute_type", None),
                ),
            )
            base_result: dict[str, Any] = {
                "task_id": task_id_value,
                "filename": file.filename,
                "source_file_available": True,
            }
            cleanup_started_at = time.perf_counter()
            cleanup_result = clean_repeated_transcript(tr.segments)
            if cleanup_result.applied_count > 0:
                log_event(
                    task_id=task_id_value,
                    event_name="transcript_cleanup_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=cleanup_result.cleaned_length,
                    stage="transcript_cleanup",
                    duration_seconds=round(time.perf_counter() - cleanup_started_at, 3),
                    success=True,
                    metadata=_metadata(
                        route="/process",
                        cleanup_issue_count=len(cleanup_result.issues),
                        cleanup_applied_count=cleanup_result.applied_count,
                        cleanup_removed_segment_count=cleanup_result.removed_segment_count,
                        cleanup_raw_length=cleanup_result.raw_length,
                        cleanup_cleaned_length=cleanup_result.cleaned_length,
                    ),
                )
            transcript_text = cleanup_result.cleaned_text
            segments_payload = list(cleanup_result.cleaned_segments)
            raw_segments_payload = [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in tr.segments
            ]
            speaker_payload: dict[str, Any] = {
                "requested": diarization_requested,
                "available": True if azure_cloud_provider else diarization_status()["available"],
                "applied": False,
            }
            if diarization_requested and azure_cloud_provider:
                speakers = sorted({
                    str(segment.get("speaker"))
                    for segment in segments_payload
                    if isinstance(segment, dict) and segment.get("speaker")
                })
                if speakers:
                    speaker_payload.update({
                        "applied": True,
                        "backend": getattr(tr, "model_source", None) or "azure_speech_transcription",
                        "speaker_count": len(speakers),
                    })
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        success=True,
                        metadata=_metadata(
                            route="/process",
                            backend=getattr(tr, "model_source", None) or "azure_speech_transcription",
                            speaker_count=len(speakers),
                        ),
                    )
                else:
                    error_reason = (
                        getattr(tr, "diarization_error", None)
                        or f"{_stt_provider_label(stt_provider_value)} did not return speaker labels"
                    )
                    speaker_payload.update({
                        "applied": False,
                        "backend": getattr(tr, "model_source", None) or "azure_speech_transcription",
                        "error_reason": error_reason,
                    })
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_failed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        success=False,
                        error_reason=error_reason,
                        metadata=_metadata(route="/process", backend=getattr(tr, "model_source", None) or "azure_speech_transcription"),
                    )
            elif diarization_requested:
                diarization_started_at = time.perf_counter()
                try:
                    turns = await loop.run_in_executor(None, lambda: diarize_audio(out_audio))
                    segments_payload = assign_speakers_to_segments(segments_payload, turns)
                    speaker_payload.update({
                        "applied": True,
                        "speaker_count": len({turn.speaker for turn in turns}),
                        "turn_count": len(turns),
                    })
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        duration_seconds=round(time.perf_counter() - diarization_started_at, 3),
                        success=True,
                        metadata=_metadata(route="/process", speaker_count=speaker_payload["speaker_count"]),
                    )
                except Exception as exc:
                    error_reason = str(exc)
                    speaker_payload.update({
                        "applied": False,
                        "error_reason": error_reason,
                    })
                    logger.warning("Speaker diarization skipped for %s: %s", task_id_value, error_reason)
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_failed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        duration_seconds=round(time.perf_counter() - diarization_started_at, 3),
                        success=False,
                        error_reason=error_reason,
                        metadata=_metadata(route="/process", failure_scope="optional_speaker_diarization"),
                    )
            base_result.update({
                "task_id": task_id_value,
                "filename": file.filename,
                "transcript_text": transcript_text,
                "raw_transcript_text": tr.text,
                "cleaned_transcript_text": cleanup_result.cleaned_text,
                "transcript_text_preview": transcript_text[:200],
                "summary_markdown": "",
                "audio_duration_seconds": round(duration_sec, 1),
                "stt_elapsed_seconds": round(stt_elapsed_sec, 1),
                "stt_realtime_factor": stt_realtime_factor,
                "stt_provider": stt_provider_value,
                "stt_provider_label": _stt_provider_label(stt_provider_value),
                "stt_model": stt_model_for_result,
                "stt_speed": speed_profile,
                "stt_language": language,
                "detected_language": tr.language,
                "source_fingerprint": source_fingerprint,
                "segments": segments_payload,
                "speaker_diarization": speaker_payload,
                "cleaned_segments": list(cleanup_result.cleaned_segments),
                "raw_segments": raw_segments_payload,
                "transcript_cleanup": _cleanup_payload(cleanup_result),
                "status": "transcript_ready",
                "source": source_type,
                "summary_skipped": summary_disabled,
            })
            if playback_audio_path is not None:
                base_result = _attach_playback_audio_artifact(task_id_value, base_result, playback_audio_path)
            base_result = _attach_result_artifacts(task_id_value, base_result)
            current_stage = "transcript_ready"
            log_event(
                task_id=task_id_value,
                event_name="transcript_ready",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                stage="transcript_ready",
                success=True,
                metadata=_metadata(route="/process", source_fingerprint=source_fingerprint),
            )
            upsert_job(
                task_id=task_id_value,
                status="running",
                stage="transcript_ready",
                progress=60,
                result=base_result,
                summary_status="pending",
            )
            yield _sse({
                "stage": "transcript_ready",
                "progress": 60,
                "result": base_result,
            })

            if summary_disabled:
                summary_status = "skipped"
                log_event(
                    task_id=task_id_value,
                    event_name="summary_skipped",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    stage="summary",
                    success=True,
                    metadata=_metadata(route="/process", reason="transcript_only_mode"),
                )
                result: dict[str, Any] = {
                    **base_result,
                    "status": "completed",
                }
                quota_final = _finalize_task_quota(
                    client_id=client_id,
                    task_id=task_id_value,
                    final_usage=_estimate_processing_units(
                        duration_seconds=duration_sec,
                        transcript_text=transcript_text,
                        summary_text="",
                        skip_summary=True,
                    ),
                    reason="Finalize transcript-only task charge",
                )
                if quota_final:
                    result["quota"] = quota_final
                result = _attach_result_artifacts(task_id_value, result)
                result = _finalize_completed_result_storage(
                    task_id_value,
                    result,
                    (get_job(task_id_value) or {}).get("metadata"),
                )
                upsert_job(
                    task_id=task_id_value,
                    status="completed",
                    stage="done",
                    progress=100,
                    result=result,
                    summary_status=summary_status,
                )
                _log_task_completed(
                    task_id=task_id_value,
                    started_at=task_started_at,
                    final_status="completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    summary_length=0,
                    summary_status=summary_status,
                    lark_requested=do_lark,
                    lark_success=None,
                    stt_provider=stt_provider_value,
                    completion_reason="summary_skipped",
                )
                _enforce_history_retention(client_id)
                yield _sse({"stage": "done", "progress": 100, "result": result})
                return

            # ── Stage 3: AI summarization ──────────────────────
            current_stage = "summary"
            upsert_job(task_id=task_id_value, status="running", stage="summary", progress=62)
            yield _sse({"stage": "summary", "progress": 62})

            summary_error: str | None = None
            summary_result = None
            summary_started_at = time.perf_counter()
            try:
                kwargs = _ai_kwargs(
                    deepseek_api_key=deepseek_api_key,
                    openai_api_key=openai_api_key,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    system_prompt=system_prompt,
                    note_mode=note_mode,
                )
                summary_result = await loop.run_in_executor(
                    None,
                    lambda: summarize_transcript_with_metadata(transcript_text, **kwargs),
                )
                summary_md = summary_result.markdown
                if not summary_md.strip():
                    raise ValueError("AI summarization returned empty result")
                summary_status = "completed"
                log_event(
                    task_id=task_id_value,
                    event_name="summary_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    summary_length=_text_len(summary_md),
                    stage="summary",
                    duration_seconds=round(time.perf_counter() - summary_started_at, 3),
                    success=True,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                        requested_note_mode=summary_result.requested_mode,
                        resolved_note_mode=summary_result.resolved_mode,
                        note_mode_chunk_count=summary_result.chunk_count,
                        note_mode_transcript_length=summary_result.transcript_length,
                        coverage_checked=summary_result.coverage_checked,
                        coverage_revision_used=summary_result.coverage_revision_used,
                    ),
                )
            except Exception as exc:
                logger.warning("AI summarization failed: %s", exc)
                summary_error = _friendly_error_message(exc)
                summary_md = ""
                summary_status = "failed"
                summary_elapsed_sec = time.perf_counter() - summary_started_at
                log_event(
                    task_id=task_id_value,
                    event_name="summary_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    stage="summary",
                    duration_seconds=round(summary_elapsed_sec, 3),
                    success=False,
                    error_reason=summary_error,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                        requested_note_mode=(note_mode or "").strip() or None,
                        raw_error=str(exc),
                    ),
                )
                result = {
                    **base_result,
                    "summary_markdown": "",
                    "summary_error": summary_error,
                    "summary_status": "failed",
                    "status": "summary_failed",
                }
                quota_final = _finalize_task_quota(
                    client_id=client_id,
                    task_id=task_id_value,
                    final_usage=_estimate_processing_units(
                        duration_seconds=duration_sec,
                        transcript_text=transcript_text,
                        summary_text="",
                        skip_summary=True,
                    ),
                    reason="Finalize transcription charge after summary failure",
                )
                if quota_final:
                    result["quota"] = quota_final
                result = _attach_result_artifacts(task_id_value, result)
                result = _finalize_completed_result_storage(
                    task_id_value,
                    result,
                    (get_job(task_id_value) or {}).get("metadata"),
                )
                upsert_job(
                    task_id=task_id_value,
                    status="failed",
                    stage="summary",
                    progress=88,
                    result=result,
                    summary_status=summary_status,
                    error_reason=summary_error,
                )
                _log_task_completed(
                    task_id=task_id_value,
                    started_at=task_started_at,
                    final_status="failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    summary_length=0,
                    summary_status=summary_status,
                    lark_requested=do_lark,
                    lark_success=False if do_lark else None,
                    stt_provider=stt_provider_value,
                    completion_reason="summary_failed",
                )
                _enforce_history_retention(client_id)
                yield _sse({"stage": "done", "progress": 100, "result": result})
                return

            upsert_job(task_id=task_id_value, status="running", stage="summary", progress=88)
            yield _sse({"stage": "summary", "progress": 88})

            # ── Build result ───────────────────────────────────
            result: dict[str, Any] = {
                **base_result,
                "summary_markdown": summary_md,
                "status": "completed",
            }
            if summary_result is not None:
                result.update({
                    "requested_note_mode": summary_result.requested_mode,
                    "resolved_note_mode": summary_result.resolved_mode,
                    "note_mode_chunk_count": summary_result.chunk_count,
                })

            # ── Stage 4: Lark export (optional) ───────────────
            if do_lark:
                current_stage = "export"
                yield _sse({"stage": "export", "progress": 90})
                stem = Path(file.filename or "media").stem
                doc_title = resolve_lark_doc_title(
                    summary_md,
                    filename_stem=stem,
                    form_title=title,
                )
                result["lark_doc_title"] = doc_title
                lark_kwargs: dict[str, Any] = {}
                if (lark_id := resolve_secret(lark_app_id, "lark_app_id")):
                    lark_kwargs["app_id"] = lark_id
                if (lark_secret := resolve_secret(lark_app_secret, "lark_app_secret")):
                    lark_kwargs["app_secret"] = lark_secret
                if folder_token:
                    lark_kwargs["folder_token"] = folder_token
                export_target = _lark_export_target(lark_via_cli)
                log_event(
                    task_id=task_id_value,
                    event_name="lark_export_started",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    summary_length=_text_len(summary_md),
                    stage="export",
                    export_target=export_target,
                    metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title),
                )
                export_started_at = time.perf_counter()
                try:
                    if _truthy_form(lark_via_cli):
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_via_lark_cli(doc_title, summary_md),
                        )
                    else:
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_to_lark(
                                doc_title, summary_md, **lark_kwargs
                            ),
                        )
                    result["lark_response"] = resp
                    lark_success = True
                    feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
                    log_event(
                        task_id=task_id_value,
                        event_name="lark_export_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        transcript_length=_text_len(transcript_text),
                        summary_length=_text_len(summary_md),
                        stage="export",
                        duration_seconds=round(time.perf_counter() - export_started_at, 3),
                        success=True,
                        export_target=export_target,
                        feishu_doc_url=feishu_doc_url,
                        metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title),
                    )
                except Exception as e:
                    result["lark_error"] = _friendly_error_message(e)
                    lark_success = False
                    log_event(
                        task_id=task_id_value,
                        event_name="lark_export_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        transcript_length=_text_len(transcript_text),
                        summary_length=_text_len(summary_md),
                        stage="export",
                        duration_seconds=round(time.perf_counter() - export_started_at, 3),
                        success=False,
                        error_reason=_friendly_error_message(e),
                        export_target=export_target,
                        metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title, raw_error=str(e)),
                    )

            # ── Done ───────────────────────────────────────────
            quota_final = _finalize_task_quota(
                client_id=client_id,
                task_id=task_id_value,
                final_usage=_estimate_processing_units(
                    duration_seconds=duration_sec,
                    transcript_text=transcript_text,
                    summary_text=summary_md,
                    skip_summary=False,
                ),
            )
            if quota_final:
                result["quota"] = quota_final
            result = _attach_result_artifacts(task_id_value, result)
            result = _finalize_completed_result_storage(
                task_id_value,
                result,
                (get_job(task_id_value) or {}).get("metadata"),
            )
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
                stt_provider=stt_provider_value,
            )
            upsert_job(
                task_id=task_id_value,
                status="completed",
                stage="done",
                progress=100,
                result=result,
                summary_status=summary_status,
            )
            _enforce_history_retention(client_id)
            yield _sse({"stage": "done", "progress": 100, "result": result})

        except asyncio.CancelledError:
            logger.info("Processing stream cancelled by client at stage=%s", current_stage)
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
            _release_task_quota(
                client_id=client_id,
                task_id=task_id_value,
                reason="Task cancelled before completion",
                metadata={"stage": current_stage},
            )
            source_duration_for_cancel = duration_sec or duration_estimate_sec
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="cancelled",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(source_duration_for_cancel, 1) if source_duration_for_cancel is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
                stt_provider=stt_provider_value,
                completion_reason="client_disconnect",
            )
            upsert_job(
                task_id=task_id_value,
                status="cancelled",
                stage=current_stage,
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                summary_status=summary_status,
                error_reason="client_disconnect",
            )
            raise
        except Exception as exc:
            logger.exception("Processing failed")
            friendly_error = _friendly_error_message(exc)
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
            if summary_status is None and current_stage == "summary":
                summary_status = "failed"
            _release_task_quota(
                client_id=client_id,
                task_id=task_id_value,
                reason="Task failed before charge finalization",
                metadata={"stage": current_stage, "raw_error": str(exc)},
            )
            log_event(
                task_id=task_id_value,
                event_name="task_failed",
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                stage=current_stage,
                success=False,
                error_reason=friendly_error,
                metadata=_metadata(route="/process", stt_provider=stt_provider_value, raw_error=str(exc)),
            )
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="failed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
                stt_provider=stt_provider_value,
                completion_reason=current_stage,
            )
            upsert_job(
                task_id=task_id_value,
                status="failed",
                stage=current_stage,
                progress=0,
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                summary_status=summary_status,
                error_reason=friendly_error,
            )
            yield _sse({"stage": "error", "progress": 0, "error": friendly_error})
        finally:
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
            if stt_queue is not None:
                try:
                    stt_queue.close()
                    stt_queue.join_thread()
                except Exception:
                    pass
            shutil.rmtree(td, ignore_errors=True)

    async def run_background_job() -> None:
        terminal_sent = False
        try:
            async for chunk in event_stream():
                event = _event_from_sse_chunk(chunk)
                if event is None:
                    continue
                if JobEventHub.is_terminal(event):
                    terminal_sent = True
                await JOB_EVENTS.publish(task_id_value, event)
        except asyncio.CancelledError:
            terminal_sent = True
            await JOB_EVENTS.publish(
                task_id_value,
                {"stage": "error", "progress": 0, "error": "Task cancelled"},
            )
        except Exception as exc:
            logger.exception("Background processing failed")
            await JOB_EVENTS.publish(
                task_id_value,
                {"stage": "error", "progress": 0, "error": str(exc)},
            )
        finally:
            if not terminal_sent:
                job = get_job(task_id_value)
                if job and job.get("status") in {"completed", "failed", "cancelled"}:
                    await JOB_EVENTS.publish(task_id_value, JobEventHub.event_from_job(job))

    await JOB_EVENTS.start(task_id_value, run_background_job)

    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id_value),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/export-lark")
async def export_lark(
    request: Request,
    markdown: str = Form(...),
    title: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    source_duration_seconds: Optional[float] = Form(None),
):
    """Standalone endpoint: export existing markdown to a Lark document."""
    loop = asyncio.get_event_loop()
    task_id_value = (task_id or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    if task_id and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
    kwargs: dict[str, Any] = {}
    if (v := resolve_secret(lark_app_id, "lark_app_id")):
        kwargs["app_id"] = v
    if (v := resolve_secret(lark_app_secret, "lark_app_secret")):
        kwargs["app_secret"] = v
    if folder_token:
        kwargs["folder_token"] = folder_token
    resolved = resolve_lark_doc_title(
        markdown,
        filename_stem="",
        form_title=title,
    )
    export_target = _lark_export_target(lark_via_cli)
    log_event(
        task_id=task_id_value,
        event_name="lark_export_started",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        summary_length=_text_len(markdown),
        stage="export",
        export_target=export_target,
        metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved),
    )
    started_at = time.perf_counter()
    try:
        if _truthy_form(lark_via_cli):
            resp = await loop.run_in_executor(
                None, lambda: export_markdown_via_lark_cli(resolved, markdown)
            )
        else:
            resp = await loop.run_in_executor(
                None, lambda: export_markdown_to_lark(resolved, markdown, **kwargs)
            )
        if isinstance(resp, dict):
            resp["doc_title"] = resolved
            resp["task_id"] = task_id_value
        feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
        log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            export_target=export_target,
            feishu_doc_url=feishu_doc_url,
            metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved),
        )
        return resp
    except Exception as exc:
        friendly_error = _friendly_error_message(exc)
        log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            export_target=export_target,
            metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved, raw_error=str(exc)),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/export-lark", trigger="manual", raw_error=str(exc)),
        )
        raise HTTPException(status_code=500, detail=friendly_error)


@app.post("/regenerate-summary")
async def regenerate_summary(
    request: Request,
    transcript: str = Form(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    source_duration_seconds: Optional[float] = Form(None),
):
    """Re-run AI summarization on an existing transcript."""
    loop = asyncio.get_event_loop()
    task_id_value = (task_id or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    if task_id and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
    kwargs = _ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
        note_mode=note_mode,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: summarize_transcript_with_metadata(transcript, **kwargs)
        )
        md = summary_result.markdown
        log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            summary_length=_text_len(md),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route="/regenerate-summary",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
                requested_note_mode=summary_result.requested_mode,
                resolved_note_mode=summary_result.resolved_mode,
                note_mode_chunk_count=summary_result.chunk_count,
                note_mode_transcript_length=summary_result.transcript_length,
                coverage_checked=summary_result.coverage_checked,
                coverage_revision_used=summary_result.coverage_revision_used,
            ),
        )
        payload = {
            "summary_markdown": md,
            "task_id": task_id_value,
            "requested_note_mode": summary_result.requested_mode,
            "resolved_note_mode": summary_result.resolved_mode,
            "note_mode_chunk_count": summary_result.chunk_count,
        }
        existing = get_job(task_id_value, client_id=client_id)
        result = dict(existing.get("result") or {}) if existing else {
            "task_id": task_id_value,
            "filename": source_filename,
            "transcript_text": transcript,
            "audio_duration_seconds": source_duration_seconds or 0,
            "source": source_type,
        }
        result.update({
            **payload,
            "summary_skipped": False,
            "status": "completed",
        })
        upsert_job(
            task_id=task_id_value,
            status="completed",
            client_id=client_id,
            stage="done",
            progress=100,
            source_type=source_type,
            source_filename=source_filename,
            summary_status="completed",
            result=result,
        )
        return payload
    except Exception as exc:
        friendly_error = _friendly_error_message(exc)
        log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/regenerate-summary", raw_error=str(exc)),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            stage="summary_regenerate",
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/regenerate-summary", raw_error=str(exc)),
        )
        upsert_job(
            task_id=task_id_value,
            status="failed",
            client_id=client_id,
            stage="summary_regenerate",
            source_type=source_type,
            source_filename=source_filename,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)


@app.post("/summarize-transcript-file")
async def summarize_transcript_file(
    request: Request,
    file: UploadFile = File(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
):
    """Parse an existing .srt/.vtt/.txt/.md transcript, optionally summarizing it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported transcript file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    source_filename = file.filename
    raw = await file.read()
    source_file_size_mb = _file_size_mb(len(raw))
    max_upload_mb = _max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
    log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=_metadata(route="/summarize-transcript-file", suffix=suffix),
    )
    upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="import",
        progress=10,
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
    )
    try:
        parsed = parse_transcript_file(raw, file.filename)
        if not parsed.text.strip():
            raise HTTPException(status_code=400, detail="Transcript file is empty")
        if parsed.duration:
            duration_error = _duration_limit_error(parsed.duration, source_filename)
            if duration_error:
                raise HTTPException(status_code=413, detail=duration_error)
    except HTTPException as exc:
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=str(exc.detail),
            metadata=_metadata(route="/summarize-transcript-file"),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="transcript_parse_failed",
        )
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="transcript_parse",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=str(exc.detail),
        )
        raise
    except Exception as exc:
        friendly_error = _friendly_error_message(exc)
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="transcript_parse_failed",
        )
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="transcript_parse",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)

    loop = asyncio.get_event_loop()
    review_segments_input = parsed.segments or tuple(
        {"start": 0.0, "end": 0.0, "text": line}
        for line in parsed.text.splitlines()
        if line.strip()
    )
    cleanup_started_at = time.perf_counter()
    cleanup_result = clean_repeated_transcript(review_segments_input)
    if cleanup_result.applied_count > 0:
        log_event(
            task_id=task_id_value,
            event_name="transcript_cleanup_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=cleanup_result.cleaned_length,
            stage="transcript_cleanup",
            duration_seconds=round(time.perf_counter() - cleanup_started_at, 3),
            success=True,
            metadata=_metadata(
                route="/summarize-transcript-file",
                cleanup_issue_count=len(cleanup_result.issues),
                cleanup_applied_count=cleanup_result.applied_count,
                cleanup_removed_segment_count=cleanup_result.removed_segment_count,
                cleanup_raw_length=cleanup_result.raw_length,
                cleanup_cleaned_length=cleanup_result.cleaned_length,
            ),
        )
    transcript_text = cleanup_result.cleaned_text
    segments_payload = list(cleanup_result.cleaned_segments) if parsed.segments else []
    raw_segments_payload = list(parsed.segments)

    log_event(
        task_id=task_id_value,
        event_name="transcript_ready",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(transcript_text),
        stage="transcript_ready",
        success=True,
        metadata=_metadata(route="/summarize-transcript-file", segment_count=len(parsed.segments)),
    )
    base_result: dict[str, Any] = {
        "task_id": task_id_value,
        "filename": file.filename,
        "transcript_text": transcript_text,
        "raw_transcript_text": parsed.text,
        "cleaned_transcript_text": cleanup_result.cleaned_text,
        "transcript_text_preview": transcript_text[:200],
        "summary_markdown": "",
        "audio_duration_seconds": round(parsed.duration, 1),
        "segments": segments_payload,
        "cleaned_segments": list(cleanup_result.cleaned_segments) if parsed.segments else [],
        "raw_segments": raw_segments_payload,
        "transcript_cleanup": _cleanup_payload(cleanup_result),
        "status": "transcript_ready",
        "source": "transcript_file",
        "summary_skipped": _truthy_form(skip_summary),
    }
    base_result = _attach_result_artifacts(task_id_value, base_result)
    upsert_job(
        task_id=task_id_value,
        status="running",
        stage="transcript_ready",
        progress=60,
        result=base_result,
        summary_status="pending",
    )

    if _truthy_form(skip_summary):
        log_event(
            task_id=task_id_value,
            event_name="summary_skipped",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            stage="summary",
            success=True,
            metadata=_metadata(route="/summarize-transcript-file", reason="transcript_only_mode"),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            summary_length=0,
            summary_status="skipped",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_skipped",
        )
        result = {**base_result, "status": "completed", "summary_skipped": True}
        result = _attach_result_artifacts(task_id_value, result)
        upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            result=result,
            summary_status="skipped",
        )
        return result

    kwargs = _ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
        note_mode=note_mode,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: summarize_transcript_with_metadata(transcript_text, **kwargs)
        )
        summary_md = summary_result.markdown
        if not summary_md.strip():
            raise ValueError("AI summarization returned empty result")
        log_event(
            task_id=task_id_value,
            event_name="summary_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            summary_length=_text_len(summary_md),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route="/summarize-transcript-file",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
                requested_note_mode=summary_result.requested_mode,
                resolved_note_mode=summary_result.resolved_mode,
                note_mode_chunk_count=summary_result.chunk_count,
                note_mode_transcript_length=summary_result.transcript_length,
                coverage_checked=summary_result.coverage_checked,
                coverage_revision_used=summary_result.coverage_revision_used,
            ),
        )
    except Exception as exc:
        friendly_error = _friendly_error_message(exc)
        log_event(
            task_id=task_id_value,
            event_name="summary_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            stage="summary",
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_failed",
        )
        failed_result = {
            **base_result,
            "status": "summary_failed",
            "summary_status": "failed",
            "summary_error": friendly_error,
        }
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="summary",
            progress=88,
            result=failed_result,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)

    result = {
        **base_result,
        "summary_markdown": summary_md,
        "status": "completed",
        "source": "transcript_file",
        "summary_skipped": False,
        "requested_note_mode": summary_result.requested_mode,
        "resolved_note_mode": summary_result.resolved_mode,
        "note_mode_chunk_count": summary_result.chunk_count,
    }
    result = _attach_result_artifacts(task_id_value, result)
    _log_task_completed(
        task_id=task_id_value,
        started_at=task_started_at,
        final_status="completed",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(transcript_text),
        summary_length=_text_len(summary_md),
        summary_status="completed",
        lark_requested=False,
        lark_success=None,
    )
    upsert_job(
        task_id=task_id_value,
        status="completed",
        stage="done",
        progress=100,
        result=result,
        summary_status="completed",
    )
    return result


@app.post("/events")
async def record_client_event(request: Request, payload: dict[str, Any] = Body(...)):
    """Record explicit client-side button events without storing user content."""
    event_name = str(payload.get("event_name") or "")
    if event_name not in CLIENT_EVENT_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event_name}")
    task_id_value = str(payload.get("task_id") or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    if event_name == "task_cancelled" and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
    raw_metadata = payload.get("metadata")
    allowed_client_metadata = (
        {k: raw_metadata.get(k) for k in ("format", "trigger") if k in raw_metadata}
        if isinstance(raw_metadata, dict)
        else {}
    )
    client_metadata = _metadata(**allowed_client_metadata)
    log_event(
        task_id=task_id_value,
        event_name=event_name,
        source_type=payload.get("source_type"),
        source_filename=payload.get("source_filename"),
        source_duration_seconds=payload.get("source_duration_seconds"),
        source_file_size_mb=payload.get("source_file_size_mb"),
        transcript_length=payload.get("transcript_length"),
        summary_length=payload.get("summary_length"),
        stage=payload.get("stage"),
        duration_seconds=payload.get("duration_seconds"),
        success=payload.get("success"),
        error_reason=payload.get("error_reason"),
        export_target=payload.get("export_target"),
        feishu_doc_url=payload.get("feishu_doc_url"),
        metadata=client_metadata,
    )
    if event_name == "task_cancelled":
        await JOB_EVENTS.cancel(task_id_value)
        log_event(
            task_id=task_id_value,
            event_name="task_completed",
            source_type=payload.get("source_type"),
            source_filename=payload.get("source_filename"),
            source_duration_seconds=payload.get("source_duration_seconds"),
            source_file_size_mb=payload.get("source_file_size_mb"),
            transcript_length=payload.get("transcript_length"),
            summary_length=payload.get("summary_length"),
            stage="cancelled",
            duration_seconds=payload.get("duration_seconds"),
            success=False,
            metadata=_metadata(
                **_runtime_context_metadata(),
                final_status="cancelled",
                total_duration_seconds=payload.get("duration_seconds"),
                summary_status=payload.get("summary_status"),
                lark_requested=payload.get("lark_requested"),
                lark_success=payload.get("lark_success"),
                source_type=payload.get("source_type"),
                pipeline_mode=_pipeline_mode(payload.get("source_type")),
                completion_reason="user_cancelled",
            ),
        )
    return {"ok": True, "task_id": task_id_value}


# Serve Vite production assets and let direct client-side routes fall back to index.
FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_DIST_DIR = FRONTEND_ROOT / "dist"
FRONTEND_DIR = FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else FRONTEND_ROOT
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
API_ROUTE_PREFIXES = {
    "account",
    "admin",
    "auth",
    "credentials",
    "events",
    "export-lark",
    "guest-trial",
    "health",
    "hotword-libraries",
    "jobs",
    "ops",
    "process",
    "queue",
    "regenerate-summary",
    "runtime-config",
    "speaker-diarization",
    "summarize-transcript-file",
    "video-sources",
}

if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="frontend-assets")


@app.get("/", include_in_schema=False)
def serve_frontend_index() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index not found")
    return FileResponse(str(FRONTEND_INDEX))


@app.get("/{client_path:path}", include_in_schema=False)
def serve_frontend_route(client_path: str) -> FileResponse:
    first_segment = (client_path or "").split("/", 1)[0]
    if first_segment in API_ROUTE_PREFIXES or "." in first_segment:
        raise HTTPException(status_code=404, detail="Not Found")
    return serve_frontend_index()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to local video file")
    parser.add_argument("--export-to-lark", action="store_true")
    parser.add_argument("--title", default=None)
    parser.add_argument("--folder-token", default=None)
    args = parser.parse_args()

    vp = Path(args.video)
    if not vp.is_file():
        raise SystemExit(f"video not found: {vp}")

    wav = extract_stt_wav(vp)
    tr = transcribe_audio(wav)
    try:
        md = summarize_transcript_to_markdown(tr.text)
    except Exception:
        md = f"# Transcript\n\n{tr.text}"

    print("SUMMARY:\n", md[:2000])
    if args.export_to_lark:
        print("Exporting to Lark...")
        try:
            export_title = resolve_lark_doc_title(
                md,
                filename_stem=vp.stem,
                form_title=args.title,
            )
            out = export_markdown_to_lark(export_title, md, folder_token=args.folder_token)
            print("Export result:", out)
        except Exception as e:
            print("Export failed:", e)
