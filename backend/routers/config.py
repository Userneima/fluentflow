from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import os
import time

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H

router = APIRouter()


@router.get("/credentials/status")
def get_credentials_status() -> dict[str, Any]:
    return H.credential_status()



@router.get("/runtime-config")
def runtime_config(request: Request) -> dict[str, Any]:
    allowed = list(H._allowed_stt_providers(request))
    return {
        "public_mode": H._public_mode_enabled(),
        "auth_mode": "accounts" if H._account_auth_enabled() else ("access_code" if H._access_control_enabled() else "open"),
        "allowed_stt_providers": allowed,
        "default_stt_provider": H._default_stt_provider(request),
        "show_maintainer_settings": not H._public_mode_enabled(),
        "limits": H._runtime_limits_for_request(request),
        "guest_trial": H._guest_trial_config(),
        "features": {
            "job_retry_from_stored_source": True,
        },
    }



@router.get("/speaker-diarization/status")
def get_speaker_diarization_status() -> dict[str, Any]:
    return H.diarization_status()



@router.post("/credentials")
def update_credentials(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    allowed = {
        "deepseek_api_key",
        "openai_api_key",
        "dashscope_api_key",
        "qwen_api_key",
        "lark_app_id",
        "lark_app_secret",
        "pyannote_auth_token",
        "elevenlabs_api_key",
        "azure_speech_key",
        "azure_speech_endpoint",
        "azure_blob_container_sas_url",
    }
    return H.save_sensitive_settings({k: v for k, v in payload.items() if k in allowed})



@router.post("/azure-speech/smoke-test")
def azure_speech_smoke_test(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    endpoint = H.resolve_secret(payload.get("azure_speech_endpoint"), "azure_speech_endpoint")
    api_key = H.resolve_secret(payload.get("azure_speech_key"), "azure_speech_key")
    if not endpoint or not api_key:
        missing = []
        if not endpoint:
            missing.append("Speech address")
        if not api_key:
            missing.append("Speech key")
        raise HTTPException(status_code=400, detail="Azure Speech smoke test is missing " + " and ".join(missing))
    try:
        return H.run_short_audio_smoke_test(
            endpoint=endpoint,
            api_key=api_key,
            language=(payload.get("language") or "en-US"),
            phrase=payload.get("phrase"),
            timeout=float(payload.get("timeout") or 60),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc



@router.get("/hotword-libraries", include_in_schema=False)
def removed_hotword_libraries() -> None:
    """Legacy endpoint kept only to avoid the SPA fallback masking removal."""
    raise HTTPException(status_code=410, detail="Built-in hotword libraries have been removed")
