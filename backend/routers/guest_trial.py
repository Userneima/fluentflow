from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H

router = APIRouter()


@router.get("/guest-trial/status")
def guest_trial_status(request: Request, task_id: Optional[str] = None) -> dict[str, Any]:
    H._enforce_guest_trial_enabled()
    if task_id:
        job = H._guest_job_for_request(request, task_id)
        return H._guest_trial_status_payload(job)
    return H._guest_trial_status_payload()



@router.post("/guest-trial/heartbeat")
def guest_trial_heartbeat(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    H._enforce_guest_trial_enabled()
    task_id = str(payload.get("task_id") or request.query_params.get("task_id") or "").strip()
    if task_id:
        job = H._guest_job_for_request(request, task_id)
        return H._guest_trial_status_payload(job)
    return H._guest_trial_status_payload()



@router.post("/guest-trial/process")
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
    H._enforce_guest_trial_enabled()
    H._enforce_guest_queue_capacity()
    H._enforce_guest_daily_ip_limit(request)
    H._enforce_submission_rate_limit(request, incoming=1)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in H.ALLOWED_SUFFIXES or suffix in H.TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    source_file_size_mb = H._upload_size_mb(file)
    effective_limit_mb = min(H._max_upload_mb(), H._guest_file_limit_mb())
    if source_file_size_mb is not None and source_file_size_mb > effective_limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"访客试用支持 {effective_limit_mb:g} MB 以内的单个音视频文件。",
        )

    content = await file.read()
    source_file_size_mb = H._file_size_mb(len(content))
    if source_file_size_mb is not None and source_file_size_mb > effective_limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"访客试用支持 {effective_limit_mb:g} MB 以内的单个音视频文件。",
        )

    token = H._new_guest_trial_token()
    client_id = H._guest_client_id(token)
    task_id_value = H._new_task_id()
    source_type = H._source_type_for_suffix(suffix)
    source_fingerprint = H._source_fingerprint(content, file.filename)
    source_path = H._persist_source_file(task_id_value, suffix, content)
    expires_at = (
        datetime.now(timezone.utc).astimezone() + H.timedelta(hours=H._guest_result_retention_hours())
    ).isoformat(timespec="seconds")

    options = H._queue_options_from_mapping({
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "note_mode": note_mode,
        "skip_summary": "false",
        "stt_model": stt_model,
        "stt_language": stt_language,
        "stt_provider": stt_provider or H._default_stt_provider(),
        "speaker_diarization": speaker_diarization,
        "system_prompt": system_prompt,
        "duration_limit_seconds": str(H._guest_duration_limit_seconds()),
    })
    metadata = H._metadata(
        route="/guest-trial/process",
        queue_options=options,
        source_path=str(source_path),
        source_fingerprint=source_fingerprint,
        guest_trial={
            "token": token,
            "ip_key": H._request_ip_key(request),
            "expires_at": expires_at,
            "file_limit_mb": effective_limit_mb,
            "duration_limit_seconds": H._guest_duration_limit_seconds(),
        },
    )
    H.log_event(
        task_id=task_id_value,
        event_name="guest_trial_queued",
        source_type=source_type,
        source_filename=file.filename,
        source_file_size_mb=source_file_size_mb,
        stage="queued",
        success=True,
        metadata=metadata,
    )
    H.upsert_job(
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
    H._enqueue_transcription_job({
        "task_id": task_id_value,
        "source_path": str(source_path),
        "filename": file.filename,
        "options": options,
        "base_url": H._queue_base_url_from_request(request),
        "client_id": client_id,
    })
    job = H.get_job(task_id_value, client_id=client_id)
    return {
        "ok": True,
        "guest_token": token,
        "task_id": task_id_value,
        "job": job,
        "queue": H._guest_queue_snapshot(task_id_value),
        "config": H._guest_trial_config(),
    }



@router.get("/guest-trial/jobs/{task_id}")
def get_guest_trial_job(request: Request, task_id: str) -> dict[str, Any]:
    H._enforce_guest_trial_enabled()
    return H._guest_job_for_request(request, task_id)



@router.get("/guest-trial/jobs/{task_id}/events")
async def stream_guest_trial_job_events(request: Request, task_id: str, since: int = 0) -> StreamingResponse:
    H._enforce_guest_trial_enabled()
    H._guest_job_for_request(request, task_id)
    return StreamingResponse(
        H.JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.post("/guest-trial/jobs/{task_id}/cancel")
async def cancel_guest_trial_job(request: Request, task_id: str) -> dict[str, Any]:
    H._enforce_guest_trial_enabled()
    job = H._guest_job_for_request(request, task_id)
    if job.get("status") not in {"queued", "running"}:
        return {"ok": True, "status": job.get("status")}
    await H.JOB_EVENTS.cancel(task_id)
    H.cancel_job_steps(task_id)
    H.upsert_job(
        task_id=task_id,
        status="cancelled",
        client_id=job.get("client_id"),
        stage="cancelled",
        progress=0,
        error_reason="guest_cancelled",
    )
    return {"ok": True, "status": "cancelled"}



@router.get("/guest-trial/jobs/{task_id}/artifacts/{kind}")
def download_guest_trial_artifact(request: Request, task_id: str, kind: str) -> FileResponse:
    H._enforce_guest_trial_enabled()
    H._guest_job_for_request(request, task_id)
    allowed = {
        "transcript_txt": ".txt",
        "transcript_srt": ".srt",
        "transcript_vtt": ".vtt",
        "transcript_bilingual_srt": ".srt",
        "transcript_bilingual_vtt": ".vtt",
        "summary_md": ".md",
        "playback_audio": ".mp3",
    }
    suffix = allowed.get(kind)
    if not suffix:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target_dir = H._artifact_storage_dir() / task_id
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Artifact not found")
    matches = sorted(path for path in target_dir.glob(f"*{suffix}") if path.is_file())
    if kind == "summary_md":
        matches = [path for path in matches if path.name.endswith("_summary.md")]
    elif kind == "transcript_bilingual_srt":
        matches = [path for path in matches if path.name.endswith("_bilingual_zh.srt")]
    elif kind == "transcript_bilingual_vtt":
        matches = [path for path in matches if path.name.endswith("_bilingual_zh.vtt")]
    elif kind == "transcript_txt":
        matches = [path for path in matches if not path.name.endswith("_summary.md")]
    if not matches:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target = matches[0]
    return FileResponse(path=str(target), filename=target.name)
