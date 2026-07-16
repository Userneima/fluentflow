"""Read-only ElevenLabs workspace usage helpers for the admin surface."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx


ELEVENLABS_USAGE_URL = "https://api.elevenlabs.io/v1/workspace/analytics/query/usage-by-product-over-time"
ELEVENLABS_REQUESTS_URL = "https://api.elevenlabs.io/v1/workspace/analytics/requests"
ELEVENLABS_STT_ENDPOINT = "/v1/speech-to-text"


def get_workspace_transcription_usage(
    *,
    start_at: datetime,
    end_at: datetime,
    api_key: str | None = None,
    timeout: float = 15,
) -> dict[str, Any]:
    """Return provider-billed credits and request telemetry without task content."""
    key = (api_key or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    window = {
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
    }
    if not key:
        return {
            "available": False,
            "reason": "ElevenLabs API key is not configured.",
            "window": window,
            "credits_used": None,
            "requests": [],
            "usage_buckets": [],
        }

    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    start_time = int(start_at.timestamp() * 1000)
    end_time = int(end_at.timestamp() * 1000)
    try:
        with httpx.Client(timeout=timeout) as client:
            usage_response = client.post(
                ELEVENLABS_USAGE_URL,
                headers=headers,
                json={
                    "start_time": start_time,
                    "end_time": end_time,
                    "interval_seconds": 60,
                    "group_by": ["product_type"],
                    "time_zone": "UTC",
                },
            )
            usage_response.raise_for_status()
            usage_payload = usage_response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "available": False,
            "reason": f"ElevenLabs usage analytics returned HTTP {exc.response.status_code}.",
            "window": window,
            "credits_used": None,
            "requests": [],
            "usage_buckets": [],
        }
    except httpx.RequestError:
        return {
            "available": False,
            "reason": "ElevenLabs usage analytics request failed.",
            "window": window,
            "credits_used": None,
            "requests": [],
            "usage_buckets": [],
        }
    except ValueError:
        return {
            "available": False,
            "reason": "ElevenLabs usage analytics returned invalid JSON.",
            "window": window,
            "credits_used": None,
            "requests": [],
            "usage_buckets": [],
        }

    request_telemetry_reason = ""
    try:
        with httpx.Client(timeout=timeout) as client:
            requests_response = client.post(
                ELEVENLABS_REQUESTS_URL,
                headers=headers,
                json={"start_time": start_time, "end_time": end_time, "limit": 1000},
            )
            requests_response.raise_for_status()
            requests_payload = requests_response.json()
    except httpx.HTTPStatusError as exc:
        request_telemetry_reason = f"ElevenLabs request analytics returned HTTP {exc.response.status_code}."
        requests_payload = {}
    except httpx.RequestError:
        request_telemetry_reason = "ElevenLabs request analytics request failed."
        requests_payload = {}
    except ValueError:
        request_telemetry_reason = "ElevenLabs request analytics returned invalid JSON."
        requests_payload = {}

    usage_rows = _tabular_rows(usage_payload)
    request_rows = _tabular_rows(requests_payload)
    usage_buckets = [
        {
            "timestamp": row.get("timestamp"),
            "credits_used": _number(row.get("credits_used")),
            "product_type": str(row.get("product_type") or ""),
        }
        for row in usage_rows
        if _is_speech_to_text(row.get("product_type"))
    ]
    requests = [
        {
            "request_id": str(row.get("request_id") or ""),
            "timestamp": row.get("timestamp"),
            "endpoint": str(row.get("endpoint") or ""),
            "success": row.get("success"),
        }
        for row in request_rows
        if str(row.get("endpoint") or "").strip() == ELEVENLABS_STT_ENDPOINT
    ]
    return {
        "available": True,
        "reason": "",
        "request_telemetry_reason": request_telemetry_reason,
        "window": window,
        "credits_used": round(sum(bucket["credits_used"] or 0 for bucket in usage_buckets), 3),
        "requests": requests,
        "usage_buckets": usage_buckets,
    }


def _tabular_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []
    names = [str(column) for column in columns]
    return [
        dict(zip(names, row))
        for row in rows
        if isinstance(row, list)
    ]


def _is_speech_to_text(value: Any) -> bool:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return normalized in {"speech_to_text", "speech_to_text_v2"}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
