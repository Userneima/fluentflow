"""STT provider resolution helpers (canonical/allowed/default/label),
extracted from server_helpers.py. Depend only on _env + os + request
attributes — re-imported by server_helpers so H._*_stt_* keep working."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Request

from backend.core._env import _public_mode_enabled, _request_is_internal_queue


def _canonical_stt_provider(value: str | None) -> str:
    provider = (value or "").strip().lower().replace("-", "_")
    if provider in {"cloud", "cloud_stt", "elevenlabs", "elevenlabs_scribe", "scribe", "scribe_v2"}:
        return "elevenlabs_scribe"
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
        if provider in {"elevenlabs_scribe", "local"} and provider not in providers:
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
    return "faster-whisper"
