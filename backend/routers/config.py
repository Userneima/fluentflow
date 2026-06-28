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
    }



@router.post("/plan-note-task")
def plan_note_task_endpoint(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Recommend note-generation settings without generating the note itself."""
    provider = str(payload.get("ai_provider") or payload.get("provider") or "").strip() or None
    model = str(payload.get("ai_model") or payload.get("model") or "").strip() or None
    provider_for_secret = (provider or os.environ.get("AI_PROVIDER") or "deepseek").strip().lower()
    if provider_for_secret == "openai":
        api_key = H.resolve_secret(payload.get("openai_api_key"), "openai_api_key")
    elif provider_for_secret == "qwen":
        api_key = H.resolve_secret(payload.get("qwen_api_key"), "qwen_api_key")
    else:
        api_key = H.resolve_secret(payload.get("deepseek_api_key"), "deepseek_api_key")

    started_at = time.perf_counter()
    task_id_value = str(payload.get("task_id") or "").strip() or H._new_task_id()
    try:
        plan = H.plan_note_task(
            filename=payload.get("filename"),
            transcript_preview=payload.get("transcript_preview"),
            transcript_length=payload.get("transcript_length"),
            duration_seconds=payload.get("duration_seconds"),
            user_goal=payload.get("user_goal"),
            current_note_mode=payload.get("current_note_mode"),
            current_prompt_preset=payload.get("current_prompt_preset"),
            provider=provider,
            model=model,
            api_key=api_key,
        )
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="agent_plan_failed",
            source_filename=payload.get("filename"),
            transcript_length=payload.get("transcript_length"),
            stage="agent_plan",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/plan-note-task", raw_error=str(exc)),
        )
        raise HTTPException(status_code=500, detail=friendly_error) from exc

    plan_payload = plan.to_dict()
    H.log_event(
        task_id=task_id_value,
        event_name="agent_plan_generated",
        source_filename=payload.get("filename"),
        transcript_length=payload.get("transcript_length"),
        stage="agent_plan",
        duration_seconds=round(time.perf_counter() - started_at, 3),
        success=True,
        metadata=H._metadata(
            route="/plan-note-task",
            material_type=plan.material_type,
            recommended_note_mode=plan.recommended_note_mode,
            recommended_prompt_preset=plan.recommended_prompt_preset,
            confidence=plan.confidence,
            planner_provider=plan.planner_provider,
            planner_model=plan.planner_model,
        ),
    )
    return {"ok": True, "task_id": task_id_value, "plan": plan_payload}



@router.get("/speaker-diarization/status")
def get_speaker_diarization_status() -> dict[str, Any]:
    return H.diarization_status()



@router.post("/credentials")
def update_credentials(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    allowed = {
        "deepseek_api_key",
        "openai_api_key",
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
