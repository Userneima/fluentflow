from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import asyncio
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


def _translation_ai_kwargs(ai_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in ai_kwargs.items()
        if key in {"api_key", "model", "provider"}
    }


@router.get("/local-history/candidates", include_in_schema=False)
def removed_local_history_candidates() -> None:
    raise HTTPException(status_code=404, detail="Local history import has been removed")


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
    cancelled_steps = H.cancel_job_steps(task_id)
    with H._QUEUE_LOCK:
        queued_before_cancel = task_id in H._QUEUED_TASK_IDS
        H._QUEUED_TASK_IDS.discard(task_id)

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
        "cancelled_steps": cancelled_steps,
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
    had_translation = any(
        str(segment.get("text_zh") or "").strip()
        for segment in H._canonical_display_segments(result)
    ) or bool(result.get("bilingual_segments") or result.get("translated_segments_zh"))
    result.update({
        "task_id": result.get("task_id") or task_id,
        "transcript_text": transcript,
        "transcript_text_preview": transcript[:200],
        "raw_segments": segments,
        "display_segments": segments,
        "subtitle_mode": "source_only",
        "translation_status": "stale" if had_translation else result.get("translation_status"),
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


@router.post("/jobs/{task_id}/translations/zh")
async def generate_job_zh_translations(
    request: Request,
    task_id: str,
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    payload = payload or {}
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = dict(job.get("result") or {})
    source_segments = (
        H._sanitize_edit_segments(payload.get("segments"))
        or H._canonical_raw_segments(result)
    )
    if not source_segments:
        raise HTTPException(status_code=400, detail="No timestamped transcript segments to translate")

    ai_kwargs = H._ai_kwargs(
        deepseek_api_key=payload.get("deepseek_api_key") or payload.get("deepseekApiKey"),
        openai_api_key=payload.get("openai_api_key") or payload.get("openaiApiKey"),
        ai_provider=payload.get("ai_provider") or payload.get("aiProvider"),
        ai_model=payload.get("ai_model") or payload.get("aiModel"),
        system_prompt=None,
    )
    translation_kwargs = _translation_ai_kwargs(ai_kwargs)
    try:
        loop = asyncio.get_running_loop()
        translation_result = await loop.run_in_executor(
            None,
            lambda: H.generate_bilingual_segments_zh(source_segments, **translation_kwargs),
        )
    except Exception as exc:
        error_reason = H._friendly_error_message(exc)
        H.logger.warning("Manual segment translation failed for %s: %s", task_id, exc)
        result.update({
            "task_id": result.get("task_id") or task_id,
            "translation_status": "failed",
            "translation_error": error_reason,
        })
        H.update_job_result(task_id, result, client_id=client_id)
        raise HTTPException(status_code=502, detail=error_reason) from exc

    bilingual_segments = translation_result.segments
    if not bilingual_segments:
        error_reason = "AI returned no usable bilingual subtitle segments"
        result.update({
            "task_id": result.get("task_id") or task_id,
            "translation_status": "failed",
            "translation_error": error_reason,
        })
        H.update_job_result(task_id, result, client_id=client_id)
        raise HTTPException(status_code=502, detail=error_reason)
    translated_segment_count = len([segment for segment in bilingual_segments if segment.get("text_zh")])

    result.update({
        "task_id": result.get("task_id") or task_id,
        "raw_segments": source_segments,
        "display_segments": bilingual_segments,
        "subtitle_mode": "bilingual_zh",
        "translation_status": "completed",
        "translation_error": None,
    })
    result = H._attach_result_artifacts(task_id, result)
    updated = H.update_job_result(task_id, result, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")

    H.log_event(
        task_id=task_id,
        event_name="translation_completed",
        source_type=job.get("source_type"),
            source_filename=job.get("source_filename"),
            stage="translation",
            success=True,
            metadata=H._metadata(
                route="/jobs/{task_id}/translations/zh",
                bilingual_segment_count=len(bilingual_segments),
                translated_segment_count=translated_segment_count,
                translation_chunk_count=translation_result.chunk_count,
                trigger="editor",
        ),
    )
    return {
        "ok": True,
        "job": updated,
        "result": updated.get("result"),
        "display_segments": bilingual_segments,
    }



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
        "frame": ".jpg",
    }
    suffix = allowed.get(kind)
    if not suffix:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target_dir = H._artifact_storage_dir() / task_id
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Artifact not found")

    if kind == "frame":
        frame_file = request.query_params.get("file", "").strip()
        if not frame_file or ".." in frame_file or "/" in frame_file or "\\" in frame_file:
            raise HTTPException(status_code=404, detail="Artifact not found")
        target = target_dir / "frames" / frame_file
        if target.is_file():
            return FileResponse(path=str(target), filename=target.name)
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
