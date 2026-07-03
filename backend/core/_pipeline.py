"""Media, STT, pipeline, subtitle helpers moved from server_helpers.py."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
import wave
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.core._env import (
    EVENT_SCHEMA_VERSION, APP_VERSION, INTERNAL_QUEUE_TOKEN,
    _env_truthy, _public_mode_enabled, _request_is_internal_queue,
)
from backend.core.runtime_paths import (
    default_artifact_dir,
    default_edited_transcript_dir,
    default_source_dir,
    default_transcript_edit_records_dir,
    default_video_source_dir,
)
from backend.core.result_schema import (
    canonical_display_segments,
    canonical_raw_segments,
    sanitize_display_segments,
    sanitize_raw_segments,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Storage path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]

def _source_storage_dir() -> Path:
    return default_source_dir()

def _video_source_storage_dir() -> Path:
    return default_video_source_dir()

def _edited_transcript_dir() -> Path:
    return default_edited_transcript_dir()

def _artifact_storage_dir() -> Path:
    return default_artifact_dir()

def _transcript_edit_records_dir() -> Path:
    return default_transcript_edit_records_dir()

# ---------------------------------------------------------------------------
# File suffix constants
# ---------------------------------------------------------------------------

ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
}

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".txt", ".md"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
VIDEO_SUFFIXES = ALLOWED_SUFFIXES - AUDIO_SUFFIXES

def _source_type_for_suffix(suffix: str) -> str:
    if suffix in TRANSCRIPT_SUFFIXES:
        return "transcript_file"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return "unknown"

# ---------------------------------------------------------------------------
# Small leaf utilities (no cross-group deps)
# ---------------------------------------------------------------------------

def _new_task_id() -> str:
    return uuid.uuid4().hex

def _text_len(value: str | None) -> int:
    return len(value or "")

def _file_size_mb(byte_count: int | None) -> float | None:
    if byte_count is None:
        return None
    return round(byte_count / (1024 * 1024), 3)

def _upload_size_mb(upload) -> float | None:
    file_obj = getattr(upload, "file", None)
    if file_obj is None:
        return None
    try:
        pos = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(pos, os.SEEK_SET)
        return _file_size_mb(size)
    except Exception:
        return None

def _path_size_mb(path: Path | str) -> float | None:
    try:
        return _file_size_mb(Path(path).stat().st_size)
    except OSError:
        return None

def _elapsed_since(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)

def _safe_filename_stem(value: str | None, fallback: str = "transcript") -> str:
    raw_stem = Path(value or fallback).stem or fallback
    safe_stem = "".join(
        ch if ch.isalnum() or ch in {" ", "-", "_", "."} else "_"
        for ch in raw_stem
    ).strip(" ._")
    return (safe_stem or fallback)[:96]

def _parse_job_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Media helpers
# ---------------------------------------------------------------------------

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
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=10,
        )
        value = float((result.stdout or "").strip())
        return value if value > 0 else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Source file / fingerprint
# ---------------------------------------------------------------------------

def _source_fingerprint(content: bytes, filename: str | None = None) -> dict[str, Any]:
    import hashlib
    return {
        "algorithm": "sha256",
        "sha256": hashlib.sha256(content).hexdigest(),
        "source_filename": filename,
        "source_size_bytes": len(content),
    }

def _source_fingerprint_for_path(path: Path | str, filename: str | None = None) -> dict[str, Any]:
    import hashlib
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

def _remove_tree(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return True
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False

# ---------------------------------------------------------------------------
# STT helpers
# ---------------------------------------------------------------------------

def _canonical_stt_provider(value: str | None) -> str:
    provider = (value or "").strip().lower().replace("-", "_")
    if provider in {"cloud", "cloud_stt", "elevenlabs", "elevenlabs_scribe", "scribe", "scribe_v2"}:
        return "elevenlabs_scribe"
    if provider in {"azure", "azure_batch", "azure_blob", "azure_speech_batch", "azure_fast", "azure_speech"}:
        return "azure_batch"
    if provider in {"local", "faster_whisper", "faster-whisper", "whisper"}:
        return "local"
    return "local"

def _request_can_use_local_stt(request=None) -> bool:
    if not _public_mode_enabled():
        return True
    if request is None:
        return False
    if _request_is_internal_queue(request):
        return True
    url_host = (request.url.hostname or "").strip().lower()
    return url_host in {"127.0.0.1", "localhost", "::1", "testclient"}

def _allowed_stt_providers(request=None) -> tuple[str, ...]:
    raw = os.environ.get("FLUENTFLOW_ALLOWED_STT_PROVIDERS")
    if raw is None or not raw.strip():
        return ("elevenlabs_scribe", "local") if _request_can_use_local_stt(request) else ("elevenlabs_scribe",)
    providers: list[str] = []
    for item in raw.split(","):
        provider = _canonical_stt_provider(item)
        if provider in {"elevenlabs_scribe", "azure_batch", "local"} and provider not in providers:
            providers.append(provider)
    if _request_can_use_local_stt(request) and "local" not in providers:
        providers.append("local")
    if _public_mode_enabled() and not _request_can_use_local_stt(request):
        providers = [provider for provider in providers if provider != "local"]
    return tuple(providers) or (("elevenlabs_scribe", "local") if _request_can_use_local_stt(request) else ("elevenlabs_scribe",))

def _default_stt_provider(request=None) -> str:
    requested = _canonical_stt_provider(os.environ.get("FLUENTFLOW_DEFAULT_STT_PROVIDER") or "elevenlabs_scribe")
    allowed = _allowed_stt_providers(request)
    return requested if requested in allowed else allowed[0]

def _normalize_stt_provider(value: str | None, request=None) -> str:
    provider = _canonical_stt_provider(value) if value else _default_stt_provider(request)
    allowed = _allowed_stt_providers(request)
    return provider if provider in allowed else _default_stt_provider(request)

def _stt_provider_label(provider: str) -> str:
    if provider == "elevenlabs_scribe":
        return "ElevenLabs Scribe"
    if provider == "azure_batch":
        return "Legacy Azure Batch"
    return "faster-whisper"

def _stt_realtime_factor(stt_elapsed_seconds: float | None, duration_seconds: float | None) -> float | None:
    if not stt_elapsed_seconds or not duration_seconds or duration_seconds <= 0:
        return None
    return max(round(stt_elapsed_seconds / duration_seconds, 4), 0.0001)

# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

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
            [ffmpeg, "-version"], check=False, capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return None
    first_line = (completed.stdout or completed.stderr or "").splitlines()
    return first_line[0][:160] if first_line else None

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _metadata(**values: Any) -> dict[str, Any]:
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        **{k: v for k, v in values.items() if v is not None},
    }

def _job_metadata_for_update(task_id: str, client_id: str | None, **values: Any) -> dict[str, Any]:
    from backend.core.job_store import get_job
    existing = get_job(task_id, client_id=client_id) if task_id else None
    current = existing.get("metadata") if existing else None
    base = current if isinstance(current, dict) else {}
    return {**base, **_metadata(**values)}

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

# ---------------------------------------------------------------------------
# Subtitle formatting
# ---------------------------------------------------------------------------

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

def _bilingual_segments(
    source_segments: list[dict[str, Any]],
    translated_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not source_segments or not translated_segments:
        return []
    output: list[dict[str, Any]] = []
    for source, translated in zip(source_segments, translated_segments):
        source_text = str(source.get("text") or "").strip()
        zh_text = str(translated.get("text") or translated.get("text_zh") or "").strip()
        if not source_text or not zh_text:
            continue
        segment: dict[str, Any] = {
            "start": source.get("start"),
            "end": source.get("end"),
            "text": f"{source_text}\n{zh_text}",
        }
        if source.get("speaker"):
            segment["speaker"] = source.get("speaker")
        output.append(segment)
    return output

def _sanitize_bilingual_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    segments: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text_en = str(item.get("text") or item.get("text_en") or "").strip()
        text_zh = str(item.get("text_zh") or item.get("zh") or "").strip()
        if not text_en or not text_zh:
            continue
        segment: dict[str, Any] = {"text": f"{text_en}\n{text_zh}"}
        for key in ("start", "end"):
            try:
                segment[key] = float(item.get(key) or 0)
            except (TypeError, ValueError):
                segment[key] = 0.0
        if item.get("speaker"):
            segment["speaker"] = str(item.get("speaker"))
        segments.append(segment)
    return segments

def _sanitize_display_segments(value: Any) -> list[dict[str, Any]]:
    return sanitize_display_segments(value)

def _canonical_raw_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    return canonical_raw_segments(result)

def _canonical_display_segments(result: dict[str, Any]) -> list[dict[str, Any]]:
    return canonical_display_segments(result)

def _sanitize_edit_segments(value: Any) -> list[dict[str, Any]]:
    return sanitize_raw_segments(value)

# ---------------------------------------------------------------------------
# Artifacts (delegates to result_artifacts)
# ---------------------------------------------------------------------------

def _with_canonical_result_segments(
    result: dict[str, Any],
    *,
    raw_segments: list[dict[str, Any]] | None = None,
    display_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.with_canonical_result_segments(
        result, raw_segments=raw_segments, display_segments=display_segments,
    )

def _subtitle_segments_from_display(display_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.subtitle_segments_from_display(display_segments)

def _write_text_artifact(task_id: str, kind: str, filename: str, content: str) -> dict[str, Any]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.write_text_artifact(task_id, kind, filename, content)

def _write_file_artifact(task_id: str, kind: str, filename: str, source_path: Path | str) -> dict[str, Any]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.write_file_artifact(task_id, kind, filename, source_path)

def _artifact_filename_for_uploaded_media(filename: str | None, fallback: str = "source_audio") -> str:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.artifact_filename_for_uploaded_media(filename, fallback=fallback)

def _attach_playback_audio_artifact(
    task_id: str, result: dict[str, Any], audio_path: Path | str, source_filename: str | None = None,
) -> dict[str, Any]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.attach_playback_audio_artifact(task_id, result, audio_path, source_filename=source_filename)

def _write_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.write_result_artifacts(task_id, result)

def _attach_result_artifacts(task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    from backend.core import artifacts as result_artifacts
    return result_artifacts.attach_result_artifacts(task_id, result)

# ---------------------------------------------------------------------------
# Artifact URL / filename
# ---------------------------------------------------------------------------

def _artifact_url(task_id: str, kind: str) -> str:
    return f"/jobs/{task_id}/artifacts/{kind}"

def _artifact_filename(result: dict[str, Any], suffix: str) -> str:
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback="transcript",
    )
    return f"{stem}{suffix}"

# ---------------------------------------------------------------------------
# Cleanup / retention
# ---------------------------------------------------------------------------

def _cleanup_task_source_files(task_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    removed: list[str] = []
    source_dir = _source_storage_dir() / task_id
    if _remove_tree(source_dir):
        removed.append(str(source_dir))
    removed.extend(_cleanup_video_source_temp_files(metadata).get("source_retention_removed_paths") or [])
    return {
        "source_retention_status": "deleted" if removed else "not_found",
        "source_retention_removed_paths": removed,
        "source_retention_cleaned_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }

def _cleanup_video_source_temp_files(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    removed: list[str] = []
    video_source = (metadata or {}).get("video_source")
    if isinstance(video_source, dict):
        for key in ("file_path", "metadata_path"):
            raw_path = str(video_source.get(key) or "").strip()
            if not raw_path:
                continue
            path = Path(raw_path).expanduser()
            if _remove_tree(path):
                removed.append(str(path))
    return {
        "source_retention_status": "deleted" if removed else "not_found",
        "source_retention_removed_paths": removed,
        "source_retention_cleaned_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }

def _cleanup_task_all_files(task_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    cleanup = _cleanup_task_source_files(task_id, metadata)
    removed = list(cleanup.get("source_retention_removed_paths") or [])
    for path in (_artifact_storage_dir() / task_id,):
        if _remove_tree(path):
            removed.append(str(path))
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    for folder, pattern in (
        (_edited_transcript_dir(), f"*__{task_suffix}_edited.txt"),
        (_transcript_edit_records_dir(), f"*__{task_suffix}_edit_records.json"),
    ):
        if folder.is_dir():
            for path in folder.glob(pattern):
                if _remove_tree(path):
                    removed.append(str(path))
    cleanup["source_retention_removed_paths"] = removed
    cleanup["history_retention_status"] = "deleted" if removed else "not_found"
    return cleanup

def _history_retention_per_client() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT", "20")), 0)
    except ValueError:
        return 20

def _artifact_retention_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_ARTIFACT_RETENTION_DAYS", "30")), 0)
    except ValueError:
        return 30

def _source_retention_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_SOURCE_RETENTION_DAYS", "7")), 0)
    except ValueError:
        return 7

def _source_retention_expiry(days: int) -> str:
    return (
        datetime.now(timezone.utc).astimezone() + timedelta(days=days)
    ).isoformat(timespec="seconds")

def _expire_retained_source_file(job: dict[str, Any], *, now: datetime | None = None) -> bool:
    task_id = str(job.get("task_id") or "")
    if not task_id:
        return False
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    if not result.get("source_file_available"):
        return False
    expires_at = _parse_job_time(result.get("source_retention_expires_at"))
    if expires_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if expires_at > current.astimezone(timezone.utc):
        return False
    cleanup = _cleanup_task_source_files(task_id, job.get("metadata"))
    next_result = {
        **result,
        "source_file_available": False,
        "source_file_storage": None,
        "source_retention_status": "expired",
        "source_retention_cleaned_at": cleanup.get("source_retention_cleaned_at"),
    }
    from backend.core.job_store import update_job_result
    update_job_result(
        task_id,
        next_result,
        client_id=job.get("client_id"),
        touch_updated_at=False,
    )
    return True

def _enforce_history_retention(client_id: str | None) -> dict[str, Any]:
    if not client_id:
        return {"pruned_count": 0, "task_ids": []}
    keep_count = _history_retention_per_client()
    retention_days = _artifact_retention_days()
    source_retention_days = _source_retention_days()
    if keep_count <= 0 and retention_days <= 0 and source_retention_days <= 0:
        return {"pruned_count": 0, "task_ids": []}
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
        if retention_days > 0
        else None
    )
    from backend.core.job_store import delete_jobs, list_jobs_for_retention
    jobs = list_jobs_for_retention(client_id=client_id)
    pruned_task_ids: list[str] = []
    expired_source_count = 0
    now = datetime.now(timezone.utc)
    for index, job in enumerate(jobs):
        task_id = str(job.get("task_id") or "")
        if not task_id or job.get("status") not in {"completed", "failed", "cancelled"}:
            continue
        if _expire_retained_source_file(job, now=now):
            expired_source_count += 1
        too_many = keep_count > 0 and index >= keep_count
        updated_at = _parse_job_time(job.get("updated_at") or job.get("created_at"))
        too_old = cutoff is not None and updated_at is not None and updated_at < cutoff
        if too_many or too_old:
            _cleanup_task_all_files(task_id, job.get("metadata"))
            pruned_task_ids.append(task_id)
    if pruned_task_ids:
        delete_jobs(pruned_task_ids, client_id=client_id)
    return {
        "pruned_count": len(pruned_task_ids),
        "task_ids": pruned_task_ids,
        "expired_source_count": expired_source_count,
    }

def _finalize_completed_result_storage(task_id: str, result: dict[str, Any], metadata: dict[str, Any] | None) -> dict[str, Any]:
    next_result = dict(result)
    artifacts = dict(next_result.get("artifacts") or {})
    if artifacts.get("playback_audio"):
        next_result["playback_audio_available"] = True
    retention_days = _source_retention_days()
    if retention_days <= 0:
        cleanup = _cleanup_task_source_files(task_id, metadata)
        next_result["source_file_available"] = False
        next_result.update({
            key: value
            for key, value in cleanup.items()
            if key != "source_retention_removed_paths"
        })
        return next_result

    _cleanup_video_source_temp_files(metadata)
    source = _find_source_file(task_id)
    if source:
        next_result.update({
            "source_file_available": True,
            "source_file_storage": "local",
            "source_retention_status": "retained",
            "source_retention_days": retention_days,
            "source_retention_expires_at": _source_retention_expiry(retention_days),
        })
    else:
        next_result.update({
            "source_file_available": False,
            "source_retention_status": "not_found",
        })
    from backend.core.tool_trace import build_tool_trace
    next_result["tool_trace"] = build_tool_trace(next_result, job={"task_id": task_id, "status": "completed"})
    return next_result

# ---------------------------------------------------------------------------
# Edited transcript backup
# ---------------------------------------------------------------------------

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
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback=task_id or "transcript",
    )
    task_suffix = _safe_filename_stem(task_id or "task")[:12]
    target_dir = _edited_transcript_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stem}__{task_suffix}_edited.txt"
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    content = _format_edited_transcript_backup(
        str(result.get("transcript_text") or ""),
        _canonical_raw_segments(result),
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
        "index", "start", "end", "before", "after",
        "previous_before", "next_before", "previous_after", "next_after", "created_at",
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
    stem = _safe_filename_stem(
        result.get("display_title") or result.get("filename") or result.get("source_filename"),
        fallback=task_id or "transcript",
    )
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

# ---------------------------------------------------------------------------
# Pipeline / export helpers
# ---------------------------------------------------------------------------

def _pipeline_mode(source_type: str | None) -> str | None:
    if source_type == "transcript_file":
        return "transcript_file"
    if source_type in {"audio", "video"}:
        return "audio_video"
    return None

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
    from backend.core.event_logger import log_event
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

def _lark_export_target(lark_export_route=None, lark_via_cli=None) -> str:
    route = (lark_export_route or "").strip().lower()
    if route in {"local_cli", "lark_cli"}:
        return "lark_cli"
    if route in {"user_oauth", "feishu_user", "feishu_user_oauth", "lark_user_oauth"}:
        return "feishu_user_oauth"
    if route in {"openapi", "lark_openapi"}:
        return "lark_openapi"
    return "lark_cli" if _truthy_form(lark_via_cli) else "lark_openapi"

def _truthy_form(val=None) -> bool:
    return bool(val and str(val).strip().lower() in ("true", "1", "yes", "on"))

# ---------------------------------------------------------------------------
# AI kwargs / planning
# ---------------------------------------------------------------------------

def _ai_kwargs(
    *,
    deepseek_api_key=None,
    openai_api_key=None,
    qwen_api_key=None,
    ai_provider=None,
    ai_model=None,
    system_prompt=None,
    note_mode=None,
) -> dict[str, Any]:
    from backend.core.local_config import resolve_secret
    kwargs: dict[str, Any] = {}
    provider_name = (ai_provider or "").strip()
    resolved_openai_key = resolve_secret(openai_api_key, "openai_api_key")
    resolved_deepseek_key = resolve_secret(deepseek_api_key, "deepseek_api_key")
    resolved_qwen_key = resolve_secret(qwen_api_key, "qwen_api_key")
    if not provider_name and resolved_openai_key:
        provider_name = "openai"
    if provider_name:
        kwargs["provider"] = provider_name
    if resolved_deepseek_key:
        kwargs["api_key"] = resolved_deepseek_key
    if resolved_openai_key and provider_name.lower() == "openai":
        kwargs["api_key"] = resolved_openai_key
    if resolved_qwen_key and provider_name.lower() == "qwen":
        kwargs["api_key"] = resolved_qwen_key
    if (m := (ai_model or "").strip()):
        kwargs["model"] = m
    if (sp := (system_prompt or "").strip()):
        kwargs["system_prompt"] = sp
    if (nm := (note_mode or "").strip()):
        kwargs["note_mode"] = nm
    return kwargs

def _requested_note_mode(note_mode: str | None) -> str:
    value = (note_mode or os.environ.get("FLUENTFLOW_NOTE_MODE") or "auto").strip().lower()
    return "direct" if value == "fast" else value

def _language_hint_for_planning(text: str) -> str:
    cjk = 0
    latin = 0
    for char in text:
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF:
            cjk += 1
        elif "a" <= char.lower() <= "z":
            latin += 1
    if cjk > latin:
        return "zh"
    if latin > cjk:
        return "en_or_latin"
    return "unknown"

PLANNER_NOTE_MODES = {"direct", "high_fidelity"}
PLANNER_SAMPLE_CHARS = 3000

def _planning_transcript_preview(transcript_text: str, *, sample_chars: int = PLANNER_SAMPLE_CHARS) -> str:
    transcript = (transcript_text or "").strip()
    if not transcript:
        return ""
    sample_size = max(500, sample_chars)
    total = len(transcript)
    non_empty_lines = [line.strip() for line in transcript.splitlines() if line.strip()]
    question_count = transcript.count("?") + transcript.count("？")
    avg_line_chars = round(sum(len(line) for line in non_empty_lines) / len(non_empty_lines), 1) if non_empty_lines else total
    stats = "\n".join([
        "【材料统计】",
        f"- total_chars: {total}",
        f"- non_empty_lines: {len(non_empty_lines)}",
        f"- avg_line_chars: {avg_line_chars}",
        f"- question_marks: {question_count}",
        f"- language_hint: {_language_hint_for_planning(transcript)}",
    ])
    if total <= sample_size * 2:
        return f"{stats}\n\n【全文样本】\n{transcript[:sample_size * 2]}"
    head = transcript[:sample_size]
    mid_start = max(0, (total // 2) - (sample_size // 2))
    middle = transcript[mid_start: mid_start + sample_size]
    tail = transcript[-sample_size:]
    return "\n\n".join([
        stats,
        f"【开头样本】\n{head}",
        f"【中段样本】\n{middle}",
        f"【结尾样本】\n{tail}",
    ])

def _plan_note_mode_for_summary(
    kwargs: dict[str, Any],
    transcript_text: str,
    *,
    task_id: str | None = None,
    route: str | None = None,
    filename: str | None = None,
    duration_seconds: float | None = None,
    current_prompt_preset: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from backend.core.event_logger import log_event
    from backend.core.note_planner import plan_note_task
    requested_mode = _requested_note_mode(kwargs.get("note_mode"))
    if requested_mode != "auto":
        return kwargs, {}
    started_at = time.perf_counter()
    transcript = transcript_text or ""
    try:
        plan = plan_note_task(
            filename=filename,
            transcript_preview=_planning_transcript_preview(transcript),
            transcript_length=len(transcript),
            duration_seconds=duration_seconds,
            current_note_mode="auto",
            current_prompt_preset=current_prompt_preset,
            provider=kwargs.get("provider"),
            model=kwargs.get("model"),
            api_key=kwargs.get("api_key"),
        )
        planned_mode = (plan.recommended_note_mode or "").strip()
        if planned_mode not in PLANNER_NOTE_MODES:
            planned_mode = "high_fidelity"
        planned_kwargs = {**kwargs, "note_mode": planned_mode}
        metadata = {
            "requested_note_mode": "auto",
            "note_mode_plan_selected_mode": planned_mode,
            "note_mode_plan_reason": plan.reason,
            "note_mode_plan_confidence": plan.confidence,
            "note_mode_plan_warnings": plan.warnings,
            "note_mode_plan_provider": plan.planner_provider,
            "note_mode_plan_model": plan.planner_model,
            "note_mode_plan_fallback": False,
        }
        log_event(
            task_id=task_id,
            event_name="note_mode_planned",
            source_filename=filename,
            transcript_length=len(transcript),
            stage="note_mode_plan",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=True,
        )
        return planned_kwargs, metadata
    except Exception:
        log_event(
            task_id=task_id,
            event_name="note_mode_plan_fallback",
            source_filename=filename,
            transcript_length=len(transcript),
            stage="note_mode_plan",
            success=True,
            metadata={"fallback": True, "reason": "Planner unavailable, high_fidelity is safer shared-mode default"},
        )
        return {**kwargs, "note_mode": "high_fidelity"}, {}

def _summary_result_metadata(summary_result: Any) -> dict[str, Any]:
    return {
        "note_mode_status": getattr(summary_result, "status", None),
        "note_mode_plan_used": getattr(summary_result, "note_mode", None),
        "note_mode_plan_warnings": getattr(summary_result, "warnings", None),
        "note_mode_segment_count": getattr(summary_result, "segment_count", None),
        "note_mode_evidence_count": getattr(summary_result, "evidence_count", None),
        "note_mode_chapter_count": getattr(summary_result, "chapter_count", None),
        "note_mode_important_evidence_count": getattr(summary_result, "important_evidence_count", None),
        "note_mode_covered_important_evidence_count": getattr(summary_result, "covered_important_evidence_count", None),
        "note_mode_coverage_missing_count": getattr(summary_result, "coverage_missing_count", None),
    }

def _cleanup_payload(cleanup_result: Any) -> dict[str, Any]:
    return {
        "applied_count": cleanup_result.applied_count,
        "removed_segment_count": cleanup_result.removed_segment_count,
        "raw_length": cleanup_result.raw_length,
        "cleaned_length": cleanup_result.cleaned_length,
        "issues": [asdict(item) for item in cleanup_result.issues[:20]],
        "issue_count": len(cleanup_result.issues),
    }
