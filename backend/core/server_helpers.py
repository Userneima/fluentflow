"""FluentFlow shared server helpers, globals, and configuration.

This module contains all helper functions, shared state, and configuration
that route modules depend on. It is imported by backend.routers.* modules.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
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
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import Request, Response, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.core._env import GUEST_TRIAL_TOKEN_HEADER, INTERNAL_QUEUE_TOKEN
from backend.core.cloud_proxy import (
    apply_remote_session_cookie,
    proxy_cloud_workspace_request,
    proxy_response_headers,
    should_stream_cloud_proxy_response,
)
from backend.core.error_diagnostics import diagnose_error
from backend.core.request_scope import (
    normalize_client_id as _normalize_client_id,
    request_client_id as _request_client_id,
    request_is_local_execution as _request_is_local_execution,
    request_is_localhost as _request_is_localhost,
    request_prefers_local_execution as _request_prefers_local_execution,
)
from backend.core.result_schema import (
    canonical_display_segments,
    canonical_raw_segments,
    normalize_result_for_storage,
    sanitize_display_segments,
    sanitize_raw_segments,
)
from backend.core.title_display import display_title_for_user
from backend.core.versioning import get_app_version
from backend.core.runtime_paths import (
    default_artifact_dir,
    default_edited_transcript_dir,
    default_source_dir,
    default_transcript_edit_records_dir,
    default_video_source_dir,
)

logger = logging.getLogger(__name__)

EVENT_SCHEMA_VERSION = "1.3"
APP_VERSION = get_app_version()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_storage_dir() -> Path:
    return default_source_dir()


def _video_source_storage_dir() -> Path:
    return default_video_source_dir()


def _edited_transcript_dir() -> Path:
    return default_edited_transcript_dir()


def _artifact_storage_dir() -> Path:
    return default_artifact_dir()


def _transcript_edit_records_dir() -> Path:
    return default_transcript_edit_records_dir()


from backend.core.job_event_hub import JobEventHub, _sse

JOB_EVENTS = JobEventHub()


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
    "/version",
    "/runtime-config",
    "/credentials/status",
    "/account/import-history",
    "/local-history/candidates",
    "/speaker-diarization/status",
}

LOCAL_STATUS_PUBLIC_PATHS = {
    "/credentials/status",
    "/speaker-diarization/status",
}

def _should_proxy_cloud_workspace(request: Request) -> bool:
    if not _cloud_workspace_enabled():
        return False
    path = request.url.path
    if path == "/" or path.startswith("/assets/"):
        return False
    if _is_frontend_spa_route(path):
        return False
    if path in LOCAL_CLOUD_WORKSPACE_PATHS:
        return False
    if _request_is_local_execution(request):
        return False
    return path in {"/auth/status", "/auth/login", "/auth/register", "/auth/logout"} or _is_api_route_path(path)


def _request_is_internal_queue(request: Request) -> bool:
    supplied = request.headers.get("x-fluentflow-internal-queue-token") or ""
    return bool(supplied and hmac.compare_digest(supplied, INTERNAL_QUEUE_TOKEN))


_proxy_response_headers = proxy_response_headers


def _should_stream_cloud_proxy_response(path: str, headers: httpx.Headers) -> bool:
    return should_stream_cloud_proxy_response(path, headers)


def _apply_remote_session_cookie(response: Response, request: Request, remote_headers: httpx.Headers) -> None:
    apply_remote_session_cookie(
        response,
        request,
        remote_headers,
        session_cookie_name=SESSION_COOKIE_NAME,
        session_max_age_seconds=_session_days() * 24 * 60 * 60,
        cookie_secure=_cookie_secure_enabled(),
    )


async def _proxy_cloud_workspace_request(request: Request) -> Response:
    return await proxy_cloud_workspace_request(
        request,
        base_url=_cloud_workspace_url(),
        session_token=_request_account_session_token(request),
        session_cookie_name=SESSION_COOKIE_NAME,
        session_max_age_seconds=_session_days() * 24 * 60 * 60,
        cookie_secure=_cookie_secure_enabled(),
        logger=logger,
    )


def _request_access_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = request.headers.get("x-fluentflow-access-token") or ""
    if header_token.strip():
        return header_token.strip()
    return (request.cookies.get("fluentflow_access_token") or "").strip()


def _request_api_key_auth(request: Request) -> dict[str, Any] | None:
    if getattr(request.state, "_api_key_auth_checked", False):
        cached = getattr(request.state, "api_key_auth", None)
        return cached if isinstance(cached, dict) else None
    request.state._api_key_auth_checked = True
    auth = authenticate_api_key(_request_access_token(request))
    if auth:
        request.state.api_key_auth = auth
        return auth
    request.state.api_key_auth = None
    return None


def _request_has_access(request: Request) -> bool:
    tokens = _configured_access_tokens()
    if not tokens:
        return True
    supplied = _request_access_token(request)
    if supplied and any(hmac.compare_digest(supplied, token) for token in tokens):
        return True
    return bool(_request_api_key_auth(request))


def _request_client_scope(request: Request | None) -> str:
    if request is not None:
        api_key_auth = _request_api_key_auth(request)
        owner_scope = str(api_key_auth.get("owner_scope") or "").strip() if api_key_auth else ""
        if owner_scope:
            return owner_scope
    if request is not None and _request_is_internal_queue(request):
        return _normalize_client_scope(request.headers.get("x-fluentflow-client-id")) or "anonymous"
    if request is not None and _account_auth_enabled():
        user = _request_account_user(request)
        if user and user.get("id"):
            return f"user:{user['id']}"
    if request is not None and _request_is_local_execution(request):
        return _request_client_id(request) or "anonymous"
    return _request_client_id(request) or "anonymous"


def _is_public_request(request: Request) -> bool:
    if request.method.upper() == "OPTIONS":
        return True
    path = request.url.path
    if request.method.upper() == "GET" and path in LOCAL_STATUS_PUBLIC_PATHS and _request_is_localhost(request):
        return True
    if path.startswith("/guest-trial"):
        return True
    if path in {"/", "/health", "/version", "/auth/status", "/auth/login", "/auth/register", "/auth/logout", "/runtime-config"}:
        return True
    if path.startswith("/assets/"):
        return True
    if _is_frontend_spa_route(path):
        return True
    return not _is_api_route_path(path)


async def beta_access_middleware(request: Request, call_next):
    if _should_proxy_cloud_workspace(request):
        return await _proxy_cloud_workspace_request(request)
    if _request_is_internal_queue(request):
        return await call_next(request)
    if _request_is_local_execution(request):
        return await call_next(request)
    if _account_auth_enabled():
        if _is_public_request(request):
            return await call_next(request)
        user = _request_account_user(request)
        if user:
            request.state.account_user = user
            return await call_next(request)
        api_key_auth = _request_api_key_auth(request)
        if api_key_auth and api_key_auth.get("user_id"):
            user = get_user_by_id(str(api_key_auth["user_id"]))
            if user and user.get("status") == "active":
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
    from backend.core.frame_extractor import extract_candidate_frames
    from backend.core.keyframe_provider import extract_keyframes
    from backend.core.visual_evidence import build_visual_evidence_from_note_images, build_visual_key_moments, inject_visual_evidence_references, rewrite_note_image_references
    from backend.core.local_stt import transcribe_audio, get_or_load_model
    from backend.core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
    from backend.core.elevenlabs_stt import transcribe_audio_scribe
    from backend.core.stt_process import drain_queue, start_transcription_process, terminate_process
    from backend.core.ai_summarizer import can_use_multimodal, generate_bilingual_segments_zh, plan_visual_evidence_requests, select_visual_evidence_frames, summarize_transcript_to_markdown, summarize_transcript_with_frames, summarize_transcript_with_metadata, translate_segments_to_zh, visual_requests_to_frame_segments
    from backend.core.transcript_correction import correct_transcript_segments, correction_result_fields, transcript_correction_enabled
    from backend.core.lark_exporter import export_markdown_to_lark
    from backend.core.lark_cli_exporter import export_markdown_via_lark_cli
    from backend.core.note_title import resolve_lark_doc_title
    from backend.core.feishu_oauth import (
        FeishuConnectionRequired,
        FeishuOAuthError,
        complete_feishu_oauth_callback,
        create_feishu_authorize_url,
        disconnect_feishu_user,
        feishu_connection_status,
        get_valid_feishu_user_access_token,
    )
    from backend.core.note_planner import plan_note_task
    from backend.core.transcript_parser import parse_transcript_file
    from backend.core.transcript_cleaner import clean_repeated_transcript
    from backend.core.event_logger import log_event
    from backend.core.job_lifecycle import (
        job_has_transcript_result,
        result_for_summary_failure,
        result_for_summary_success,
        result_for_transcript_only,
    )
    from backend.core.job_store import (
        acquire_next_job_step,
        cancel_job_steps,
        complete_job_step,
        delete_jobs,
        enqueue_job_step,
        fail_job_step,
        get_job,
        list_job_steps,
        list_job_summaries,
        list_jobs,
        list_jobs_for_retention,
        migrate_job_display_titles,
        requeue_running_job_steps,
        update_job_result,
        upsert_job,
    )
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
        save_feishu_connection,
    )
    from backend.core.api_key_store import (
        authenticate_api_key,
        create_api_key,
        list_api_keys,
        revoke_api_key,
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
    from backend.core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source, video_source_failure_reason
except ImportError:
    from core.audio_handler import extract_compressed_mp3, extract_stt_wav
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
    from core.elevenlabs_stt import transcribe_audio_scribe
    from core.stt_process import drain_queue, start_transcription_process, terminate_process
    from core.frame_extractor import extract_candidate_frames
    from core.keyframe_provider import extract_keyframes
    from core.visual_evidence import build_visual_evidence_from_note_images, build_visual_key_moments, inject_visual_evidence_references, rewrite_note_image_references
    from core.ai_summarizer import can_use_multimodal, generate_bilingual_segments_zh, plan_visual_evidence_requests, select_visual_evidence_frames, summarize_transcript_to_markdown, summarize_transcript_with_frames, summarize_transcript_with_metadata, translate_segments_to_zh, visual_requests_to_frame_segments
    from core.transcript_correction import correct_transcript_segments, correction_result_fields, transcript_correction_enabled
    from core.lark_exporter import export_markdown_to_lark
    from core.lark_cli_exporter import export_markdown_via_lark_cli
    from core.note_title import resolve_lark_doc_title
    from core.feishu_oauth import (
        FeishuConnectionRequired,
        FeishuOAuthError,
        complete_feishu_oauth_callback,
        create_feishu_authorize_url,
        disconnect_feishu_user,
        feishu_connection_status,
        get_valid_feishu_user_access_token,
    )
    from core.note_planner import plan_note_task
    from core.transcript_parser import parse_transcript_file
    from core.transcript_cleaner import clean_repeated_transcript
    from core.event_logger import log_event
    from core.job_lifecycle import (
        job_has_transcript_result,
        result_for_summary_failure,
        result_for_summary_success,
        result_for_transcript_only,
    )
    from core.job_store import (
        acquire_next_job_step,
        cancel_job_steps,
        complete_job_step,
        delete_jobs,
        enqueue_job_step,
        fail_job_step,
        get_job,
        list_job_steps,
        list_job_summaries,
        list_jobs,
        list_jobs_for_retention,
        migrate_job_display_titles,
        requeue_running_job_steps,
        update_job_result,
        upsert_job,
    )
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
        save_feishu_connection,
    )
    from core.api_key_store import (
        authenticate_api_key,
        create_api_key,
        list_api_keys,
        revoke_api_key,
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
    from core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source, video_source_failure_reason


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
    if not user:
        api_key_auth = _request_api_key_auth(request)
        if api_key_auth and api_key_auth.get("user_id"):
            user = get_user_by_id(str(api_key_auth["user_id"]))
            if user and user.get("status") != "active":
                user = None
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

    return str(diagnose_error(error).get("detail") or "").strip()


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
    if _env_truthy("FLUENTFLOW_TRUSTED_PROXY"):
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
    return (request.headers.get(GUEST_TRIAL_TOKEN_HEADER) or "").strip()


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
    removed.extend(_cleanup_video_source_temp_files(metadata).get("source_retention_removed_paths") or [])
    return {
        "source_retention_status": "deleted" if removed else "not_found",
        "source_retention_removed_paths": removed,
        "source_retention_cleaned_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _cleanup_video_source_temp_files(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    removed: list[str] = []

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


def _expire_retained_source_file(job: dict[str, Any], *, now: datetime | None = None) -> bool:
    task_id = str(job.get("task_id") or "")
    if not task_id:
        return False
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if not result.get("source_file_available"):
        return False
    expires_at = _parse_job_time(result.get("source_retention_expires_at"))
    if expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if expires_at > current.astimezone(timezone.utc):
        return False
    cleanup = _cleanup_task_source_files(task_id, job.get("metadata"))
    next_result = {
        **result,
        "source_file_available": False,
        "source_file_storage": None,
        "source_retention_status": "expired",
        "source_retention_cleaned_at": cleanup.get("source_retention_cleaned_at"),
    }
    update_job_result(
        task_id,
        next_result,
        client_id=job.get("client_id"),
        touch_updated_at=False,
    )
    return True


def _enforce_history_retention(client_id: str | None) -> dict[str, Any]:
    if not client_id:
        return {"pruned_count": 0, "task_ids": []}
    keep_count = _history_retention_per_client()
    retention_days = _artifact_retention_days()
    source_retention_days = _source_retention_days()
    if keep_count <= 0 and retention_days <= 0 and source_retention_days <= 0:
        return {"pruned_count": 0, "task_ids": []}

    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
        if retention_days > 0
        else None
    )
    jobs = list_jobs_for_retention(client_id=client_id)
    pruned_task_ids: list[str] = []
    expired_source_count = 0
    now = datetime.now(timezone.utc)
    for index, job in enumerate(jobs):
        task_id = str(job.get("task_id") or "")
        if not task_id or job.get("status") not in {"completed", "failed", "cancelled"}:
            continue
        if _expire_retained_source_file(job, now=now):
            expired_source_count += 1
        too_many = keep_count > 0 and index >= keep_count
        updated_at = _parse_job_time(job.get("updated_at") or job.get("created_at"))
        too_old = cutoff is not None and updated_at is not None and updated_at < cutoff
        if too_many or too_old:
            _cleanup_task_all_files(task_id, job.get("metadata"))
            pruned_task_ids.append(task_id)

    if pruned_task_ids:
        delete_jobs(pruned_task_ids, client_id=client_id)
    return {
        "pruned_count": len(pruned_task_ids),
        "task_ids": pruned_task_ids,
        "expired_source_count": expired_source_count,
    }


def _finalize_completed_result_storage(task_id: str, result: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    next_result = dict(result)
    artifacts = dict(next_result.get("artifacts") or {})
    if artifacts.get("playback_audio"):
        next_result["playback_audio_available"] = True
    retention_days = _source_retention_days()
    if retention_days <= 0:
        cleanup = _cleanup_task_source_files(task_id, metadata)
        next_result["source_file_available"] = False
        next_result.update({
            key: value
            for key, value in cleanup.items()
            if key != "source_retention_removed_paths"
        })
        return next_result

    _cleanup_video_source_temp_files(metadata)
    source = _find_source_file(task_id)
    if source:
        next_result.update({
            "source_file_available": True,
            "source_file_storage": "local",
            "source_retention_status": "retained",
            "source_retention_days": retention_days,
            "source_retention_expires_at": _source_retention_expiry(retention_days),
        })
    else:
        next_result.update({
            "source_file_available": False,
            "source_retention_status": "not_found",
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


def _artifact_url(task_id: str, kind: str, *, filename: str | None = None) -> str:
    if kind == "frame" and filename:
        frame_name = Path(filename).name
        if frame_name:
            return f"/jobs/{task_id}/artifacts/frame?file={quote(frame_name)}"
    return f"/jobs/{task_id}/artifacts/{kind}"


def _artifact_filename(result: dict[str, Any], suffix: str) -> str:
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback="transcript",
    )
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


def _bilingual_segments(
    source_segments: list[dict[str, Any]],
    translated_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not source_segments or not translated_segments:
        return []
    output: list[dict[str, Any]] = []
    for source, translated in zip(source_segments, translated_segments):
        source_text = str(source.get("text") or "").strip()
        zh_text = str(translated.get("text") or translated.get("text_zh") or "").strip()
        if not source_text or not zh_text:
            continue
        segment: dict[str, Any] = {
            "start": source.get("start"),
            "end": source.get("end"),
            "text": f"{source_text}\n{zh_text}",
        }
        if source.get("speaker"):
            segment["speaker"] = source.get("speaker")
        output.append(segment)
    return output


def _sanitize_bilingual_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    segments: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text_en = str(item.get("text") or item.get("text_en") or "").strip()
        text_zh = str(item.get("text_zh") or item.get("zh") or "").strip()
        if not text_en or not text_zh:
            continue
        segment: dict[str, Any] = {
            "text": f"{text_en}\n{text_zh}",
        }
        for key in ("start", "end"):
            try:
                segment[key] = float(item.get(key) or 0)
            except (TypeError, ValueError):
                segment[key] = 0.0
        if item.get("speaker"):
            segment["speaker"] = str(item.get("speaker"))
        segments.append(segment)
    return segments


def _sanitize_display_segments(value: Any) -> list[dict[str, Any]]:
    return sanitize_display_segments(value)


def _canonical_raw_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    return canonical_raw_segments(result)


def _canonical_display_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    return canonical_display_segments(result)


def _with_canonical_result_segments(
    result: dict[str, Any],
    *,
    raw_segments: list[dict[str, Any]] | None = None,
    display_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    next_result = dict(result)
    raw = _sanitize_edit_segments(raw_segments) if raw_segments is not None else _canonical_raw_segments(next_result)
    if display_segments is not None:
        display = _sanitize_display_segments(display_segments)
    else:
        display_probe = dict(next_result)
        if raw and not display_probe.get("raw_segments"):
            display_probe["raw_segments"] = raw
        display = _canonical_display_segments(display_probe)
    if raw:
        next_result["raw_segments"] = raw
    if display:
        next_result["display_segments"] = display
        if any(str(segment.get("text_zh") or "").strip() for segment in display):
            next_result["subtitle_mode"] = "bilingual_zh"
        elif not next_result.get("subtitle_mode"):
            next_result["subtitle_mode"] = "source_only"
    return normalize_result_for_storage(next_result) or next_result


def _subtitle_segments_from_display(display_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subtitles: list[dict[str, Any]] = []
    for segment in _sanitize_display_segments(display_segments):
        text = str(segment.get("text") or "").strip()
        text_zh = str(segment.get("text_zh") or "").strip()
        if not text_zh:
            continue
        next_segment = dict(segment)
        next_segment["text"] = "\n".join(part for part in (text, text_zh) if part)
        subtitles.append(next_segment)
    return subtitles


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


def _safe_artifact_relative_path(filename: str) -> Path:
    path = Path(filename)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Artifact filename must be a safe relative path")
    return path


def _write_file_artifact(task_id: str, kind: str, filename: str, source_path: Path | str) -> dict[str, Any]:
    target_dir = _artifact_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    relative_path = _safe_artifact_relative_path(filename)
    path = target_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copyfile(str(source_path), tmp)
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {
        "kind": kind,
        "filename": str(relative_path).replace("\\", "/"),
        "url": _artifact_url(task_id, kind, filename=str(relative_path)),
        "size_bytes": path.stat().st_size,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _artifact_filename_for_uploaded_media(filename: str | None, fallback: str = "source_audio") -> str:
    raw = Path(filename or "").name
    suffix = Path(raw).suffix.lower()
    if suffix not in {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus", ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
        suffix = ".bin"
    return f"{_safe_filename_stem(raw, fallback=fallback)}{suffix}"


def _attach_playback_audio_artifact(
    task_id: str,
    result: dict[str, Any],
    audio_path: Path | str,
    source_filename: str | None = None,
) -> dict[str, Any]:
    path = Path(audio_path)
    if not path.is_file():
        return result
    artifact_filename = (
        _artifact_filename_for_uploaded_media(source_filename)
        if source_filename
        else _artifact_filename(result, "_audio.mp3")
    )
    try:
        artifact = _write_file_artifact(
            task_id,
            "playback_audio",
            artifact_filename,
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
    next_result["playback_audio_storage"] = "local"
    return next_result


def _write_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    transcript = str(result.get("transcript_text") or "").strip()
    normalized_result = _with_canonical_result_segments(result)
    raw_segments = _canonical_raw_segments(normalized_result)
    display_segments = _canonical_display_segments(normalized_result)
    if transcript:
        artifacts["transcript_txt"] = _write_text_artifact(
            task_id,
            "transcript_txt",
            _artifact_filename(result, ".txt"),
            transcript.rstrip() + "\n",
        )
    if raw_segments:
        artifacts["transcript_srt"] = _write_text_artifact(
            task_id,
            "transcript_srt",
            _artifact_filename(result, ".srt"),
            _format_srt(raw_segments),
        )
        artifacts["transcript_vtt"] = _write_text_artifact(
            task_id,
            "transcript_vtt",
            _artifact_filename(result, ".vtt"),
            _format_vtt(raw_segments),
        )
        bilingual = _subtitle_segments_from_display(display_segments)
        if not bilingual:
            translated_segments = _sanitize_edit_segments(result.get("translated_segments_zh"))
            bilingual = _bilingual_segments(raw_segments, translated_segments)
        if bilingual:
            artifacts["transcript_bilingual_srt"] = _write_text_artifact(
                task_id,
                "transcript_bilingual_srt",
                _artifact_filename(result, "_bilingual_zh.srt"),
                _format_srt(bilingual),
            )
            artifacts["transcript_bilingual_vtt"] = _write_text_artifact(
                task_id,
                "transcript_bilingual_vtt",
                _artifact_filename(result, "_bilingual_zh.vtt"),
                _format_vtt(bilingual),
            )
    summary = str(result.get("summary_markdown") or "").strip()
    if summary:
        artifacts["summary_md"] = _write_text_artifact(
            task_id,
            "summary_md",
            _artifact_filename(result, "_summary.md"),
            summary.rstrip() + "\n",
        )
    frame_artifacts = result.get("frame_artifacts")
    if isinstance(frame_artifacts, list):
        for frame_artifact in frame_artifacts:
            if isinstance(frame_artifact, dict) and frame_artifact.get("kind") == "frame":
                key = f"frame_{Path(str(frame_artifact.get('filename') or '')).stem}"
                artifacts[key] = frame_artifact
    return artifacts


def _attach_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    normalized_result = _with_canonical_result_segments(result)
    try:
        artifacts = _write_result_artifacts(task_id, normalized_result)
    except Exception as exc:
        logger.warning("Result artifact write failed for %s: %s", task_id, exc)
        return result
    if not artifacts:
        return normalized_result
    next_result = dict(normalized_result)
    next_result["artifacts"] = {**dict(normalized_result.get("artifacts") or {}), **artifacts}
    return next_result


def _write_edited_transcript_backup(task_id: str, result: dict[str, Any]) -> Path:
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback=task_id or "transcript",
    )
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _edited_transcript_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edited.txt"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    content = _format_edited_transcript_backup(
        str(result.get("transcript_text") or ""),
        _canonical_raw_segments(result),
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
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback=task_id or "transcript",
    )
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
    return sanitize_raw_segments(value)


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
    if provider in {"cloud", "cloud_stt", "elevenlabs", "elevenlabs_scribe", "scribe", "scribe_v2"}:
        return "elevenlabs_scribe"
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
        return ("elevenlabs_scribe", "local") if _request_can_use_local_stt(request) else ("elevenlabs_scribe",)
    providers: list[str] = []
    for item in raw.split(","):
        provider = _canonical_stt_provider(item)
        if provider in {"elevenlabs_scribe", "azure_batch", "local"} and provider not in providers:
            providers.append(provider)
    if _request_can_use_local_stt(request) and "local" not in providers:
        providers.append("local")
    if _public_mode_enabled() and not _request_can_use_local_stt(request):
        providers = [provider for provider in providers if provider != "local"]
    return tuple(providers) or (("elevenlabs_scribe", "local") if _request_can_use_local_stt(request) else ("elevenlabs_scribe",))


def _default_stt_provider(request: Request | None = None) -> str:
    requested = _canonical_stt_provider(os.environ.get("FLUENTFLOW_DEFAULT_STT_PROVIDER") or "elevenlabs_scribe")
    allowed = _allowed_stt_providers(request)
    return requested if requested in allowed else allowed[0]


def _normalize_stt_provider(value: str | None, request: Request | None = None) -> str:
    provider = _canonical_stt_provider(value) if value else _default_stt_provider(request)
    allowed = _allowed_stt_providers(request)
    return provider if provider in allowed else _default_stt_provider(request)


def _stt_provider_label(provider: str) -> str:
    if provider == "elevenlabs_scribe":
        return "ElevenLabs Scribe"
    if provider == "azure_batch":
        return "Legacy Azure Batch"
    return "faster-whisper"


def _lark_export_target(lark_export_route: Optional[str] = None, lark_via_cli: Optional[str] = None) -> str:
    route = (lark_export_route or "").strip().lower()
    if route in {"local_cli", "lark_cli"}:
        return "lark_cli"
    if route in {"user_oauth", "feishu_user", "feishu_user_oauth", "lark_user_oauth"}:
        return "feishu_user_oauth"
    if route in {"openapi", "lark_openapi"}:
        return "lark_openapi"
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
    qwen_api_key: Optional[str] = None,
    ai_provider: Optional[str],
    ai_model: Optional[str],
    system_prompt: Optional[str],
    note_mode: Optional[str] = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    provider_name = (ai_provider or "").strip()
    resolved_openai_key = resolve_secret(openai_api_key, "openai_api_key")
    resolved_deepseek_key = resolve_secret(deepseek_api_key, "deepseek_api_key")
    resolved_qwen_key = resolve_secret(qwen_api_key, "qwen_api_key")
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
    if resolved_qwen_key and provider_name.lower() == "qwen":
        kwargs["api_key"] = resolved_qwen_key
    if (m := (ai_model or "").strip()):
        kwargs["model"] = m
    if (sp := (system_prompt or "").strip()):
        kwargs["system_prompt"] = sp
    if (nm := (note_mode or "").strip()):
        kwargs["note_mode"] = nm
    return kwargs


PLANNER_NOTE_MODES = {"direct", "high_fidelity"}
PLANNER_SAMPLE_CHARS = 3000


def _requested_note_mode(note_mode: str | None) -> str:
    value = (note_mode or os.environ.get("FLUENTFLOW_NOTE_MODE") or "auto").strip().lower()
    return "direct" if value == "fast" else value


def _language_hint_for_planning(text: str) -> str:
    cjk = 0
    latin = 0
    for char in text:
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF:
            cjk += 1
        elif "a" <= char.lower() <= "z":
            latin += 1
    if cjk > latin:
        return "zh"
    if latin > cjk:
        return "en_or_latin"
    return "unknown"


def _planning_transcript_preview(transcript_text: str, *, sample_chars: int = PLANNER_SAMPLE_CHARS) -> str:
    transcript = (transcript_text or "").strip()
    if not transcript:
        return ""
    sample_size = max(500, sample_chars)
    total = len(transcript)
    non_empty_lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    question_count = transcript.count("?") + transcript.count("？")
    avg_line_chars = round(sum(len(line) for line in non_empty_lines) / len(non_empty_lines), 1) if non_empty_lines else total
    stats = "\n".join([
        "【材料统计】",
        f"- total_chars: {total}",
        f"- non_empty_lines: {len(non_empty_lines)}",
        f"- avg_line_chars: {avg_line_chars}",
        f"- question_marks: {question_count}",
        f"- language_hint: {_language_hint_for_planning(transcript)}",
    ])
    if total <= sample_size * 2:
        return f"{stats}\n\n【全文样本】\n{transcript[:sample_size * 2]}"
    head = transcript[:sample_size]
    mid_start = max(0, (total // 2) - (sample_size // 2))
    middle = transcript[mid_start: mid_start + sample_size]
    tail = transcript[-sample_size:]
    return "\n\n".join([
        stats,
        f"【开头样本】\n{head}",
        f"【中段样本】\n{middle}",
        f"【结尾样本】\n{tail}",
    ])


def _plan_note_mode_for_summary(
    kwargs: dict[str, Any],
    transcript_text: str,
    *,
    task_id: str | None = None,
    route: str | None = None,
    filename: str | None = None,
    duration_seconds: float | None = None,
    current_prompt_preset: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    requested_mode = _requested_note_mode(kwargs.get("note_mode"))
    if requested_mode != "auto":
        return kwargs, {}

    started_at = time.perf_counter()
    transcript = transcript_text or ""
    try:
        plan = plan_note_task(
            filename=filename,
            transcript_preview=_planning_transcript_preview(transcript),
            transcript_length=len(transcript),
            duration_seconds=duration_seconds,
            current_note_mode="auto",
            current_prompt_preset=current_prompt_preset,
            provider=kwargs.get("provider"),
            model=kwargs.get("model"),
            api_key=kwargs.get("api_key"),
        )
        planned_mode = (plan.recommended_note_mode or "").strip()
        if planned_mode not in PLANNER_NOTE_MODES:
            planned_mode = "high_fidelity"
        planned_kwargs = {**kwargs, "note_mode": planned_mode}
        metadata = {
            "requested_note_mode": "auto",
            "note_mode_plan_material_type": plan.material_type,
            "note_mode_plan_selected_mode": planned_mode,
            "note_mode_plan_reason": plan.reason,
            "note_mode_plan_confidence": plan.confidence,
            "note_mode_plan_warnings": plan.warnings,
            "note_mode_plan_provider": plan.planner_provider,
            "note_mode_plan_model": plan.planner_model,
            "note_mode_plan_fallback": False,
        }
        log_event(
            task_id=task_id,
            event_name="note_mode_planned",
            source_filename=filename,
            transcript_length=len(transcript),
            stage="note_mode_plan",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route=route,
                selected_note_mode=planned_mode,
                confidence=plan.confidence,
                planner_provider=plan.planner_provider,
                planner_model=plan.planner_model,
            ),
        )
        return planned_kwargs, metadata
    except Exception as exc:
        friendly_error = _friendly_error_message(exc)
        logger.warning("AI note mode planning failed, falling back to length rule: %s", exc)
        log_event(
            task_id=task_id,
            event_name="note_mode_plan_failed",
            source_filename=filename,
            transcript_length=len(transcript),
            stage="note_mode_plan",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route=route, raw_error=str(exc)),
        )
        return kwargs, {
            "requested_note_mode": "auto",
            "note_mode_plan_reason": "AI 规划失败，已按长度规则自动选择。",
            "note_mode_plan_fallback": True,
            "note_mode_plan_error": friendly_error,
        }


def _summary_result_metadata(summary_result: Any) -> dict[str, Any]:
    return {
        "resolved_note_mode": getattr(summary_result, "resolved_mode", None),
        "note_mode_chunk_count": getattr(summary_result, "chunk_count", None),
        "note_mode_transcript_length": getattr(summary_result, "transcript_length", None),
        "coverage_checked": getattr(summary_result, "coverage_checked", None),
        "coverage_revision_used": getattr(summary_result, "coverage_revision_used", None),
        "note_mode_segment_count": getattr(summary_result, "segment_count", None),
        "note_mode_evidence_count": getattr(summary_result, "evidence_count", None),
        "note_mode_chapter_count": getattr(summary_result, "chapter_count", None),
        "note_mode_important_evidence_count": getattr(summary_result, "important_evidence_count", None),
        "note_mode_covered_important_evidence_count": getattr(summary_result, "covered_important_evidence_count", None),
        "note_mode_coverage_missing_count": getattr(summary_result, "coverage_missing_count", None),
    }


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
        return max(float(os.environ.get("FLUENTFLOW_QUEUE_PROCESS_TIMEOUT_SECONDS", "3600")), 60.0)
    except ValueError:
        return 3600.0


def _stale_job_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_STALE_JOB_SECONDS", "7200")), 60.0)
    except ValueError:
        return 7200.0


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


def _enqueue_transcription_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    if not task_id:
        return
    enqueue_job_step(
        task_id=task_id,
        step_type="transcription",
        input=dict(item),
        step_key=f"{task_id}:transcription",
        priority=100,
        max_attempts=1,
    )
    with _QUEUE_LOCK:
        _QUEUED_TASK_IDS.add(task_id)
        _TRANSCRIPTION_QUEUE.put({"wake": "transcription", "task_id": task_id})
        _ensure_queue_worker_started_locked()


def _queue_status_snapshot() -> dict[str, Any]:
    with _QUEUE_LOCK:
        queued_task_ids = sorted(_QUEUED_TASK_IDS)
    queued_steps = list_job_steps(statuses=["queued"], limit=200)
    running_steps = list_job_steps(statuses=["running"], limit=200)
    return {
        "worker_alive": bool(_QUEUE_THREAD and _QUEUE_THREAD.is_alive()),
        "queue_depth": len(queued_steps),
        "running_step_count": len(running_steps),
        "tracked_task_count": len(queued_task_ids),
        "tracked_task_ids": queued_task_ids[:20],
        "queued_step_count": len(queued_steps),
        "queued_steps": [
            {
                "task_id": step.get("task_id"),
                "step_type": step.get("step_type"),
                "attempt_count": step.get("attempt_count"),
            }
            for step in queued_steps[:20]
        ],
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
        signal = _TRANSCRIPTION_QUEUE.get()
        task_id = ""
        try:
            while True:
                step = acquire_next_job_step(
                    step_types=("video_source", "transcription"),
                    lock_timeout_seconds=_queue_timeout_seconds(),
                )
                if not step:
                    break
                task_id = str(step.get("task_id") or "")
                step_id = int(step.get("id") or 0)
                try:
                    _run_job_step(step)
                    if step_id:
                        complete_job_step(step_id)
                except Exception as exc:
                    logger.exception("Background step failed for %s/%s", task_id, step.get("step_type"))
                    if step_id:
                        fail_job_step(step_id, error_reason=_friendly_error_message(exc))
                    _handle_step_failure(step, exc)
        except Exception as exc:
            logger.exception("Background worker failed after signal %s", signal)
        finally:
            with _QUEUE_LOCK:
                _QUEUED_TASK_IDS.clear()
            _TRANSCRIPTION_QUEUE.task_done()


def _run_job_step(step: dict[str, Any]) -> None:
    step_type = str(step.get("step_type") or "")
    item = dict(step.get("input") or {})
    if step_type == "transcription":
        _run_queued_transcription(item)
        return
    if step_type == "video_source":
        _run_video_source_job(item)
        return
    raise RuntimeError(f"Unsupported background step type: {step_type}")


def _handle_step_failure(step: dict[str, Any], exc: Exception) -> None:
    task_id = str(step.get("task_id") or "")
    item = dict(step.get("input") or {})
    if not task_id:
        return
    friendly_error = _friendly_error_message(exc)
    if str(step.get("step_type") or "") == "transcription":
        _release_task_quota(
            client_id=_normalize_client_scope(str(item.get("client_id") or "")),
            task_id=task_id,
            reason="Queued processing failed before completion",
            metadata={"route": "/queue/process", "stage": "queued", "raw_error": str(exc)},
        )
    upsert_job(
        task_id=task_id,
        status="failed",
        client_id=_normalize_client_scope(str(item.get("client_id") or "")),
        stage=str(step.get("step_type") or "queued"),
        progress=0,
        error_reason=friendly_error,
    )
    _publish_job_event_from_thread(
        task_id,
        {"stage": "error", "progress": 0, "error": friendly_error},
    )


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
        "title": options.get("title") or str(item.get("display_title") or "").strip() or display_title_for_user(filename, Path(filename).stem),
        "raw_title": str(item.get("raw_title") or "").strip(),
        "display_title": str(item.get("display_title") or "").strip(),
    }
    headers = {"Accept": "text/event-stream"}
    if str(options.get("stt_provider") or "").strip().lower() == "local":
        headers["X-FluentFlow-Execution-Target"] = "local"
    if client_id:
        headers["X-FluentFlow-Client-Id"] = client_id
    headers["X-FluentFlow-Internal-Queue-Token"] = INTERNAL_QUEUE_TOKEN
    tokens = _configured_access_tokens()
    if tokens:
        headers["X-FluentFlow-Access-Token"] = tokens[0]
    data_fields = {k: str(v) for k, v in fields.items() if v is not None and str(v) != ""}
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    with httpx.Client(timeout=_queue_timeout_seconds()) as client:
        with open(source_path, "rb") as f:
            response = client.post(
                f"{base_url}/process",
                data=data_fields,
                files={"file": (filename, f, content_type)},
                headers=headers,
            )
        if response.is_error:
            raise RuntimeError(f"Queued processing request failed: HTTP {response.status_code} {response.text[:800]}")


def _submit_transcript_source_file(
    *,
    task_id: str,
    source_path: Path,
    filename: str,
    options: dict[str, Any],
    base_url: str,
    client_id: str | None,
) -> None:
    fields = {
        **options,
        "task_id": task_id,
    }
    headers = {"X-FluentFlow-Internal-Queue-Token": INTERNAL_QUEUE_TOKEN}
    if str(options.get("stt_provider") or "").strip().lower() == "local":
        headers["X-FluentFlow-Execution-Target"] = "local"
    if client_id:
        headers["X-FluentFlow-Client-Id"] = client_id
    tokens = _configured_access_tokens()
    if tokens:
        headers["X-FluentFlow-Access-Token"] = tokens[0]
    data_fields = {k: str(v) for k, v in fields.items() if v is not None and str(v) != ""}
    content_type = mimetypes.guess_type(filename)[0] or "text/plain"
    with httpx.Client(timeout=_queue_timeout_seconds()) as client:
        with open(source_path, "rb") as f:
            response = client.post(
                f"{base_url}/summarize-transcript-file",
                data=data_fields,
                files={"file": (filename, f, content_type)},
                headers=headers,
            )
        if response.is_error:
            raise RuntimeError(f"Queued transcript summary request failed: HTTP {response.status_code} {response.text[:800]}")


def _queue_options_from_form(
    *,
    export_to_lark: Optional[str],
    lark_export_route: Optional[str],
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
    elevenlabs_api_key: Optional[str],
    azure_speech_key: Optional[str],
    azure_speech_endpoint: Optional[str],
    azure_blob_container_sas_url: Optional[str],
    speaker_diarization: Optional[str],
    lark_app_id: Optional[str],
    lark_app_secret: Optional[str],
    system_prompt: Optional[str],
    prompt_preset: Optional[str] = None,
    prompt_preset_label: Optional[str] = None,
) -> dict[str, str]:
    raw: dict[str, Optional[str]] = {
        "export_to_lark": export_to_lark,
        "lark_export_route": lark_export_route,
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
        "prompt_preset": prompt_preset,
        "prompt_preset_label": prompt_preset_label,
    }
    return {key: value.strip() for key, value in raw.items() if isinstance(value, str) and value.strip()}


def _queue_options_from_mapping(payload: dict[str, Any] | None) -> dict[str, str]:
    allowed = {
        "export_to_lark",
        "lark_export_route",
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
        "prompt_preset",
        "prompt_preset_label",
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
        "media_type": getattr(saved, "media_type", "video") or "video",
        "source_url": saved.source_url,
        "duration_seconds": getattr(saved, "duration_seconds", None),
        "estimated_size_bytes": getattr(saved, "estimated_size_bytes", None),
        "video_id": saved.video_id,
        "raw_title": getattr(saved, "raw_title", None) or saved.title,
        "display_title": getattr(saved, "display_title", None) or display_title_for_user(saved.title, saved.filename),
        "title": saved.title,
        "filename": saved.filename,
        "file_path": saved.file_path,
        "file_url": saved.file_url,
        "metadata_path": saved.metadata_path,
        "size_bytes": saved.size_bytes,
        "downloaded_at": saved.downloaded_at,
        "asset_strategy": getattr(saved, "asset_strategy", None),
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
        progress_value = _video_source_progress_value(progress)
        upsert_job(
            task_id=task_id,
            status="running",
            client_id=client_id,
            stage=progress.stage,
            progress=progress_value,
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
        _publish_job_event_from_thread(
            task_id,
            {
                "stage": progress.stage,
                "progress": progress_value,
                "message": progress.message,
                "loaded_bytes": progress.loaded_bytes,
                "total_bytes": progress.total_bytes,
            },
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
        source_suffix = source_path.suffix or Path(saved.filename).suffix or ".mp4"
        target_path = _copy_source_file(task_id, source_suffix, source_path)
        source_fingerprint = _source_fingerprint_for_path(target_path, saved.filename)
        source_file_size_mb = _path_size_mb(target_path)
        duration_estimate_sec = _media_duration_seconds(target_path)
        quota_estimate = _estimate_processing_units(
            duration_seconds=duration_estimate_sec,
            skip_summary=_truthy_form(options.get("skip_summary")),
            estimate_only=True,
        )
        media_type = getattr(saved, "media_type", "video") or "video"
        metadata = _metadata(
            route="/video-sources/jobs",
            queue_options=options,
            source_path=str(target_path),
            source_fingerprint=source_fingerprint,
            raw_title=getattr(saved, "raw_title", None) or saved.title,
            display_title=getattr(saved, "display_title", None) or display_title_for_user(saved.title, saved.filename),
            video_source=_public_video_source_metadata(saved),
            asset_strategy=getattr(saved, "asset_strategy", None),
        )
        quota_reservation = None if media_type == "transcript" else _reserve_task_quota(
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
            source_type="transcript_file" if media_type == "transcript" else "video",
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
            source_type="transcript_file" if media_type == "transcript" else "video",
            source_filename=saved.filename,
            source_file_size_mb=source_file_size_mb,
            metadata=metadata,
        )
        _publish_job_event_from_thread(task_id, {"stage": "queued", "progress": 0})
        if media_type == "transcript":
            _submit_transcript_source_file(
                task_id=task_id,
                source_path=target_path,
                filename=saved.filename,
                options=options,
                base_url=base_url,
                client_id=client_id,
            )
            return
        enqueue_item = {
            "task_id": task_id,
            "source_path": str(target_path),
            "filename": saved.filename,
            "raw_title": getattr(saved, "raw_title", None) or saved.title,
            "display_title": getattr(saved, "display_title", None) or display_title_for_user(saved.title, saved.filename),
            "options": options,
            "base_url": base_url,
        }
        if client_id:
            enqueue_item["client_id"] = client_id
        _enqueue_transcription_job(enqueue_item)
    except Exception as exc:
        logger.exception("Video source job failed for %s", task_id)
        friendly_error = _friendly_error_message(exc)
        failure_reason = video_source_failure_reason(exc)
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
                asset_strategy={
                    "transcript_asset": {"status": "unavailable"},
                    "playback_asset": {
                        "status": "available" if input_text else "unavailable",
                        "playback_mode": "external_url" if input_text else "unavailable",
                        "source_url": input_text or None,
                    },
                    "visual_asset": {"status": "unavailable"},
                    "download_status": "failed",
                    "failure_reason": failure_reason,
                },
            ),
        )
        _publish_job_event_from_thread(
            task_id,
            {"stage": "error", "progress": 100, "error": friendly_error},
        )


def _start_video_source_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    if not task_id:
        return
    enqueue_job_step(
        task_id=task_id,
        step_type="video_source",
        input=dict(item),
        step_key=f"{task_id}:video_source",
        priority=50,
        max_attempts=1,
    )
    with _QUEUE_LOCK:
        _QUEUED_TASK_IDS.add(task_id)
        _TRANSCRIPTION_QUEUE.put({"wake": "video_source", "task_id": task_id})
        _ensure_queue_worker_started_locked()


def _resume_queued_transcription_jobs(base_url: str | None = None) -> None:
    requeued_steps = requeue_running_job_steps()
    recovered = 0
    failed = 0
    for job in list_jobs(limit=200):
        status = job.get("status")
        raw_metadata = job.get("metadata") or {}
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        if status not in {"queued", "running"}:
            continue
        task_id = str(job.get("task_id") or "")
        if list_job_steps(task_id=task_id, statuses=["queued", "running"], limit=1):
            recovered += 1
            continue
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
    if recovered or failed or requeued_steps:
        with _QUEUE_LOCK:
            _TRANSCRIPTION_QUEUE.put({"wake": "startup_recovery"})
            _ensure_queue_worker_started_locked()
        logger.info(
            "Startup queue recovery finished: recovered=%s failed=%s requeued_steps=%s",
            recovered,
            failed,
            requeued_steps,
        )


async def _startup_resume_queue() -> None:
    global _QUEUE_EVENT_LOOP
    _QUEUE_EVENT_LOOP = asyncio.get_running_loop()
    migrated = migrate_job_display_titles()
    if migrated:
        logger.info("Backfilled display titles for %s existing jobs", migrated)
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
        if not credentials.get("elevenlabs_api_key_configured"):
            failures.append("缺少 ElevenLabs API Key")
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


# ── SPA / Frontend paths ───────────────────────────────────────
FRONTEND_ROOT: Path = Path(__file__).resolve().parents[2] / "frontend"
FRONTEND_DIST_DIR: Path = FRONTEND_ROOT / "dist"
FRONTEND_DIR: Path = FRONTEND_DIST_DIR if (FRONTEND_DIST_DIR / "index.html").exists() else FRONTEND_ROOT
FRONTEND_INDEX: Path = FRONTEND_DIR / "index.html"
API_ROUTE_PREFIXES: set[str] = {
    "account",
    "admin",
    "agent",
    "auth",
    "credentials",
    "events",
    "export-lark",
    "guest-trial",
    "health",
    "hotword-libraries",
    "jobs",
    "local-history",
    "ops",
    "process",
    "queue",
    "regenerate-summary",
    "runtime-config",
    "speaker-diarization",
    "summarize-transcript-file",
    "video-sources",
}

FRONTEND_EXACT_PATHS: set[str] = {
    "/app",
    "/media-text",
    "/agent",
    "/processing",
    "/tasks",
    "/editor",
    "/admin",
    "/settings",
    "/workspace/api",
    "/about",
}

FRONTEND_ROUTE_PREFIXES: tuple[str, ...] = (
    "/about/",
    "/tasks/",
)


def _is_frontend_spa_route(path: str | None) -> bool:
    normalized = "/" + (path or "").strip("/")
    if normalized == "/":
        return True
    return normalized in FRONTEND_EXACT_PATHS or normalized.startswith(FRONTEND_ROUTE_PREFIXES)


def _is_api_route_path(path: str | None) -> bool:
    normalized = "/" + (path or "").strip("/")
    if _is_frontend_spa_route(normalized):
        return False
    first_segment = (normalized.lstrip("/").split("/", 1)[0] or "")
    return first_segment in API_ROUTE_PREFIXES
