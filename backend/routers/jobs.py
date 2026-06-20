from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H

router = APIRouter()


@router.get("/local-history/candidates")
def local_history_candidates(request: Request, limit: int = 100) -> dict[str, Any]:
    if not H._local_history_export_allowed(request):
        return {"jobs": [], "count": 0, "available": False}
    safe_limit = max(1, min(int(limit or 100), 200))
    candidates = [
        job
        for job in H.list_jobs(limit=safe_limit)
        if isinstance(job.get("result"), dict)
        and (job.get("status") == "completed" or H.job_has_transcript_result(job))
    ]
    return {"jobs": candidates, "count": len(candidates), "available": True}



@router.get("/jobs/{task_id}")
def get_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job



@router.post("/jobs/{task_id}/cancel")
async def cancel_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Job is already {job.get('status')}")

    cancelled_running_task = await H.JOB_EVENTS.cancel(task_id)
    with H._QUEUE_LOCK:
        queued_before_cancel = task_id in H._QUEUED_TASK_IDS

    H._release_task_quota(
        client_id=client_id,
        task_id=task_id,
        reason="Task cancelled from background tasks",
        metadata={"route": "/jobs/{task_id}/cancel", "stage": job.get("stage")},
    )
    H.upsert_job(
        task_id=task_id,
        status="cancelled",
        client_id=job.get("client_id") or client_id,
        stage=job.get("stage") or "cancelled",
        progress=job.get("progress") or 0,
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        source_file_size_mb=job.get("source_file_size_mb"),
        summary_status=job.get("summary_status"),
        error_reason="user_cancelled",
        metadata=job.get("metadata"),
    )
    await H.JOB_EVENTS.publish(
        task_id,
        {"stage": "error", "progress": job.get("progress") or 0, "error": "Task cancelled"},
    )
    H.log_event(
        task_id=task_id,
        event_name="task_cancelled",
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        source_file_size_mb=job.get("source_file_size_mb"),
        stage=job.get("stage"),
        success=False,
        metadata=H._metadata(trigger="background_tasks"),
    )
    return {
        "ok": True,
        "task_id": task_id,
        "status": "cancelled",
        "cancelled_running_task": cancelled_running_task,
        "queued_before_cancel": queued_before_cancel,
    }


def _delete_job_for_request(request: Request, task_id: str) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Cancel running jobs before deleting them")
    H._cleanup_task_all_files(task_id, job.get("metadata"))
    deleted = H.delete_jobs([task_id], client_id=client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "task_id": task_id, "deleted": True}



@router.delete("/jobs/{task_id}")
def delete_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    return _delete_job_for_request(request, task_id)



@router.post("/jobs/{task_id}/delete")
def delete_job_detail_fallback(request: Request, task_id: str) -> dict[str, Any]:
    return _delete_job_for_request(request, task_id)



@router.patch("/jobs/{task_id}/transcript")
def update_job_transcript(request: Request, task_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = dict(job.get("result") or {})
    transcript = payload.get("transcript_text")
    if not isinstance(transcript, str):
        raise HTTPException(status_code=400, detail="transcript_text is required")
    max_chars = int(os.environ.get("FLUENTFLOW_MAX_TRANSCRIPT_EDIT_CHARS", "1000000"))
    if len(transcript) > max_chars:
        raise HTTPException(status_code=413, detail=f"Transcript edit is too large: {len(transcript)} chars")

    segments = H._sanitize_edit_segments(payload.get("segments"))
    edit_records = H._sanitize_edit_records(payload.get("edit_records"))
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
        backup_path = H._write_edited_transcript_backup(task_id, result)
        edit_records_path = H._write_transcript_edit_records_backup(task_id, result, edit_records)
    except Exception as exc:
        H.logger.warning("Edited transcript backup failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Edited transcript backup failed") from exc

    result.update({
        "edited_transcript_path": str(backup_path),
        "edited_transcript_saved_at": edited_at,
        "transcript_edit_records_path": str(edit_records_path),
    })
    result = H._attach_result_artifacts(task_id, result)
    updated = H.update_job_result(task_id, result, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": updated, "result": updated.get("result")}



@router.get("/jobs/{task_id}/events")
async def stream_job_events(request: Request, task_id: str, since: int = 0) -> StreamingResponse:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        H.JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.get("/jobs/{task_id}/source")
def download_job_source(request: Request, task_id: str) -> FileResponse:
    if not H.get_job(task_id, client_id=H._request_client_scope(request)):
        raise HTTPException(status_code=404, detail="Source file not found")
    source = H._find_source_file(task_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path=str(source), filename=source.name)



@router.post("/jobs/{task_id}/playback-audio")
async def upload_job_playback_audio(request: Request, task_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    filename = Path(file.filename or "source_audio").name
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
        ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
    }
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Unsupported media format")

    content = await file.read()
    size_mb = H._file_size_mb(len(content))
    limit_mb = H._max_upload_mb()
    if size_mb is not None and limit_mb > 0 and size_mb > limit_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {size_mb} MB. Limit is {limit_mb:g} MB.",
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = Path(tmp.name)
        result = dict(job.get("result") or {})
        result["task_id"] = result.get("task_id") or task_id
        result["filename"] = result.get("filename") or filename
        result = H._attach_playback_audio_artifact(task_id, result, temp_path, source_filename=filename)
        updated = H.update_job_result(task_id, result, client_id=client_id)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except TypeError:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": updated, "result": updated.get("result")}



@router.get("/jobs/{task_id}/artifacts/{kind}")
def download_job_artifact(request: Request, task_id: str, kind: str) -> FileResponse:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Artifact not found")
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
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    artifact = (result.get("artifacts") or {}).get(kind) if isinstance(result.get("artifacts"), dict) else None
    artifact_filename = Path(str((artifact or {}).get("filename") or "")).name if isinstance(artifact, dict) else ""
    if artifact_filename:
        target = target_dir / artifact_filename
        if target.is_file():
            return FileResponse(path=str(target), filename=target.name)
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
