"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes:
  GET  /health   – liveness check
  POST /process  – upload video/audio, run STT + summarize, optional Lark export
                   returns Server-Sent Events for real-time progress
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(title="FluentFlow")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5185",
        "http://localhost:5185",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.core.audio_handler import extract_stt_wav
    from backend.core.local_stt import transcribe_audio, get_or_load_model
    from backend.core.ai_summarizer import summarize_transcript_to_markdown
    from backend.core.lark_exporter import export_markdown_to_lark
    from backend.core.lark_cli_exporter import export_markdown_via_lark_cli
    from backend.core.note_title import resolve_lark_doc_title
    from backend.core.transcript_parser import parse_transcript_file
    from backend.core.event_logger import log_event
except ImportError:
    from core.audio_handler import extract_stt_wav
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.ai_summarizer import summarize_transcript_to_markdown
    from core.lark_exporter import export_markdown_to_lark
    from core.lark_cli_exporter import export_markdown_via_lark_cli
    from core.note_title import resolve_lark_doc_title
    from core.transcript_parser import parse_transcript_file
    from core.event_logger import log_event


def _truthy_form(val: Optional[str]) -> bool:
    return bool(val and val.strip().lower() in ("true", "1", "yes", "on"))


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
}

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt", ".md"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_SUFFIXES = ALLOWED_SUFFIXES - AUDIO_SUFFIXES


def _new_task_id() -> str:
    return uuid.uuid4().hex


def _source_type_for_suffix(suffix: str) -> str:
    if suffix in TRANSCRIPT_SUFFIXES:
        return "transcript_file"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return "unknown"


def _file_size_mb(byte_count: int | None) -> float | None:
    if byte_count is None:
        return None
    return round(byte_count / (1024 * 1024), 3)


def _text_len(value: str | None) -> int:
    return len(value or "")


def _metadata(**values: Any) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _lark_export_target(lark_via_cli: Optional[str]) -> str:
    return "lark_cli" if _truthy_form(lark_via_cli) else "lark_openapi"


def _pipeline_mode(source_type: str | None) -> str | None:
    if source_type == "transcript_file":
        return "transcript_file"
    if source_type in {"audio", "video"}:
        return "audio_video"
    return None


def _elapsed_since(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


def _log_task_completed(
    *,
    task_id: str,
    started_at: float,
    final_status: str,
    source_type: str | None = None,
    source_filename: str | None = None,
    source_duration_seconds: float | None = None,
    source_file_size_mb: float | None = None,
    transcript_length: int | None = None,
    summary_length: int | None = None,
    summary_status: str | None = None,
    lark_requested: bool | None = None,
    lark_success: bool | None = None,
    completion_reason: str | None = None,
) -> None:
    total_duration = _elapsed_since(started_at)
    log_event(
        task_id=task_id,
        event_name="task_completed",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        source_file_size_mb=source_file_size_mb,
        transcript_length=transcript_length,
        summary_length=summary_length,
        stage="done" if final_status == "completed" else final_status,
        duration_seconds=total_duration,
        success=final_status == "completed",
        metadata=_metadata(
            final_status=final_status,
            total_duration_seconds=total_duration,
            summary_status=summary_status,
            lark_requested=lark_requested,
            lark_success=lark_success,
            source_type=source_type,
            pipeline_mode=_pipeline_mode(source_type),
            completion_reason=completion_reason,
        ),
    )


CLIENT_EVENT_NAMES = {
    "summary_downloaded",
    "transcript_downloaded",
    "task_cancelled",
}


def _ai_kwargs(
    *,
    deepseek_api_key: Optional[str],
    openai_api_key: Optional[str],
    ai_provider: Optional[str],
    ai_model: Optional[str],
    system_prompt: Optional[str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    provider_name = (ai_provider or "").strip()
    if not provider_name and (openai_api_key or "").strip():
        provider_name = "openai"
    if provider_name:
        kwargs["provider"] = provider_name
    if (k := (deepseek_api_key or "").strip()):
        kwargs["api_key"] = k
    if (k := (openai_api_key or "").strip()) and provider_name.lower() == "openai":
        kwargs["api_key"] = k
    if (m := (ai_model or "").strip()):
        kwargs["model"] = m
    if (sp := (system_prompt or "").strip()):
        kwargs["system_prompt"] = sp
    return kwargs


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process")
async def process_video(
    file: UploadFile = File(...),
    export_to_lark: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
) -> StreamingResponse:
    """Upload a file and stream processing progress via SSE."""

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    do_lark = _truthy_form(export_to_lark)
    summary_disabled = _truthy_form(skip_summary)
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or _new_task_id()
    source_filename = file.filename
    source_type = _source_type_for_suffix(suffix)
    td = tempfile.mkdtemp()
    in_path = Path(td) / f"upload{suffix}"
    content = await file.read()
    source_file_size_mb = _file_size_mb(len(content))
    with open(in_path, "wb") as f:
        f.write(content)

    log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=_metadata(route="/process"),
    )

    loop = asyncio.get_event_loop()
    model_size = (stt_model or "").strip() or "small"
    speed_profile = (stt_speed or "").strip() or "balanced"
    language = (stt_language or "").strip() or "auto"

    async def event_stream() -> AsyncGenerator[str, None]:
        current_stage = "import"
        duration_sec: float | None = None
        transcript_text = ""
        summary_md = ""
        summary_status: str | None = None
        lark_success: bool | None = None
        try:
            # ── Stage 1: Audio extraction ──────────────────────
            current_stage = "audio"
            yield _sse({"stage": "audio", "progress": 5})
            audio_started_at = time.perf_counter()
            out_audio = await loop.run_in_executor(
                None, lambda: extract_stt_wav(in_path)
            )
            audio_elapsed_sec = time.perf_counter() - audio_started_at
            log_event(
                task_id=task_id_value,
                event_name="audio_extracted",
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                stage="audio",
                duration_seconds=round(audio_elapsed_sec, 3),
                success=True,
                metadata=_metadata(route="/process"),
            )
            yield _sse({"stage": "audio", "progress": 20})

            # ── Stage 2: STT transcription ─────────────────────
            current_stage = "stt"
            yield _sse({"stage": "stt", "progress": 22})

            progress_state: dict[str, float] = {"last_sent": 22.0}

            def stt_progress_cb(frac: float) -> None:
                progress_state["latest"] = 22 + frac * 38  # 22–60 range

            stt_started_at = time.perf_counter()
            tr = await loop.run_in_executor(
                None,
                lambda: transcribe_audio(
                    out_audio,
                    model_size=model_size,
                    speed_profile=speed_profile,
                    language=language,
                    on_progress=stt_progress_cb,
                ),
            )
            stt_elapsed_sec = time.perf_counter() - stt_started_at
            yield _sse({"stage": "stt", "progress": 60})

            duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
            transcript_text = tr.text
            log_event(
                task_id=task_id_value,
                event_name="stt_completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(tr.text),
                stage="stt",
                duration_seconds=round(stt_elapsed_sec, 3),
                success=True,
                metadata=_metadata(
                    route="/process",
                    stt_model=model_size,
                    stt_speed=speed_profile,
                    stt_language=language,
                    detected_language=tr.language,
                    language_probability=tr.language_probability,
                    segment_count=len(tr.segments),
                ),
            )
            base_result: dict[str, Any] = {
                "task_id": task_id_value,
                "filename": file.filename,
                "transcript_text": tr.text,
                "transcript_text_preview": tr.text[:200],
                "summary_markdown": "",
                "audio_duration_seconds": round(duration_sec, 1),
                "stt_elapsed_seconds": round(stt_elapsed_sec, 1),
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in tr.segments
                ],
                "status": "transcript_ready",
                "source": source_type,
                "summary_skipped": summary_disabled,
            }
            current_stage = "transcript_ready"
            log_event(
                task_id=task_id_value,
                event_name="transcript_ready",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(tr.text),
                stage="transcript_ready",
                success=True,
                metadata=_metadata(route="/process"),
            )
            yield _sse({
                "stage": "transcript_ready",
                "progress": 60,
                "result": base_result,
            })

            if summary_disabled:
                summary_status = "skipped"
                log_event(
                    task_id=task_id_value,
                    event_name="summary_skipped",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    stage="summary",
                    success=True,
                    metadata=_metadata(route="/process", reason="transcript_only_mode"),
                )
                result: dict[str, Any] = {
                    **base_result,
                    "status": "completed",
                }
                _log_task_completed(
                    task_id=task_id_value,
                    started_at=task_started_at,
                    final_status="completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    summary_length=0,
                    summary_status=summary_status,
                    lark_requested=do_lark,
                    lark_success=None,
                    completion_reason="summary_skipped",
                )
                yield _sse({"stage": "done", "progress": 100, "result": result})
                return

            # ── Stage 3: AI summarization ──────────────────────
            current_stage = "summary"
            yield _sse({"stage": "summary", "progress": 62})

            summary_error: str | None = None
            summary_started_at = time.perf_counter()
            try:
                kwargs = _ai_kwargs(
                    deepseek_api_key=deepseek_api_key,
                    openai_api_key=openai_api_key,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    system_prompt=system_prompt,
                )
                summary_md = await loop.run_in_executor(
                    None,
                    lambda: summarize_transcript_to_markdown(tr.text, **kwargs),
                )
                if not summary_md.strip():
                    raise ValueError("AI summarization returned empty result")
                summary_status = "completed"
                log_event(
                    task_id=task_id_value,
                    event_name="summary_completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    summary_length=_text_len(summary_md),
                    stage="summary",
                    duration_seconds=round(time.perf_counter() - summary_started_at, 3),
                    success=True,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                    ),
                )
            except Exception as exc:
                logger.warning("AI summarization failed, using raw transcript: %s", exc)
                summary_error = str(exc)
                summary_md = f"# Transcript\n\n{tr.text}"
                summary_status = "fallback_used"
                summary_elapsed_sec = time.perf_counter() - summary_started_at
                log_event(
                    task_id=task_id_value,
                    event_name="summary_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    stage="summary",
                    duration_seconds=round(summary_elapsed_sec, 3),
                    success=False,
                    error_reason=summary_error,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                    ),
                )
                log_event(
                    task_id=task_id_value,
                    event_name="summary_fallback_used",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    summary_length=_text_len(summary_md),
                    stage="summary",
                    success=True,
                    metadata=_metadata(route="/process", fallback="raw_transcript"),
                )

            yield _sse({"stage": "summary", "progress": 88})

            # ── Build result ───────────────────────────────────
            result: dict[str, Any] = {
                **base_result,
                "summary_markdown": summary_md,
                "status": "completed",
            }

            # ── Stage 4: Lark export (optional) ───────────────
            if do_lark:
                current_stage = "export"
                yield _sse({"stage": "export", "progress": 90})
                stem = Path(file.filename or "media").stem
                doc_title = resolve_lark_doc_title(
                    summary_md,
                    filename_stem=stem,
                    form_title=title,
                )
                result["lark_doc_title"] = doc_title
                lark_kwargs: dict[str, Any] = {}
                if (lark_id := (lark_app_id or "").strip()):
                    lark_kwargs["app_id"] = lark_id
                if (lark_secret := (lark_app_secret or "").strip()):
                    lark_kwargs["app_secret"] = lark_secret
                if folder_token:
                    lark_kwargs["folder_token"] = folder_token
                export_target = _lark_export_target(lark_via_cli)
                log_event(
                    task_id=task_id_value,
                    event_name="lark_export_started",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(tr.text),
                    summary_length=_text_len(summary_md),
                    stage="export",
                    export_target=export_target,
                    metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title),
                )
                export_started_at = time.perf_counter()
                try:
                    if _truthy_form(lark_via_cli):
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_via_lark_cli(doc_title, summary_md),
                        )
                    else:
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_to_lark(
                                doc_title, summary_md, **lark_kwargs
                            ),
                        )
                    result["lark_response"] = resp
                    lark_success = True
                    feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
                    log_event(
                        task_id=task_id_value,
                        event_name="lark_export_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        transcript_length=_text_len(tr.text),
                        summary_length=_text_len(summary_md),
                        stage="export",
                        duration_seconds=round(time.perf_counter() - export_started_at, 3),
                        success=True,
                        export_target=export_target,
                        feishu_doc_url=feishu_doc_url,
                        metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title),
                    )
                except Exception as e:
                    result["lark_error"] = str(e)
                    lark_success = False
                    log_event(
                        task_id=task_id_value,
                        event_name="lark_export_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        transcript_length=_text_len(tr.text),
                        summary_length=_text_len(summary_md),
                        stage="export",
                        duration_seconds=round(time.perf_counter() - export_started_at, 3),
                        success=False,
                        error_reason=str(e),
                        export_target=export_target,
                        metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title),
                    )

            # ── Done ───────────────────────────────────────────
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(tr.text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
            )
            yield _sse({"stage": "done", "progress": 100, "result": result})

        except Exception as exc:
            logger.exception("Processing failed")
            if summary_status is None and current_stage == "summary":
                summary_status = "failed"
            log_event(
                task_id=task_id_value,
                event_name="task_failed",
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                stage=current_stage,
                success=False,
                error_reason=str(exc),
                metadata=_metadata(route="/process"),
            )
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="failed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1) if duration_sec is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
                completion_reason=current_stage,
            )
            yield _sse({"stage": "error", "progress": 0, "error": str(exc)})
        finally:
            shutil.rmtree(td, ignore_errors=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/export-lark")
async def export_lark(
    markdown: str = Form(...),
    title: Optional[str] = Form(None),
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
    task_id_value = (task_id or "").strip() or _new_task_id()
    kwargs: dict[str, Any] = {}
    if (v := (lark_app_id or "").strip()):
        kwargs["app_id"] = v
    if (v := (lark_app_secret or "").strip()):
        kwargs["app_secret"] = v
    if folder_token:
        kwargs["folder_token"] = folder_token
    resolved = resolve_lark_doc_title(
        markdown,
        filename_stem="",
        form_title=title,
    )
    export_target = _lark_export_target(lark_via_cli)
    log_event(
        task_id=task_id_value,
        event_name="lark_export_started",
        source_type=source_type,
        source_filename=source_filename,
        source_duration_seconds=source_duration_seconds,
        summary_length=_text_len(markdown),
        stage="export",
        export_target=export_target,
        metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved),
    )
    started_at = time.perf_counter()
    try:
        if _truthy_form(lark_via_cli):
            resp = await loop.run_in_executor(
                None, lambda: export_markdown_via_lark_cli(resolved, markdown)
            )
        else:
            resp = await loop.run_in_executor(
                None, lambda: export_markdown_to_lark(resolved, markdown, **kwargs)
            )
        if isinstance(resp, dict):
            resp["doc_title"] = resolved
            resp["task_id"] = task_id_value
        feishu_doc_url = resp.get("url") if isinstance(resp, dict) else None
        log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            export_target=export_target,
            feishu_doc_url=feishu_doc_url,
            metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved),
        )
        return resp
    except Exception as exc:
        log_event(
            task_id=task_id_value,
            event_name="lark_export_completed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=str(exc),
            export_target=export_target,
            metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            summary_length=_text_len(markdown),
            stage="export",
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/export-lark", trigger="manual"),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/regenerate-summary")
async def regenerate_summary(
    transcript: str = Form(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    source_filename: Optional[str] = Form(None),
    source_duration_seconds: Optional[float] = Form(None),
):
    """Re-run AI summarization on an existing transcript."""
    loop = asyncio.get_event_loop()
    task_id_value = (task_id or "").strip() or _new_task_id()
    kwargs = _ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
    )
    started_at = time.perf_counter()
    try:
        md = await loop.run_in_executor(
            None, lambda: summarize_transcript_to_markdown(transcript, **kwargs)
        )
        log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            summary_length=_text_len(md),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route="/regenerate-summary",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
            ),
        )
        return {"summary_markdown": md, "task_id": task_id_value}
    except Exception as exc:
        log_event(
            task_id=task_id_value,
            event_name="summary_regenerated",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/regenerate-summary"),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type=source_type,
            source_filename=source_filename,
            source_duration_seconds=source_duration_seconds,
            transcript_length=_text_len(transcript),
            stage="summary_regenerate",
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/regenerate-summary"),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/summarize-transcript-file")
async def summarize_transcript_file(
    file: UploadFile = File(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
):
    """Parse an existing .srt/.vtt/.txt/.md transcript, optionally summarizing it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported transcript file type: {suffix}")

    task_started_at = time.perf_counter()
    task_id_value = (task_id or "").strip() or _new_task_id()
    source_filename = file.filename
    raw = await file.read()
    source_file_size_mb = _file_size_mb(len(raw))
    log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=_metadata(route="/summarize-transcript-file", suffix=suffix),
    )
    try:
        parsed = parse_transcript_file(raw, file.filename)
        if not parsed.text.strip():
            raise HTTPException(status_code=400, detail="Transcript file is empty")
    except HTTPException as exc:
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=str(exc.detail),
            metadata=_metadata(route="/summarize-transcript-file"),
        )
        _log_task_completed(
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
        raise
    except Exception as exc:
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/summarize-transcript-file"),
        )
        _log_task_completed(
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
        raise HTTPException(status_code=500, detail=str(exc))

    log_event(
        task_id=task_id_value,
        event_name="transcript_ready",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(parsed.text),
        stage="transcript_ready",
        success=True,
        metadata=_metadata(route="/summarize-transcript-file", segment_count=len(parsed.segments)),
    )

    if _truthy_form(skip_summary):
        log_event(
            task_id=task_id_value,
            event_name="summary_skipped",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            stage="summary",
            success=True,
            metadata=_metadata(route="/summarize-transcript-file", reason="transcript_only_mode"),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            summary_length=0,
            summary_status="skipped",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_skipped",
        )
        return {
            "task_id": task_id_value,
            "filename": file.filename,
            "transcript_text": parsed.text,
            "transcript_text_preview": parsed.text[:200],
            "summary_markdown": "",
            "audio_duration_seconds": round(parsed.duration, 1),
            "segments": list(parsed.segments),
            "status": "completed",
            "source": "transcript_file",
            "summary_skipped": True,
        }

    loop = asyncio.get_event_loop()
    kwargs = _ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
    )
    started_at = time.perf_counter()
    try:
        summary_md = await loop.run_in_executor(
            None, lambda: summarize_transcript_to_markdown(parsed.text, **kwargs)
        )
        if not summary_md.strip():
            raise ValueError("AI summarization returned empty result")
        log_event(
            task_id=task_id_value,
            event_name="summary_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            summary_length=_text_len(summary_md),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route="/summarize-transcript-file",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
            ),
        )
    except Exception as exc:
        log_event(
            task_id=task_id_value,
            event_name="summary_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/summarize-transcript-file"),
        )
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            stage="summary",
            success=False,
            error_reason=str(exc),
            metadata=_metadata(route="/summarize-transcript-file"),
        )
        _log_task_completed(
            task_id=task_id_value,
            started_at=task_started_at,
            final_status="failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(parsed.text),
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_failed",
        )
        raise HTTPException(status_code=500, detail=str(exc))

    _log_task_completed(
        task_id=task_id_value,
        started_at=task_started_at,
        final_status="completed",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(parsed.text),
        summary_length=_text_len(summary_md),
        summary_status="completed",
        lark_requested=False,
        lark_success=None,
    )
    return {
        "task_id": task_id_value,
        "filename": file.filename,
        "transcript_text": parsed.text,
        "transcript_text_preview": parsed.text[:200],
        "summary_markdown": summary_md,
        "audio_duration_seconds": round(parsed.duration, 1),
        "segments": list(parsed.segments),
        "status": "completed",
        "source": "transcript_file",
        "summary_skipped": False,
    }


@app.post("/events")
async def record_client_event(payload: dict[str, Any] = Body(...)):
    """Record explicit client-side button events without storing user content."""
    event_name = str(payload.get("event_name") or "")
    if event_name not in CLIENT_EVENT_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event_name}")
    task_id_value = str(payload.get("task_id") or "").strip() or _new_task_id()
    raw_metadata = payload.get("metadata")
    client_metadata = (
        {k: raw_metadata.get(k) for k in ("format", "trigger") if k in raw_metadata}
        if isinstance(raw_metadata, dict)
        else None
    )
    log_event(
        task_id=task_id_value,
        event_name=event_name,
        source_type=payload.get("source_type"),
        source_filename=payload.get("source_filename"),
        source_duration_seconds=payload.get("source_duration_seconds"),
        source_file_size_mb=payload.get("source_file_size_mb"),
        transcript_length=payload.get("transcript_length"),
        summary_length=payload.get("summary_length"),
        stage=payload.get("stage"),
        duration_seconds=payload.get("duration_seconds"),
        success=payload.get("success"),
        error_reason=payload.get("error_reason"),
        export_target=payload.get("export_target"),
        feishu_doc_url=payload.get("feishu_doc_url"),
        metadata=client_metadata,
    )
    if event_name == "task_cancelled":
        log_event(
            task_id=task_id_value,
            event_name="task_completed",
            source_type=payload.get("source_type"),
            source_filename=payload.get("source_filename"),
            source_duration_seconds=payload.get("source_duration_seconds"),
            source_file_size_mb=payload.get("source_file_size_mb"),
            transcript_length=payload.get("transcript_length"),
            summary_length=payload.get("summary_length"),
            stage="cancelled",
            duration_seconds=payload.get("duration_seconds"),
            success=False,
            metadata=_metadata(
                final_status="cancelled",
                total_duration_seconds=payload.get("duration_seconds"),
                summary_status=payload.get("summary_status"),
                lark_requested=payload.get("lark_requested"),
                lark_success=payload.get("lark_success"),
                source_type=payload.get("source_type"),
                pipeline_mode=_pipeline_mode(payload.get("source_type")),
                completion_reason="user_cancelled",
            ),
        )
    return {"ok": True, "task_id": task_id_value}


# Mount frontend static files last so API routes take precedence
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to local video file")
    parser.add_argument("--export-to-lark", action="store_true")
    parser.add_argument("--title", default=None)
    parser.add_argument("--folder-token", default=None)
    args = parser.parse_args()

    vp = Path(args.video)
    if not vp.is_file():
        raise SystemExit(f"video not found: {vp}")

    wav = extract_stt_wav(vp)
    tr = transcribe_audio(wav)
    try:
        md = summarize_transcript_to_markdown(tr.text)
    except Exception:
        md = f"# Transcript\n\n{tr.text}"

    print("SUMMARY:\n", md[:2000])
    if args.export_to_lark:
        print("Exporting to Lark...")
        try:
            export_title = resolve_lark_doc_title(
                md,
                filename_stem=vp.stem,
                form_title=args.title,
            )
            out = export_markdown_to_lark(export_title, md, folder_token=args.folder_token)
            print("Export result:", out)
        except Exception as e:
            print("Export failed:", e)
