"""Local speech-to-text with faster-whisper (timestamped segments)."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_LOCAL_MODEL_DIR = Path.home() / ".cache" / "faster-whisper-models"
_ZH_INITIAL_PROMPT = (
    "以下是普通话中文语音转录。请使用简体中文输出，保留必要的英文术语、数字和专有名词。"
)
_ZH_HOTWORDS = "简体中文 普通话 线下 创造营 产品经理 作业 同学 老师 课题"
_SEGMENT_NORM_RE = re.compile(r"[\s，。！？、,.!?;；:：'\"“”‘’（）()【】\[\]《》<>-]+")
_STT_SPEED_PROFILES: dict[str, dict[str, Any]] = {
    "fast": {
        "beam_size": 1,
        "best_of": 1,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "vad_parameters": {"min_silence_duration_ms": 350},
    },
    "balanced": {
        "beam_size": 3,
        "best_of": 3,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "vad_parameters": {"min_silence_duration_ms": 500},
    },
    "accurate": {
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "vad_parameters": {"min_silence_duration_ms": 500},
    },
}

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
_opencc_converter: Any | None = None
_opencc_checked = False


def _to_simplified_chinese(text: str) -> str:
    """Convert Traditional Chinese output to Simplified when OpenCC is available."""
    global _opencc_converter, _opencc_checked
    if not text:
        return text
    if not _opencc_checked:
        _opencc_checked = True
        try:
            from opencc import OpenCC

            _opencc_converter = OpenCC("t2s")
        except Exception as exc:
            logger.info("OpenCC not available; STT text will not be converted: %s", exc)
            _opencc_converter = None
    if _opencc_converter is None:
        return text
    return _opencc_converter.convert(text)


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
        if _looks_like_low_confidence_hallucination(seg):
            continue
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


def _simplify_segments(
    segments: tuple[TranscriptSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    return tuple(
        TranscriptSegment(start=s.start, end=s.end, text=_to_simplified_chinese(s.text))
        for s in segments
    )


def _looks_like_low_confidence_hallucination(seg: Any) -> bool:
    """Use Whisper metadata to suppress common silence/noise hallucinations."""
    no_speech_prob = getattr(seg, "no_speech_prob", None)
    avg_logprob = getattr(seg, "avg_logprob", None)
    compression_ratio = getattr(seg, "compression_ratio", None)

    if (
        no_speech_prob is not None
        and avg_logprob is not None
        and float(no_speech_prob) >= 0.75
        and float(avg_logprob) <= -0.6
    ):
        return True
    if (
        compression_ratio is not None
        and avg_logprob is not None
        and float(compression_ratio) >= 2.6
        and float(avg_logprob) <= -0.5
    ):
        return True
    return False


def _normalize_for_repeat_filter(text: str) -> str:
    return _SEGMENT_NORM_RE.sub("", text or "").lower()


def _filter_repeated_hallucination_segments(
    segments: tuple[TranscriptSegment, ...],
) -> tuple[TranscriptSegment, ...]:
    """Drop runs like "大学生 课题" repeated through silent/noisy spans."""
    kept: list[TranscriptSegment] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        norm = _normalize_for_repeat_filter(seg.text)
        if not norm:
            i += 1
            continue

        j = i + 1
        while j < len(segments) and _normalize_for_repeat_filter(segments[j].text) == norm:
            j += 1

        run = segments[i:j]
        run_count = len(run)
        span = run[-1].end - run[0].start if run else 0
        short_phrase = len(norm) <= 18
        repeated_noise = short_phrase and (run_count >= 4 or (run_count >= 3 and span >= 8))
        if repeated_noise:
            logger.info(
                "Dropping repeated STT hallucination run: %r x%s",
                run[0].text,
                run_count,
            )
        else:
            kept.extend(run)
        i = j
    return tuple(kept)


def _transcribe_profile_defaults(speed_profile: str | None) -> dict[str, Any]:
    profile = (speed_profile or "balanced").strip().lower()
    if profile not in _STT_SPEED_PROFILES:
        profile = "balanced"
    return {
        key: (value.copy() if isinstance(value, dict) else value)
        for key, value in _STT_SPEED_PROFILES[profile].items()
    }


def _normalize_language(language: str | None) -> str | None:
    value = (language or "auto").strip().lower()
    aliases = {
        "auto": None,
        "detect": None,
        "": None,
        "zh-cn": "zh",
        "zh_hans": "zh",
        "chinese": "zh",
        "cn": "zh",
        "english": "en",
    }
    return aliases.get(value, value)


def transcribe_audio(
    audio_path: str | Path,
    *,
    model: WhisperModel | None = None,
    model_size: str = "small",
    compute_type: str = "int8",
    vad_filter: bool = True,
    language: str | None = None,
    speed_profile: str | None = None,
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

    language = _normalize_language(language)
    transcribe_defaults = _transcribe_profile_defaults(speed_profile)
    if language == "zh":
        transcribe_defaults.update({
            "initial_prompt": _ZH_INITIAL_PROMPT,
            "hotwords": _ZH_HOTWORDS,
        })
    transcribe_defaults.update(transcribe_kwargs)

    segments_iter, info = model.transcribe(
        str(path),
        vad_filter=vad_filter,
        language=language,
        **transcribe_defaults,
    )
    duration = getattr(info, "duration", None)
    segments, text = _collect_segments(
        segments_iter,
        total_duration=duration,
        on_progress=on_progress,
    )
    segments = _simplify_segments(segments)
    segments = _filter_repeated_hallucination_segments(segments)
    text = " ".join(s.text for s in segments)
    return TranscriptionResult(
        text=text,
        segments=segments,
        language=getattr(info, "language", None),
        language_probability=getattr(info, "language_probability", None),
        duration=duration,
    )
