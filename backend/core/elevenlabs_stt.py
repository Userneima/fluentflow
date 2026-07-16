"""ElevenLabs Scribe speech-to-text adapter.

The adapter converts ElevenLabs responses into the same TranscriptionResult
shape used by local faster-whisper.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .local_stt import TranscriptSegment, TranscriptionResult

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVENLABS_MODEL_ID = "scribe_v2"


@dataclass(frozen=True)
class ElevenLabsWord:
    text: str
    start: float | None
    end: float | None
    speaker: str | None = None


def transcribe_audio_scribe(
    audio_path: Path | str,
    *,
    api_key: str | None,
    language: str | None = None,
    diarization_enabled: bool = False,
    timeout: float = 1800,
    progress_callback: Callable[[str, dict[str, Any] | None], None] | None = None,
) -> TranscriptionResult:
    key = (api_key or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ElevenLabs API key is not configured")

    path = Path(audio_path)
    if not path.is_file():
        raise RuntimeError(f"Audio file not found: {path}")

    def notify(status: str, **metadata: Any) -> None:
        if progress_callback:
            progress_callback(status, metadata)

    data: dict[str, Any] = {
        "model_id": ELEVENLABS_MODEL_ID,
        "diarize": "true" if diarization_enabled else "false",
        "timestamps_granularity": "word",
    }
    language_code = _elevenlabs_language_code(language)
    if language_code:
        data["language_code"] = language_code

    notify("elevenlabs_uploading", elevenlabs_audio_size_mb=_file_size_mb(path))
    try:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, _content_type(path))}
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    ELEVENLABS_STT_URL,
                    headers={"xi-api-key": key},
                    data=data,
                    files=files,
                )
        notify("elevenlabs_processing")
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:800]
        raise RuntimeError(f"ElevenLabs transcription failed: HTTP {exc.response.status_code} {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"ElevenLabs transcription request failed: {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("ElevenLabs transcription returned invalid JSON") from exc

    notify("elevenlabs_normalizing")
    return parse_scribe_transcription_result(payload)


def parse_scribe_transcription_result(payload: dict[str, Any]) -> TranscriptionResult:
    text = str(payload.get("text") or "").strip()
    words = _parse_words(payload.get("words"))
    segments = _segments_from_words(words)

    if not text:
        text = " ".join(segment.text for segment in segments).strip()
    if not text:
        raise RuntimeError("ElevenLabs transcription returned no usable speech")
    if text and not segments:
        segments = (TranscriptSegment(start=0.0, end=0.0, text=text),)

    duration = _duration_from_words(words) or (segments[-1].end if segments else None)
    return TranscriptionResult(
        text=text,
        segments=segments,
        language=_string_or_none(payload.get("language_code")),
        language_probability=_float_or_none(payload.get("language_probability")),
        duration=duration,
        model_cache_hit=None,
        model_load_seconds=None,
        model_source="elevenlabs_scribe",
        compute_type=None,
        device_requested="cloud",
        device_resolved="elevenlabs",
        cpu_threads=None,
        num_workers=None,
        vad_filter=None,
    )


def _parse_words(value: Any) -> list[ElevenLabsWord]:
    if not isinstance(value, list):
        return []
    words: list[ElevenLabsWord] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text") or item.get("word") or ""
        text = str(raw_text).strip()
        if not text:
            continue
        word_type = str(item.get("type") or "").strip().lower()
        if word_type in {"spacing", "audio_event"}:
            continue
        words.append(
            ElevenLabsWord(
                text=text,
                start=_float_or_none(item.get("start")),
                end=_float_or_none(item.get("end")),
                speaker=_speaker_label(item.get("speaker_id") or item.get("speaker")),
            )
        )
    return words


def _segments_from_words(words: list[ElevenLabsWord]) -> tuple[TranscriptSegment, ...]:
    if not words:
        return ()
    segments: list[TranscriptSegment] = []
    current: list[ElevenLabsWord] = []
    current_speaker: str | None = None
    last_end: float | None = None

    def flush() -> None:
        nonlocal current, current_speaker, last_end
        if not current:
            return
        start = next((word.start for word in current if word.start is not None), 0.0) or 0.0
        end = next((word.end for word in reversed(current) if word.end is not None), start) or start
        text = _join_word_text(word.text for word in current)
        if text:
            segments.append(TranscriptSegment(start=round(start, 3), end=round(end, 3), text=text, speaker=current_speaker))
        current = []
        current_speaker = None
        last_end = None

    for word in words:
        gap = (word.start - last_end) if word.start is not None and last_end is not None else 0.0
        sentence_break = bool(current and current[-1].text.endswith((".", "?", "!", "。", "？", "！", "；", ";")))
        speaker_changed = bool(current and word.speaker and current_speaker and word.speaker != current_speaker)
        too_long = len(_join_word_text(item.text for item in current)) >= 220
        if current and (speaker_changed or gap >= 1.2 or (sentence_break and len(current) >= 8) or too_long):
            flush()
        if not current:
            current_speaker = word.speaker
        current.append(word)
        if word.end is not None:
            last_end = word.end
    flush()
    return tuple(segments)


def _join_word_text(parts: Any) -> str:
    text = ""
    for part in parts:
        token = str(part or "").strip()
        if not token:
            continue
        if not text:
            text = token
        elif token in {".", ",", "?", "!", ":", ";", "。", "，", "？", "！", "：", "；"}:
            text += token
        elif _looks_cjk(text[-1]) or _looks_cjk(token[0]):
            text += token
        else:
            text += " " + token
    return text.strip()


def _looks_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _duration_from_words(words: list[ElevenLabsWord]) -> float | None:
    values = [word.end for word in words if word.end is not None]
    if not values:
        return None
    return round(max(values), 3)


def _elevenlabs_language_code(language: str | None) -> str | None:
    value = (language or "").strip().lower()
    if value in {"en", "en-us", "english"}:
        return "eng"
    if value in {"zh", "zh-cn", "chinese", "mandarin"}:
        return "zho"
    return None


def _speaker_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper.startswith("SPEAKER_"):
        return upper
    if raw.isdigit():
        return f"SPEAKER_{int(raw) + 1}"
    return upper.replace(" ", "_")


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _file_size_mb(path: Path) -> float | None:
    try:
        return round(path.stat().st_size / (1024 * 1024), 3)
    except OSError:
        return None


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".m4a":
        return "audio/mp4"
    return "application/octet-stream"
