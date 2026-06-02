"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes:
  GET  /health   – liveness check
  POST /process  – upload video/audio, run STT + summarize, optional Lark export
                   returns Server-Sent Events for real-time progress
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
import wave
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(title="FluentFlow")

EVENT_SCHEMA_VERSION = "1.3"
APP_VERSION = "local"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_SOURCE_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "sources"


def _edited_transcript_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_EDITED_TRANSCRIPT_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "edited_transcripts"


def _transcript_edit_records_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "transcript_edit_records"


class JobEventHub:
    """In-memory fan-out for live job progress events.

    Durable completion state lives in the SQLite job store. This hub only keeps
    recent live events so clients can disconnect and resubscribe without
    cancelling the underlying processing task.
    """

    def __init__(self, max_events_per_job: int = 500) -> None:
        self.max_events_per_job = max_events_per_job
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        if not task_id:
            return
        async with self._lock:
            history = self._events.setdefault(task_id, [])
            payload = dict(event)
            payload["event_index"] = len(history)
            history.append(payload)
            if len(history) > self.max_events_per_job:
                del history[: len(history) - self.max_events_per_job]
                for index, item in enumerate(history):
                    item["event_index"] = index
            subscribers = list(self._subscribers.get(task_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def start(self, task_id: str, runner: Any) -> None:
        async with self._lock:
            existing = self._tasks.get(task_id)
            if existing and not existing.done():
                return
            self._tasks[task_id] = asyncio.create_task(runner())

    async def subscribe(self, task_id: str, since: int = 0) -> AsyncGenerator[str, None]:
        cached = await self.cached_events(task_id)
        start = max(0, int(since or 0))
        for event in cached[start:]:
            yield _sse(event)
            if self.is_terminal(event):
                return

        job = get_job(task_id)
        if job and job.get("status") in {"completed", "failed", "cancelled"}:
            terminal = self.event_from_job(job)
            await self.publish(task_id, terminal)
            yield _sse(terminal)
            return

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(queue)
        try:
            while True:
                event = await queue.get()
                yield _sse(event)
                if self.is_terminal(event):
                    return
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(task_id)
                if subscribers:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(task_id, None)

    async def cached_events(self, task_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._events.get(task_id, []))

    async def has_running_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            return bool(task and not task.done())

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
        if not task or task.done():
            return False
        task.cancel()
        return True

    @staticmethod
    def is_terminal(event: dict[str, Any]) -> bool:
        return event.get("stage") in {"done", "error"}

    @staticmethod
    def event_from_job(job: dict[str, Any]) -> dict[str, Any]:
        status = job.get("status")
        result = job.get("result")
        if status == "completed" or result:
            return {"stage": "done", "progress": 100, "result": result or {}}
        return {
            "stage": "error",
            "progress": job.get("progress") or 0,
            "error": job.get("error_reason") or f"Job {status or 'failed'}",
        }


JOB_EVENTS = JobEventHub()

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
    from backend.core.stt_process import drain_queue, start_transcription_process, terminate_process
    from backend.core.ai_summarizer import summarize_transcript_to_markdown, summarize_transcript_with_metadata
    from backend.core.lark_exporter import export_markdown_to_lark
    from backend.core.lark_cli_exporter import export_markdown_via_lark_cli
    from backend.core.note_title import resolve_lark_doc_title
    from backend.core.transcript_parser import parse_transcript_file
    from backend.core.transcript_cleaner import clean_repeated_transcript
    from backend.core.event_logger import log_event
    from backend.core.job_store import get_job, list_jobs, update_job_result, upsert_job
    from backend.core.local_config import credential_status, resolve_secret, save_sensitive_settings
    from backend.core.speaker_diarization import assign_speakers_to_segments, diarization_status, diarize_audio
except ImportError:
    from core.audio_handler import extract_stt_wav
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.stt_process import drain_queue, start_transcription_process, terminate_process
    from core.ai_summarizer import summarize_transcript_to_markdown, summarize_transcript_with_metadata
    from core.lark_exporter import export_markdown_to_lark
    from core.lark_cli_exporter import export_markdown_via_lark_cli
    from core.note_title import resolve_lark_doc_title
    from core.transcript_parser import parse_transcript_file
    from core.transcript_cleaner import clean_repeated_transcript
    from core.event_logger import log_event
    from core.job_store import get_job, list_jobs, update_job_result, upsert_job
    from core.local_config import credential_status, resolve_secret, save_sensitive_settings
    from core.speaker_diarization import assign_speakers_to_segments, diarization_status, diarize_audio


def _truthy_form(val: Optional[str]) -> bool:
    return bool(val and val.strip().lower() in ("true", "1", "yes", "on"))


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_from_sse_chunk(chunk: str) -> dict[str, Any] | None:
    for line in chunk.splitlines():
        if line.startswith("data: "):
            try:
                payload = json.loads(line[6:])
            except json.JSONDecodeError:
                return None
            return payload if isinstance(payload, dict) else None
    return None


ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
}

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt", ".md"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_SUFFIXES = ALLOWED_SUFFIXES - AUDIO_SUFFIXES


def _max_upload_mb() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_MAX_UPLOAD_MB", "2048")), 1.0)
    except ValueError:
        return 2048.0


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


def _source_fingerprint(content: bytes, filename: str | None = None) -> dict[str, Any]:
    """Return a content fingerprint for comparing reruns without storing content."""
    return {
        "algorithm": "sha256",
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_filename": filename,
        "source_size_bytes": len(content),
    }


def _persist_source_file(task_id: str, suffix: str, content: bytes) -> Path:
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix or '.bin'}"
    target.write_bytes(content)
    return target


def _find_source_file(task_id: str) -> Path | None:
    if not task_id:
        return None
    target_dir = _source_storage_dir() / task_id
    if not target_dir.is_dir():
        return None
    candidates = sorted(path for path in target_dir.glob("source.*") if path.is_file())
    return candidates[0] if candidates else None


def _safe_filename_stem(value: str | None, fallback: str = "transcript") -> str:
    raw_stem = Path(value or fallback).stem or fallback
    safe_stem = "".join(
        ch if ch.isalnum() or ch in {" ", "-", "_", "."} else "_"
        for ch in raw_stem
    ).strip(" ._")
    return (safe_stem or fallback)[:96]


def _format_backup_timestamp(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_edited_transcript_backup(transcript: str, segments: list[dict[str, Any]]) -> str:
    usable_segments = [
        segment for segment in segments
        if isinstance(segment, dict) and str(segment.get("text") or "").strip()
    ]
    if not usable_segments:
        return transcript.rstrip() + "\n"
    lines = [
        f"[{_format_backup_timestamp(segment.get('start'))}] {str(segment.get('text') or '').strip()}"
        for segment in usable_segments
    ]
    return "\n".join(lines).rstrip() + "\n"


def _write_edited_transcript_backup(task_id: str, result: dict[str, Any]) -> Path:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback=task_id or "transcript")
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _edited_transcript_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edited.txt"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    content = _format_edited_transcript_backup(
        str(result.get("transcript_text") or ""),
        _sanitize_edit_segments(result.get("segments")),
    )
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def _sanitize_edit_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    allowed_keys = {
        "index",
        "start",
        "end",
        "before",
        "after",
        "previous_before",
        "next_before",
        "previous_after",
        "next_after",
        "created_at",
    }
    for item in value[:500]:
        if not isinstance(item, dict):
            continue
        record: dict[str, Any] = {}
        for key in allowed_keys:
            if key not in item:
                continue
            raw = item.get(key)
            if key in {"index"}:
                try:
                    record[key] = int(raw)
                except (TypeError, ValueError):
                    record[key] = 0
            elif key in {"start", "end"}:
                try:
                    record[key] = float(raw)
                except (TypeError, ValueError):
                    record[key] = 0.0
            else:
                record[key] = str(raw or "")[:4000]
        if str(record.get("before") or "").strip() != str(record.get("after") or "").strip():
            records.append(record)
    return records


def _write_transcript_edit_records_backup(task_id: str, result: dict[str, Any], records: list[dict[str, Any]]) -> Path:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback=task_id or "transcript")
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _transcript_edit_records_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edit_records.json"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "task_id": task_id,
        "source_filename": result.get("filename") or result.get("source_filename"),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "record_count": len(records),
        "records": records,
    }
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def _wav_duration_seconds(path: Path | str) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            if frame_rate <= 0:
                return None
            return wav.getnframes() / frame_rate
    except Exception:
        return None


def _text_len(value: str | None) -> int:
    return len(value or "")


def _sanitize_edit_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    segments: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        segment: dict[str, Any] = {"text": text}
        for key in ("start", "end"):
            try:
                segment[key] = float(item.get(key) or 0)
            except (TypeError, ValueError):
                segment[key] = 0.0
        if item.get("speaker"):
            segment["speaker"] = str(item.get("speaker"))
        segments.append(segment)
    return segments


def _metadata(**values: Any) -> dict[str, Any]:
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        **{k: v for k, v in values.items() if v is not None},
    }


def _package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


@lru_cache(maxsize=1)
def _ffmpeg_version() -> str | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        completed = subprocess.run(
            [ffmpeg, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    first_line = (completed.stdout or completed.stderr or "").splitlines()
    return first_line[0][:160] if first_line else None


@lru_cache(maxsize=1)
def _runtime_context_metadata() -> dict[str, Any]:
    return _metadata(
        runtime_os=platform.system(),
        runtime_machine=platform.machine(),
        runtime_cpu_count=os.cpu_count(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        faster_whisper_version=_package_version("faster-whisper"),
        ctranslate2_version=_package_version("ctranslate2"),
        ffmpeg_version=_ffmpeg_version(),
    )


def _stt_realtime_factor(stt_elapsed_seconds: float | None, duration_seconds: float | None) -> float | None:
    if not stt_elapsed_seconds or not duration_seconds or duration_seconds <= 0:
        return None
    return max(round(stt_elapsed_seconds / duration_seconds, 4), 0.0001)


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
            **_runtime_context_metadata(),
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
    note_mode: Optional[str] = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    provider_name = (ai_provider or "").strip()
    resolved_openai_key = resolve_secret(openai_api_key, "openai_api_key")
    resolved_deepseek_key = resolve_secret(deepseek_api_key, "deepseek_api_key")
    if not provider_name and resolved_openai_key:
        provider_name = "openai"
    if provider_name:
        kwargs["provider"] = provider_name
    if resolved_deepseek_key:
        k = resolved_deepseek_key
        kwargs["api_key"] = k
    if resolved_openai_key and provider_name.lower() == "openai":
        k = resolved_openai_key
        kwargs["api_key"] = k
    if (m := (ai_model or "").strip()):
        kwargs["model"] = m
    if (sp := (system_prompt or "").strip()):
        kwargs["system_prompt"] = sp
    if (nm := (note_mode or "").strip()):
        kwargs["note_mode"] = nm
    return kwargs


def _cleanup_payload(cleanup_result: Any) -> dict[str, Any]:
    return {
        "applied_count": cleanup_result.applied_count,
        "removed_segment_count": cleanup_result.removed_segment_count,
        "raw_length": cleanup_result.raw_length,
        "cleaned_length": cleanup_result.cleaned_length,
        "issues": [asdict(item) for item in cleanup_result.issues[:20]],
        "issue_count": len(cleanup_result.issues),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "runtime": _runtime_context_metadata(),
    }


@app.get("/credentials/status")
def get_credentials_status() -> dict[str, Any]:
    return credential_status()


@app.get("/speaker-diarization/status")
def get_speaker_diarization_status() -> dict[str, Any]:
    return diarization_status()


@app.post("/credentials")
def update_credentials(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    allowed = {"deepseek_api_key", "openai_api_key", "lark_app_id", "lark_app_secret", "pyannote_auth_token"}
    return save_sensitive_settings({k: v for k, v in payload.items() if k in allowed})


@app.get("/jobs")
def get_jobs(limit: int = 50) -> dict[str, Any]:
    return {"jobs": list_jobs(limit=limit)}


@app.get("/jobs/{task_id}")
def get_job_detail(task_id: str) -> dict[str, Any]:
    job = get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/jobs/{task_id}/transcript")
def update_job_transcript(task_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    job = get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = dict(job.get("result") or {})
    transcript = payload.get("transcript_text")
    if not isinstance(transcript, str):
        raise HTTPException(status_code=400, detail="transcript_text is required")
    max_chars = int(os.environ.get("FLUENTFLOW_MAX_TRANSCRIPT_EDIT_CHARS", "1000000"))
    if len(transcript) > max_chars:
        raise HTTPException(status_code=413, detail=f"Transcript edit is too large: {len(transcript)} chars")

    segments = _sanitize_edit_segments(payload.get("segments"))
    edit_records = _sanitize_edit_records(payload.get("edit_records"))
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
        backup_path = _write_edited_transcript_backup(task_id, result)
        edit_records_path = _write_transcript_edit_records_backup(task_id, result, edit_records)
    except Exception as exc:
        logger.warning("Edited transcript backup failed for %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Edited transcript backup failed") from exc

    result.update({
        "edited_transcript_path": str(backup_path),
        "edited_transcript_saved_at": edited_at,
        "transcript_edit_records_path": str(edit_records_path),
    })
    updated = update_job_result(task_id, result)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": updated, "result": updated.get("result")}


@app.get("/jobs/{task_id}/events")
async def stream_job_events(task_id: str, since: int = 0) -> StreamingResponse:
    job = get_job(task_id)
    if not job and not await JOB_EVENTS.has_running_task(task_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/jobs/{task_id}/source")
def download_job_source(task_id: str) -> FileResponse:
    source = _find_source_file(task_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path=str(source), filename=source.name)


@app.get("/hotword-libraries", include_in_schema=False)
def removed_hotword_libraries() -> None:
    """Legacy endpoint kept only to avoid the SPA fallback masking removal."""
    raise HTTPException(status_code=410, detail="Built-in hotword libraries have been removed")


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
    note_mode: Optional[str] = Form(None),
    skip_summary: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    stt_speed: Optional[str] = Form(None),
    stt_language: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
    task_id: Optional[str] = Form(None),
    source_last_modified_ms: Optional[str] = Form(None),
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
    content = await file.read()
    source_file_size_mb = _file_size_mb(len(content))
    max_upload_mb = _max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
    source_fingerprint = _source_fingerprint(content, source_filename)
    in_path = _persist_source_file(task_id_value, suffix, content)

    log_event(
        task_id=task_id_value,
        event_name="source_imported",
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        stage="import",
        success=True,
        metadata=_metadata(
            route="/process",
            source_fingerprint=source_fingerprint,
            source_last_modified_ms=source_last_modified_ms,
        ),
    )
    upsert_job(
        task_id=task_id_value,
        status="running",
        stage="import",
        progress=0,
        source_type=source_type,
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
        metadata={"source_fingerprint": source_fingerprint},
    )

    loop = asyncio.get_event_loop()
    model_size = (stt_model or "").strip() or "medium"
    if model_size in {"tiny", "base", "small"}:
        model_size = "medium"
    speed_profile = (stt_speed or "").strip() or "balanced"
    language = (stt_language or "").strip() or "auto"
    diarization_requested = _truthy_form(speaker_diarization)

    async def event_stream() -> AsyncGenerator[str, None]:
        current_stage = "import"
        duration_sec: float | None = None
        duration_estimate_sec: float | None = None
        transcript_text = ""
        summary_md = ""
        summary_status: str | None = None
        lark_success: bool | None = None
        stt_process = None
        stt_queue = None
        try:
            # ── Stage 1: Audio extraction ──────────────────────
            current_stage = "audio"
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=5)
            yield _sse({"stage": "audio", "progress": 5})
            audio_started_at = time.perf_counter()
            out_audio = await loop.run_in_executor(
                None, lambda: extract_stt_wav(in_path, output_path=Path(td) / "stt.wav")
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
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=20)
            yield _sse({"stage": "audio", "progress": 20})

            # ── Stage 2: STT transcription ─────────────────────
            current_stage = "stt"
            upsert_job(task_id=task_id_value, status="running", stage="stt", progress=22)
            yield _sse({"stage": "stt", "progress": 22, "stt_progress": 0, "stt_status": "starting"})

            duration_estimate_sec = _wav_duration_seconds(out_audio)
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

            stt_started_at = time.perf_counter()
            stt_process, stt_queue = start_transcription_process(
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
                for message in drain_queue(stt_queue):
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
                    for message in drain_queue(stt_queue):
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
                    upsert_job(
                        task_id=task_id_value,
                        status="running",
                        stage="stt",
                        progress=round(latest_progress, 1),
                        metadata={
                            "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                            "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                            "stt_elapsed_seconds": round(now - stt_started_at, 1),
                            "stt_status": progress_state.get("stt_status"),
                        },
                    )
                    yield _sse({
                        "stage": "stt",
                        "progress": round(latest_progress, 1),
                        "stt_progress": round(float(progress_state.get("stt_progress") or 0), 4),
                        "transcribed_seconds": round(float(progress_state.get("transcribed_seconds") or 0), 1),
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                    })
            if stt_process is not None:
                stt_process.join(timeout=2)
            tr = stt_result
            stt_elapsed_sec = time.perf_counter() - stt_started_at
            upsert_job(
                task_id=task_id_value,
                status="running",
                stage="stt",
                progress=60,
                metadata={
                    "stt_progress": 1,
                    "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                },
            )
            yield _sse({
                "stage": "stt",
                "progress": 60,
                "stt_progress": 1,
                "transcribed_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
            })

            duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
            stt_realtime_factor = _stt_realtime_factor(stt_elapsed_sec, duration_sec)
            transcript_text = tr.text
            log_event(
                task_id=task_id_value,
                event_name="stt_completed",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                stage="stt",
                duration_seconds=round(stt_elapsed_sec, 3),
                success=True,
                metadata=_metadata(
                    **_runtime_context_metadata(),
                    route="/process",
                    source_fingerprint=source_fingerprint,
                    stt_model=model_size,
                    stt_speed=speed_profile,
                    stt_language=language,
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
                "filename": file.filename,
                "source_file_available": True,
            }
            cleanup_started_at = time.perf_counter()
            cleanup_result = clean_repeated_transcript(tr.segments)
            if cleanup_result.applied_count > 0:
                log_event(
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
                    metadata=_metadata(
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
                {"start": s.start, "end": s.end, "text": s.text}
                for s in tr.segments
            ]
            speaker_payload: dict[str, Any] = {
                "requested": diarization_requested,
                "available": diarization_status()["available"],
                "applied": False,
            }
            if diarization_requested:
                diarization_started_at = time.perf_counter()
                try:
                    turns = await loop.run_in_executor(None, lambda: diarize_audio(out_audio))
                    segments_payload = assign_speakers_to_segments(segments_payload, turns)
                    speaker_payload.update({
                        "applied": True,
                        "speaker_count": len({turn.speaker for turn in turns}),
                        "turn_count": len(turns),
                    })
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        duration_seconds=round(time.perf_counter() - diarization_started_at, 3),
                        success=True,
                        metadata=_metadata(route="/process", speaker_count=speaker_payload["speaker_count"]),
                    )
                except Exception as exc:
                    error_reason = str(exc)
                    speaker_payload.update({
                        "applied": False,
                        "error_reason": error_reason,
                    })
                    logger.warning("Speaker diarization skipped for %s: %s", task_id_value, error_reason)
                    log_event(
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
                        metadata=_metadata(route="/process", failure_scope="optional_speaker_diarization"),
                    )
            base_result.update({
                "task_id": task_id_value,
                "filename": file.filename,
                "transcript_text": transcript_text,
                "raw_transcript_text": tr.text,
                "cleaned_transcript_text": cleanup_result.cleaned_text,
                "transcript_text_preview": transcript_text[:200],
                "summary_markdown": "",
                "audio_duration_seconds": round(duration_sec, 1),
                "stt_elapsed_seconds": round(stt_elapsed_sec, 1),
                "stt_realtime_factor": stt_realtime_factor,
                "stt_model": model_size,
                "stt_speed": speed_profile,
                "stt_language": language,
                "detected_language": tr.language,
                "source_fingerprint": source_fingerprint,
                "segments": segments_payload,
                "speaker_diarization": speaker_payload,
                "cleaned_segments": list(cleanup_result.cleaned_segments),
                "raw_segments": raw_segments_payload,
                "transcript_cleanup": _cleanup_payload(cleanup_result),
                "status": "transcript_ready",
                "source": source_type,
                "summary_skipped": summary_disabled,
            })
            current_stage = "transcript_ready"
            log_event(
                task_id=task_id_value,
                event_name="transcript_ready",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(duration_sec, 1),
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                stage="transcript_ready",
                success=True,
                metadata=_metadata(route="/process", source_fingerprint=source_fingerprint),
            )
            upsert_job(
                task_id=task_id_value,
                status="running",
                stage="transcript_ready",
                progress=60,
                result=base_result,
                summary_status="pending",
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
                    transcript_length=_text_len(transcript_text),
                    stage="summary",
                    success=True,
                    metadata=_metadata(route="/process", reason="transcript_only_mode"),
                )
                result: dict[str, Any] = {
                    **base_result,
                    "status": "completed",
                }
                upsert_job(
                    task_id=task_id_value,
                    status="completed",
                    stage="done",
                    progress=100,
                    result=result,
                    summary_status=summary_status,
                )
                _log_task_completed(
                    task_id=task_id_value,
                    started_at=task_started_at,
                    final_status="completed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
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
            upsert_job(task_id=task_id_value, status="running", stage="summary", progress=62)
            yield _sse({"stage": "summary", "progress": 62})

            summary_error: str | None = None
            summary_result = None
            summary_started_at = time.perf_counter()
            try:
                kwargs = _ai_kwargs(
                    deepseek_api_key=deepseek_api_key,
                    openai_api_key=openai_api_key,
                    ai_provider=ai_provider,
                    ai_model=ai_model,
                    system_prompt=system_prompt,
                    note_mode=note_mode,
                )
                summary_result = await loop.run_in_executor(
                    None,
                    lambda: summarize_transcript_with_metadata(transcript_text, **kwargs),
                )
                summary_md = summary_result.markdown
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
                    transcript_length=_text_len(transcript_text),
                    summary_length=_text_len(summary_md),
                    stage="summary",
                    duration_seconds=round(time.perf_counter() - summary_started_at, 3),
                    success=True,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                        requested_note_mode=summary_result.requested_mode,
                        resolved_note_mode=summary_result.resolved_mode,
                        note_mode_chunk_count=summary_result.chunk_count,
                        note_mode_transcript_length=summary_result.transcript_length,
                        coverage_checked=summary_result.coverage_checked,
                        coverage_revision_used=summary_result.coverage_revision_used,
                    ),
                )
            except Exception as exc:
                logger.warning("AI summarization failed: %s", exc)
                summary_error = str(exc)
                summary_md = ""
                summary_status = "failed"
                summary_elapsed_sec = time.perf_counter() - summary_started_at
                log_event(
                    task_id=task_id_value,
                    event_name="summary_failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    stage="summary",
                    duration_seconds=round(summary_elapsed_sec, 3),
                    success=False,
                    error_reason=summary_error,
                    metadata=_metadata(
                        route="/process",
                        ai_provider=(ai_provider or "").strip() or None,
                        ai_model=(ai_model or "").strip() or None,
                        requested_note_mode=(note_mode or "").strip() or None,
                    ),
                )
                result = {
                    **base_result,
                    "summary_markdown": "",
                    "summary_error": summary_error,
                    "summary_status": "failed",
                    "status": "summary_failed",
                }
                upsert_job(
                    task_id=task_id_value,
                    status="failed",
                    stage="summary",
                    progress=88,
                    result=result,
                    summary_status=summary_status,
                    error_reason=summary_error,
                )
                _log_task_completed(
                    task_id=task_id_value,
                    started_at=task_started_at,
                    final_status="failed",
                    source_type=source_type,
                    source_filename=source_filename,
                    source_duration_seconds=round(duration_sec, 1),
                    source_file_size_mb=source_file_size_mb,
                    transcript_length=_text_len(transcript_text),
                    summary_length=0,
                    summary_status=summary_status,
                    lark_requested=do_lark,
                    lark_success=False if do_lark else None,
                    completion_reason="summary_failed",
                )
                yield _sse({"stage": "done", "progress": 100, "result": result})
                return

            upsert_job(task_id=task_id_value, status="running", stage="summary", progress=88)
            yield _sse({"stage": "summary", "progress": 88})

            # ── Build result ───────────────────────────────────
            result: dict[str, Any] = {
                **base_result,
                "summary_markdown": summary_md,
                "status": "completed",
            }
            if summary_result is not None:
                result.update({
                    "requested_note_mode": summary_result.requested_mode,
                    "resolved_note_mode": summary_result.resolved_mode,
                    "note_mode_chunk_count": summary_result.chunk_count,
                })

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
                if (lark_id := resolve_secret(lark_app_id, "lark_app_id")):
                    lark_kwargs["app_id"] = lark_id
                if (lark_secret := resolve_secret(lark_app_secret, "lark_app_secret")):
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
                    transcript_length=_text_len(transcript_text),
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
                        transcript_length=_text_len(transcript_text),
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
                        transcript_length=_text_len(transcript_text),
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
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
            )
            upsert_job(
                task_id=task_id_value,
                status="completed",
                stage="done",
                progress=100,
                result=result,
                summary_status=summary_status,
            )
            yield _sse({"stage": "done", "progress": 100, "result": result})

        except asyncio.CancelledError:
            logger.info("Processing stream cancelled by client at stage=%s", current_stage)
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
            source_duration_for_cancel = duration_sec or duration_estimate_sec
            _log_task_completed(
                task_id=task_id_value,
                started_at=task_started_at,
                final_status="cancelled",
                source_type=source_type,
                source_filename=source_filename,
                source_duration_seconds=round(source_duration_for_cancel, 1) if source_duration_for_cancel is not None else None,
                source_file_size_mb=source_file_size_mb,
                transcript_length=_text_len(transcript_text),
                summary_length=_text_len(summary_md),
                summary_status=summary_status,
                lark_requested=do_lark,
                lark_success=lark_success,
                completion_reason="client_disconnect",
            )
            upsert_job(
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
            logger.exception("Processing failed")
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
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
            upsert_job(
                task_id=task_id_value,
                status="failed",
                stage=current_stage,
                progress=0,
                source_type=source_type,
                source_filename=source_filename,
                source_file_size_mb=source_file_size_mb,
                summary_status=summary_status,
                error_reason=str(exc),
            )
            yield _sse({"stage": "error", "progress": 0, "error": str(exc)})
        finally:
            if stt_process is not None and stt_process.is_alive():
                terminate_process(stt_process)
            if stt_queue is not None:
                try:
                    stt_queue.close()
                    stt_queue.join_thread()
                except Exception:
                    pass
            shutil.rmtree(td, ignore_errors=True)

    async def run_background_job() -> None:
        terminal_sent = False
        try:
            async for chunk in event_stream():
                event = _event_from_sse_chunk(chunk)
                if event is None:
                    continue
                if JobEventHub.is_terminal(event):
                    terminal_sent = True
                await JOB_EVENTS.publish(task_id_value, event)
        except asyncio.CancelledError:
            terminal_sent = True
            await JOB_EVENTS.publish(
                task_id_value,
                {"stage": "error", "progress": 0, "error": "Task cancelled"},
            )
        except Exception as exc:
            logger.exception("Background processing failed")
            await JOB_EVENTS.publish(
                task_id_value,
                {"stage": "error", "progress": 0, "error": str(exc)},
            )
        finally:
            if not terminal_sent:
                job = get_job(task_id_value)
                if job and job.get("status") in {"completed", "failed", "cancelled"}:
                    await JOB_EVENTS.publish(task_id_value, JobEventHub.event_from_job(job))

    await JOB_EVENTS.start(task_id_value, run_background_job)

    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id_value),
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
    if (v := resolve_secret(lark_app_id, "lark_app_id")):
        kwargs["app_id"] = v
    if (v := resolve_secret(lark_app_secret, "lark_app_secret")):
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
    note_mode: Optional[str] = Form(None),
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
        note_mode=note_mode,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: summarize_transcript_with_metadata(transcript, **kwargs)
        )
        md = summary_result.markdown
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
                requested_note_mode=summary_result.requested_mode,
                resolved_note_mode=summary_result.resolved_mode,
                note_mode_chunk_count=summary_result.chunk_count,
                note_mode_transcript_length=summary_result.transcript_length,
                coverage_checked=summary_result.coverage_checked,
                coverage_revision_used=summary_result.coverage_revision_used,
            ),
        )
        payload = {
            "summary_markdown": md,
            "task_id": task_id_value,
            "requested_note_mode": summary_result.requested_mode,
            "resolved_note_mode": summary_result.resolved_mode,
            "note_mode_chunk_count": summary_result.chunk_count,
        }
        existing = get_job(task_id_value)
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
        upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            source_type=source_type,
            source_filename=source_filename,
            summary_status="completed",
            result=result,
        )
        return payload
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
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="summary_regenerate",
            source_type=source_type,
            source_filename=source_filename,
            summary_status="failed",
            error_reason=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/summarize-transcript-file")
async def summarize_transcript_file(
    file: UploadFile = File(...),
    deepseek_api_key: Optional[str] = Form(None),
    openai_api_key: Optional[str] = Form(None),
    ai_provider: Optional[str] = Form(None),
    ai_model: Optional[str] = Form(None),
    note_mode: Optional[str] = Form(None),
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
    max_upload_mb = _max_upload_mb()
    if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
        )
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
    upsert_job(
        task_id=task_id_value,
        status="running",
        stage="import",
        progress=10,
        source_type="transcript_file",
        source_filename=source_filename,
        source_file_size_mb=source_file_size_mb,
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
        upsert_job(
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
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="transcript_parse",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            summary_status="failed",
            error_reason=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))

    loop = asyncio.get_event_loop()
    review_segments_input = parsed.segments or tuple(
        {"start": 0.0, "end": 0.0, "text": line}
        for line in parsed.text.splitlines()
        if line.strip()
    )
    cleanup_started_at = time.perf_counter()
    cleanup_result = clean_repeated_transcript(review_segments_input)
    if cleanup_result.applied_count > 0:
        log_event(
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
            metadata=_metadata(
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

    log_event(
        task_id=task_id_value,
        event_name="transcript_ready",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(transcript_text),
        stage="transcript_ready",
        success=True,
        metadata=_metadata(route="/summarize-transcript-file", segment_count=len(parsed.segments)),
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
        "segments": segments_payload,
        "cleaned_segments": list(cleanup_result.cleaned_segments) if parsed.segments else [],
        "raw_segments": raw_segments_payload,
        "transcript_cleanup": _cleanup_payload(cleanup_result),
        "status": "transcript_ready",
        "source": "transcript_file",
        "summary_skipped": _truthy_form(skip_summary),
    }
    upsert_job(
        task_id=task_id_value,
        status="running",
        stage="transcript_ready",
        progress=60,
        result=base_result,
        summary_status="pending",
    )

    if _truthy_form(skip_summary):
        log_event(
            task_id=task_id_value,
            event_name="summary_skipped",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
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
            transcript_length=_text_len(transcript_text),
            summary_length=0,
            summary_status="skipped",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_skipped",
        )
        result = {**base_result, "status": "completed", "summary_skipped": True}
        upsert_job(
            task_id=task_id_value,
            status="completed",
            stage="done",
            progress=100,
            result=result,
            summary_status="skipped",
        )
        return result

    kwargs = _ai_kwargs(
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        system_prompt=system_prompt,
        note_mode=note_mode,
    )
    started_at = time.perf_counter()
    try:
        summary_result = await loop.run_in_executor(
            None, lambda: summarize_transcript_with_metadata(transcript_text, **kwargs)
        )
        summary_md = summary_result.markdown
        if not summary_md.strip():
            raise ValueError("AI summarization returned empty result")
        log_event(
            task_id=task_id_value,
            event_name="summary_completed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_duration_seconds=round(parsed.duration, 1),
            source_file_size_mb=source_file_size_mb,
            transcript_length=_text_len(transcript_text),
            summary_length=_text_len(summary_md),
            stage="summary",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
            metadata=_metadata(
                route="/summarize-transcript-file",
                ai_provider=(ai_provider or "").strip() or None,
                ai_model=(ai_model or "").strip() or None,
                requested_note_mode=summary_result.requested_mode,
                resolved_note_mode=summary_result.resolved_mode,
                note_mode_chunk_count=summary_result.chunk_count,
                note_mode_transcript_length=summary_result.transcript_length,
                coverage_checked=summary_result.coverage_checked,
                coverage_revision_used=summary_result.coverage_revision_used,
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
            transcript_length=_text_len(transcript_text),
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
            transcript_length=_text_len(transcript_text),
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
            transcript_length=_text_len(transcript_text),
            summary_status="failed",
            lark_requested=False,
            lark_success=None,
            completion_reason="summary_failed",
        )
        failed_result = {
            **base_result,
            "status": "summary_failed",
            "summary_status": "failed",
            "summary_error": str(exc),
        }
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="summary",
            progress=88,
            result=failed_result,
            summary_status="failed",
            error_reason=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc))

    result = {
        **base_result,
        "summary_markdown": summary_md,
        "status": "completed",
        "source": "transcript_file",
        "summary_skipped": False,
        "requested_note_mode": summary_result.requested_mode,
        "resolved_note_mode": summary_result.resolved_mode,
        "note_mode_chunk_count": summary_result.chunk_count,
    }
    _log_task_completed(
        task_id=task_id_value,
        started_at=task_started_at,
        final_status="completed",
        source_type="transcript_file",
        source_filename=source_filename,
        source_duration_seconds=round(parsed.duration, 1),
        source_file_size_mb=source_file_size_mb,
        transcript_length=_text_len(transcript_text),
        summary_length=_text_len(summary_md),
        summary_status="completed",
        lark_requested=False,
        lark_success=None,
    )
    upsert_job(
        task_id=task_id_value,
        status="completed",
        stage="done",
        progress=100,
        result=result,
        summary_status="completed",
    )
    return result


@app.post("/events")
async def record_client_event(payload: dict[str, Any] = Body(...)):
    """Record explicit client-side button events without storing user content."""
    event_name = str(payload.get("event_name") or "")
    if event_name not in CLIENT_EVENT_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event_name}")
    task_id_value = str(payload.get("task_id") or "").strip() or _new_task_id()
    raw_metadata = payload.get("metadata")
    allowed_client_metadata = (
        {k: raw_metadata.get(k) for k in ("format", "trigger") if k in raw_metadata}
        if isinstance(raw_metadata, dict)
        else {}
    )
    client_metadata = _metadata(**allowed_client_metadata)
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
        await JOB_EVENTS.cancel(task_id_value)
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
                **_runtime_context_metadata(),
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


# Serve frontend assets and let direct client-side routes fall back to index.
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
API_ROUTE_PREFIXES = {
    "credentials",
    "events",
    "export-lark",
    "health",
    "hotword-libraries",
    "jobs",
    "process",
    "regenerate-summary",
    "speaker-diarization",
    "summarize-transcript-file",
}

if (FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="frontend-assets")


@app.get("/", include_in_schema=False)
def serve_frontend_index() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index not found")
    return FileResponse(str(FRONTEND_INDEX))


@app.get("/{client_path:path}", include_in_schema=False)
def serve_frontend_route(client_path: str) -> FileResponse:
    first_segment = (client_path or "").split("/", 1)[0]
    if first_segment in API_ROUTE_PREFIXES or "." in first_segment:
        raise HTTPException(status_code=404, detail="Not Found")
    return serve_frontend_index()


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
