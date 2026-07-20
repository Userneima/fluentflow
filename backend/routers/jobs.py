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

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H
from backend.core.media_preflight import MediaPreflightError, preflight_media_file
from backend.core.oss_upload_sessions import get_oss_upload_session
from backend.core.task_detail import build_task_detail, build_task_snapshot
from backend.core.desktop_sync_client import sync_terminal_local_job
from backend.core.desktop_sync_policy import desktop_sync_read_only_detail, is_local_desktop_sync_job

router = APIRouter()


@router.get("/local-history/candidates", include_in_schema=False)
def local_history_import_removed() -> None:
    raise HTTPException(status_code=410, detail="Local history import has been removed")


def _translation_ai_kwargs(ai_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in ai_kwargs.items()
        if key in {"api_key", "model", "provider"}
    }


def _reject_cloud_write_to_desktop_sync_job(request: Request, job: dict[str, Any]) -> None:
    if is_local_desktop_sync_job(job) and not H._request_is_local_execution(request):
        raise HTTPException(status_code=409, detail=desktop_sync_read_only_detail(job))


def _sync_local_desktop_result_after_write(
    request: Request,
    updated: dict[str, Any] | None,
    background_tasks: BackgroundTasks,
) -> None:
    if updated and H._request_is_local_execution(request):
        background_tasks.add_task(sync_terminal_local_job, updated)


@router.get("/jobs/{task_id}")
def get_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {**job, "task_snapshot": build_task_snapshot(job)}


@router.get("/jobs/{task_id}/detail")
def get_job_processing_detail(request: Request, task_id: str) -> dict[str, Any]:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    steps = H.list_job_steps(task_id=task_id, limit=100)
    return build_task_detail(job, job_steps=steps)



@router.post("/jobs/{task_id}/cancel")
async def cancel_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)
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
    _reject_cloud_write_to_desktop_sync_job(request, job)
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


@router.post("/jobs/{task_id}/retry")
def retry_job_from_stored_source(request: Request, task_id: str) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)
    if job.get("status") in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Cancel the active job before retrying it")

    source = H._find_source_file(task_id)
    if not source:
        return _retry_job_from_oss_source(request=request, task_id=task_id, job=job, client_id=client_id)

    H._enforce_submission_rate_limit(request, incoming=1)
    H._enforce_active_job_limit(client_id, incoming=1)
    H._enforce_global_active_job_limit(incoming=1)

    filename = Path(job.get("source_filename") or source.name).name
    suffix = source.suffix or Path(filename).suffix.lower() or ".mp4"
    new_task_id = H._new_task_id()
    target_path = H._copy_source_file(new_task_id, suffix, source)
    source_file_size_mb = H._path_size_mb(target_path)
    source_type = H._source_type_for_suffix(suffix)
    source_fingerprint = H._source_fingerprint_for_path(target_path, filename)
    try:
        media_preflight = preflight_media_file(target_path)
    except MediaPreflightError as exc:
        H.log_event(
            task_id=new_task_id,
            event_name="media_preflight_rejected",
            source_type=source_type,
            source_filename=filename,
            source_file_size_mb=source_file_size_mb,
            stage="import",
            success=False,
            error_reason=str(exc),
            metadata=H._metadata(
                route="/jobs/{task_id}/retry",
                retry_source_task_id=task_id,
                media_preflight={"status": "rejected", "code": exc.code, **exc.metadata},
            ),
        )
        H._remove_tree(target_path.parent)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duration_estimate_sec = media_preflight.duration_seconds or H._media_duration_seconds(target_path)
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    options = H._queue_options_from_mapping(metadata.get("queue_options") if isinstance(metadata.get("queue_options"), dict) else metadata)
    if filename and "title" not in options:
        options["title"] = Path(filename).stem

    H._enforce_daily_quota(client_id, incoming_jobs=1, incoming_upload_mb=source_file_size_mb)
    H._enforce_global_daily_quota(client_id=client_id, incoming_jobs=1, incoming_upload_mb=source_file_size_mb)
    quota_estimate = H._estimate_processing_units(
        duration_seconds=duration_estimate_sec,
        skip_summary=H._truthy_form(options.get("skip_summary")),
        estimate_only=True,
    )
    quota_reservation = H._reserve_task_quota(
        client_id=client_id,
        task_id=new_task_id,
        estimate=quota_estimate,
        reason="Retried task processing reservation",
    )

    next_metadata = H._metadata(
        route="/jobs/{task_id}/retry",
        retry_source_task_id=task_id,
        queue_options=options,
        queue_position=1,
        queue_total=1,
        source_path=str(target_path),
        source_fingerprint=source_fingerprint,
        media_preflight={"status": "passed", **media_preflight.as_metadata()},
        quota=quota_reservation,
    )
    H.log_event(
        task_id=new_task_id,
        event_name="task_retried",
        source_type=source_type,
        source_filename=filename,
        source_file_size_mb=source_file_size_mb,
        stage="queued",
        success=True,
        metadata=next_metadata,
    )
    H.upsert_job(
        task_id=new_task_id,
        status="queued",
        client_id=client_id,
        stage="queued",
        progress=0,
        source_type=source_type,
        source_filename=filename,
        source_file_size_mb=source_file_size_mb,
        metadata=next_metadata,
    )
    H._enqueue_transcription_job({
        "task_id": new_task_id,
        "source_path": str(target_path),
        "filename": filename,
        "options": options,
        "base_url": H._queue_base_url_from_request(request),
        "client_id": client_id,
    })
    queued_job = H.get_job(new_task_id, client_id=client_id) or {
        "task_id": new_task_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "source_type": source_type,
        "source_filename": filename,
        "source_file_size_mb": source_file_size_mb,
        "metadata": next_metadata,
    }
    return {"ok": True, "source_task_id": task_id, "task_id": new_task_id, "job": {**queued_job, "task_snapshot": build_task_snapshot(queued_job)}}


def _retry_job_from_oss_source(
    *,
    request: Request,
    task_id: str,
    job: dict[str, Any],
    client_id: str,
) -> dict[str, Any]:
    """Queue a new task from the same-account completed OSS source object."""

    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    session_id = str(metadata.get("oss_upload_session_id") or "").strip()
    if metadata.get("source_storage") != "oss" or not session_id:
        raise HTTPException(status_code=404, detail="Original source file is no longer available")

    session = get_oss_upload_session(session_id, owner_scope=client_id)
    if not session or session.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Original cloud source is no longer available")

    H._enforce_submission_rate_limit(request, incoming=1)
    H._enforce_active_job_limit(client_id, incoming=1)
    H._enforce_global_active_job_limit(incoming=1)

    filename = Path(str(session.get("source_filename") or job.get("source_filename") or "source.mp4")).name
    suffix = Path(filename).suffix.lower()
    if suffix not in H.ALLOWED_SUFFIXES or suffix in H.TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=422, detail="Original cloud source has an unsupported file type")
    try:
        content_length = int(session.get("content_length") or 0)
    except (TypeError, ValueError):
        content_length = 0
    if content_length <= 0:
        raise HTTPException(status_code=404, detail="Original cloud source is no longer available")

    source_file_size_mb = H._file_size_mb(content_length)
    H._enforce_daily_quota(client_id, incoming_jobs=1, incoming_upload_mb=source_file_size_mb)
    H._enforce_global_daily_quota(client_id=client_id, incoming_jobs=1, incoming_upload_mb=source_file_size_mb)

    options = H._queue_options_from_mapping(
        metadata.get("queue_options") if isinstance(metadata.get("queue_options"), dict) else metadata
    )
    if filename and "title" not in options:
        options["title"] = Path(filename).stem
    new_task_id = H._new_task_id()
    source_type = H._source_type_for_suffix(suffix)
    next_metadata = H._metadata(
        route="/jobs/{task_id}/retry",
        retry_source_task_id=task_id,
        source_storage="oss",
        oss_upload_session_id=session_id,
        queue_options=options,
        queue_position=1,
        queue_total=1,
    )
    H.log_event(
        task_id=new_task_id,
        event_name="task_retried",
        source_type=source_type,
        source_filename=filename,
        source_file_size_mb=source_file_size_mb,
        stage="source_download",
        success=True,
        metadata=next_metadata,
    )
    H.upsert_job(
        task_id=new_task_id,
        status="queued",
        client_id=client_id,
        stage="source_download",
        progress=0,
        source_type=source_type,
        source_filename=filename,
        source_file_size_mb=source_file_size_mb,
        metadata=next_metadata,
    )
    H._enqueue_oss_source_download({
        "task_id": new_task_id,
        "object_key": session["object_key"],
        "expected_size_bytes": content_length,
        "filename": filename,
        "options": options,
        "base_url": H._queue_base_url_from_request(request),
        "client_id": client_id,
        "oss_upload_session_id": session_id,
        "route": "/jobs/{task_id}/retry",
    })
    queued_job = H.get_job(new_task_id, client_id=client_id) or {
        "task_id": new_task_id,
        "status": "queued",
        "stage": "source_download",
        "progress": 0,
        "source_type": source_type,
        "source_filename": filename,
        "source_file_size_mb": source_file_size_mb,
        "metadata": next_metadata,
    }
    return {
        "ok": True,
        "source_task_id": task_id,
        "task_id": new_task_id,
        "job": {**queued_job, "task_snapshot": build_task_snapshot(queued_job)},
    }



@router.patch("/jobs/{task_id}/transcript")
def update_job_transcript(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)
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
    _sync_local_desktop_result_after_write(request, updated, background_tasks)
    return {"ok": True, "job": updated, "result": updated.get("result")}


@router.patch("/jobs/{task_id}/summary")
def update_job_summary(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)
    result = dict(job.get("result") or {})
    summary = payload.get("summary_markdown")
    if not isinstance(summary, str):
        raise HTTPException(status_code=400, detail="summary_markdown is required")
    max_chars = int(os.environ.get("FLUENTFLOW_MAX_SUMMARY_EDIT_CHARS", "500000"))
    if len(summary) > max_chars:
        raise HTTPException(status_code=413, detail=f"Summary edit is too large: {len(summary)} chars")

    edited_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    result.update({
        "task_id": result.get("task_id") or task_id,
        "summary_markdown": summary,
        "summary_skipped": False,
        "summary_status": "completed" if summary.strip() else result.get("summary_status") or "completed",
        "summary_error": None,
        "summary_edited": True,
        "summary_edited_at": edited_at,
    })
    result = H._attach_result_artifacts(task_id, result)
    updated = H.update_job_result(task_id, result, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    _sync_local_desktop_result_after_write(request, updated, background_tasks)
    return {"ok": True, "job": updated, "result": updated.get("result")}


@router.post("/jobs/{task_id}/translations/zh")
async def generate_job_zh_translations(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[dict[str, Any]] = Body(None),
) -> dict[str, Any]:
    payload = payload or {}
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)

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
    _sync_local_desktop_result_after_write(request, updated, background_tasks)

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
async def upload_job_playback_audio(
    request: Request,
    task_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    job = H.get_job(task_id, client_id=client_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _reject_cloud_write_to_desktop_sync_job(request, job)
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
    _sync_local_desktop_result_after_write(request, updated, background_tasks)
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
