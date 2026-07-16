from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H

router = APIRouter()

_CLOUD_STT_DIAGNOSTIC_FIELDS = (
    "elevenlabs_audio_size_mb",
    "elevenlabs_duration_seconds",
    "elevenlabs_model",
    "elevenlabs_request_started_at",
    "elevenlabs_response_received_at",
    "elevenlabs_request_id",
    "elevenlabs_http_status",
    "elevenlabs_response_valid_json",
    "elevenlabs_response_text_chars",
    "elevenlabs_response_word_count",
    "elevenlabs_outcome",
)


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _minute_key(value: Any) -> str:
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return ""
    return parsed.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()


def _cloud_stt_task(job: dict[str, Any]) -> dict[str, Any] | None:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    diagnostics = result.get("cloud_transcription") if isinstance(result.get("cloud_transcription"), dict) else metadata
    provider = str(result.get("stt_provider") or metadata.get("stt_provider") or diagnostics.get("provider") or "").strip()
    if provider != "elevenlabs_scribe":
        return None
    return {
        "task_id": job.get("task_id"),
        "title": result.get("display_title") or metadata.get("display_title") or result.get("filename") or job.get("source_filename"),
        "status": job.get("status"),
        "updated_at": job.get("updated_at"),
        "audio_duration_seconds": result.get("audio_duration_seconds") or diagnostics.get("elevenlabs_duration_seconds"),
        **{field: diagnostics[field] for field in _CLOUD_STT_DIAGNOSTIC_FIELDS if diagnostics.get(field) is not None},
    }


def _attribute_task_credits(tasks: list[dict[str, Any]], provider_usage: dict[str, Any]) -> None:
    """Attribute credits only when the provider request and 60-second bucket are unique."""
    requests = provider_usage.get("requests") if isinstance(provider_usage.get("requests"), list) else []
    buckets = provider_usage.get("usage_buckets") if isinstance(provider_usage.get("usage_buckets"), list) else []
    request_by_id = {
        str(item.get("request_id") or ""): item
        for item in requests
        if isinstance(item, dict) and str(item.get("request_id") or "")
    }
    requests_by_minute: dict[str, list[dict[str, Any]]] = {}
    for item in requests:
        if isinstance(item, dict):
            requests_by_minute.setdefault(_minute_key(item.get("timestamp")), []).append(item)
    credits_by_minute: dict[str, float] = {}
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        try:
            credits = float(bucket.get("credits_used"))
        except (TypeError, ValueError):
            continue
        minute = _minute_key(bucket.get("timestamp"))
        if minute:
            credits_by_minute[minute] = credits_by_minute.get(minute, 0.0) + credits

    for task in tasks:
        request_id = str(task.get("elevenlabs_request_id") or "")
        request = request_by_id.get(request_id)
        minute = _minute_key(request.get("timestamp")) if request else ""
        matching_tasks = [
            item for item in tasks
            if str(item.get("elevenlabs_request_id") or "") in {
                str(candidate.get("request_id") or "")
                for candidate in requests_by_minute.get(minute, [])
            }
        ]
        if request and len(requests_by_minute.get(minute, [])) == 1 and len(matching_tasks) == 1 and minute in credits_by_minute:
            task["credit_attribution"] = {
                "status": "attributed",
                "credits_used": round(credits_by_minute[minute], 3),
                "provider_timestamp": request.get("timestamp"),
            }
        else:
            task["credit_attribution"] = {
                "status": "unattributed",
                "reason": "Provider credits are aggregated; this request cannot be uniquely matched.",
            }


@router.get("/admin/users")
def admin_list_users(request: Request, limit: int = 100) -> dict[str, Any]:
    H._require_admin_user(request)
    users = []
    for user in H.list_users(limit=limit):
        public = H._public_account_payload(user)
        if public:
            users.append(public)
    return {"users": users}


@router.get("/admin/cloud-transcription-usage")
def admin_cloud_transcription_usage(
    request: Request,
    hours: int = 168,
    limit: int = 100,
) -> dict[str, Any]:
    H._require_admin_user(request)
    safe_hours = max(1, min(int(hours or 168), 24 * 30))
    safe_limit = max(1, min(int(limit or 100), 200))
    end_at = datetime.now(timezone.utc)
    start_at = end_at - timedelta(hours=safe_hours)
    provider_usage = H.get_elevenlabs_workspace_usage(start_at=start_at, end_at=end_at)
    tasks = [item for job in H.list_jobs(limit=200) if (item := _cloud_stt_task(job))]
    tasks = [
        task for task in tasks
        if (_parse_iso_datetime(task.get("elevenlabs_response_received_at") or task.get("updated_at")) or end_at) >= start_at
    ]
    _attribute_task_credits(tasks, provider_usage)
    tasks = tasks[:safe_limit]
    attributed_credits = sum(
        float((task.get("credit_attribution") or {}).get("credits_used") or 0)
        for task in tasks
        if (task.get("credit_attribution") or {}).get("status") == "attributed"
    )
    return {
        "provider": "elevenlabs_scribe",
        "window": provider_usage.get("window") or {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        "workspace_usage": {
            "available": bool(provider_usage.get("available")),
            "reason": provider_usage.get("reason") or "",
            "request_telemetry_reason": provider_usage.get("request_telemetry_reason") or "",
            "credits_used": provider_usage.get("credits_used"),
            "provider_request_count": len(provider_usage.get("requests") or []),
            "currency": "credits",
        },
        "tasks": tasks,
        "task_count": len(tasks),
        "attributed_task_count": sum(
            1 for task in tasks if (task.get("credit_attribution") or {}).get("status") == "attributed"
        ),
        "attributed_credits_used": round(attributed_credits, 3),
    }



@router.post("/admin/users/{user_id}/balance-adjustments")
def admin_adjust_user_balance(
    request: Request,
    user_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    admin = H._require_admin_user(request)
    target = H.get_user_by_id(user_id)
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
        tx = H.add_admin_adjustment(
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
        "user": H._public_account_payload(target),
    }
