"""Local speech-to-text with faster-whisper (timestamped segments)."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_LOCAL_MODEL_DIR = Path.home() / ".cache" / "faster-whisper-models"

_SIZE_ALIASES: dict[str, str] = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large-v2": "large-v2",
    "large-v3": "large-v3",
}


def _resolve_model(model_size: str) -> str:
    """Return a local path if a pre-downloaded model exists, else the name for HF."""
    alias = _SIZE_ALIASES.get(model_size, model_size)
    local = _LOCAL_MODEL_DIR / alias
    if local.is_dir() and (local / "model.bin").is_file():
        return str(local)
    return model_size


# ── Singleton model cache ────────────────────────────────────────────
_model_cache: dict[str, WhisperModel] = {}
_model_lock = threading.Lock()


def get_or_load_model(model_size: str = "small", compute_type: str = "int8") -> WhisperModel:
    """Return a cached WhisperModel, loading it once on first call."""
    resolved = _resolve_model(model_size)
    key = f"{resolved}|{compute_type}"
    with _model_lock:
        if key not in _model_cache:
            logger.info("Loading Whisper model: %s (compute=%s)…", resolved, compute_type)
            _model_cache[key] = WhisperModel(resolved, compute_type=compute_type)
            logger.info("Whisper model loaded.")
        return _model_cache[key]


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    segments: tuple[TranscriptSegment, ...]
    language: str | None
    language_probability: float | None
    duration: float | None


def _collect_segments(
    segments: Iterable[Any],
    *,
    total_duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> tuple[tuple[TranscriptSegment, ...], str]:
    """Iterate the lazy segment generator, optionally reporting progress."""
    normalized: list[TranscriptSegment] = []
    parts: list[str] = []
    for seg in segments:
        t = (seg.text or "").strip()
        if not t:
            continue
        normalized.append(
            TranscriptSegment(start=float(seg.start), end=float(seg.end), text=t)
        )
        parts.append(t)
        if on_progress and total_duration and total_duration > 0:
            on_progress(min(float(seg.end) / total_duration, 1.0))
    return tuple(normalized), " ".join(parts)


def transcribe_audio(
    audio_path: str | Path,
    *,
    model: WhisperModel | None = None,
    model_size: str = "small",
    compute_type: str = "int8",
    vad_filter: bool = True,
    language: str | None = None,
    on_progress: Callable[[float], None] | None = None,
    **transcribe_kwargs: Any,
) -> TranscriptionResult:
    """
    Transcribe audio with faster-whisper.

    Args:
        on_progress: Optional callback receiving a float 0.0–1.0 during transcription.
    """
    path = Path(audio_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Audio not found: {path}")

    if model is None:
        model = get_or_load_model(model_size, compute_type)

    segments_iter, info = model.transcribe(
        str(path),
        vad_filter=vad_filter,
        language=language,
        **transcribe_kwargs,
    )
    duration = getattr(info, "duration", None)
    segments, text = _collect_segments(
        segments_iter,
        total_duration=duration,
        on_progress=on_progress,
    )
    return TranscriptionResult(
        text=text,
        segments=segments,
        language=getattr(info, "language", None),
        language_probability=getattr(info, "language_probability", None),
        duration=duration,
    )
