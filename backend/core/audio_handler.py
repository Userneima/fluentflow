"""Extract/compress audio from video or audio files (for downstream STT)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus", ".webm"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".ts", ".m4v"}


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_SUFFIXES


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH; it is required for audio processing")
    return ffmpeg


def extract_compressed_mp3(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    bitrate: str = "64k",
) -> Path:
    """
    Prepare a compressed MP3 from a video **or** audio source.

    Uses ffmpeg directly for both video and audio — avoids moviepy compatibility
    issues and works reliably across all ffmpeg versions.

    Returns:
        Absolute path to the written MP3.
    """
    src = Path(input_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"File not found: {src}")

    if output_path is None:
        out = src.with_name(f"{src.stem}_fluentflow.mp3")
    else:
        out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _require_ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-b:a", bitrate, str(out)],
        check=True, capture_output=True,
    )
    return out
