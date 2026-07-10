from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import functools
import json
import uuid
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import asyncio
import shutil
import tempfile
import time

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H
from backend.core.chapter_coverage import bind_chapter_coverage_time_ranges
from backend.core.media_job import (
    _normalized_source_language,
    _is_english_source,
    _translation_ai_kwargs,
    _run_transcript_correction_stage,
    MediaJobContext,
    _stream_media_job,
    execute_media_job,
)


router = APIRouter()


@router.post("/queue/process")
async def queue_process(
    request: Request,
    files: list[UploadFile] = File(...),
    export_to_lark: Optional[str] = Form(None),
    lark_export_route: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    raw_title: Optional[str] = Form(None),
    display_title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    qwen_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    generate_visuals: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    stt_provider: Optional[str] = Form(None),
    elevenlabs_api_key: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    prompt_preset: Optional[str] = Form(None),
    prompt_preset_label: Optional[str] = Form(None),
) -> dict[str, Any]:
    """Persist multiple media files and process them sequentially in the backend."""
    client_id = H._request_client_scope(request)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    max_queue_files = H._max_queue_files()
    if len(files) > max_queue_files:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files uploaded: {len(files)}. Limit is {max_queue_files}.",
        )
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower() or ".mp4"
        if not upload.filename:
            raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")
        if suffix not in H.ALLOWED_SUFFIXES or suffix in H.TRANSCRIPT_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    H._enforce_submission_rate_limit(request, incoming=len(files))
    H._enforce_active_job_limit(client_id, incoming=len(files))
    H._enforce_global_active_job_limit(incoming=len(files))
    max_upload_mb = H._max_upload_mb()
    total_upload_mb = 0.0
    for upload in files:
        source_file_size_mb = H._upload_size_mb(upload)
        if source_file_size_mb is None:
            continue
        total_upload_mb += source_file_size_mb
        if source_file_size_mb > max_upload_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
            )
    H._enforce_daily_quota(client_id, incoming_jobs=len(files), incoming_upload_mb=total_upload_mb)
    H._enforce_global_daily_quota(client_id=client_id, incoming_jobs=len(files), incoming_upload_mb=total_upload_mb)

    base_options = H._queue_options_from_form(
        export_to_lark=export_to_lark,
        lark_export_route=lark_export_route,
        lark_via_cli=lark_via_cli,
        title=title if len(files) == 1 else None,
        folder_token=folder_token,
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        note_mode=note_mode,
        skip_summary=skip_summary,
        generate_visuals=generate_visuals,
        stt_model=stt_model,
        stt_speed=stt_speed,
        stt_language=stt_language,
        stt_provider=stt_provider,
        elevenlabs_api_key=elevenlabs_api_key,
        azure_speech_key=azure_speech_key,
        azure_speech_endpoint=azure_speech_endpoint,
        azure_blob_container_sas_url=azure_blob_container_sas_url,
        speaker_diarization=speaker_diarization,
        lark_app_id=lark_app_id,
        lark_app_secret=lark_app_secret,
        system_prompt=system_prompt,
        prompt_preset=prompt_preset,
        prompt_preset_label=prompt_preset_label,
    )
    base_url = H._queue_base_url_from_request(request)
    queued: list[dict[str, Any]] = []
    total = len(files)
    for index, upload in enumerate(files, start=1):
        filename = upload.filename or f"source-{index}"
        suffix = Path(filename).suffix.lower() or ".mp4"
        content = await upload.read()
        source_file_size_mb = H._file_size_mb(len(content))
        if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
            )
        task_id_value = H._new_task_id()
        source_type = H._source_type_for_suffix(suffix)
        source_fingerprint = H._source_fingerprint(content, filename)
        source_path = H._persist_source_file(task_id_value, suffix, content)
        metadata = H._metadata(
            route="/queue/process",
            queue_options=base_options,
            queue_position=index,
            queue_total=total,
            source_path=str(source_path),
            source_fingerprint=source_fingerprint,
        )
        duration_estimate_sec = H._media_duration_seconds(source_path)
        quota_estimate = H._estimate_processing_units(
            duration_seconds=duration_estimate_sec,
            skip_summary=H._truthy_form(base_options.get("skip_summary")),
            estimate_only=True,
        )
        quota_reservation = H._reserve_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            estimate=quota_estimate,
        )
        if quota_reservation:
            metadata["quota"] = quota_reservation
        H.log_event(
            task_id=task_id_value,
            event_name="source_queued",
            source_type=source_type,
            source_filename=filename,
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
            source_filename=filename,
            source_file_size_mb=source_file_size_mb,
            metadata=metadata,
        )
        H._enqueue_transcription_job({
            "task_id": task_id_value,
            "source_path": str(source_path),
            "filename": filename,
            "options": base_options,
            "base_url": base_url,
            "client_id": client_id,
        })
        queued.append({
            "task_id": task_id_value,
            "filename": filename,
            "source_type": source_type,
            "source_file_size_mb": source_file_size_mb,
            "status": "queued",
            "queue_position": index,
            "queue_total": total,
        })
    return {"ok": True, "queued": queued, "count": len(queued)}



@router.post("/process")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    export_to_lark: Optional[str] = Form(None),
    lark_export_route: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    raw_title: Optional[str] = Form(None),
    display_title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    qwen_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    generate_visuals: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    stt_provider: Optional[str] = Form(None),
    elevenlabs_api_key: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    prompt_preset: Optional[str] = Form(None),
    prompt_preset_label: Optional[str] = Form(None),
    duration_limit_seconds: Optional[float] = Form(None),
    task_id: Optional[str] = Form(None),
    source_last_modified_ms: Optional[str] = Form(None),
) -> StreamingResponse:
    """Upload a file and stream processing progress via SSE."""

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    do_lark = H._truthy_form(export_to_lark)
    summary_disabled = H._truthy_form(skip_summary)
    visuals_enabled = H._truthy_form(generate_visuals)
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in H.ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or H._new_task_id()
    client_id = H._request_client_scope(request)
    H._enforce_submission_rate_limit(request, incoming=1)
    H._enforce_active_job_limit(client_id, incoming=1, exclude_task_id=task_id_value)
    H._enforce_global_active_job_limit(incoming=1, exclude_task_id=task_id_value)
    source_filename = file.filename
    raw_title_value = (raw_title or title or Path(source_filename).stem).strip()
    display_title_value = (display_title or H.display_title_for_user(raw_title_value, source_filename)).strip()
    source_type = H._source_type_for_suffix(suffix)
    td = tempfile.mkdtemp()
    content = await file.read()
    source_file_size_mb = H._file_size_mb(len(content))
    max_upload_mb = H._max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
    H._enforce_daily_quota(
        client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    H._enforce_global_daily_quota(
        client_id=client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    source_fingerprint = H._source_fingerprint(content, source_filename)
    in_path = H._persist_source_file(task_id_value, suffix, content)
    duration_preflight_sec = H._media_duration_seconds(in_path)
    quota_estimate = H._estimate_processing_units(
        duration_seconds=duration_preflight_sec,
        skip_summary=summary_disabled,
        estimate_only=True,
    )
    try:
        quota_reservation = None if H._request_is_internal_queue(request) else H._reserve_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            estimate=quota_estimate,
        )
    except HTTPException:
        try:
            in_path.unlink(missing_ok=True)
        except Exception:
            pass
        shutil.rmtree(td, ignore_errors=True)
        raise

    H.log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=H._metadata(
            route="/process",
            raw_title=raw_title_value,
            display_title=display_title_value,
            source_fingerprint=source_fingerprint,
            source_last_modified_ms=source_last_modified_ms,
            quota=quota_reservation,
            quota_estimate=quota_estimate,
        ),
    )
    H.upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="import",
        progress=0,
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        metadata=H._job_metadata_for_update(
            task_id_value,
            client_id,
            route="/process",
            raw_title=raw_title_value,
            display_title=display_title_value,
            source_fingerprint=source_fingerprint,
            source_last_modified_ms=source_last_modified_ms,
            quota=quota_reservation,
            quota_estimate=quota_estimate,
        ),
    )

    loop = asyncio.get_event_loop()
    model_size = (stt_model or "").strip() or "medium"
    if model_size in {"tiny", "base", "small"}:
        model_size = "medium"
    speed_profile = (stt_speed or "").strip() or "balanced"
    language = "auto"
    stt_provider_value = H._normalize_stt_provider(stt_provider, request)
    elevenlabs_cloud_provider = stt_provider_value == "elevenlabs_scribe"
    azure_cloud_provider = stt_provider_value == "azure_batch"
    cloud_stt_provider = elevenlabs_cloud_provider or azure_cloud_provider
    diarization_requested = H._truthy_form(speaker_diarization)
    elevenlabs_key_value: str | None = None
    azure_endpoint_value: str | None = None
    azure_key_value: str | None = None
    azure_blob_container_sas_value: str | None = None
    if elevenlabs_cloud_provider:
        elevenlabs_key_value = H.resolve_secret(elevenlabs_api_key, "elevenlabs_api_key")
    if azure_cloud_provider:
        azure_endpoint_value = H.resolve_secret(azure_speech_endpoint, "azure_speech_endpoint")
        azure_key_value = H.resolve_secret(azure_speech_key, "azure_speech_key")
    if stt_provider_value == "azure_batch":
        azure_blob_container_sas_value = H.resolve_secret(
            azure_blob_container_sas_url,
            "azure_blob_container_sas_url",
        )

    account_user = H._request_account_user(request)
    ctx = MediaJobContext(
        task_id_value=task_id_value,
        client_id=client_id,
        source_type=source_type,
        source_filename=source_filename,
        raw_title_value=raw_title_value,
        display_title_value=display_title_value,
        suffix=suffix,
        td=td,
        in_path=in_path,
        content=content,
        source_fingerprint=source_fingerprint,
        source_file_size_mb=source_file_size_mb,
        max_upload_mb=max_upload_mb,
        duration_preflight_sec=duration_preflight_sec,
        quota_estimate=quota_estimate,
        quota_reservation=quota_reservation,
        task_started_at=task_started_at,
        loop=loop,
        model_size=model_size,
        speed_profile=speed_profile,
        language=language,
        stt_provider_value=stt_provider_value,
        elevenlabs_cloud_provider=elevenlabs_cloud_provider,
        azure_cloud_provider=azure_cloud_provider,
        cloud_stt_provider=cloud_stt_provider,
        diarization_requested=diarization_requested,
        elevenlabs_key_value=elevenlabs_key_value,
        azure_endpoint_value=azure_endpoint_value,
        azure_key_value=azure_key_value,
        azure_blob_container_sas_value=azure_blob_container_sas_value,
        do_lark=do_lark,
        summary_disabled=summary_disabled,
        generate_visuals=visuals_enabled,
        source_last_modified_ms=source_last_modified_ms,
        export_to_lark=export_to_lark,
        lark_export_route=lark_export_route,
        lark_via_cli=lark_via_cli,
        folder_token=folder_token,
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        qwen_api_key=qwen_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        note_mode=note_mode,
        skip_summary=skip_summary,
        system_prompt=system_prompt,
        prompt_preset=prompt_preset,
        prompt_preset_label=prompt_preset_label,
        account_user=account_user,
        title=title,
        lark_app_id=lark_app_id,
        lark_app_secret=lark_app_secret,
        duration_limit_seconds=duration_limit_seconds,
    )

    await H.JOB_EVENTS.start(task_id_value, functools.partial(execute_media_job, ctx))

    return StreamingResponse(
        H.JOB_EVENTS.subscribe(task_id_value),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.post("/export-lark")
async def export_lark(
    request: Request,
    markdown: str = Form(...),
    title: Optional[str] = Form(None),
    lark_export_route: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    source_duration_seconds: Optional[float] = Form(None),
):
    """Standalone endpoint: export existing markdown to a Lark document."""
    loop = asyncio.get_event_loop()
    task_id_value = (task_id or "").strip() or H._new_task_id()
    client_id = H._request_client_scope(request)
    existing_job = H.get_job(task_id_value, client_id=client_id) if task_id else None
    if task_id and not existing_job:
        H.logger.info("Manual Lark export continues without stored job: task_id=%s", task_id_value)
    kwargs: dict[str, Any] = {}
    if (v := H.resolve_secret(lark_app_id, "lark_app_id")):
        kwargs["app_id"] = v
    if (v := H.resolve_secret(lark_app_secret, "lark_app_secret")):
        kwargs["app_secret"] = v
    if folder_token:
        kwargs["folder_token"] = folder_token
    resolved = H.resolve_lark_doc_title(
        markdown,
        filename_stem="",
        form_title=title,
    )
    export_target = H._lark_export_target(lark_export_route, lark_via_cli)
    H.log_event(
        task_id=task_id_value,
        event_name="lark_export_started",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        summary_length=H._text_len(markdown),
        stage="export",
        export_target=export_target,
        metadata=H._metadata(route="/export-lark", trigger="manual", doc_title=resolved),
    )
    started_at = time.perf_counter()
    try:
        if export_target == "lark_cli":
            resp = await loop.run_in_executor(
                None, lambda: H.export_markdown_via_lark_cli(resolved, markdown)
            )
        elif export_target == "feishu_user_oauth":
            user = H._require_account_user(request)
            user_access_token = H.get_valid_feishu_user_access_token(str(user["id"]))
            resp = await loop.run_in_executor(
                None,
                lambda: H.export_markdown_to_lark(
                    resolved,
                    markdown,
                    task_id=task_id_value,
                    artifact_root=H._artifact_storage_dir(),
                    user_access_token=user_access_token,
                    **kwargs,
                )
            )
        else:
            resp = await loop.run_in_executor(
                None,
                lambda: H.export_markdown_to_lark(
                    resolved,
                    markdown,
                    task_id=task_id_value,
                    artifact_root=H._artifact_storage_dir(),
                    **kwargs,
                )
            )
        if isinstance(resp, dict):
            resp["doc_title"] = resolved
            resp["task_id"] = task_id_value
        feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
        H.log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=H._text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            export_target=export_target,
            feishu_doc_url=feishu_doc_url,
            metadata=H._metadata(route="/export-lark", trigger="manual", doc_title=resolved),
        )
        return resp
    except HTTPException:
        raise
    except H.FeishuConnectionRequired as exc:
        friendly_error = str(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=H._text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            export_target=export_target,
            metadata=H._metadata(route="/export-lark", trigger="manual", doc_title=resolved, feishu_connection_required=True),
        )
        raise HTTPException(status_code=409, detail=friendly_error) from exc
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=H._text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            export_target=export_target,
            metadata=H._metadata(route="/export-lark", trigger="manual", doc_title=resolved, raw_error=str(exc)),
        )
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=H._text_len(markdown),
            stage="export",
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/export-lark", trigger="manual", raw_error=str(exc)),
        )
        raise HTTPException(status_code=500, detail=friendly_error)



@router.post("/regenerate-summary")
async def regenerate_summary(
    request: Request,
    transcript: str = Form(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    qwen_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    prompt_preset: Optional[str] = Form(None),
    prompt_preset_label: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    source_duration_seconds: Optional[float] = Form(None),
):
    """Re-run AI summarization on an existing transcript."""
    loop = asyncio.get_event_loop()
    requested_task_id = (task_id or "").strip()
    task_id_value = requested_task_id or H._new_task_id()
    client_id = H._request_client_scope(request)
    existing_job = H.get_job(task_id_value, client_id=client_id) if requested_task_id else None
    regenerated_from_task_id = None
    if requested_task_id and not existing_job:
        regenerated_from_task_id = requested_task_id
        task_id_value = H._new_task_id()
    kwargs = H._ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        qwen_api_key=qwen_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
        note_mode=note_mode,
    )
    kwargs, note_mode_plan = H._plan_note_mode_for_summary(
        kwargs,
        transcript,
        task_id=task_id_value,
        route="/regenerate-summary",
        filename=source_filename,
        duration_seconds=source_duration_seconds,
        current_prompt_preset=prompt_preset,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: H.summarize_transcript_with_metadata(transcript, **kwargs)
        )
        md = summary_result.markdown
        H.log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=H._text_len(transcript),
            summary_length=H._text_len(md),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=H._metadata(
                route="/regenerate-summary",
                regenerated_from_task_id=regenerated_from_task_id,
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
                requested_note_mode=note_mode_plan.get("requested_note_mode") or summary_result.requested_mode,
                **H._summary_result_metadata(summary_result),
                **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
            ),
        )
        payload = {
            "summary_markdown": md,
            "task_id": task_id_value,
            "requested_note_mode": note_mode_plan.get("requested_note_mode") or summary_result.requested_mode,
            "resolved_note_mode": summary_result.resolved_mode,
            "note_mode_chunk_count": summary_result.chunk_count,
            "note_mode_segment_count": getattr(summary_result, "segment_count", None),
            "note_mode_evidence_count": getattr(summary_result, "evidence_count", None),
            "note_mode_chapter_count": getattr(summary_result, "chapter_count", None),
            "note_mode_important_evidence_count": getattr(summary_result, "important_evidence_count", None),
            "note_mode_covered_important_evidence_count": getattr(summary_result, "covered_important_evidence_count", None),
            "note_mode_coverage_missing_count": getattr(summary_result, "coverage_missing_count", None),
            "chapter_coverage": getattr(summary_result, "chapter_coverage", None),
            **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
            "prompt_preset": (prompt_preset or "").strip() or None,
            "prompt_preset_label": (prompt_preset_label or "").strip() or None,
            "regenerated_from_task_id": regenerated_from_task_id,
        }
        existing = existing_job if existing_job and task_id_value == requested_task_id else H.get_job(task_id_value, client_id=client_id)
        result = dict(existing.get("result") or {}) if existing else {
            "task_id": task_id_value,
            "filename": source_filename,
            "transcript_text": transcript,
            "audio_duration_seconds": source_duration_seconds or 0,
            "source": source_type,
        }
        result.update({
            **payload,
            "summary_skipped": False,
            "status": "completed",
        })
        result = bind_chapter_coverage_time_ranges(result)
        if isinstance(result.get("chapter_coverage"), dict):
            payload["chapter_coverage"] = result["chapter_coverage"]
        H.upsert_job(
            task_id=task_id_value,
            status="completed",
            client_id=client_id,
            stage="done",
            progress=100,
            source_type=source_type,
            source_filename=source_filename,
            summary_status="completed",
            result=result,
        )
        return payload
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=H._text_len(transcript),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/regenerate-summary", raw_error=str(exc)),
        )
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=H._text_len(transcript),
            stage="summary_regenerate",
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/regenerate-summary", raw_error=str(exc)),
        )
        H.upsert_job(
            task_id=task_id_value,
            status="failed",
            client_id=client_id,
            stage="summary_regenerate",
            source_type=source_type,
            source_filename=source_filename,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)



@router.post("/summarize-transcript-file")
async def summarize_transcript_file(
    request: Request,
    file: UploadFile = File(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    qwen_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    prompt_preset: Optional[str] = Form(None),
    prompt_preset_label: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
):
    """Parse an existing .srt/.vtt/.txt/.md transcript, optionally summarizing it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in H.TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported transcript file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or H._new_task_id()
    client_id = H._request_client_scope(request)
    summary_disabled = H._truthy_form(skip_summary)
    H._enforce_submission_rate_limit(request, incoming=1)
    source_filename = file.filename
    raw = await file.read()
    source_file_size_mb = H._file_size_mb(len(raw))
    max_upload_mb = H._max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
    H._enforce_daily_quota(
        client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    H._enforce_global_daily_quota(
        client_id=client_id,
        incoming_jobs=1,
        incoming_upload_mb=source_file_size_mb,
        exclude_task_id=task_id_value,
    )
    H.log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=H._metadata(route="/summarize-transcript-file", suffix=suffix),
    )
    H.upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="import",
        progress=10,
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
    )
    try:
        parsed = H.parse_transcript_file(raw, file.filename)
        if not parsed.text.strip():
            raise HTTPException(status_code=400, detail="Transcript file is empty")
        if parsed.duration:
            duration_error = H._duration_limit_error(parsed.duration, source_filename)
            if duration_error:
                raise HTTPException(status_code=413, detail=duration_error)
    except HTTPException as exc:
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=str(exc.detail),
            metadata=H._metadata(route="/summarize-transcript-file"),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="transcript_parse_failed",
        )
        H.upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="transcript_parse",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=str(exc.detail),
        )
        raise
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/summarize-transcript-file", raw_error=str(exc)),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="transcript_parse_failed",
        )
        H.upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="transcript_parse",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)

    loop = asyncio.get_event_loop()
    review_segments_input = parsed.segments or tuple(
        {"start": 0.0, "end": 0.0, "text": line}
        for line in parsed.text.splitlines()
        if line.strip()
    )
    cleanup_started_at = time.perf_counter()
    cleanup_result = H.clean_repeated_transcript(review_segments_input)
    if cleanup_result.applied_count > 0:
        H.log_event(
            task_id=task_id_value,
            event_name="transcript_cleanup_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=cleanup_result.cleaned_length,
            stage="transcript_cleanup",
            duration_seconds=round(time.perf_counter() - cleanup_started_at, 3),
            success=True,
            metadata=H._metadata(
                route="/summarize-transcript-file",
                cleanup_issue_count=len(cleanup_result.issues),
                cleanup_applied_count=cleanup_result.applied_count,
                cleanup_removed_segment_count=cleanup_result.removed_segment_count,
                cleanup_raw_length=cleanup_result.raw_length,
                cleanup_cleaned_length=cleanup_result.cleaned_length,
            ),
        )
    transcript_text = cleanup_result.cleaned_text
    segments_payload = list(cleanup_result.cleaned_segments) if parsed.segments else []
    raw_segments_payload = list(parsed.segments)
    quota_estimate = H._estimate_processing_units(
        transcript_text=None if summary_disabled else transcript_text,
        skip_summary=summary_disabled,
        estimate_only=True,
    )
    try:
        quota_reservation = H._reserve_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            estimate=quota_estimate,
            reason="Transcript file AI summary reservation",
        )
    except HTTPException as exc:
        error_detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            stage="quota",
            success=False,
            error_reason=error_detail,
            metadata=H._metadata(route="/summarize-transcript-file", quota_estimate=quota_estimate),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="quota",
        )
        H.upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="quota",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=error_detail,
        )
        raise

    H.log_event(
        task_id=task_id_value,
        event_name="transcript_ready",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=H._text_len(transcript_text),
        stage="transcript_ready",
        success=True,
        metadata=H._metadata(route="/summarize-transcript-file", segment_count=len(parsed.segments)),
    )
    base_result: dict[str, Any] = {
        "task_id": task_id_value,
        "filename": file.filename,
        "transcript_text": transcript_text,
        "raw_transcript_text": parsed.text,
        "cleaned_transcript_text": cleanup_result.cleaned_text,
        "transcript_text_preview": transcript_text[:200],
        "summary_markdown": "",
        "audio_duration_seconds": round(parsed.duration, 1),
        "display_segments": segments_payload,
        "raw_segments": segments_payload,
        "stt_raw_segments": raw_segments_payload,
        "transcript_cleanup": H._cleanup_payload(cleanup_result),
        "status": "transcript_ready",
        "source": "transcript_file",
        "summary_skipped": summary_disabled,
    }
    if quota_reservation:
        base_result["quota"] = quota_reservation
    note_transcript_text = transcript_text
    if not summary_disabled and H.transcript_correction_enabled():
        H.upsert_job(task_id=task_id_value, status="running", stage="transcript_correction", progress=61)
        correction_fields, note_transcript_text, _note_segments_payload = await _run_transcript_correction_stage(
            loop=loop,
            task_id=task_id_value,
            route="/summarize-transcript-file",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_text=transcript_text,
            segments=segments_payload,
            deepseek_api_key=deepseek_api_key,
        )
        base_result.update(correction_fields)
    elif not summary_disabled:
        base_result["note_generation_transcript_source"] = "transcript_text"
    base_result = H._attach_result_artifacts(task_id_value, base_result)
    H.upsert_job(
        task_id=task_id_value,
        status="running",
        stage="transcript_ready",
        progress=60,
        result=base_result,
        summary_status="pending",
        metadata=H._job_metadata_for_update(
            task_id_value,
            client_id,
            route="/summarize-transcript-file",
            quota=quota_reservation,
            quota_estimate=quota_estimate,
        ),
    )

    if summary_disabled:
        H.log_event(
            task_id=task_id_value,
            event_name="summary_skipped",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            stage="summary",
            success=True,
            metadata=H._metadata(route="/summarize-transcript-file", reason="transcript_only_mode"),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            summary_length=0,
            summary_status="skipped",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_skipped",
        )
        result = H.result_for_transcript_only(base_result)
        quota_final = H._finalize_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            final_usage=H._estimate_processing_units(skip_summary=True),
            reason="Finalize transcript-only import charge",
        ) if quota_reservation else None
        if quota_final:
            result["quota"] = quota_final
        result = H._attach_result_artifacts(task_id_value, result)
        H.upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            result=result,
            summary_status="skipped",
        )
        return result

    kwargs = H._ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        qwen_api_key=qwen_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
        note_mode=note_mode,
    )
    kwargs, note_mode_plan = H._plan_note_mode_for_summary(
        kwargs,
        note_transcript_text,
        task_id=task_id_value,
        route="/summarize-transcript-file",
        filename=source_filename,
        duration_seconds=parsed.duration,
        current_prompt_preset=prompt_preset,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: H.summarize_transcript_with_metadata(note_transcript_text, **kwargs)
        )
        summary_md = summary_result.markdown
        if not summary_md.strip():
            raise ValueError("AI summarization returned empty result")
        H.log_event(
            task_id=task_id_value,
            event_name="summary_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(note_transcript_text),
            summary_length=H._text_len(summary_md),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=H._metadata(
                route="/summarize-transcript-file",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
                requested_note_mode=note_mode_plan.get("requested_note_mode") or summary_result.requested_mode,
                note_generation_transcript_source=base_result.get("note_generation_transcript_source"),
                **H._summary_result_metadata(summary_result),
                **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
            ),
        )
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id_value,
            event_name="summary_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(note_transcript_text),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(
                route="/summarize-transcript-file",
                raw_error=str(exc),
                note_generation_transcript_source=base_result.get("note_generation_transcript_source"),
            ),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(note_transcript_text),
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_failed",
        )
        failed_result = H.result_for_summary_failure(base_result, friendly_error)
        failed_result.update({key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")})
        quota_final = H._finalize_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            final_usage=H._estimate_processing_units(skip_summary=True),
            reason="Release transcript import AI reservation after summary failure",
        ) if quota_reservation else None
        if quota_final:
            failed_result["quota"] = quota_final
        failed_result = H._attach_result_artifacts(task_id_value, failed_result)
        H.upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            result=failed_result,
            summary_status="failed",
            error_reason=friendly_error,
        )
        return failed_result

    result = H.result_for_summary_success(
        base_result,
        summary_md,
        requested_note_mode=note_mode_plan.get("requested_note_mode") or summary_result.requested_mode,
        resolved_note_mode=summary_result.resolved_mode,
        note_mode_chunk_count=summary_result.chunk_count,
        note_mode_segment_count=getattr(summary_result, "segment_count", None),
        note_mode_evidence_count=getattr(summary_result, "evidence_count", None),
        note_mode_chapter_count=getattr(summary_result, "chapter_count", None),
        note_mode_important_evidence_count=getattr(summary_result, "important_evidence_count", None),
        note_mode_covered_important_evidence_count=getattr(summary_result, "covered_important_evidence_count", None),
        note_mode_coverage_missing_count=getattr(summary_result, "coverage_missing_count", None),
        chapter_coverage=getattr(summary_result, "chapter_coverage", None),
        note_mode_plan_reason=note_mode_plan.get("note_mode_plan_reason"),
        note_mode_plan_confidence=note_mode_plan.get("note_mode_plan_confidence"),
        note_mode_plan_warnings=note_mode_plan.get("note_mode_plan_warnings"),
        note_mode_plan_provider=note_mode_plan.get("note_mode_plan_provider"),
        note_mode_plan_model=note_mode_plan.get("note_mode_plan_model"),
        note_mode_plan_fallback=note_mode_plan.get("note_mode_plan_fallback"),
        note_mode_plan_error=note_mode_plan.get("note_mode_plan_error"),
        note_mode_plan_selected_mode=note_mode_plan.get("note_mode_plan_selected_mode"),
        prompt_preset=(prompt_preset or "").strip() or None,
        prompt_preset_label=(prompt_preset_label or "").strip() or None,
    )
    quota_final = H._finalize_task_quota(
        client_id=client_id,
        task_id=task_id_value,
        final_usage=H._estimate_processing_units(
            transcript_text=note_transcript_text,
            summary_text=summary_md,
            skip_summary=False,
        ),
    ) if quota_reservation else None
    if quota_final:
        result["quota"] = quota_final
    result = H._attach_result_artifacts(task_id_value, result)
    H._log_task_completed(
        task_id=task_id_value,
        started_at=task_started_at,
        final_status="completed",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=H._text_len(transcript_text),
        summary_length=H._text_len(summary_md),
        summary_status="completed",
        lark_requested=False,
        lark_success=None,
    )
    H.upsert_job(
        task_id=task_id_value,
        status="completed",
        stage="done",
        progress=100,
        result=result,
        summary_status="completed",
    )
    return result
