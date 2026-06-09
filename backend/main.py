"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes:
  GET  /health   – liveness check
  POST /process  – upload video/audio, run STT + summarize, optional Lark export
                   returns Server-Sent Events for real-time progress
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib.metadata
import json
import logging
import mimetypes
import os
import platform
import queue as thread_queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import wave
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
import urllib.error
import urllib.request

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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


def _video_source_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_VIDEO_SOURCE_DIR")
    return Path(override).expanduser() if override else _project_root() / "视频文件"


def _edited_transcript_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_EDITED_TRANSCRIPT_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "edited_transcripts"


def _artifact_storage_dir() -> Path:
    override = os.environ.get("FLUENTFLOW_ARTIFACT_DIR")
    return Path(override).expanduser() if override else _project_root() / "data" / "artifacts"


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


def _configured_access_tokens() -> tuple[str, ...]:
    raw = os.environ.get("FLUENTFLOW_ACCESS_TOKENS") or os.environ.get("FLUENTFLOW_ACCESS_TOKEN") or ""
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _access_control_enabled() -> bool:
    return bool(_configured_access_tokens())


def _request_access_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = request.headers.get("x-fluentflow-access-token") or ""
    if header_token.strip():
        return header_token.strip()
    return (request.cookies.get("fluentflow_access_token") or "").strip()


def _request_has_access(request: Request) -> bool:
    tokens = _configured_access_tokens()
    if not tokens:
        return True
    supplied = _request_access_token(request)
    return bool(supplied and any(hmac.compare_digest(supplied, token) for token in tokens))


def _normalize_client_id(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    safe = "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"})
    return safe[:96] or None


def _request_client_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return _normalize_client_id(
        request.headers.get("x-fluentflow-client-id")
        or request.cookies.get("fluentflow_client_id")
    )


def _request_client_scope(request: Request | None) -> str:
    return _request_client_id(request) or "anonymous"


def _is_public_request(request: Request) -> bool:
    if request.method.upper() == "OPTIONS":
        return True
    path = request.url.path
    if path in {"/", "/health", "/auth/status", "/auth/login"}:
        return True
    if path.startswith("/assets/"):
        return True
    first_segment = (path.lstrip("/").split("/", 1)[0] or "")
    return first_segment not in API_ROUTE_PREFIXES


@app.middleware("http")
async def beta_access_middleware(request: Request, call_next):
    if not _access_control_enabled() or _is_public_request(request) or _request_has_access(request):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={
            "detail": "FluentFlow beta access code is required.",
            "access_required": True,
        },
    )

try:
    from backend.core.audio_handler import extract_compressed_mp3, extract_stt_wav
    from backend.core.local_stt import transcribe_audio, get_or_load_model
    from backend.core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
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
    from backend.core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source
except ImportError:
    from core.audio_handler import extract_compressed_mp3, extract_stt_wav
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.azure_stt import run_short_audio_smoke_test, transcribe_audio_batch
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
    from core.video_source import SavedVideoSource, VideoSourceProgress, download_video_source


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


def _max_queue_files() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_MAX_QUEUE_FILES", "5")), 1)
    except ValueError:
        return 5


def _max_media_duration_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS", "14400")), 0.0)
    except ValueError:
        return 14400.0


def _runtime_limits() -> dict[str, Any]:
    duration_limit = _max_media_duration_seconds()
    return {
        "max_upload_mb": _max_upload_mb(),
        "max_queue_files": _max_queue_files(),
        "max_media_duration_seconds": duration_limit if duration_limit > 0 else None,
        "access_control_enabled": _access_control_enabled(),
    }


def _duration_limit_error(duration_seconds: float, filename: str | None = None) -> str | None:
    limit = _max_media_duration_seconds()
    if limit <= 0 or duration_seconds <= limit:
        return None
    name = f"「{filename}」" if filename else "当前媒体"
    return (
        f"{name}时长过长：约 {duration_seconds / 60:.1f} 分钟，"
        f"当前限制为 {limit / 60:.1f} 分钟。"
    )


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


def _friendly_error_message(error: Any) -> str:
    """Convert infrastructure errors into user-facing Chinese copy."""

    raw = str(error or "").strip()
    if not raw:
        return "处理失败，但没有返回具体原因。请重试一次。"
    lowered = raw.lower()

    if "cloud transcription backend configuration is incomplete" in lowered:
        return "云端转录暂不可用：后端 Azure Speech 配置不完整。请联系产品维护者检查 Speech endpoint 和 key。"
    if "cloud transcription storage is not configured" in lowered:
        return "云端转录暂不可用：后端 Blob/SAS 存储配置缺失。请联系产品维护者检查 Azure 存储设置。"
    if "only \"standard\" subscriptions" in lowered or 'only \\"standard\\" subscriptions' in lowered or "invalidsubscription" in lowered:
        return "云端转录提交失败：当前区域的 Speech 资源不是 Batch 支持的 Standard 订阅。请检查 Azure Speech 区域和定价层。"
    if "invalidlocale" in lowered or "specified locale is not supported" in lowered:
        return "云端转录提交失败：当前音频语言不被 Azure 支持。请切换为中文/英文，或改用本地转录。"
    if "invalidmodel" in lowered or "specified model is not supported" in lowered:
        return "云端转录提交失败：当前 Azure 资源不支持所选模型。请切换云端 Batch 默认模型或改用本地转录。"
    if "diarization is currently not supported" in lowered:
        return "云端转录提交失败：当前 Azure 路线不支持说话人区分。请关闭说话人区分后重试。"
    if "eof occurred in violation of protocol" in lowered or "broken pipe" in lowered:
        return "云端上传中断：通常是网络或 Azure 边缘服务断开连接。请重试；如果文件很大，优先使用 Azure Batch 或减小音频体积。"
    if "azure blob upload failed" in lowered:
        return "云端上传到 Blob 失败。请检查 SAS URL 是否仍有效、是否允许写入，以及网络是否稳定。"
    if "queued processing request failed" in lowered:
        return "后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务并检查上传大小限制。"
    if "no position encodings are defined" in lowered:
        return "本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。"
    if "downloaded video is too large" in lowered or "file is too large" in lowered:
        return "文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。"
    if "unsupported transcript file type" in lowered:
        return "不支持这个字幕/转录文件格式。请上传 SRT、VTT、TXT 或 Markdown 文件。"
    if "unsupported file type" in lowered:
        return "不支持这个文件格式。请上传视频或音频文件。"
    if "no file uploaded" in lowered:
        return "没有收到上传文件。请重新选择文件后再试。"
    if "queued source file is missing" in lowered:
        return "后台任务找不到原始文件。文件可能已被清理，请重新上传。"
    if "暂时无法自动解析这个视频链接" in raw:
        return "暂时无法自动解析这个视频链接。请换一个分享链接，或直接上传视频文件。"
    if "没有识别到视频链接" in raw:
        return "没有识别到视频链接。请粘贴完整的分享文本或视频 URL。"
    if "视频下载失败" in raw or "视频文件过大" in raw:
        return raw
    return raw


def _path_size_mb(path: Path | str) -> float | None:
    try:
        return _file_size_mb(Path(path).stat().st_size)
    except OSError:
        return None


def _source_fingerprint(content: bytes, filename: str | None = None) -> dict[str, Any]:
    """Return a content fingerprint for comparing reruns without storing content."""
    return {
        "algorithm": "sha256",
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_filename": filename,
        "source_size_bytes": len(content),
    }


def _source_fingerprint_for_path(path: Path | str, filename: str | None = None) -> dict[str, Any]:
    hasher = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    return {
        "algorithm": "sha256",
        "sha256": hasher.hexdigest(),
        "source_filename": filename,
        "source_size_bytes": size,
    }


def _persist_source_file(task_id: str, suffix: str, content: bytes) -> Path:
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix or '.bin'}"
    target.write_bytes(content)
    return target


def _copy_source_file(task_id: str, suffix: str, source_path: Path | str) -> Path:
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{suffix or '.mp4'}"
    tmp = target_dir / f".source.{uuid.uuid4().hex}.tmp"
    shutil.copyfile(str(source_path), tmp)
    tmp.replace(target)
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


def _artifact_url(task_id: str, kind: str) -> str:
    return f"/jobs/{task_id}/artifacts/{kind}"


def _artifact_filename(result: dict[str, Any], suffix: str) -> str:
    stem = _safe_filename_stem(result.get("filename") or result.get("source_filename"), fallback="transcript")
    return f"{stem}{suffix}"


def _format_subtitle_timestamp(seconds: Any, *, separator: str) -> str:
    try:
        value = max(0.0, float(seconds))
    except (TypeError, ValueError):
        value = 0.0
    total = int(value)
    millis = int(round((value - total) * 1000))
    if millis >= 1000:
        total += 1
        millis -= 1000
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _format_srt(segments: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_subtitle_timestamp(segment.get("start"), separator=",")
        end = _format_subtitle_timestamp(segment.get("end"), separator=",")
        blocks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks).rstrip() + ("\n" if blocks else "")


def _format_vtt(segments: list[dict[str, Any]]) -> str:
    blocks = ["WEBVTT\n"]
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_subtitle_timestamp(segment.get("start"), separator=".")
        end = _format_subtitle_timestamp(segment.get("end"), separator=".")
        blocks.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(blocks).rstrip() + "\n"


def _write_text_artifact(task_id: str, kind: str, filename: str, content: str) -> dict[str, Any]:
    target_dir = _artifact_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    tmp = target_dir / f".{filename}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {
        "kind": kind,
        "filename": filename,
        "url": _artifact_url(task_id, kind),
        "size_bytes": path.stat().st_size,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _write_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    transcript = str(result.get("transcript_text") or "").strip()
    segments = _sanitize_edit_segments(result.get("segments"))
    if transcript:
        artifacts["transcript_txt"] = _write_text_artifact(
            task_id,
            "transcript_txt",
            _artifact_filename(result, ".txt"),
            transcript.rstrip() + "\n",
        )
    if segments:
        artifacts["transcript_srt"] = _write_text_artifact(
            task_id,
            "transcript_srt",
            _artifact_filename(result, ".srt"),
            _format_srt(segments),
        )
        artifacts["transcript_vtt"] = _write_text_artifact(
            task_id,
            "transcript_vtt",
            _artifact_filename(result, ".vtt"),
            _format_vtt(segments),
        )
    summary = str(result.get("summary_markdown") or "").strip()
    if summary:
        artifacts["summary_md"] = _write_text_artifact(
            task_id,
            "summary_md",
            _artifact_filename(result, "_summary.md"),
            summary.rstrip() + "\n",
        )
    return artifacts


def _attach_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        artifacts = _write_result_artifacts(task_id, result)
    except Exception as exc:
        logger.warning("Result artifact write failed for %s: %s", task_id, exc)
        return result
    if not artifacts:
        return result
    next_result = dict(result)
    next_result["artifacts"] = artifacts
    return next_result


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


def _media_duration_seconds(path: Path | str) -> float | None:
    wav_duration = _wav_duration_seconds(path)
    if wav_duration is not None:
        return wav_duration
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = float((result.stdout or "").strip())
        return value if value > 0 else None
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


def _normalize_stt_provider(value: str | None) -> str:
    provider = (value or "").strip().lower().replace("-", "_")
    if provider in {"azure", "azure_batch", "azure_blob", "azure_speech_batch", "azure_fast", "azure_speech"}:
        return "azure_batch"
    return "local"


def _stt_provider_label(provider: str) -> str:
    if provider == "azure_batch":
        return "Cloud Transcription"
    return "faster-whisper"


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
    stt_provider: str | None = None,
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
            stt_provider=stt_provider,
            stt_provider_label=_stt_provider_label(stt_provider) if stt_provider else None,
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


_TRANSCRIPTION_QUEUE: thread_queue.Queue[dict[str, Any]] = thread_queue.Queue()
_QUEUE_THREAD: threading.Thread | None = None
_QUEUE_LOCK = threading.Lock()
_QUEUED_TASK_IDS: set[str] = set()
_QUEUE_EVENT_LOOP: asyncio.AbstractEventLoop | None = None


def _queue_timeout_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_QUEUE_PROCESS_TIMEOUT_SECONDS", "86400")), 60.0)
    except ValueError:
        return 86400.0


def _queue_base_url_from_request(request: Request | None = None) -> str:
    configured = (os.environ.get("FLUENTFLOW_SELF_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    if request is not None:
        return str(request.base_url).rstrip("/")
    return "http://127.0.0.1:8000"


def _publish_job_event_from_thread(task_id: str, event: dict[str, Any]) -> None:
    loop = _QUEUE_EVENT_LOOP
    if not loop or loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(JOB_EVENTS.publish(task_id, event), loop)
    except Exception:
        logger.debug("Queue event publish failed for %s", task_id, exc_info=True)


def _multipart_process_body(
    *,
    fields: dict[str, Any],
    file_path: Path,
    filename: str,
) -> tuple[bytes, str]:
    boundary = f"----FluentFlowQueue{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value)
        if text == "":
            continue
        chunks.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
            text.encode("utf-8"),
            b"\r\n",
        ])
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    chunks.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="file"; filename="{Path(filename).name}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _enqueue_transcription_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    if not task_id:
        return
    with _QUEUE_LOCK:
        if task_id in _QUEUED_TASK_IDS:
            return
        _QUEUED_TASK_IDS.add(task_id)
        _TRANSCRIPTION_QUEUE.put(dict(item))
        _ensure_queue_worker_started_locked()


def _ensure_queue_worker_started_locked() -> None:
    global _QUEUE_THREAD
    if _QUEUE_THREAD and _QUEUE_THREAD.is_alive():
        return
    _QUEUE_THREAD = threading.Thread(
        target=_queue_worker_loop,
        name="fluentflow-transcription-queue",
        daemon=True,
    )
    _QUEUE_THREAD.start()


def _queue_worker_loop() -> None:
    while True:
        item = _TRANSCRIPTION_QUEUE.get()
        task_id = str(item.get("task_id") or "")
        try:
            _run_queued_transcription(item)
        except Exception as exc:
            logger.exception("Queued transcription failed for %s", task_id)
            if task_id:
                friendly_error = _friendly_error_message(exc)
                upsert_job(
                    task_id=task_id,
                    status="failed",
                    client_id=_normalize_client_id(str(item.get("client_id") or "")),
                    stage="queued",
                    progress=0,
                    error_reason=friendly_error,
                )
                _publish_job_event_from_thread(
                    task_id,
                    {"stage": "error", "progress": 0, "error": friendly_error},
                )
        finally:
            if task_id:
                with _QUEUE_LOCK:
                    _QUEUED_TASK_IDS.discard(task_id)
            _TRANSCRIPTION_QUEUE.task_done()


def _run_queued_transcription(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    source_path = Path(str(item.get("source_path") or ""))
    filename = str(item.get("filename") or source_path.name or "source")
    base_url = str(item.get("base_url") or _queue_base_url_from_request()).rstrip("/")
    options = dict(item.get("options") or {})
    client_id = _normalize_client_id(str(item.get("client_id") or ""))
    if not task_id:
        raise RuntimeError("Queued task is missing task_id")
    if not source_path.is_file():
        raise RuntimeError("Queued source file is missing")

    job = get_job(task_id)
    if job and job.get("status") in {"completed", "failed", "cancelled"}:
        return

    fields = {
        **options,
        "task_id": task_id,
        "title": options.get("title") or Path(filename).stem,
    }
    body, content_type = _multipart_process_body(fields=fields, file_path=source_path, filename=filename)
    headers = {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Accept": "text/event-stream",
    }
    if client_id:
        headers["X-FluentFlow-Client-Id"] = client_id
    tokens = _configured_access_tokens()
    if tokens:
        headers["X-FluentFlow-Access-Token"] = tokens[0]
    request = urllib.request.Request(
        f"{base_url}/process",
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=_queue_timeout_seconds()) as response:
            while response.read(64 * 1024):
                pass
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Queued processing request failed: HTTP {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Queued processing request failed: {exc.reason}") from exc


def _queue_options_from_form(
    *,
    export_to_lark: Optional[str],
    lark_via_cli: Optional[str],
    title: Optional[str],
    folder_token: Optional[str],
    deepseek_api_key: Optional[str],
    openai_api_key: Optional[str],
    ai_provider: Optional[str],
    ai_model: Optional[str],
    note_mode: Optional[str],
    skip_summary: Optional[str],
    stt_model: Optional[str],
    stt_speed: Optional[str],
    stt_language: Optional[str],
    stt_provider: Optional[str],
    azure_speech_key: Optional[str],
    azure_speech_endpoint: Optional[str],
    azure_blob_container_sas_url: Optional[str],
    speaker_diarization: Optional[str],
    lark_app_id: Optional[str],
    lark_app_secret: Optional[str],
    system_prompt: Optional[str],
) -> dict[str, str]:
    raw: dict[str, Optional[str]] = {
        "export_to_lark": export_to_lark,
        "lark_via_cli": lark_via_cli,
        "title": title,
        "folder_token": folder_token,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "note_mode": note_mode,
        "skip_summary": skip_summary,
        "stt_model": stt_model,
        "stt_speed": stt_speed,
        "stt_language": stt_language,
        "stt_provider": stt_provider,
        "azure_speech_endpoint": azure_speech_endpoint,
        "speaker_diarization": speaker_diarization,
        "system_prompt": system_prompt,
    }
    return {key: value.strip() for key, value in raw.items() if isinstance(value, str) and value.strip()}


def _queue_options_from_mapping(payload: dict[str, Any] | None) -> dict[str, str]:
    allowed = {
        "export_to_lark",
        "lark_via_cli",
        "title",
        "folder_token",
        "ai_provider",
        "ai_model",
        "note_mode",
        "skip_summary",
        "stt_model",
        "stt_speed",
        "stt_language",
        "stt_provider",
        "azure_speech_endpoint",
        "speaker_diarization",
        "system_prompt",
    }
    result: dict[str, str] = {}
    for key, value in (payload or {}).items():
        if key not in allowed or value is None:
            continue
        text = str(value).strip()
        if text:
            result[key] = text
    return result


def _public_video_source_metadata(saved: SavedVideoSource) -> dict[str, Any]:
    return {
        "provider": saved.provider,
        "source_url": saved.source_url,
        "video_id": saved.video_id,
        "title": saved.title,
        "filename": saved.filename,
        "file_path": saved.file_path,
        "file_url": saved.file_url,
        "metadata_path": saved.metadata_path,
        "size_bytes": saved.size_bytes,
        "downloaded_at": saved.downloaded_at,
    }


def _video_source_progress_value(progress: VideoSourceProgress) -> float:
    if progress.stage == "resolving":
        return float(progress.percent or 8)
    if progress.stage == "downloading":
        pct = progress.percent if progress.percent is not None else 0
        return 10 + max(0, min(100, float(pct))) * 0.45
    if progress.stage == "saving":
        return 58
    return 0


def _run_video_source_job(item: dict[str, Any]) -> None:
    task_id = str(item.get("task_id") or "")
    input_text = str(item.get("input") or "")
    title = str(item.get("title") or "").strip() or None
    options = dict(item.get("options") or {})
    base_url = str(item.get("base_url") or _queue_base_url_from_request())
    client_id = _normalize_client_id(str(item.get("client_id") or ""))
    if not task_id:
        return

    def on_progress(progress: VideoSourceProgress) -> None:
        upsert_job(
            task_id=task_id,
            status="running",
            client_id=client_id,
            stage=progress.stage,
            progress=_video_source_progress_value(progress),
            summary_status=progress.message,
            metadata=_metadata(
                route="/video-sources/jobs",
                queue_options=options,
                video_source_progress={
                    "message": progress.message,
                    "loaded_bytes": progress.loaded_bytes,
                    "total_bytes": progress.total_bytes,
                },
            ),
        )

    try:
        saved = download_video_source(
            input_text,
            title=title,
            video_dir=_video_source_storage_dir(),
            on_progress=on_progress,
        )
        saved_size_mb = _file_size_mb(saved.size_bytes)
        max_upload_mb = _max_upload_mb()
        if saved_size_mb is not None and saved_size_mb > max_upload_mb:
            raise RuntimeError(
                f"Downloaded video is too large: {saved_size_mb} MB. Limit is {max_upload_mb:g} MB."
            )
        source_path = Path(saved.file_path)
        target_path = _copy_source_file(task_id, ".mp4", source_path)
        source_fingerprint = _source_fingerprint_for_path(target_path, saved.filename)
        source_file_size_mb = _path_size_mb(target_path)
        metadata = _metadata(
            route="/video-sources/jobs",
            queue_options=options,
            source_path=str(target_path),
            source_fingerprint=source_fingerprint,
            video_source=_public_video_source_metadata(saved),
        )
        log_event(
            task_id=task_id,
            event_name="video_source_downloaded",
            source_type="video",
            source_filename=saved.filename,
            source_file_size_mb=source_file_size_mb,
            stage="queued",
            success=True,
            metadata=metadata,
        )
        upsert_job(
            task_id=task_id,
            status="queued",
            client_id=client_id,
            stage="queued",
            progress=0,
            source_type="video",
            source_filename=saved.filename,
            source_file_size_mb=source_file_size_mb,
            metadata=metadata,
        )
        enqueue_item = {
            "task_id": task_id,
            "source_path": str(target_path),
            "filename": saved.filename,
            "options": options,
            "base_url": base_url,
        }
        if client_id:
            enqueue_item["client_id"] = client_id
        _enqueue_transcription_job(enqueue_item)
    except Exception as exc:
        logger.exception("Video source job failed for %s", task_id)
        friendly_error = _friendly_error_message(exc)
        upsert_job(
            task_id=task_id,
            status="failed",
            client_id=client_id,
            stage="failed",
            progress=100,
            source_type="video_link",
            source_filename=title or (input_text[:80] if input_text else "video link"),
            error_reason=friendly_error,
            metadata=_metadata(
                route="/video-sources/jobs",
                queue_options=options,
                raw_error=str(exc),
            ),
        )


def _start_video_source_job(item: dict[str, Any]) -> None:
    threading.Thread(
        target=_run_video_source_job,
        args=(dict(item),),
        name=f"fluentflow-video-source-{item.get('task_id') or 'job'}",
        daemon=True,
    ).start()


def _resume_queued_transcription_jobs(base_url: str | None = None) -> None:
    for job in list_jobs(limit=200):
        status = job.get("status")
        metadata = job.get("metadata") or {}
        if status not in {"queued", "running"}:
            continue
        if not metadata.get("queue_options") or not metadata.get("source_path"):
            continue
        task_id = str(job.get("task_id") or "")
        source_path = Path(str(metadata.get("source_path") or ""))
        if not task_id or not source_path.is_file():
            continue
        upsert_job(
            task_id=task_id,
            status="queued",
            stage="queued",
            progress=0,
            metadata=metadata,
        )
        _enqueue_transcription_job({
            "task_id": task_id,
            "source_path": str(source_path),
            "filename": job.get("source_filename") or source_path.name,
            "options": metadata.get("queue_options") or {},
            "base_url": base_url or _queue_base_url_from_request(),
            "client_id": job.get("client_id"),
        })


@app.on_event("startup")
async def _startup_resume_queue() -> None:
    global _QUEUE_EVENT_LOOP
    _QUEUE_EVENT_LOOP = asyncio.get_running_loop()
    _resume_queued_transcription_jobs()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "runtime": _runtime_context_metadata(),
        "limits": _runtime_limits(),
    }


@app.get("/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    return {
        "access_required": _access_control_enabled(),
        "authenticated": (not _access_control_enabled()) or _request_has_access(request),
    }


@app.post("/auth/login")
def auth_login(
    response: Response,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    token = str(payload.get("access_token") or payload.get("token") or "").strip()
    if not _access_control_enabled():
        return {"ok": True, "access_required": False}
    if not token or not any(hmac.compare_digest(token, configured) for configured in _configured_access_tokens()):
        raise HTTPException(status_code=401, detail="Invalid access code")
    response.set_cookie(
        key="fluentflow_access_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=(os.environ.get("FLUENTFLOW_COOKIE_SECURE") or "").lower() in {"1", "true", "yes", "on"},
        samesite="lax",
    )
    return {"ok": True, "access_required": True}


@app.get("/credentials/status")
def get_credentials_status() -> dict[str, Any]:
    return credential_status()


@app.get("/speaker-diarization/status")
def get_speaker_diarization_status() -> dict[str, Any]:
    return diarization_status()


@app.post("/credentials")
def update_credentials(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    allowed = {
        "deepseek_api_key",
        "openai_api_key",
        "lark_app_id",
        "lark_app_secret",
        "pyannote_auth_token",
        "azure_speech_key",
        "azure_speech_endpoint",
        "azure_blob_container_sas_url",
    }
    return save_sensitive_settings({k: v for k, v in payload.items() if k in allowed})


@app.post("/azure-speech/smoke-test")
def azure_speech_smoke_test(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    endpoint = resolve_secret(payload.get("azure_speech_endpoint"), "azure_speech_endpoint")
    api_key = resolve_secret(payload.get("azure_speech_key"), "azure_speech_key")
    if not endpoint or not api_key:
        missing = []
        if not endpoint:
            missing.append("Speech address")
        if not api_key:
            missing.append("Speech key")
        raise HTTPException(status_code=400, detail="Azure Speech smoke test is missing " + " and ".join(missing))
    try:
        return run_short_audio_smoke_test(
            endpoint=endpoint,
            api_key=api_key,
            language=(payload.get("language") or "en-US"),
            phrase=payload.get("phrase"),
            timeout=float(payload.get("timeout") or 60),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/jobs")
def get_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    return {"jobs": list_jobs(limit=limit, client_id=_request_client_scope(request))}


@app.get("/jobs/{task_id}")
def get_job_detail(request: Request, task_id: str) -> dict[str, Any]:
    job = get_job(task_id, client_id=_request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/jobs/{task_id}/transcript")
def update_job_transcript(request: Request, task_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    client_id = _request_client_scope(request)
    job = get_job(task_id, client_id=client_id)
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
    result = _attach_result_artifacts(task_id, result)
    updated = update_job_result(task_id, result, client_id=client_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "job": updated, "result": updated.get("result")}


@app.get("/jobs/{task_id}/events")
async def stream_job_events(request: Request, task_id: str, since: int = 0) -> StreamingResponse:
    job = get_job(task_id, client_id=_request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return StreamingResponse(
        JOB_EVENTS.subscribe(task_id, since=since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/jobs/{task_id}/source")
def download_job_source(request: Request, task_id: str) -> FileResponse:
    if not get_job(task_id, client_id=_request_client_scope(request)):
        raise HTTPException(status_code=404, detail="Source file not found")
    source = _find_source_file(task_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path=str(source), filename=source.name)


@app.get("/jobs/{task_id}/artifacts/{kind}")
def download_job_artifact(request: Request, task_id: str, kind: str) -> FileResponse:
    if not get_job(task_id, client_id=_request_client_scope(request)):
        raise HTTPException(status_code=404, detail="Artifact not found")
    allowed = {
        "transcript_txt": ".txt",
        "transcript_srt": ".srt",
        "transcript_vtt": ".vtt",
        "summary_md": ".md",
    }
    suffix = allowed.get(kind)
    if not suffix:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target_dir = _artifact_storage_dir() / task_id
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Artifact not found")
    matches = sorted(path for path in target_dir.glob(f"*{suffix}") if path.is_file())
    if kind == "summary_md":
        matches = [path for path in matches if path.name.endswith("_summary.md")]
    elif kind == "transcript_txt":
        matches = [path for path in matches if not path.name.endswith("_summary.md")]
    if not matches:
        raise HTTPException(status_code=404, detail="Artifact not found")
    target = matches[0]
    return FileResponse(path=str(target), filename=target.name)


@app.get("/hotword-libraries", include_in_schema=False)
def removed_hotword_libraries() -> None:
    """Legacy endpoint kept only to avoid the SPA fallback masking removal."""
    raise HTTPException(status_code=410, detail="Built-in hotword libraries have been removed")


@app.post("/video-sources/jobs")
async def create_video_source_job(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    input_text = str(payload.get("input") or "").strip()
    title = str(payload.get("title") or "").strip()
    client_id = _request_client_scope(request)
    if not input_text:
        raise HTTPException(status_code=400, detail="缺少视频分享文本或视频链接")
    if len(input_text) > 4000:
        raise HTTPException(status_code=400, detail="分享文本过长")

    options = _queue_options_from_mapping(payload.get("options") if isinstance(payload.get("options"), dict) else {})
    task_id_value = _new_task_id()
    display_name = title or input_text[:80]
    metadata = _metadata(
        route="/video-sources/jobs",
        queue_options=options,
        video_source_input_preview=input_text[:200],
    )
    log_event(
        task_id=task_id_value,
        event_name="video_source_submitted",
        source_type="video_link",
        source_filename=display_name,
        stage="resolving",
        success=True,
        metadata=metadata,
    )
    upsert_job(
        task_id=task_id_value,
        status="running",
        client_id=client_id,
        stage="resolving",
        progress=2,
        source_type="video_link",
        source_filename=display_name,
        metadata=metadata,
    )
    _start_video_source_job({
        "task_id": task_id_value,
        "input": input_text,
        "title": title or None,
        "options": options,
        "base_url": _queue_base_url_from_request(request),
        "client_id": client_id,
    })
    return {
        "ok": True,
        "job": {
            "task_id": task_id_value,
            "status": "running",
            "stage": "resolving",
            "source_type": "video_link",
            "source_filename": display_name,
        },
    }


@app.get("/video-sources/jobs")
def list_video_source_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    jobs = [
        job for job in list_jobs(limit=200, client_id=_request_client_scope(request))
        if (job.get("metadata") or {}).get("route") == "/video-sources/jobs"
    ][:safe_limit]
    return {"jobs": jobs}


@app.post("/queue/process")
async def queue_process(
    request: Request,
    files: list[UploadFile] = File(...),
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
    stt_provider: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
    speaker_diarization: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
) -> dict[str, Any]:
    """Persist multiple media files and process them sequentially in the backend."""
    client_id = _request_client_scope(request)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    max_queue_files = _max_queue_files()
    if len(files) > max_queue_files:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files uploaded: {len(files)}. Limit is {max_queue_files}.",
        )
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower() or ".mp4"
        if not upload.filename:
            raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")
        if suffix not in ALLOWED_SUFFIXES or suffix in TRANSCRIPT_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    base_options = _queue_options_from_form(
        export_to_lark=export_to_lark,
        lark_via_cli=lark_via_cli,
        title=title if len(files) == 1 else None,
        folder_token=folder_token,
        deepseek_api_key=deepseek_api_key,
        openai_api_key=openai_api_key,
        ai_provider=ai_provider,
        ai_model=ai_model,
        note_mode=note_mode,
        skip_summary=skip_summary,
        stt_model=stt_model,
        stt_speed=stt_speed,
        stt_language=stt_language,
        stt_provider=stt_provider,
        azure_speech_key=azure_speech_key,
        azure_speech_endpoint=azure_speech_endpoint,
        azure_blob_container_sas_url=azure_blob_container_sas_url,
        speaker_diarization=speaker_diarization,
        lark_app_id=lark_app_id,
        lark_app_secret=lark_app_secret,
        system_prompt=system_prompt,
    )
    base_url = _queue_base_url_from_request(request)
    max_upload_mb = _max_upload_mb()
    queued: list[dict[str, Any]] = []
    total = len(files)
    for index, upload in enumerate(files, start=1):
        filename = upload.filename or f"source-{index}"
        suffix = Path(filename).suffix.lower() or ".mp4"
        content = await upload.read()
        source_file_size_mb = _file_size_mb(len(content))
        if source_file_size_mb is not None and source_file_size_mb > max_upload_mb:
            raise HTTPException(
                status_code=413,
                detail=f"File is too large: {source_file_size_mb} MB. Limit is {max_upload_mb:g} MB.",
            )
        task_id_value = _new_task_id()
        source_type = _source_type_for_suffix(suffix)
        source_fingerprint = _source_fingerprint(content, filename)
        source_path = _persist_source_file(task_id_value, suffix, content)
        metadata = _metadata(
            route="/queue/process",
            queue_options=base_options,
            queue_position=index,
            queue_total=total,
            source_path=str(source_path),
            source_fingerprint=source_fingerprint,
        )
        log_event(
            task_id=task_id_value,
            event_name="source_queued",
            source_type=source_type,
            source_filename=filename,
            source_file_size_mb=source_file_size_mb,
            stage="queued",
            success=True,
            metadata=metadata,
        )
        upsert_job(
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
        _enqueue_transcription_job({
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


@app.post("/process")
async def process_video(
    request: Request,
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
    stt_provider: Optional[str] = Form(None),
    azure_speech_key: Optional[str] = Form(None),
    azure_speech_endpoint: Optional[str] = Form(None),
    azure_blob_container_sas_url: Optional[str] = Form(None),
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
    client_id = _request_client_scope(request)
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
        client_id=client_id,
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
    stt_provider_value = _normalize_stt_provider(stt_provider)
    azure_cloud_provider = stt_provider_value == "azure_batch"
    diarization_requested = _truthy_form(speaker_diarization)
    azure_endpoint_value: str | None = None
    azure_key_value: str | None = None
    azure_blob_container_sas_value: str | None = None
    if azure_cloud_provider:
        azure_endpoint_value = resolve_secret(azure_speech_endpoint, "azure_speech_endpoint")
        azure_key_value = resolve_secret(azure_speech_key, "azure_speech_key")
    if stt_provider_value == "azure_batch":
        azure_blob_container_sas_value = resolve_secret(
            azure_blob_container_sas_url,
            "azure_blob_container_sas_url",
        )

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
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=5)
            yield _sse({"stage": "audio", "progress": 5})
            audio_started_at = time.perf_counter()
            if azure_cloud_provider:
                audio_output_format = "mp3"
                out_audio = await loop.run_in_executor(
                    None, lambda: extract_compressed_mp3(in_path, output_path=Path(td) / "azure_stt.mp3")
                )
            else:
                audio_output_format = "wav"
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
                metadata=_metadata(
                    route="/process",
                    stt_provider=stt_provider_value,
                    stt_provider_label=_stt_provider_label(stt_provider_value),
                    audio_output_format=audio_output_format,
                    audio_output_size_mb=_path_size_mb(out_audio),
                ),
            )
            upsert_job(task_id=task_id_value, status="running", stage="audio", progress=20)
            yield _sse({"stage": "audio", "progress": 20})

            # ── Stage 2: STT transcription ─────────────────────
            current_stage = "stt"
            upsert_job(task_id=task_id_value, status="running", stage="stt", progress=22)
            yield _sse({"stage": "stt", "progress": 22, "stt_progress": 0, "stt_status": "starting"})

            duration_estimate_sec = _media_duration_seconds(out_audio)
            if duration_estimate_sec:
                duration_error = _duration_limit_error(duration_estimate_sec, source_filename)
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

            azure_inline_limits: dict[str, Any] = {}
            stt_started_at = time.perf_counter()
            if stt_provider_value == "azure_batch":
                azure_inline_limits = {
                    "azure_batch_audio_size_mb": _path_size_mb(out_audio),
                    "azure_batch_duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                }

                def on_azure_batch_progress(status: str, metadata: dict[str, Any] | None = None) -> None:
                    progress_state["stt_status"] = status
                    if metadata:
                        azure_inline_limits.update(metadata)

                progress_state["stt_status"] = "azure_batch_uploading"
                azure_task = loop.run_in_executor(
                    None,
                    lambda: transcribe_audio_batch(
                        out_audio,
                        endpoint=azure_endpoint_value,
                        api_key=azure_key_value,
                        container_sas_url=azure_blob_container_sas_value,
                        locale=language,
                        diarization_enabled=diarization_requested,
                        display_name=f"FluentFlow {Path(file.filename).stem}",
                        progress_callback=on_azure_batch_progress,
                    ),
                )
                last_emit_at = time.perf_counter()
                while not azure_task.done():
                    await asyncio.sleep(1)
                    now = time.perf_counter()
                    if now - last_emit_at < 2:
                        continue
                    last_emit_at = now
                    upsert_job(
                        task_id=task_id_value,
                        status="running",
                        stage="stt",
                        progress=25,
                        metadata={
                            "stt_provider": stt_provider_value,
                            "stt_provider_label": _stt_provider_label(stt_provider_value),
                            **azure_inline_limits,
                            "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                            "stt_elapsed_seconds": round(now - stt_started_at, 1),
                            "stt_status": progress_state.get("stt_status"),
                        },
                    )
                    yield _sse({
                        "stage": "stt",
                        "progress": 25,
                        **azure_inline_limits,
                        "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                        "stt_elapsed_seconds": round(now - stt_started_at, 1),
                        "stt_status": progress_state.get("stt_status"),
                        "stt_provider": stt_provider_value,
                    })
                tr = azure_task.result()
            else:
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
                                "stt_provider": stt_provider_value,
                                "stt_provider_label": _stt_provider_label(stt_provider_value),
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
                            "stt_provider": stt_provider_value,
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
                    "stt_provider": stt_provider_value,
                    "stt_provider_label": _stt_provider_label(stt_provider_value),
                    **azure_inline_limits,
                    "stt_progress": 1,
                    "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                },
            )
            yield _sse({
                "stage": "stt",
                "progress": 60,
                "stt_progress": 1,
                **azure_inline_limits,
                "transcribed_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                "duration_seconds": round(duration_estimate_sec, 1) if duration_estimate_sec else None,
                "stt_provider": stt_provider_value,
            })

            duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
            stt_realtime_factor = _stt_realtime_factor(stt_elapsed_sec, duration_sec)
            transcript_text = tr.text
            if stt_provider_value == "azure_batch":
                stt_model_for_result = "azure-batch-transcription"
            else:
                stt_model_for_result = model_size
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
                    stt_provider=stt_provider_value,
                    stt_provider_label=_stt_provider_label(stt_provider_value),
                    stt_model=stt_model_for_result,
                    stt_speed=speed_profile,
                    stt_language=language,
                    **azure_inline_limits,
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
                "available": True if azure_cloud_provider else diarization_status()["available"],
                "applied": False,
            }
            if diarization_requested and azure_cloud_provider:
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
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_completed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        success=True,
                        metadata=_metadata(
                            route="/process",
                            backend=getattr(tr, "model_source", None) or "azure_speech_transcription",
                            speaker_count=len(speakers),
                        ),
                    )
                else:
                    error_reason = (
                        getattr(tr, "diarization_error", None)
                        or f"{_stt_provider_label(stt_provider_value)} did not return speaker labels"
                    )
                    speaker_payload.update({
                        "applied": False,
                        "backend": getattr(tr, "model_source", None) or "azure_speech_transcription",
                        "error_reason": error_reason,
                    })
                    log_event(
                        task_id=task_id_value,
                        event_name="speaker_diarization_failed",
                        source_type=source_type,
                        source_filename=source_filename,
                        source_duration_seconds=round(duration_sec, 1),
                        source_file_size_mb=source_file_size_mb,
                        stage="speaker_diarization",
                        success=False,
                        error_reason=error_reason,
                        metadata=_metadata(route="/process", backend=getattr(tr, "model_source", None) or "azure_speech_transcription"),
                    )
            elif diarization_requested:
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
                "stt_provider": stt_provider_value,
                "stt_provider_label": _stt_provider_label(stt_provider_value),
                "stt_model": stt_model_for_result,
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
            base_result = _attach_result_artifacts(task_id_value, base_result)
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
                result = _attach_result_artifacts(task_id_value, result)
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
                    stt_provider=stt_provider_value,
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
                summary_error = _friendly_error_message(exc)
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
                        raw_error=str(exc),
                    ),
                )
                result = {
                    **base_result,
                    "summary_markdown": "",
                    "summary_error": summary_error,
                    "summary_status": "failed",
                    "status": "summary_failed",
                }
                result = _attach_result_artifacts(task_id_value, result)
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
                    stt_provider=stt_provider_value,
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
                    result["lark_error"] = _friendly_error_message(e)
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
                        error_reason=_friendly_error_message(e),
                        export_target=export_target,
                        metadata=_metadata(route="/process", trigger="auto", doc_title=doc_title, raw_error=str(e)),
                    )

            # ── Done ───────────────────────────────────────────
            result = _attach_result_artifacts(task_id_value, result)
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
                stt_provider=stt_provider_value,
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
                stt_provider=stt_provider_value,
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
            friendly_error = _friendly_error_message(exc)
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
                error_reason=friendly_error,
                metadata=_metadata(route="/process", stt_provider=stt_provider_value, raw_error=str(exc)),
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
                stt_provider=stt_provider_value,
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
                error_reason=friendly_error,
            )
            yield _sse({"stage": "error", "progress": 0, "error": friendly_error})
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
    request: Request,
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
    client_id = _request_client_scope(request)
    if task_id and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
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
        friendly_error = _friendly_error_message(exc)
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
            error_reason=friendly_error,
            export_target=export_target,
            metadata=_metadata(route="/export-lark", trigger="manual", doc_title=resolved, raw_error=str(exc)),
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
            error_reason=friendly_error,
            metadata=_metadata(route="/export-lark", trigger="manual", raw_error=str(exc)),
        )
        raise HTTPException(status_code=500, detail=friendly_error)


@app.post("/regenerate-summary")
async def regenerate_summary(
    request: Request,
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
    client_id = _request_client_scope(request)
    if task_id and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
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
        existing = get_job(task_id_value, client_id=client_id)
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
        friendly_error = _friendly_error_message(exc)
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
            error_reason=friendly_error,
            metadata=_metadata(route="/regenerate-summary", raw_error=str(exc)),
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
            error_reason=friendly_error,
            metadata=_metadata(route="/regenerate-summary", raw_error=str(exc)),
        )
        upsert_job(
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


@app.post("/summarize-transcript-file")
async def summarize_transcript_file(
    request: Request,
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
    client_id = _request_client_scope(request)
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
        client_id=client_id,
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
        if parsed.duration:
            duration_error = _duration_limit_error(parsed.duration, source_filename)
            if duration_error:
                raise HTTPException(status_code=413, detail=duration_error)
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
        friendly_error = _friendly_error_message(exc)
        log_event(
            task_id=task_id_value,
            event_name="task_failed",
            source_type="transcript_file",
            source_filename=source_filename,
            source_file_size_mb=source_file_size_mb,
            stage="transcript_parse",
            success=False,
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
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
    base_result = _attach_result_artifacts(task_id_value, base_result)
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
        result = _attach_result_artifacts(task_id_value, result)
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
        friendly_error = _friendly_error_message(exc)
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
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
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
            error_reason=friendly_error,
            metadata=_metadata(route="/summarize-transcript-file", raw_error=str(exc)),
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
            "summary_error": friendly_error,
        }
        upsert_job(
            task_id=task_id_value,
            status="failed",
            stage="summary",
            progress=88,
            result=failed_result,
            summary_status="failed",
            error_reason=friendly_error,
        )
        raise HTTPException(status_code=500, detail=friendly_error)

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
    result = _attach_result_artifacts(task_id_value, result)
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
async def record_client_event(request: Request, payload: dict[str, Any] = Body(...)):
    """Record explicit client-side button events without storing user content."""
    event_name = str(payload.get("event_name") or "")
    if event_name not in CLIENT_EVENT_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event_name}")
    task_id_value = str(payload.get("task_id") or "").strip() or _new_task_id()
    client_id = _request_client_scope(request)
    if event_name == "task_cancelled" and not get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
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
    "auth",
    "credentials",
    "events",
    "export-lark",
    "health",
    "hotword-libraries",
    "jobs",
    "process",
    "queue",
    "regenerate-summary",
    "speaker-diarization",
    "summarize-transcript-file",
    "video-sources",
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
