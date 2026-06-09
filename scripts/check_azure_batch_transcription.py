#!/usr/bin/env python3
"""Smoke-test FluentFlow's Azure Batch + Blob/SAS transcription path.

The command reuses FluentFlow's audio preprocessing, uploads the compressed
audio to the configured Azure Blob container SAS URL, submits an Azure Batch
transcription job, polls until completion, and prints compact JSON metrics. It
does not write analytics events or job history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.audio_handler import extract_compressed_mp3  # noqa: E402
from backend.core.azure_stt import (  # noqa: E402
    DEFAULT_BATCH_TRANSCRIPTION_API_VERSION,
    file_size_mb,
    normalize_azure_speech_address,
    transcribe_audio_batch,
)
from backend.core.local_config import get_sensitive_setting  # noqa: E402


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_duration_seconds(path: Path) -> float | None:
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


def endpoint_host(address: str | None) -> str | None:
    endpoint = normalize_azure_speech_address(address)
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    return parsed.netloc or parsed.path.split("/")[0] or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Audio or video file to check")
    parser.add_argument("--language", default="auto", help="auto, zh, en, zh-CN, en-US")
    parser.add_argument("--diarization", action="store_true", help="Request Azure Batch speaker diarization")
    parser.add_argument("--address", default=None, help="Azure Speech address or region override")
    parser.add_argument("--endpoint", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--key", default=None, help="Azure Speech key override")
    parser.add_argument("--container-sas-url", default=None, help="Azure Blob container SAS URL override")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-wait-seconds", type=float, default=7200)
    parser.add_argument("--poll-interval-seconds", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Validate preprocessing and configuration without calling Azure")
    parser.add_argument("--include-preview", action="store_true", help="Include a 200-character transcript preview")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Source file not found: {source}")

    endpoint = normalize_azure_speech_address(args.address or args.endpoint or get_sensitive_setting("azure_speech_endpoint"))
    api_key = (args.key or get_sensitive_setting("azure_speech_key") or "").strip()
    container_sas_url = (args.container_sas_url or get_sensitive_setting("azure_blob_container_sas_url") or "").strip()
    started_at = time.perf_counter()
    progress_events: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="fluentflow_azure_batch_check_") as td:
        audio_path = Path(td) / f"{source.stem}_azure_batch.mp3"
        extract_started_at = time.perf_counter()
        extract_compressed_mp3(source, output_path=audio_path)
        extract_elapsed = time.perf_counter() - extract_started_at
        duration = media_duration_seconds(audio_path)

        payload: dict[str, Any] = {
            "status": "dry_run" if args.dry_run else "pending",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": {
                "filename": source.name,
                "size_mb": file_size_mb(source),
                "fingerprint": {
                    "algorithm": "sha256",
                    "sha256": file_sha256(source),
                    "source_size_bytes": source.stat().st_size,
                },
            },
            "azure": {
                "address_configured": bool(endpoint),
                "endpoint_host": endpoint_host(endpoint),
                "key_configured": bool(api_key),
                "blob_container_sas_configured": bool(container_sas_url),
                "api_version": DEFAULT_BATCH_TRANSCRIPTION_API_VERSION,
                "requested_language": args.language,
                "diarization_requested": bool(args.diarization),
                "dry_run": bool(args.dry_run),
            },
            "preprocess": {
                "audio_extract_seconds": round(extract_elapsed, 3),
                "audio_format": "mp3",
                "audio_size_mb": file_size_mb(audio_path),
                "audio_duration_seconds": round(duration, 3) if duration else None,
            },
        }

        if not args.dry_run:
            missing = []
            if not endpoint:
                missing.append("Azure Speech address")
            if not api_key:
                missing.append("Azure Speech key")
            if not container_sas_url:
                missing.append("Azure Blob container SAS URL")
            if missing:
                raise SystemExit("Missing configuration: " + ", ".join(missing))

            def on_progress(status: str, metadata: dict[str, Any] | None = None) -> None:
                progress_events.append({
                    "at_seconds": round(time.perf_counter() - started_at, 1),
                    "status": status,
                    "metadata": metadata or {},
                })

            azure_started_at = time.perf_counter()
            result = transcribe_audio_batch(
                audio_path,
                endpoint=endpoint,
                api_key=api_key,
                container_sas_url=container_sas_url,
                locale=args.language,
                diarization_enabled=args.diarization,
                timeout=args.timeout,
                poll_interval_seconds=args.poll_interval_seconds,
                max_wait_seconds=args.max_wait_seconds,
                progress_callback=on_progress,
            )
            azure_elapsed = time.perf_counter() - azure_started_at
            source_duration = result.duration or (result.segments[-1].end if result.segments else duration)
            realtime_factor = azure_elapsed / source_duration if source_duration and source_duration > 0 else None
            payload.update({
                "status": "completed",
                "progress_events": progress_events,
                "metrics": {
                    "source_duration_seconds": round(source_duration, 3) if source_duration else None,
                    "azure_elapsed_seconds": round(azure_elapsed, 3),
                    "azure_realtime_factor": round(realtime_factor, 4) if realtime_factor else None,
                    "azure_realtime_speed": round(1 / realtime_factor, 3) if realtime_factor else None,
                    "total_elapsed_seconds": round(time.perf_counter() - started_at, 3),
                    "segment_count": len(result.segments),
                    "speaker_segment_count": sum(1 for segment in result.segments if segment.speaker),
                    "transcript_length": len(result.text or ""),
                    "detected_language": result.language,
                },
            })
            if args.include_preview:
                payload["transcript_preview"] = (result.text or "")[:200]

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
