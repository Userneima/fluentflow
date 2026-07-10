"""Media job pipeline extracted from routers/processing.py.

Holds MediaJobContext, the _stream_media_job pipeline generator, execute_media_job,
and the transcript-correction / source-language helpers. Re-imported by processing.py
(facade) so route handlers and the server_helpers queue worker keep working unchanged.
"""

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

from fastapi import Request

import backend.core.server_helpers as H
from backend.core.chapter_coverage import bind_chapter_coverage_time_ranges


def _normalized_source_language(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if not text:
        return None
    if text.startswith("en") or text in {"english"}:
        return "en"
    if text.startswith("zh") or text in {"chinese", "mandarin"}:
        return "zh"
    return text.split("-", 1)[0]


def _is_english_source(value: str | None) -> bool:
    return _normalized_source_language(value) == "en"


def _translation_ai_kwargs(ai_kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in ai_kwargs.items()
        if key in {"api_key", "model", "provider"}
    }


async def _run_transcript_correction_stage(
    *,
    loop: asyncio.AbstractEventLoop,
    task_id: str,
    route: str,
    source_type: str,
    source_filename: str | None,
    source_duration_seconds: float | None,
    source_file_size_mb: float | None,
    transcript_text: str,
    segments: list[dict[str, Any]],
    deepseek_api_key: str | None,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Run optional conservative transcript correction without failing the task."""
    if not H.transcript_correction_enabled():
        return {"note_generation_transcript_source": "transcript_text"}, transcript_text, segments

    started_at = time.perf_counter()
    correction_result = await loop.run_in_executor(
        None,
        lambda: H.correct_transcript_segments(
            segments,
            api_key=H.resolve_secret(deepseek_api_key, "deepseek_api_key"),
            provider="deepseek",
        ),
    )
    note_transcript_text = correction_result.corrected_text or transcript_text
    note_segments = correction_result.corrected_segments or segments
    fields = H.correction_result_fields(
        correction_result,
        note_input_applied=bool(correction_result.corrected_text),
    )
    fields["note_generation_transcript_source"] = (
        "corrected_transcript" if correction_result.corrected_text else "transcript_text"
    )
    H.log_event(
        task_id=task_id,
        event_name="transcript_correction_completed" if correction_result.status in {"completed", "no_changes"} else "transcript_correction_unavailable",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        source_file_size_mb=source_file_size_mb,
        transcript_length=H._text_len(transcript_text),
        stage="transcript_correction",
        duration_seconds=round(time.perf_counter() - started_at, 3),
        success=correction_result.status in {"completed", "no_changes"},
        error_reason=correction_result.error,
        metadata=H._metadata(
            route=route,
            correction_status=correction_result.status,
            correction_applied_count=correction_result.applied_count,
            correction_rejected_count=correction_result.rejected_count,
            correction_provider=correction_result.provider,
            correction_model=correction_result.model,
            note_generation_transcript_source=fields["note_generation_transcript_source"],
        ),
    )
    return fields, note_transcript_text, note_segments


@dataclass
class MediaJobContext:
    """All state the media processing pipeline needs, decoupled from FastAPI Request."""

    task_id_value: str
    client_id: Any
    source_type: str
    source_filename: str
    raw_title_value: str
    display_title_value: str
    suffix: str
    td: str
    in_path: Any
    content: bytes
    source_fingerprint: Any
    source_file_size_mb: float | None
    max_upload_mb: Any
    duration_preflight_sec: float | None
    quota_estimate: Any
    quota_reservation: Any
    task_started_at: float
    loop: Any
    model_size: str
    speed_profile: str
    language: str
    stt_provider_value: str
    elevenlabs_cloud_provider: bool
    azure_cloud_provider: bool
    cloud_stt_provider: bool
    diarization_requested: bool
    elevenlabs_key_value: str | None
    azure_endpoint_value: str | None
    azure_key_value: str | None
    azure_blob_container_sas_value: str | None
    do_lark: bool
    summary_disabled: bool
    generate_visuals: bool
    source_last_modified_ms: Any
    export_to_lark: Any
    lark_export_route: Any
    lark_via_cli: Any
    folder_token: Any
    deepseek_api_key: Any
    openai_api_key: Any
    qwen_api_key: Any
    ai_provider: Any
    ai_model: Any
    note_mode: Any
    skip_summary: Any
    system_prompt: Any
    prompt_preset: Any
    prompt_preset_label: Any
    account_user: dict[str, Any] | None
    title: Any
    lark_app_id: Any
    lark_app_secret: Any
    duration_limit_seconds: float | None


async def _stream_media_job(ctx: MediaJobContext) -> AsyncGenerator[str, None]:
    """Run the full media pipeline for one job, yielding SSE chunks. No FastAPI Request."""
    task_id_value = ctx.task_id_value
    client_id = ctx.client_id
    source_type = ctx.source_type
    source_filename = ctx.source_filename
    raw_title_value = ctx.raw_title_value
    display_title_value = ctx.display_title_value
    suffix = ctx.suffix
    td = ctx.td
    in_path = ctx.in_path
    content = ctx.content
    source_fingerprint = ctx.source_fingerprint
    source_file_size_mb = ctx.source_file_size_mb
    max_upload_mb = ctx.max_upload_mb
    duration_preflight_sec = ctx.duration_preflight_sec
    quota_estimate = ctx.quota_estimate
    quota_reservation = ctx.quota_reservation
    task_started_at = ctx.task_started_at
    loop = ctx.loop
    model_size = ctx.model_size
    speed_profile = ctx.speed_profile
    language = ctx.language
    stt_provider_value = ctx.stt_provider_value
    elevenlabs_cloud_provider = ctx.elevenlabs_cloud_provider
    azure_cloud_provider = ctx.azure_cloud_provider
    cloud_stt_provider = ctx.cloud_stt_provider
    diarization_requested = ctx.diarization_requested
    elevenlabs_key_value = ctx.elevenlabs_key_value
    azure_endpoint_value = ctx.azure_endpoint_value
    azure_key_value = ctx.azure_key_value
    azure_blob_container_sas_value = ctx.azure_blob_container_sas_value
    do_lark = ctx.do_lark
    summary_disabled = ctx.summary_disabled
    generate_visuals = ctx.generate_visuals
    source_last_modified_ms = ctx.source_last_modified_ms
    export_to_lark = ctx.export_to_lark
    lark_export_route = ctx.lark_export_route
    lark_via_cli = ctx.lark_via_cli
    folder_token = ctx.folder_token
    deepseek_api_key = ctx.deepseek_api_key
    openai_api_key = ctx.openai_api_key
    qwen_api_key = ctx.qwen_api_key
    ai_provider = ctx.ai_provider
    ai_model = ctx.ai_model
    note_mode = ctx.note_mode
    skip_summary = ctx.skip_summary
    system_prompt = ctx.system_prompt
    prompt_preset = ctx.prompt_preset
    prompt_preset_label = ctx.prompt_preset_label
    account_user = ctx.account_user
    title = ctx.title
    lark_app_id = ctx.lark_app_id
    lark_app_secret = ctx.lark_app_secret
    duration_limit_seconds = ctx.duration_limit_seconds

    current_stage = "import"
    duration_sec: float | None = None
    duration_estimate_sec: float | None = None
    transcript_text = ""
    summary_md = ""
    summary_status: str | None = None
    lark_success: bool | None = None
    stt_process = None
    stt_queue = None
    playback_audio_path: Path | None = None
    try:
        if elevenlabs_cloud_provider and not elevenlabs_key_value:
            raise RuntimeError(
                "ElevenLabs transcription backend configuration is incomplete. "
                "Please contact the product maintainer."
            )
        if azure_cloud_provider and (not azure_endpoint_value or not azure_key_value):
            raise RuntimeError(
                "Cloud transcription backend configuration is incomplete. "
                "Please contact the product maintainer."
            )
        if stt_provider_value == "azure_batch" and not azure_blob_container_sas_value:
            raise RuntimeError(
                "Cloud transcription storage is not configured. "
                "Please contact the product maintainer."
            )

        # ── Stage 1: Audio extraction ──────────────────────
        current_stage = "audio"
        H.upsert_job(task_id=task_id_value, status="running", stage="audio", progress=5)
        yield H._sse({"stage": "audio", "progress": 5})
        audio_started_at = time.perf_counter()
        if cloud_stt_provider:
            audio_output_format = "mp3"
            out_audio = await loop.run_in_executor(
                None, lambda: H.extract_compressed_mp3(in_path, output_path=Path(td) / "cloud_stt.mp3")
            )
            playback_audio_path = out_audio
        else:
            audio_output_format = "wav"
            out_audio = await loop.run_in_executor(
                None, lambda: H.extract_stt_wav(in_path, output_path=Path(td) / "stt.wav")
            )
            playback_audio_path = await loop.run_in_executor(
                None, lambda: H.extract_compressed_mp3(in_path, output_path=Path(td) / "playback.mp3")
            )
        audio_elapsed_sec = time.perf_counter() - audio_started_at
        H.log_event(
            task_id=task_id_value,
            event_name="audio_extracted",
            source_type=source_type,
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="audio",
            duration_seconds=round(audio_elapsed_sec, 3),
            success=True,
            metadata=H._metadata(
                route="/process",
                stt_provider=stt_provider_value,
                stt_provider_label=H._stt_provider_label(stt_provider_value),
                audio_output_format=audio_output_format,
                audio_output_size_mb=H._path_size_mb(out_audio),
            ),
        )
        H.upsert_job(task_id=task_id_value, status="running", stage="audio", progress=20)
        yield H._sse({"stage": "audio", "progress": 20})

        # ── Stage 1.5: Visual evidence placeholders ──
        # Actual frame extraction happens after the text note exists, so the
        # text model can request only the time windows where screenshots help.
        frame_paths: list[str] = []
        frame_metadata: list[dict[str, Any]] = []
        visual_requests: list[dict[str, Any]] = []
        visual_selections: list[dict[str, Any]] = []
        visual_evidence_error: str | None = None

        # ── Stage 2: STT transcription ─────────────────────
        current_stage = "stt"
        H.upsert_job(task_id=task_id_value, status="running", stage="stt", progress=22)
        yield H._sse({"stage": "stt", "progress": 22, "stt_progress": 0, "stt_status": "starting"})

        duration_estimate_sec = H._media_duration_seconds(out_audio)
        if duration_estimate_sec:
            duration_error = H._duration_limit_error(duration_estimate_sec, source_filename, duration_limit_seconds)
            if duration_error:
                raise RuntimeError(duration_error)
        status_progress_floor = {
            "starting": 22.0,
            "loading_model": 23.0,
            "chunking_audio": 24.0,
            "preparing_audio": 24.0,
            "waiting_first_segment": 25.0,
            "transcribing_chunks": 25.0,
            "transcribing_segments": 25.0,
        }
        progress_state: dict[str, Any] = {
            "latest": 22.0,
            "stt_progress": 0.0,
            "transcribed_seconds": 0.0,
            "duration_seconds": duration_estimate_sec,
            "stt_status": "starting",
        }

        cloud_stt_metadata: dict[str, Any] = {}
        stt_started_at = time.perf_counter()
        stt_timeout = H._stale_job_seconds()
        if stt_provider_value == "elevenlabs_scribe":
            cloud_stt_metadata = {
                "elevenlabs_audio_size_mb": H._path_size_mb(out_audio),
                "elevenlabs_duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            }

            def on_elevenlabs_progress(status: str, metadata: dict[str, Any] | None = None) -> None:
                progress_state["stt_status"] = status
                if metadata:
                    cloud_stt_metadata.update(metadata)

            progress_state["stt_status"] = "elevenlabs_uploading"
            elevenlabs_task = loop.run_in_executor(
                None,
                lambda: H.transcribe_audio_scribe(
                    out_audio,
                    api_key=elevenlabs_key_value,
                    language=language,
                    diarization_enabled=diarization_requested,
                    timeout=stt_timeout,
                    progress_callback=on_elevenlabs_progress,
                ),
            )
            last_emit_at = time.perf_counter()
            while not elevenlabs_task.done():
                await asyncio.sleep(1)
                now = time.perf_counter()
                if now - stt_started_at > stt_timeout:
                    elevenlabs_task.cancel()
                    try:
                        await elevenlabs_task
                    except Exception:
                        pass
                    raise RuntimeError("STT processing timed out")
                if now - last_emit_at < 2:
                    continue
                last_emit_at = now
                H.upsert_job(
                    task_id=task_id_value,
                    status="running",
                    stage="stt",
                    progress=25,
                    metadata={
                        "stt_provider": stt_provider_value,
                        "stt_provider_label": H._stt_provider_label(stt_provider_value),
                        **cloud_stt_metadata,
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                    },
                )
                yield H._sse({
                    "stage": "stt",
                    "progress": 25,
                    **cloud_stt_metadata,
                    "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                    "stt_elapsed_seconds": round(now - stt_started_at, 1),
                    "stt_status": progress_state.get("stt_status"),
                    "stt_provider": stt_provider_value,
                })
            tr = elevenlabs_task.result()
        elif stt_provider_value == "azure_batch":
            cloud_stt_metadata = {
                "azure_batch_audio_size_mb": H._path_size_mb(out_audio),
                "azure_batch_duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            }

            def on_azure_batch_progress(status: str, metadata: dict[str, Any] | None = None) -> None:
                progress_state["stt_status"] = status
                if metadata:
                    cloud_stt_metadata.update(metadata)

            progress_state["stt_status"] = "azure_batch_uploading"
            azure_task = loop.run_in_executor(
                None,
                lambda: H.transcribe_audio_batch(
                    out_audio,
                    endpoint=azure_endpoint_value,
                    api_key=azure_key_value,
                    container_sas_url=azure_blob_container_sas_value,
                    locale=language,
                    diarization_enabled=diarization_requested,
                    display_name=f"FluentFlow {Path(source_filename).stem}",
                    progress_callback=on_azure_batch_progress,
                ),
            )
            last_emit_at = time.perf_counter()
            while not azure_task.done():
                await asyncio.sleep(1)
                now = time.perf_counter()
                if now - stt_started_at > stt_timeout:
                    azure_task.cancel()
                    try:
                        await azure_task
                    except Exception:
                        pass
                    raise RuntimeError("STT processing timed out")
                if now - last_emit_at < 2:
                    continue
                last_emit_at = now
                H.upsert_job(
                    task_id=task_id_value,
                    status="running",
                    stage="stt",
                    progress=25,
                    metadata={
                        "stt_provider": stt_provider_value,
                        "stt_provider_label": H._stt_provider_label(stt_provider_value),
                        **cloud_stt_metadata,
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                    },
                )
                yield H._sse({
                    "stage": "stt",
                    "progress": 25,
                    **cloud_stt_metadata,
                    "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                    "stt_elapsed_seconds": round(now - stt_started_at, 1),
                    "stt_status": progress_state.get("stt_status"),
                    "stt_provider": stt_provider_value,
                })
            tr = azure_task.result()
        else:
            stt_process, stt_queue = H.start_transcription_process(
                out_audio,
                model_size=model_size,
                speed_profile=speed_profile,
                language=language,
            )
            stt_result = None
            stt_error: str | None = None
            last_sent_progress = 22.0
            last_emit_at = time.perf_counter()
            while True:
                if time.perf_counter() - stt_started_at > stt_timeout:
                    if stt_process is not None and stt_process.is_alive():
                        stt_process.terminate()
                        stt_process.join(timeout=5)
                    raise RuntimeError("STT processing timed out")
                for message in H.drain_queue(stt_queue):
                    message_type = message.get("type")
                    if message_type == "progress":
                        safe_frac = max(0.0, min(float(message.get("value") or 0), 1.0))
                        progress_state["stt_progress"] = safe_frac
                        progress_state["latest"] = max(
                            float(progress_state.get("latest") or 22.0),
                            22 + safe_frac * 38,  # 22–60 range
                        )
                        if duration_estimate_sec:
                            progress_state["transcribed_seconds"] = safe_frac * duration_estimate_sec
                    elif message_type == "status":
                        status = message.get("status") or progress_state["stt_status"]
                        progress_state["stt_status"] = status
                        progress_state["latest"] = max(
                            float(progress_state.get("latest") or 22.0),
                            status_progress_floor.get(str(status), 22.0),
                        )
                    elif message_type == "result":
                        stt_result = message.get("result")
                    elif message_type == "error":
                        stt_error = message.get("error") or "STT worker failed"

                if stt_result is not None:
                    break
                if stt_error:
                    raise RuntimeError(stt_error)
                if stt_process is not None and not stt_process.is_alive():
                    for message in H.drain_queue(stt_queue):
                        if message.get("type") == "result":
                            stt_result = message.get("result")
                        elif message.get("type") == "error":
                            stt_error = message.get("error") or "STT worker failed"
                    if stt_result is not None:
                        break
                    if stt_error:
                        raise RuntimeError(stt_error)
                    raise RuntimeError(f"STT worker exited unexpectedly with code {stt_process.exitcode}")

                await asyncio.sleep(0.5)
                latest_progress = float(progress_state.get("latest") or 22.0)
                now = time.perf_counter()
                if latest_progress >= last_sent_progress + 1 or now - last_emit_at >= 2:
                    last_sent_progress = max(last_sent_progress, latest_progress)
                    last_emit_at = now
                    H.upsert_job(
                        task_id=task_id_value,
                        status="running",
                        stage="stt",
                        progress=round(latest_progress, 1),
                        metadata={
                            "stt_provider": stt_provider_value,
                            "stt_provider_label": H._stt_provider_label(stt_provider_value),
                            "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                            "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                            "stt_elapsed_seconds": round(now - stt_started_at, 1),
                            "stt_status": progress_state.get("stt_status"),
                        },
                    )
                    yield H._sse({
                        "stage": "stt",
                        "progress": round(latest_progress, 1),
                        "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                        "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                        "stt_provider": stt_provider_value,
                    })
            if stt_process is not None:
                stt_process.join(timeout=2)
            tr = stt_result
        stt_elapsed_sec = time.perf_counter() - stt_started_at
        H.upsert_job(
            task_id=task_id_value,
            status="running",
            stage="stt",
            progress=60,
            metadata={
                "stt_provider": stt_provider_value,
                "stt_provider_label": H._stt_provider_label(stt_provider_value),
                **cloud_stt_metadata,
                "stt_progress": 1,
                "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            },
        )
        yield H._sse({
            "stage": "stt",
            "progress": 60,
            "stt_progress": 1,
            **cloud_stt_metadata,
            "transcribed_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            "stt_provider": stt_provider_value,
        })

        duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
        stt_realtime_factor = H._stt_realtime_factor(stt_elapsed_sec, duration_sec)
        transcript_text = tr.text
        if stt_provider_value == "azure_batch":
            stt_model_for_result = "azure-batch-transcription"
        elif stt_provider_value == "elevenlabs_scribe":
            stt_model_for_result = "scribe_v2"
        else:
            stt_model_for_result = model_size
        H.log_event(
            task_id=task_id_value,
            event_name="stt_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=round(duration_sec, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            stage="stt",
            duration_seconds=round(stt_elapsed_sec, 3),
            success=True,
            metadata=H._metadata(
                **H._runtime_context_metadata(),
                route="/process",
                source_fingerprint=source_fingerprint,
                stt_provider=stt_provider_value,
                stt_provider_label=H._stt_provider_label(stt_provider_value),
                stt_model=stt_model_for_result,
                stt_speed=speed_profile,
                stt_language=language,
                **cloud_stt_metadata,
                device_requested=getattr(tr, "device_requested", None) or "auto",
                device_resolved=getattr(tr, "device_resolved", None),
                vad_filter=getattr(tr, "vad_filter", None),
                cpu_threads=getattr(tr, "cpu_threads", None),
                num_workers=getattr(tr, "num_workers", None),
                detected_language=tr.language,
                language_probability=tr.language_probability,
                segment_count=len(tr.segments),
                stt_realtime_factor=stt_realtime_factor,
                model_cache_hit=getattr(tr, "model_cache_hit", None),
                model_load_seconds=getattr(tr, "model_load_seconds", None),
                model_source=getattr(tr, "model_source", None),
                compute_type=getattr(tr, "compute_type", None),
            ),
        )
        base_result: dict[str, Any] = {
            "task_id": task_id_value,
            "filename": source_filename,
            "raw_title": raw_title_value,
            "display_title": display_title_value,
            "source_file_available": True,
        }
        cleanup_started_at = time.perf_counter()
        cleanup_result = H.clean_repeated_transcript(tr.segments)
        if cleanup_result.applied_count > 0:
            H.log_event(
                task_id=task_id_value,
                event_name="transcript_cleanup_completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=cleanup_result.cleaned_length,
                stage="transcript_cleanup",
                duration_seconds=round(time.perf_counter() - cleanup_started_at, 3),
                success=True,
                metadata=H._metadata(
                    route="/process",
                    cleanup_issue_count=len(cleanup_result.issues),
                    cleanup_applied_count=cleanup_result.applied_count,
                    cleanup_removed_segment_count=cleanup_result.removed_segment_count,
                    cleanup_raw_length=cleanup_result.raw_length,
                    cleanup_cleaned_length=cleanup_result.cleaned_length,
                ),
            )
        transcript_text = cleanup_result.cleaned_text
        segments_payload = list(cleanup_result.cleaned_segments)
        raw_segments_payload = [
            {"start": s.start, "end": s.end, "text": s.text, "speaker": getattr(s, "speaker", None)}
            for s in tr.segments
        ]
        speaker_payload: dict[str, Any] = {
            "requested": diarization_requested,
            "available": True if cloud_stt_provider else H.diarization_status()["available"],
            "applied": False,
        }
        if diarization_requested and cloud_stt_provider:
            speakers = sorted({
                str(segment.get("speaker"))
                for segment in segments_payload
                if isinstance(segment, dict) and segment.get("speaker")
            })
            if speakers:
                speaker_payload.update({
                    "applied": True,
                    "backend": getattr(tr, "model_source", None) or "azure_speech_transcription",
                    "speaker_count": len(speakers),
                })
                H.log_event(
                    task_id=task_id_value,
                    event_name="speaker_diarization_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    stage="speaker_diarization",
                    success=True,
                    metadata=H._metadata(
                        route="/process",
                        backend=getattr(tr, "model_source", None) or "azure_speech_transcription",
                        speaker_count=len(speakers),
                    ),
                )
            else:
                error_reason = (
                    getattr(tr, "diarization_error", None)
                    or f"{H._stt_provider_label(stt_provider_value)} did not return speaker labels"
                )
                speaker_payload.update({
                    "applied": False,
                    "backend": getattr(tr, "model_source", None) or "azure_speech_transcription",
                    "error_reason": error_reason,
                })
                H.log_event(
                    task_id=task_id_value,
                    event_name="speaker_diarization_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    stage="speaker_diarization",
                    success=False,
                    error_reason=error_reason,
                    metadata=H._metadata(route="/process", backend=getattr(tr, "model_source", None) or "azure_speech_transcription"),
                )
        elif diarization_requested:
            diarization_started_at = time.perf_counter()
            try:
                turns = await loop.run_in_executor(None, lambda: H.diarize_audio(out_audio))
                segments_payload = H.assign_speakers_to_segments(segments_payload, turns)
                speaker_payload.update({
                    "applied": True,
                    "speaker_count": len({turn.speaker for turn in turns}),
                    "turn_count": len(turns),
                })
                H.log_event(
                    task_id=task_id_value,
                    event_name="speaker_diarization_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    stage="speaker_diarization",
                    duration_seconds=round(time.perf_counter() - diarization_started_at, 3),
                    success=True,
                    metadata=H._metadata(route="/process", speaker_count=speaker_payload["speaker_count"]),
                )
            except Exception as exc:
                error_reason = str(exc)
                speaker_payload.update({
                    "applied": False,
                    "error_reason": error_reason,
                })
                H.logger.warning("Speaker diarization skipped for %s: %s", task_id_value, error_reason)
                H.log_event(
                    task_id=task_id_value,
                    event_name="speaker_diarization_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    stage="speaker_diarization",
                    duration_seconds=round(time.perf_counter() - diarization_started_at, 3),
                    success=False,
                    error_reason=error_reason,
                    metadata=H._metadata(route="/process", failure_scope="optional_speaker_diarization"),
                )
        source_language = _normalized_source_language(getattr(tr, "language", None)) or _normalized_source_language(language)
        bilingual_segments: list[dict[str, Any]] = []
        translation_status = "not_applicable"
        translation_error: str | None = None
        if _is_english_source(source_language) and segments_payload:
            current_stage = "translation"
            translation_status = "running"
            H.upsert_job(task_id=task_id_value, status="running", stage="translation", progress=61)
            yield H._sse({"stage": "translation", "progress": 61})
            translation_started_at = time.perf_counter()
            try:
                translation_kwargs = _translation_ai_kwargs(H._ai_kwargs(
                    deepseek_api_key=deepseek_api_key,
                    openai_api_key=openai_api_key,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    system_prompt=None,
                ))
                translation_result = await loop.run_in_executor(
                    None,
                    lambda: H.generate_bilingual_segments_zh(segments_payload, **translation_kwargs),
                )
                bilingual_segments = translation_result.segments
                translation_status = "completed" if bilingual_segments else "failed"
                if not bilingual_segments:
                    translation_error = "AI returned no usable bilingual subtitle segments"
                H.log_event(
                    task_id=task_id_value,
                    event_name="translation_completed" if bilingual_segments else "translation_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=H._text_len(transcript_text),
                    stage="translation",
                    duration_seconds=round(time.perf_counter() - translation_started_at, 3),
                    success=bool(bilingual_segments),
                    error_reason=translation_error,
                    metadata=H._metadata(
                        route="/process",
                        source_language=source_language,
                        bilingual_segment_count=len(bilingual_segments),
                        translated_segment_count=len([segment for segment in bilingual_segments if segment.get("text_zh")]),
                        translation_chunk_count=translation_result.chunk_count,
                    ),
                )
            except Exception as exc:
                translation_status = "failed"
                translation_error = H._friendly_error_message(exc)
                H.logger.warning("Segment translation failed for %s: %s", task_id_value, exc)
                H.log_event(
                    task_id=task_id_value,
                    event_name="translation_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=H._text_len(transcript_text),
                    stage="translation",
                    duration_seconds=round(time.perf_counter() - translation_started_at, 3),
                    success=False,
                    error_reason=translation_error,
                    metadata=H._metadata(route="/process", source_language=source_language, raw_error=str(exc)),
                )
        base_result.update({
            "task_id": task_id_value,
            "filename": source_filename,
            "raw_title": raw_title_value,
            "display_title": display_title_value,
            "transcript_text": transcript_text,
            "raw_transcript_text": tr.text,
            "cleaned_transcript_text": cleanup_result.cleaned_text,
            "transcript_text_preview": transcript_text[:200],
            "summary_markdown": "",
            "audio_duration_seconds": round(duration_sec, 1),
            "stt_elapsed_seconds": round(stt_elapsed_sec, 1),
            "stt_realtime_factor": stt_realtime_factor,
            "stt_provider": stt_provider_value,
            "stt_provider_label": H._stt_provider_label(stt_provider_value),
            "stt_model": stt_model_for_result,
            "stt_speed": speed_profile,
            "stt_language": language,
            "detected_language": tr.language,
            "source_language": source_language,
            "subtitle_mode": "bilingual_zh" if bilingual_segments else "source_only",
            "translation_status": translation_status,
            "translation_error": translation_error,
            "source_fingerprint": source_fingerprint,
            "display_segments": bilingual_segments or segments_payload,
            "raw_segments": segments_payload,
            "speaker_diarization": speaker_payload,
            "stt_raw_segments": raw_segments_payload,
            "transcript_cleanup": H._cleanup_payload(cleanup_result),
            "status": "transcript_ready",
            "source": source_type,
            "summary_skipped": summary_disabled,
        })
        note_transcript_text = transcript_text
        note_segments_payload = segments_payload
        if not summary_disabled and H.transcript_correction_enabled():
            current_stage = "transcript_correction"
            H.upsert_job(task_id=task_id_value, status="running", stage="transcript_correction", progress=61)
            yield H._sse({"stage": "transcript_correction", "progress": 61})
            correction_fields, note_transcript_text, note_segments_payload = await _run_transcript_correction_stage(
                loop=loop,
                task_id=task_id_value,
                route="/process",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_text=transcript_text,
                segments=segments_payload,
                deepseek_api_key=deepseek_api_key,
            )
            base_result.update(correction_fields)
        elif not summary_disabled:
            base_result["note_generation_transcript_source"] = "transcript_text"
        if playback_audio_path is not None:
            base_result = H._attach_playback_audio_artifact(task_id_value, base_result, playback_audio_path)
        base_result = H._attach_result_artifacts(task_id_value, base_result)
        current_stage = "transcript_ready"
        H.log_event(
            task_id=task_id_value,
            event_name="transcript_ready",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=round(duration_sec, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            stage="transcript_ready",
            success=True,
            metadata=H._metadata(route="/process", source_fingerprint=source_fingerprint),
        )
        H.upsert_job(
            task_id=task_id_value,
            status="running",
            stage="transcript_ready",
            progress=60,
            result=base_result,
            summary_status="pending",
        )
        yield H._sse({
            "stage": "transcript_ready",
            "progress": 60,
            "result": base_result,
        })

        if summary_disabled:
            summary_status = "skipped"
            H.log_event(
                task_id=task_id_value,
                event_name="summary_skipped",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(note_transcript_text),
                stage="summary",
                success=True,
                metadata=H._metadata(route="/process", reason="transcript_only_mode"),
            )
            result = H.result_for_transcript_only(base_result)
            quota_final = H._finalize_task_quota(
                client_id=client_id,
                task_id=task_id_value,
                final_usage=H._estimate_processing_units(
                    duration_seconds=duration_sec,
                    transcript_text=transcript_text,
                    summary_text="",
                    skip_summary=True,
                ),
                reason="Finalize transcript-only task charge",
            )
            if quota_final:
                result["quota"] = quota_final
            result = H._attach_result_artifacts(task_id_value, result)
            result = H._finalize_completed_result_storage(
                task_id_value,
                result,
                (H.get_job(task_id_value) or {}).get("metadata"),
            )
            H.upsert_job(
                task_id=task_id_value,
                status="completed",
                stage="done",
                progress=100,
                result=result,
                summary_status=summary_status,
            )
            H._log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(transcript_text),
                summary_length=0,
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=None,
                stt_provider=stt_provider_value,
                completion_reason="summary_skipped",
            )
            H._enforce_history_retention(client_id)
            yield H._sse({"stage": "done", "progress": 100, "result": result})
            return

        # ── Stage 3: AI summarization ──────────────────────
        current_stage = "summary"
        H.upsert_job(task_id=task_id_value, status="running", stage="summary", progress=62)
        yield H._sse({"stage": "summary", "progress": 62})

        summary_error: str | None = None
        summary_result = None
        note_mode_plan: dict[str, Any] = {}
        summary_started_at = time.perf_counter()
        try:
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
                route="/process",
                filename=source_filename,
                duration_seconds=duration_sec,
                current_prompt_preset=prompt_preset,
            )
            summary_result = await loop.run_in_executor(
                None,
                lambda: H.summarize_transcript_with_metadata(note_transcript_text, **kwargs),
            )
            summary_md = summary_result.markdown
            if not summary_md.strip():
                raise ValueError("AI summarization returned empty result")
            summary_status = "completed"
            if generate_visuals and source_type == "video" and note_segments_payload:
                try:
                    visual_plan = await loop.run_in_executor(
                        None,
                        lambda: H.plan_visual_evidence_requests(
                            summary_md,
                            note_segments_payload,
                            api_key=kwargs.get("api_key"),
                            model=kwargs.get("model"),
                            provider=kwargs.get("provider"),
                        ),
                    )
                    visual_requests = visual_plan.requests
                    if visual_requests:
                        frames_output_dir = H._artifact_storage_dir() / task_id_value / "frames"
                        frames_output_dir.mkdir(parents=True, exist_ok=True)
                        keyframe_result = await loop.run_in_executor(
                            None,
                            lambda: H.extract_keyframes(
                                str(in_path),
                                frames_output_dir,
                                segments=H.visual_requests_to_frame_segments(visual_requests),
                                scene_threshold=0.3,
                                max_scene_frames=0,
                                min_gap_seconds=0.8,
                            ),
                        )
                        frame_paths = [str(f["path"]) for f in keyframe_result.frames]
                        frame_metadata = keyframe_result.frames
                        if keyframe_result.skipped_reason:
                            visual_evidence_error = keyframe_result.skipped_reason
                            H.logger.info(
                                "Frame extraction skipped for %s via %s: %s",
                                task_id_value,
                                keyframe_result.provider,
                                keyframe_result.skipped_reason,
                            )
                    if frame_metadata:
                        visual_api_key = H.resolve_secret(qwen_api_key, "qwen_api_key")
                        if not visual_api_key and (kwargs.get("provider") == "qwen"):
                            visual_api_key = kwargs.get("api_key") or ""
                        visual_selection = await loop.run_in_executor(
                            None,
                            lambda: H.select_visual_evidence_frames(
                                visual_requests,
                                frame_metadata,
                                api_key=visual_api_key or None,
                                provider="qwen",
                            ),
                        )
                        visual_selections = visual_selection.selections
                except Exception as exc:
                    visual_evidence_error = H._friendly_error_message(exc)
                    H.logger.warning("Visual evidence planning failed for %s: %s", task_id_value, exc)
            H.log_event(
                task_id=task_id_value,
                event_name="summary_completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(note_transcript_text),
                summary_length=H._text_len(summary_md),
                stage="summary",
                duration_seconds=round(time.perf_counter() - summary_started_at, 3),
                success=True,
                metadata=H._metadata(
                    route="/process",
                    ai_provider=(ai_provider or "").strip() or None,
                    ai_model=(ai_model or "").strip() or None,
                    requested_note_mode=note_mode_plan.get("requested_note_mode") or (summary_result.requested_mode if summary_result is not None else None),
                    **H._summary_result_metadata(summary_result),
                    **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
                    visual_request_count=len(visual_requests) if visual_requests else None,
                    visual_selection_count=len(visual_selections) if visual_selections else None,
                    visual_evidence_error=visual_evidence_error,
                    frame_count=len(frame_paths) if frame_paths else None,
                    note_generation_transcript_source=base_result.get("note_generation_transcript_source"),
                ),
            )
        except Exception as exc:
            H.logger.warning("AI summarization failed: %s", exc)
            summary_error = H._friendly_error_message(exc)
            summary_md = ""
            summary_status = "failed"
            summary_elapsed_sec = time.perf_counter() - summary_started_at
            H.log_event(
                task_id=task_id_value,
                event_name="summary_failed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(transcript_text),
                stage="summary",
                duration_seconds=round(summary_elapsed_sec, 3),
                success=False,
                error_reason=summary_error,
                metadata=H._metadata(
                    route="/process",
                    ai_provider=(ai_provider or "").strip() or None,
                    ai_model=(ai_model or "").strip() or None,
                    requested_note_mode=note_mode_plan.get("requested_note_mode") or (note_mode or "").strip() or None,
                    raw_error=str(exc),
                    note_generation_transcript_source=base_result.get("note_generation_transcript_source"),
                    **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
                ),
            )
            result = H.result_for_summary_failure(base_result, summary_error)
            result.update({key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")})
            quota_final = H._finalize_task_quota(
                client_id=client_id,
                task_id=task_id_value,
                final_usage=H._estimate_processing_units(
                    duration_seconds=duration_sec,
                    transcript_text=note_transcript_text,
                    summary_text="",
                    skip_summary=True,
                ),
                reason="Finalize transcription charge after summary failure",
            )
            if quota_final:
                result["quota"] = quota_final
            result = H._attach_result_artifacts(task_id_value, result)
            result = H._finalize_completed_result_storage(
                task_id_value,
                result,
                (H.get_job(task_id_value) or {}).get("metadata"),
            )
            H.upsert_job(
                task_id=task_id_value,
                status="completed",
                stage="done",
                progress=100,
                result=result,
                summary_status=summary_status,
                error_reason=summary_error,
            )
            H._log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(note_transcript_text),
                summary_length=0,
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=False if do_lark else None,
                stt_provider=stt_provider_value,
                completion_reason="summary_failed",
            )
            H._enforce_history_retention(client_id)
            yield H._sse({"stage": "done", "progress": 100, "result": result})
            return

        H.upsert_job(task_id=task_id_value, status="running", stage="summary", progress=88)
        yield H._sse({"stage": "summary", "progress": 88})

        # ── Build result ───────────────────────────────────
        result = H.result_for_summary_success(
            base_result,
            summary_md,
            requested_note_mode=note_mode_plan.get("requested_note_mode") or (summary_result.requested_mode if summary_result is not None else None),
            resolved_note_mode=summary_result.resolved_mode if summary_result is not None else None,
            note_mode_chunk_count=summary_result.chunk_count if summary_result is not None else None,
            note_mode_segment_count=getattr(summary_result, "segment_count", None) if summary_result is not None else None,
            note_mode_evidence_count=getattr(summary_result, "evidence_count", None) if summary_result is not None else None,
            note_mode_chapter_count=getattr(summary_result, "chapter_count", None) if summary_result is not None else None,
            note_mode_important_evidence_count=getattr(summary_result, "important_evidence_count", None) if summary_result is not None else None,
            note_mode_covered_important_evidence_count=getattr(summary_result, "covered_important_evidence_count", None) if summary_result is not None else None,
            note_mode_coverage_missing_count=getattr(summary_result, "coverage_missing_count", None) if summary_result is not None else None,
            chapter_coverage=getattr(summary_result, "chapter_coverage", None) if summary_result is not None else None,
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
        if visual_requests:
            result["visual_requests"] = visual_requests
        if visual_selections:
            result["visual_frame_selections"] = visual_selections
            summary_md = H.inject_visual_evidence_references(summary_md, visual_selections)

        # Register frame files as artifacts
        if frame_paths:
            frame_artifacts = []
            for fm in frame_metadata:
                frame_name = Path(fm["path"]).name
                try:
                    art = H._write_file_artifact(task_id_value, "frame", f"frames/{frame_name}", fm["path"])
                    for key in (
                        "timestamp_seconds",
                        "source",
                        "provider",
                        "visual_hash",
                        "brightness",
                        "contrast",
                        "edge_contrast",
                        "low_information",
                        "visual_request_id",
                        "note_section",
                        "query",
                        "reason",
                        "purpose",
                    ):
                        if fm.get(key) is not None:
                            art[key] = fm.get(key)
                    art["content_type"] = "image/jpeg"
                    frame_artifacts.append(art)
                except Exception as exc:
                    H.logger.warning("Frame artifact write failed for %s: %s", task_id_value, exc)
            if frame_artifacts:
                result["frame_artifacts"] = frame_artifacts
                result["visual_evidence_pipeline"] = "text_plan_qwen_local_window"
                result["frame_count"] = len(frame_artifacts)
                summary_md = H.rewrite_note_image_references(summary_md, frame_artifacts)
                result["summary_markdown"] = summary_md
                visual_payload = H.build_visual_evidence_from_note_images(
                    summary_md,
                    frame_artifacts,
                    provider=frame_artifacts[0].get("provider"),
                )
                result.update(visual_payload)
                result.update(H.build_visual_key_moments(
                    visual_selections,
                    frame_artifacts,
                    visual_evidence=visual_payload.get("visual_evidence") if isinstance(visual_payload.get("visual_evidence"), list) else [],
                    provider=frame_artifacts[0].get("provider"),
                ))
            elif visual_requests:
                summary_md = str(result.get("summary_markdown") or summary_md)
                result["visual_evidence"] = []
                result["visual_artifacts"] = {}
                result["visual_key_moments"] = []
                result["visual_key_moments_status"] = "unavailable"
                result["visual_key_moments_reason"] = "没有成功写入候选帧产物；关键画面候选不可用。"
                result["visual_evidence_status"] = "unavailable"
                result["visual_evidence_reason"] = (
                    visual_evidence_error
                    or "截图候选帧没有成功写入产物，最终笔记不插入截图。"
                )
        elif visual_requests:
            result["visual_evidence"] = []
            result["visual_artifacts"] = {}
            result["visual_key_moments"] = []
            result["visual_key_moments_status"] = "unavailable"
            result["visual_key_moments_reason"] = "文本模型提出了截图需求，但当前任务没有生成可用候选帧。"
            result["visual_evidence_status"] = "unavailable"
            result["visual_evidence_reason"] = (
                visual_evidence_error
                or "文本模型提出了截图需求，但当前任务没有生成可用候选帧。"
            )

        # ── Stage 4: Lark export (optional) ───────────────
        if do_lark:
            current_stage = "export"
            yield H._sse({"stage": "export", "progress": 90})
            stem = Path(source_filename or "media").stem
            doc_title = H.resolve_lark_doc_title(
                summary_md,
                filename_stem=display_title_value or stem,
                form_title=title or display_title_value,
            )
            result["lark_doc_title"] = doc_title
            lark_kwargs: dict[str, Any] = {}
            if (lark_id := H.resolve_secret(lark_app_id, "lark_app_id")):
                lark_kwargs["app_id"] = lark_id
            if (lark_secret := H.resolve_secret(lark_app_secret, "lark_app_secret")):
                lark_kwargs["app_secret"] = lark_secret
            if folder_token:
                lark_kwargs["folder_token"] = folder_token
            export_target = H._lark_export_target(lark_export_route, lark_via_cli)
            H.log_event(
                task_id=task_id_value,
                event_name="lark_export_started",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=H._text_len(transcript_text),
                summary_length=H._text_len(summary_md),
                stage="export",
                export_target=export_target,
                metadata=H._metadata(route="/process", trigger="auto", doc_title=doc_title),
            )
            export_started_at = time.perf_counter()
            try:
                if export_target == "lark_cli":
                    resp = await loop.run_in_executor(
                        None,
                        lambda: H.export_markdown_via_lark_cli(doc_title, summary_md),
                    )
                elif export_target == "feishu_user_oauth":
                    user = ctx.account_user
                    if not user or not user.get("id"):
                        raise RuntimeError("FluentFlow account login is required.")
                    user_access_token = H.get_valid_feishu_user_access_token(str(user["id"]))
                    resp = await loop.run_in_executor(
                        None,
                        lambda: H.export_markdown_to_lark(
                            doc_title,
                            summary_md,
                            task_id=task_id_value,
                            artifact_root=H._artifact_storage_dir(),
                            user_access_token=user_access_token,
                            **lark_kwargs,
                        ),
                    )
                else:
                    resp = await loop.run_in_executor(
                        None,
                        lambda: H.export_markdown_to_lark(
                            doc_title,
                            summary_md,
                            task_id=task_id_value,
                            artifact_root=H._artifact_storage_dir(),
                            **lark_kwargs,
                        ),
                    )
                result["lark_response"] = resp
                lark_success = True
                feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
                H.log_event(
                    task_id=task_id_value,
                    event_name="lark_export_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=H._text_len(transcript_text),
                    summary_length=H._text_len(summary_md),
                    stage="export",
                    duration_seconds=round(time.perf_counter() - export_started_at, 3),
                    success=True,
                    export_target=export_target,
                    feishu_doc_url=feishu_doc_url,
                    metadata=H._metadata(route="/process", trigger="auto", doc_title=doc_title),
                )
            except Exception as e:
                result["lark_error"] = H._friendly_error_message(e)
                lark_success = False
                H.log_event(
                    task_id=task_id_value,
                    event_name="lark_export_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=H._text_len(transcript_text),
                    summary_length=H._text_len(summary_md),
                    stage="export",
                    duration_seconds=round(time.perf_counter() - export_started_at, 3),
                    success=False,
                    error_reason=H._friendly_error_message(e),
                    export_target=export_target,
                    metadata=H._metadata(route="/process", trigger="auto", doc_title=doc_title, raw_error=str(e)),
                )

        # ── Done ───────────────────────────────────────────
        quota_final = H._finalize_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            final_usage=H._estimate_processing_units(
                duration_seconds=duration_sec,
                transcript_text=note_transcript_text,
                summary_text=summary_md,
                skip_summary=False,
            ),
        )
        if quota_final:
            result["quota"] = quota_final
        result = H._attach_result_artifacts(task_id_value, result)
        result = H._finalize_completed_result_storage(
            task_id_value,
            result,
            (H.get_job(task_id_value) or {}).get("metadata"),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            summary_length=H._text_len(summary_md),
            summary_status=summary_status,
            lark_requested=do_lark,
            lark_success=lark_success,
            stt_provider=stt_provider_value,
        )
        H.upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            result=result,
            summary_status=summary_status,
        )
        H._enforce_history_retention(client_id)
        yield H._sse({"stage": "done", "progress": 100, "result": result})

    except asyncio.CancelledError:
        H.logger.info("Processing stream cancelled by client at stage=%s", current_stage)
        if stt_process is not None and stt_process.is_alive():
            H.terminate_process(stt_process)
        H._release_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            reason="Task cancelled before completion",
            metadata={"stage": current_stage},
        )
        source_duration_for_cancel = duration_sec or duration_estimate_sec
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="cancelled",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=round(source_duration_for_cancel, 1) if source_duration_for_cancel is not None else None,
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            summary_length=H._text_len(summary_md),
            summary_status=summary_status,
            lark_requested=do_lark,
            lark_success=lark_success,
            stt_provider=stt_provider_value,
            completion_reason="client_disconnect",
        )
        H.upsert_job(
            task_id=task_id_value,
            status="cancelled",
            stage=current_stage,
            source_type=source_type,
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status=summary_status,
            error_reason="client_disconnect",
        )
        raise
    except Exception as exc:
        H.logger.exception("Processing failed")
        friendly_error = H._friendly_error_message(exc)
        if stt_process is not None and stt_process.is_alive():
            H.terminate_process(stt_process)
        if summary_status is None and current_stage == "summary":
            summary_status = "failed"
        H._release_task_quota(
            client_id=client_id,
            task_id=task_id_value,
            reason="Task failed before charge finalization",
            metadata={"stage": current_stage, "raw_error": str(exc)},
        )
        H.log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage=current_stage,
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route="/process", stt_provider=stt_provider_value, raw_error=str(exc)),
        )
        H._log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
            source_file_size_mb=source_file_size_mb,
            transcript_length=H._text_len(transcript_text),
            summary_length=H._text_len(summary_md),
            summary_status=summary_status,
            lark_requested=do_lark,
            lark_success=lark_success,
            stt_provider=stt_provider_value,
            completion_reason=current_stage,
        )
        H.upsert_job(
            task_id=task_id_value,
            status="failed",
            stage=current_stage,
            progress=0,
            source_type=source_type,
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status=summary_status,
            error_reason=friendly_error,
        )
        yield H._sse({"stage": "error", "progress": 0, "error": friendly_error})
    finally:
        if stt_process is not None and stt_process.is_alive():
            H.terminate_process(stt_process)
        if stt_queue is not None:
            try:
                stt_queue.close()
                stt_queue.join_thread()
            except Exception:
                pass
        shutil.rmtree(td, ignore_errors=True)


async def execute_media_job(ctx: MediaJobContext) -> None:
    """Drain the pipeline stream into the job event hub."""
    terminal_sent = False
    try:
        async for chunk in _stream_media_job(ctx):
            event = H._event_from_sse_chunk(chunk)
            if event is None:
                continue
            if H.JobEventHub.is_terminal(event):
                terminal_sent = True
            await H.JOB_EVENTS.publish(ctx.task_id_value, event)
    except asyncio.CancelledError:
        terminal_sent = True
        await H.JOB_EVENTS.publish(
            ctx.task_id_value,
            {"stage": "error", "progress": 0, "error": "Task cancelled"},
        )
    except Exception as exc:
        H.logger.exception("Background processing failed")
        await H.JOB_EVENTS.publish(
            ctx.task_id_value,
            {"stage": "error", "progress": 0, "error": str(exc)},
        )
    finally:
        if not terminal_sent:
            job = H.get_job(ctx.task_id_value)
            if job and job.get("status") in {"completed", "failed", "cancelled"}:
                await H.JOB_EVENTS.publish(ctx.task_id_value, H.JobEventHub.event_from_job(job))
