"""Azure Speech fast transcription adapter.

This module intentionally converts Azure responses into the same
TranscriptionResult shape used by the local faster-whisper pipeline, so the
rest of FluentFlow can keep using transcript cleanup, editor, summary, and
export code without branching.
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import ssl
import subprocess
import tempfile
import time
import uuid
import urllib.error
import urllib.request
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

from .local_stt import TranscriptSegment, TranscriptionResult

DEFAULT_FAST_TRANSCRIPTION_API_VERSION = "2025-10-15"
FALLBACK_FAST_TRANSCRIPTION_API_VERSION = "2024-11-15"
FAST_TRANSCRIPTION_API_VERSION = (
    os.environ.get("FLUENTFLOW_AZURE_FAST_API_VERSION")
    or DEFAULT_FAST_TRANSCRIPTION_API_VERSION
)
AZURE_FAST_MODEL_NAME = "azure-fast-transcription"
AZURE_BATCH_MODEL_NAME = "azure-batch-transcription"
DEFAULT_BATCH_TRANSCRIPTION_API_VERSION = "2025-10-15"
AZURE_BLOB_SERVICE_VERSION = "2023-11-03"
DEFAULT_AZURE_AUTO_LOCALES: tuple[str, ...] = ()
AZURE_REGION_ALIASES = {
    "eastaisa": "eastasia",
}
_DISPLAY_SEGMENT_END_RE = re.compile(r"([^。！？!?；;\n]+[。！？!?；;]?|[^\n]+)")
_DISPLAY_SEGMENT_SOFT_RE = re.compile(r"[。！？!?；;，,、\s]")


@dataclass(frozen=True)
class AzureWordTiming:
    text: str
    start: float
    end: float


def azure_fast_max_inline_upload_mb() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_AZURE_FAST_MAX_INLINE_MB", "240")), 1.0)
    except ValueError:
        return 240.0


def azure_fast_max_inline_duration_seconds(diarization_enabled: bool = False) -> float:
    env_key = (
        "FLUENTFLOW_AZURE_FAST_MAX_DIARIZATION_SECONDS"
        if diarization_enabled
        else "FLUENTFLOW_AZURE_FAST_MAX_DURATION_SECONDS"
    )
    try:
        return max(float(os.environ.get(env_key, "7200")), 1.0)
    except ValueError:
        return 7200.0


def file_size_mb(path: Path | str) -> float | None:
    try:
        return round(Path(path).stat().st_size / (1024 * 1024), 3)
    except OSError:
        return None


def validate_azure_fast_inline_audio(
    audio_path: Path | str,
    *,
    duration_seconds: float | None,
    diarization_enabled: bool = False,
) -> dict[str, Any]:
    size_mb = file_size_mb(audio_path)
    max_size_mb = azure_fast_max_inline_upload_mb()
    max_duration_seconds = azure_fast_max_inline_duration_seconds(diarization_enabled)
    if size_mb is not None and size_mb >= max_size_mb:
        raise RuntimeError(
            "Azure Fast Transcription inline upload is too large: "
            f"{size_mb:g} MB after audio preprocessing. "
            f"Current local limit is {max_size_mb:g} MB. "
            "Use local STT or a future Azure Batch/Blob flow for longer recordings."
        )
    if duration_seconds is not None and duration_seconds >= max_duration_seconds:
        duration_minutes = round(duration_seconds / 60, 1)
        limit_minutes = round(max_duration_seconds / 60, 1)
        raise RuntimeError(
            "Azure Fast Transcription inline audio is too long: "
            f"{duration_minutes:g} minutes after audio preprocessing. "
            f"Current local limit is {limit_minutes:g} minutes. "
            "Use local STT or a future Azure Batch/Blob flow for longer recordings."
        )
    return {
        "azure_fast_inline_audio_size_mb": size_mb,
        "azure_fast_inline_duration_seconds": round(duration_seconds, 1) if duration_seconds is not None else None,
        "azure_fast_inline_max_mb": max_size_mb,
        "azure_fast_inline_max_duration_seconds": max_duration_seconds,
    }


def azure_locale_from_language(language: str | None) -> str:
    locales = azure_locales_from_language(language)
    return locales[0] if locales else "auto"


def azure_locales_from_language(language: str | None) -> list[str]:
    value = (language or "").strip().lower()
    if value in {"en", "en-us", "english"}:
        return ["en-US"]
    if value in {"zh", "zh-cn", "chinese", "mandarin"}:
        return ["zh-CN"]
    return list(DEFAULT_AZURE_AUTO_LOCALES)


def azure_short_audio_locale_from_language(language: str | None) -> str:
    locales = azure_locales_from_language(language)
    if locales:
        return locales[0]
    return "en-US"


def normalize_azure_speech_address(value: str | None) -> str:
    """Accept either a region name or an Azure Speech service address."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    raw = AZURE_REGION_ALIASES.get(raw.lower(), raw)
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return raw
    if "." not in raw and "/" not in raw:
        return f"https://{raw}.api.cognitive.microsoft.com"
    parsed = urlparse(f"https://{raw}")
    if parsed.netloc:
        return f"https://{parsed.netloc}"
    return f"https://{raw}"


def recognize_short_audio(
    audio_path: Path | str,
    *,
    endpoint: str | None,
    api_key: str | None,
    language: str | None = "en-US",
    timeout: float = 60,
) -> dict[str, Any]:
    resolved_endpoint = normalize_azure_speech_address(endpoint)
    resolved_key = (api_key or "").strip()
    if not resolved_endpoint:
        raise RuntimeError("Azure Speech address is not configured")
    if not resolved_key:
        raise RuntimeError("Azure Speech key is not configured")
    path = Path(audio_path)
    if not path.is_file():
        raise RuntimeError(f"Audio file not found: {path}")
    data = path.read_bytes()
    request = urllib.request.Request(
        _short_audio_recognition_url(resolved_endpoint, azure_short_audio_locale_from_language(language)),
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Content-Length": str(len(data)),
            "Ocp-Apim-Subscription-Key": resolved_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Azure short audio recognition failed: HTTP {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Azure short audio recognition failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure short audio recognition returned invalid JSON") from exc


def run_short_audio_smoke_test(
    *,
    endpoint: str | None,
    api_key: str | None,
    language: str | None = "en-US",
    phrase: str | None = None,
    timeout: float = 60,
) -> dict[str, Any]:
    test_phrase = (phrase or "Hello, this is a FluentFlow Azure speech test.").strip()
    if not test_phrase:
        test_phrase = "Hello, this is a FluentFlow Azure speech test."
    started_at = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="fluentflow_azure_smoke_") as td:
        wav_path = Path(td) / "azure_smoke.wav"
        _create_local_tts_wav(test_phrase, wav_path)
        payload = recognize_short_audio(
            wav_path,
            endpoint=endpoint,
            api_key=api_key,
            language=language,
            timeout=timeout,
        )
    recognition_status = str(payload.get("RecognitionStatus") or "")
    display_text = str(payload.get("DisplayText") or "").strip()
    ok = recognition_status.lower() == "success" and bool(display_text)
    return {
        "ok": ok,
        "recognition_status": recognition_status or "Unknown",
        "display_text": display_text,
        "language": azure_short_audio_locale_from_language(language),
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        "endpoint_host": urlparse(normalize_azure_speech_address(endpoint)).netloc,
    }


def normalize_azure_blob_container_sas_url(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.path.strip("/"):
        raise RuntimeError(
            "Azure Blob container SAS URL is invalid. Paste the full HTTPS container SAS URL, "
            "for example https://<account>.blob.core.windows.net/<container>?<sas>."
        )
    if not parsed.query:
        raise RuntimeError("Azure Blob container SAS URL is missing the SAS query string.")
    container_path = "/" + parsed.path.strip("/").split("/")[0]
    return urlunparse((parsed.scheme, parsed.netloc, container_path, "", parsed.query, ""))


def transcribe_audio_batch(
    audio_path: Path | str,
    *,
    endpoint: str | None,
    api_key: str | None,
    container_sas_url: str | None,
    locale: str | None = "zh-CN",
    diarization_enabled: bool = False,
    diarization_max_speakers: int = 5,
    display_name: str | None = None,
    timeout: float = 600,
    poll_interval_seconds: float = 5,
    max_wait_seconds: float = 7200,
    progress_callback: Any | None = None,
) -> TranscriptionResult:
    resolved_endpoint = normalize_azure_speech_address(endpoint)
    resolved_key = (api_key or "").strip()
    resolved_container_sas = normalize_azure_blob_container_sas_url(container_sas_url)
    if not resolved_endpoint:
        raise RuntimeError("Azure Speech address is not configured")
    if not resolved_key:
        raise RuntimeError("Azure Speech key is not configured")
    if not resolved_container_sas:
        raise RuntimeError("Azure Blob container SAS URL is not configured")

    path = Path(audio_path)
    if not path.is_file():
        raise RuntimeError(f"Audio file not found: {path}")

    def notify(status: str, **metadata: Any) -> None:
        if progress_callback:
            progress_callback(status, metadata)

    notify("azure_batch_uploading", upload_size_mb=file_size_mb(path))
    blob_name = f"fluentflow/{uuid.uuid4().hex}/{path.name}"
    content_url = upload_audio_to_blob_sas(path, resolved_container_sas, blob_name=blob_name, timeout=timeout)

    active_locale, language_identification = _batch_locale_config(locale)
    notify("azure_batch_submitting")
    submission = submit_batch_transcription(
        endpoint=resolved_endpoint,
        api_key=resolved_key,
        content_urls=[content_url],
        locale=active_locale,
        display_name=display_name or f"FluentFlow {path.stem}",
        language_identification=language_identification,
        diarization_enabled=diarization_enabled,
        diarization_max_speakers=diarization_max_speakers,
        timeout=timeout,
    )
    transcription_url = submission.get("self") or submission.get("location")
    files_url = _transcription_files_url(submission)
    if not transcription_url:
        raise RuntimeError("Azure Batch transcription submission did not return a status URL")

    notify("azure_batch_waiting", transcription_url=_redact_query(transcription_url))
    completed = poll_batch_transcription(
        transcription_url,
        api_key=resolved_key,
        timeout=timeout,
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
        progress_callback=progress_callback,
    )
    files_url = files_url or _transcription_files_url(completed)
    if not files_url:
        raise RuntimeError("Azure Batch transcription did not return a result files URL")

    notify("azure_batch_downloading")
    result_payload = download_batch_transcription_result(files_url, api_key=resolved_key, timeout=timeout)
    return parse_batch_transcription_result(result_payload, locale=active_locale)


def upload_audio_to_blob_sas(
    audio_path: Path | str,
    container_sas_url: str,
    *,
    blob_name: str | None = None,
    timeout: float = 600,
) -> str:
    path = Path(audio_path)
    container_url = normalize_azure_blob_container_sas_url(container_sas_url)
    target_blob_name = (blob_name or path.name).strip().lstrip("/")
    if not target_blob_name:
        raise RuntimeError("Azure Blob upload target name is empty")
    blob_url = _blob_sas_url(container_url, target_blob_name)
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = path.read_bytes()
    request = urllib.request.Request(
        blob_url,
        data=data,
        method="PUT",
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
            "x-ms-blob-type": "BlockBlob",
            "x-ms-version": AZURE_BLOB_SERVICE_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status not in {200, 201, 202}:
                raise RuntimeError(f"Azure Blob upload failed: HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Azure Blob upload failed: HTTP {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Azure Blob upload failed: {exc.reason}") from exc
    return blob_url


def submit_batch_transcription(
    *,
    endpoint: str,
    api_key: str,
    content_urls: list[str],
    locale: str,
    display_name: str,
    language_identification: dict[str, Any] | None = None,
    diarization_enabled: bool = False,
    diarization_max_speakers: int = 5,
    timeout: float = 600,
    api_version: str = DEFAULT_BATCH_TRANSCRIPTION_API_VERSION,
) -> dict[str, Any]:
    if not content_urls:
        raise RuntimeError("Azure Batch transcription requires at least one content URL")
    properties: dict[str, Any] = {
        "wordLevelTimestampsEnabled": True,
        "displayFormWordLevelTimestampsEnabled": True,
        "punctuationMode": "DictatedAndAutomatic",
        "profanityFilterMode": "None",
        "timeToLiveHours": 48,
    }
    if language_identification:
        properties["languageIdentification"] = language_identification
    if diarization_enabled:
        properties["diarization"] = {
            "enabled": True,
            "maxSpeakers": max(2, min(int(diarization_max_speakers or 5), 35)),
        }
    payload = {
        "displayName": display_name.strip() or "FluentFlow transcription",
        "locale": locale,
        "contentUrls": content_urls,
        "properties": properties,
    }
    request = urllib.request.Request(
        _batch_submit_url(endpoint, api_version),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            location = response.headers.get("Location")
            if location:
                body["location"] = location
            return body
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Azure Batch transcription submit failed: HTTP {exc.code} {message}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure Batch transcription submit returned invalid JSON") from exc


def poll_batch_transcription(
    transcription_url: str,
    *,
    api_key: str,
    timeout: float = 600,
    poll_interval_seconds: float = 5,
    max_wait_seconds: float = 7200,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    last_status: str | None = None
    while True:
        payload, retry_after = _get_batch_json(transcription_url, api_key=api_key, timeout=timeout)
        status = str(payload.get("status") or "")
        if progress_callback and status != last_status:
            progress_callback("azure_batch_waiting", {"azure_batch_status": status or "Unknown"})
            last_status = status
        if status.lower() == "succeeded":
            return payload
        if status.lower() == "failed":
            error = payload.get("properties", {}).get("error") or payload.get("error") or {}
            raise RuntimeError(f"Azure Batch transcription failed: {json.dumps(error, ensure_ascii=False)[:800]}")
        if time.perf_counter() - started_at > max_wait_seconds:
            raise RuntimeError("Azure Batch transcription timed out before completion")
        delay = retry_after or poll_interval_seconds
        time.sleep(max(1.0, min(float(delay), 60.0)))


def download_batch_transcription_result(files_url: str, *, api_key: str, timeout: float = 600) -> dict[str, Any]:
    files_payload, _ = _get_batch_json(files_url, api_key=api_key, timeout=timeout)
    values = files_payload.get("values") or files_payload.get("value")
    if not isinstance(values, list):
        raise RuntimeError("Azure Batch transcription files response is invalid")
    transcription_file = None
    for item in values:
        if isinstance(item, dict) and item.get("kind") == "Transcription":
            transcription_file = item
            break
    if not transcription_file:
        raise RuntimeError("Azure Batch transcription result file was not found")
    content_url = (
        transcription_file.get("links", {}).get("contentUrl")
        if isinstance(transcription_file.get("links"), dict)
        else None
    )
    if not content_url:
        raise RuntimeError("Azure Batch transcription result file has no content URL")
    try:
        with urllib.request.urlopen(content_url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Azure Batch transcription result download failed: HTTP {exc.code} {message}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure Batch transcription result returned invalid JSON") from exc


def transcribe_audio_fast(
    audio_path: Path | str,
    *,
    endpoint: str | None,
    api_key: str | None,
    locale: str | None = "zh-CN",
    locales: list[str] | tuple[str, ...] | None = None,
    diarization_enabled: bool = False,
    diarization_max_speakers: int = 5,
    timeout: float = 600,
    max_retries: int = 3,
) -> TranscriptionResult:
    resolved_endpoint = normalize_azure_speech_address(endpoint)
    resolved_key = (api_key or "").strip()
    if not resolved_endpoint:
        raise RuntimeError("Azure Speech address is not configured")
    if not resolved_key:
        raise RuntimeError("Azure Speech key is not configured")

    path = Path(audio_path)
    if not path.is_file():
        raise RuntimeError(f"Audio file not found: {path}")

    requested_locales = list(locales) if locales is not None else azure_locales_from_language(locale)
    active_locales = list(requested_locales)
    max_speakers = max(2, min(int(diarization_max_speakers or 5), 35))
    definition = _fast_transcription_definition(
        active_locales,
        diarization_enabled=diarization_enabled,
        diarization_max_speakers=max_speakers,
    )

    api_versions = _fast_transcription_api_versions(FAST_TRANSCRIPTION_API_VERSION)
    api_version_index = 0
    api_version = api_versions[api_version_index]
    url = _fast_transcription_url(resolved_endpoint, api_version)
    request = _build_fast_transcription_request(url, path, definition, resolved_key)
    payload: dict[str, Any]
    diarization_error: str | None = None
    upload_attempt = 0
    for _ in range(max(0, int(max_retries)) + 4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                break
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")[:800]
            if active_locales and _is_invalid_locale_error(exc.code, message):
                active_locales = []
                definition = _fast_transcription_definition(
                    active_locales,
                    diarization_enabled=diarization_enabled,
                    diarization_max_speakers=max_speakers,
                )
                request = _build_fast_transcription_request(url, path, definition, resolved_key)
                continue
            if _is_invalid_model_error(exc.code, message) and api_version_index + 1 < len(api_versions):
                api_version_index += 1
                api_version = api_versions[api_version_index]
                url = _fast_transcription_url(resolved_endpoint, api_version)
                request = _build_fast_transcription_request(url, path, definition, resolved_key)
                continue
            if _is_invalid_model_error(exc.code, message):
                raise RuntimeError(
                    _invalid_model_error_message(
                        endpoint=resolved_endpoint,
                        api_version=api_version,
                    )
                ) from exc
            if diarization_enabled and _is_diarization_unsupported_error(exc.code, message):
                diarization_enabled = False
                definition = _fast_transcription_definition(
                    active_locales,
                    diarization_enabled=False,
                    diarization_max_speakers=max_speakers,
                )
                request = _build_fast_transcription_request(url, path, definition, resolved_key)
                diarization_error = (
                    "Azure Fast Transcription does not support speaker diarization "
                    "for this request; retried without speaker diarization."
                )
                continue
            raise RuntimeError(f"Azure fast transcription failed: HTTP {exc.code} {message}") from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if upload_attempt < max_retries and _is_transient_upload_error(reason):
                upload_attempt += 1
                time.sleep(min(2.0, 0.5 * upload_attempt))
                continue
            raise RuntimeError(_network_error_message(reason, path, resolved_endpoint)) from exc
        except ssl.SSLError as exc:
            if upload_attempt < max_retries and _is_transient_upload_error(exc):
                upload_attempt += 1
                time.sleep(min(2.0, 0.5 * upload_attempt))
                continue
            raise RuntimeError(_network_error_message(exc, path, resolved_endpoint)) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Azure fast transcription returned invalid JSON") from exc
    else:  # pragma: no cover - loop always breaks or raises
        raise RuntimeError("Azure fast transcription failed")
    fallback_locale = active_locales[0] if len(active_locales) == 1 else "auto"
    result = parse_fast_transcription_result(payload, locale=fallback_locale)
    if diarization_error:
        return replace(result, diarization_error=diarization_error)
    return result


def parse_fast_transcription_result(payload: dict[str, Any], *, locale: str = "zh-CN") -> TranscriptionResult:
    phrases = payload.get("phrases")
    if not isinstance(phrases, list):
        phrases = []

    segments: list[TranscriptSegment] = []
    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        text = _phrase_text(phrase)
        if not text:
            continue
        start_ms = _number_value(phrase, "offsetMilliseconds", "offsetInTicks")
        duration_ms = _number_value(phrase, "durationMilliseconds", "durationInTicks")
        start = _milliseconds_to_seconds(start_ms)
        duration = _milliseconds_to_seconds(duration_ms)
        end = start + duration if duration > 0 else start
        segments.append(TranscriptSegment(start=start, end=end, text=text, speaker=_phrase_speaker(phrase)))

    text = _combined_text(payload) or " ".join(segment.text for segment in segments).strip()
    duration = _duration_seconds(payload, segments)
    if text and not segments:
        segments.append(TranscriptSegment(start=0.0, end=duration or 0.0, text=text))

    detected_locale = _detected_locale(payload, fallback=locale)
    return TranscriptionResult(
        text=text,
        segments=tuple(segments),
        language=detected_locale,
        language_probability=None,
        duration=duration,
        model_cache_hit=None,
        model_load_seconds=None,
        model_source="azure_speech_fast_transcription",
        compute_type=None,
        device_requested="cloud",
        device_resolved="azure",
        cpu_threads=None,
        num_workers=None,
        vad_filter=None,
    )


def parse_batch_transcription_result(payload: dict[str, Any], *, locale: str = "zh-CN") -> TranscriptionResult:
    phrases = payload.get("recognizedPhrases")
    if not isinstance(phrases, list):
        phrases = payload.get("phrases")
    if not isinstance(phrases, list):
        phrases = []

    segments: list[TranscriptSegment] = []
    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        text = _phrase_text(phrase)
        if not text:
            continue
        start_ms = _number_value(phrase, "offsetMilliseconds", "offsetInTicks")
        duration_ms = _number_value(phrase, "durationMilliseconds", "durationInTicks")
        start = _milliseconds_to_seconds(start_ms)
        duration = _milliseconds_to_seconds(duration_ms)
        end = start + duration if duration > 0 else start
        segments.extend(_segments_from_phrase(phrase, text=text, start=start, end=end, speaker=_phrase_speaker(phrase)))

    text = _combined_text(payload) or " ".join(segment.text for segment in segments).strip()
    duration = _duration_seconds(payload, segments)
    if text and not segments:
        segments.append(TranscriptSegment(start=0.0, end=duration or 0.0, text=text))

    detected_locale = _detected_locale(payload, fallback=locale)
    return TranscriptionResult(
        text=text,
        segments=tuple(segments),
        language=detected_locale,
        language_probability=None,
        duration=duration,
        model_cache_hit=None,
        model_load_seconds=None,
        model_source="azure_speech_batch_transcription",
        compute_type=None,
        device_requested="cloud",
        device_resolved="azure",
        cpu_threads=None,
        num_workers=None,
        vad_filter=None,
    )


def _azure_display_segment_max_chars() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_CHARS", "80")), 20)
    except ValueError:
        return 80


def _azure_display_segment_max_seconds() -> float:
    try:
        return max(float(os.environ.get("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_SECONDS", "12")), 3.0)
    except ValueError:
        return 12.0


def _segments_from_phrase(
    phrase: dict[str, Any],
    *,
    text: str,
    start: float,
    end: float,
    speaker: str | None,
) -> list[TranscriptSegment]:
    duration = max(end - start, 0.0)
    max_chars = _azure_display_segment_max_chars()
    max_seconds = _azure_display_segment_max_seconds()
    target_count = max(1, int((duration + max_seconds - 0.001) // max_seconds)) if duration > 0 else 1
    chunks = _split_display_text(text, max_chars=max_chars, min_chunks=target_count)
    if len(chunks) <= 1:
        return [TranscriptSegment(start=start, end=end, text=text, speaker=speaker)]

    words = _phrase_word_timings(phrase)
    if words:
        return _segments_from_word_timings(chunks, words, phrase_start=start, phrase_end=end, speaker=speaker)
    return _segments_from_proportions(chunks, phrase_start=start, phrase_end=end, speaker=speaker)


def _split_display_text(text: str, *, max_chars: int, min_chunks: int = 1) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    units = [match.group(0).strip() for match in _DISPLAY_SEGMENT_END_RE.finditer(raw) if match.group(0).strip()]
    if not units:
        units = [raw]

    chunks: list[str] = []
    current = ""
    for index, unit in enumerate(units):
        remaining_units = len(units) - index
        should_keep_unit_boundary = (
            bool(current)
            and len(chunks) + 1 < min_chunks
            and len(chunks) + 1 + remaining_units >= min_chunks
        )
        if current and len(current) + len(unit) > max_chars:
            chunks.append(current.strip())
            current = unit
        elif should_keep_unit_boundary:
            chunks.append(current.strip())
            current = unit
        else:
            current = f"{current}{unit}" if _is_cjk_like(current + unit) else f"{current} {unit}".strip()
    if current.strip():
        chunks.append(current.strip())

    expanded: list[str] = []
    for chunk in chunks:
        expanded.extend(_split_long_chunk(chunk, max_chars=max_chars))
    chunks = expanded or [raw]

    while len(chunks) < min_chunks:
        index = max(range(len(chunks)), key=lambda i: len(chunks[i]))
        left, right = _split_chunk_near_middle(chunks[index])
        if not left or not right:
            break
        chunks[index : index + 1] = [left, right]

    return [chunk for chunk in chunks if chunk.strip()]


def _split_long_chunk(text: str, *, max_chars: int) -> list[str]:
    chunk = text.strip()
    if len(chunk) <= max_chars:
        return [chunk]
    parts: list[str] = []
    pending = chunk
    while len(pending) > max_chars:
        left, right = _split_chunk_near(pending, max_chars)
        if not left or not right:
            break
        parts.append(left)
        pending = right
    if pending:
        parts.append(pending)
    return parts or [chunk]


def _split_chunk_near_middle(text: str) -> tuple[str, str]:
    return _split_chunk_near(text, max(1, len(text) // 2))


def _split_chunk_near(text: str, target: int) -> tuple[str, str]:
    value = text.strip()
    if len(value) <= 1:
        return value, ""
    target = max(1, min(target, len(value) - 1))
    candidates = [
        match.start() + 1
        for match in _DISPLAY_SEGMENT_SOFT_RE.finditer(value)
        if 0 < match.start() + 1 < len(value)
    ]
    if candidates:
        cut = min(candidates, key=lambda pos: abs(pos - target))
    else:
        cut = target
    return value[:cut].strip(), value[cut:].strip()


def _segments_from_word_timings(
    chunks: list[str],
    words: list[AzureWordTiming],
    *,
    phrase_start: float,
    phrase_end: float,
    speaker: str | None,
) -> list[TranscriptSegment]:
    word_lengths = [max(len(_normalize_timing_text(word.text)), 1) for word in words]
    total = sum(word_lengths)
    chunk_lengths = [max(len(_normalize_timing_text(chunk)), 1) for chunk in chunks]
    chunk_total = sum(chunk_lengths)
    if total <= 0 or chunk_total <= 0:
        return _segments_from_proportions(chunks, phrase_start=phrase_start, phrase_end=phrase_end, speaker=speaker)

    segments: list[TranscriptSegment] = []
    word_index = 0
    word_progress = 0
    chunk_progress = 0
    for chunk_index, chunk in enumerate(chunks):
        chunk_progress += chunk_lengths[chunk_index]
        target = round(chunk_progress / chunk_total * total)
        target = max(target, word_progress + 1)
        start_index = min(word_index, len(words) - 1)
        while word_index < len(words) - 1 and word_progress + word_lengths[word_index] < target:
            word_progress += word_lengths[word_index]
            word_index += 1
        end_index = min(word_index, len(words) - 1)
        start = words[start_index].start if chunk_index > 0 else phrase_start
        end = words[end_index].end
        if chunk_index == len(chunks) - 1:
            end = max(end, phrase_end)
        segments.append(_bounded_segment(start, end, chunk, speaker, phrase_start, phrase_end))
        word_index = min(end_index + 1, len(words) - 1)
        word_progress = min(target, total)
    return _smooth_segment_boundaries(segments, phrase_start=phrase_start, phrase_end=phrase_end)


def _segments_from_proportions(
    chunks: list[str],
    *,
    phrase_start: float,
    phrase_end: float,
    speaker: str | None,
) -> list[TranscriptSegment]:
    duration = max(phrase_end - phrase_start, 0.0)
    lengths = [max(len(_normalize_timing_text(chunk)), 1) for chunk in chunks]
    total = sum(lengths)
    segments: list[TranscriptSegment] = []
    elapsed = 0
    for index, chunk in enumerate(chunks):
        start = phrase_start + duration * (elapsed / total) if total else phrase_start
        elapsed += lengths[index]
        end = phrase_start + duration * (elapsed / total) if total else phrase_end
        if index == len(chunks) - 1:
            end = phrase_end
        segments.append(_bounded_segment(start, end, chunk, speaker, phrase_start, phrase_end))
    return _smooth_segment_boundaries(segments, phrase_start=phrase_start, phrase_end=phrase_end)


def _bounded_segment(
    start: float,
    end: float,
    text: str,
    speaker: str | None,
    phrase_start: float,
    phrase_end: float,
) -> TranscriptSegment:
    safe_start = round(max(phrase_start, min(float(start), phrase_end)), 3)
    safe_end = round(max(safe_start, min(float(end), phrase_end)), 3)
    return TranscriptSegment(start=safe_start, end=safe_end, text=text.strip(), speaker=speaker)


def _smooth_segment_boundaries(
    segments: list[TranscriptSegment],
    *,
    phrase_start: float,
    phrase_end: float,
) -> list[TranscriptSegment]:
    if not segments:
        return []
    smoothed: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        start = segment.start if index > 0 else phrase_start
        if index < len(segments) - 1:
            next_start = segments[index + 1].start
            end = max(segment.end, next_start)
        else:
            end = phrase_end
        smoothed.append(TranscriptSegment(start=round(start, 3), end=round(max(start, end), 3), text=segment.text, speaker=segment.speaker))
    return smoothed


def _phrase_word_timings(phrase: dict[str, Any]) -> list[AzureWordTiming]:
    candidates: list[Any] = []
    for key in ("displayWords", "display_words", "words", "Words"):
        value = phrase.get(key)
        if isinstance(value, list):
            candidates.append(value)
    nbest = phrase.get("nBest") or phrase.get("n_best")
    if isinstance(nbest, list):
        for item in nbest:
            if not isinstance(item, dict):
                continue
            for key in ("displayWords", "display_words", "words", "Words"):
                value = item.get(key)
                if isinstance(value, list):
                    candidates.append(value)

    timings: list[AzureWordTiming] = []
    for words in candidates:
        timings = [_word_timing(word) for word in words if isinstance(word, dict)]
        timings = [word for word in timings if word is not None]
        if timings:
            return sorted(timings, key=lambda word: (word.start, word.end))
    return []


def _word_timing(word: dict[str, Any]) -> AzureWordTiming | None:
    text = _word_text(word)
    if not text:
        return None
    start_ms = _number_value(word, "offsetMilliseconds", "offsetInTicks")
    duration_ms = _number_value(word, "durationMilliseconds", "durationInTicks")
    start = _milliseconds_to_seconds(start_ms)
    duration = _milliseconds_to_seconds(duration_ms)
    if duration <= 0:
        return None
    return AzureWordTiming(text=text, start=start, end=round(start + duration, 3))


def _word_text(word: dict[str, Any]) -> str:
    for key in ("display", "word", "text", "lexical"):
        value = word.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_timing_text(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?;；:：'\"“”‘’（）()【】\[\]《》<>-]+", "", text or "")


def _is_cjk_like(text: str) -> bool:
    compact = (text or "").strip()
    if not compact:
        return True
    cjk = sum(1 for char in compact if "\u4e00" <= char <= "\u9fff")
    return cjk >= max(1, len(compact) // 3)


def _build_multipart_body(audio_path: Path, definition: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"fluentflow-{uuid.uuid4().hex}"
    content_type = f"multipart/form-data; boundary={boundary}"
    audio_type = mimetypes.guess_type(str(audio_path))[0] or "application/octet-stream"
    parts: list[bytes] = []

    def add_header(value: str) -> None:
        parts.append(value.encode("utf-8"))

    add_header(f"--{boundary}\r\n")
    add_header('Content-Disposition: form-data; name="definition"\r\n')
    add_header("Content-Type: application/json\r\n\r\n")
    parts.append(json.dumps(definition, ensure_ascii=False).encode("utf-8"))
    add_header("\r\n")

    add_header(f"--{boundary}\r\n")
    add_header(f'Content-Disposition: form-data; name="audio"; filename="{audio_path.name}"\r\n')
    add_header(f"Content-Type: {audio_type}\r\n\r\n")
    parts.append(audio_path.read_bytes())
    add_header("\r\n")

    add_header(f"--{boundary}--\r\n")
    return b"".join(parts), content_type


def _fast_transcription_definition(
    locales: list[str] | tuple[str, ...],
    *,
    diarization_enabled: bool,
    diarization_max_speakers: int,
) -> dict[str, Any]:
    definition: dict[str, Any] = {}
    if locales:
        definition["locales"] = list(locales)
    if diarization_enabled:
        definition["diarization"] = {
            "enabled": True,
            "maxSpeakers": diarization_max_speakers,
        }
    return definition


def _fast_transcription_url(endpoint: str, api_version: str) -> str:
    return (
        f"{endpoint}/speechtotext/transcriptions:transcribe"
        f"?api-version={api_version}"
    )


def _batch_submit_url(endpoint: str, api_version: str) -> str:
    return (
        f"{normalize_azure_speech_address(endpoint)}/speechtotext/transcriptions:submit"
        f"?api-version={api_version}"
    )


def _short_audio_recognition_url(endpoint: str, language: str) -> str:
    parsed = urlparse(normalize_azure_speech_address(endpoint))
    host = parsed.netloc or parsed.path
    path = "/speech/recognition/conversation/cognitiveservices/v1"
    if host.endswith(".api.cognitive.microsoft.com"):
        region = host.split(".", 1)[0]
        host = f"{region}.stt.speech.microsoft.com"
    elif host.endswith(".cognitiveservices.azure.com"):
        path = "/stt/speech/recognition/conversation/cognitiveservices/v1"
    query = urlencode({"language": language, "format": "simple"})
    return urlunparse(("https", host, path, "", query, ""))


def _create_local_tts_wav(phrase: str, output_path: Path) -> None:
    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if not say:
        raise RuntimeError("Azure smoke test requires macOS 'say' to generate a short local test voice.")
    if not ffmpeg:
        raise RuntimeError("Azure smoke test requires ffmpeg to prepare 16 kHz mono PCM WAV audio.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    aiff_path = output_path.with_suffix(".aiff")
    try:
        subprocess.run([say, "-o", str(aiff_path), phrase], check=True, capture_output=True, text=True, timeout=20)
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(aiff_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-acodec",
                "pcm_s16le",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"Azure smoke test audio generation failed: {detail or exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Azure smoke test audio generation timed out") from exc


def _blob_sas_url(container_sas_url: str, blob_name: str) -> str:
    parsed = urlparse(normalize_azure_blob_container_sas_url(container_sas_url))
    encoded_name = "/".join(quote(part, safe="") for part in blob_name.strip("/").split("/") if part)
    path = f"{parsed.path.rstrip('/')}/{encoded_name}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def _batch_locale_config(language: str | None) -> tuple[str, dict[str, Any] | None]:
    locales = azure_locales_from_language(language)
    if len(locales) == 1:
        return locales[0], None
    value = (language or "").strip().lower()
    if value in {"auto", "", "detect", "auto-detect"}:
        return "zh-CN", {
            "candidateLocales": ["zh-CN", "en-US"],
            "mode": "Continuous",
        }
    return "zh-CN", None


def _transcription_files_url(payload: dict[str, Any]) -> str | None:
    links = payload.get("links")
    if isinstance(links, dict):
        value = links.get("files")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _get_batch_json(url: str, *, api_key: str, timeout: float) -> tuple[dict[str, Any], int | None]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Ocp-Apim-Subscription-Key": api_key},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            retry_after = response.headers.get("Retry-After")
            try:
                retry_seconds = int(retry_after) if retry_after else None
            except ValueError:
                retry_seconds = None
            return json.loads(response.read().decode("utf-8")), retry_seconds
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"Azure Batch transcription request failed: HTTP {exc.code} {message}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure Batch transcription returned invalid JSON") from exc


def _redact_query(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "<redacted>", ""))


def _fast_transcription_api_versions(primary: str) -> list[str]:
    versions = [
        (primary or "").strip() or DEFAULT_FAST_TRANSCRIPTION_API_VERSION,
        DEFAULT_FAST_TRANSCRIPTION_API_VERSION,
        FALLBACK_FAST_TRANSCRIPTION_API_VERSION,
    ]
    out: list[str] = []
    for version in versions:
        if version and version not in out:
            out.append(version)
    return out


def _build_fast_transcription_request(
    url: str,
    audio_path: Path,
    definition: dict[str, Any],
    api_key: str,
) -> urllib.request.Request:
    body, content_type = _build_multipart_body(audio_path, definition)
    return urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Ocp-Apim-Subscription-Key": api_key,
        },
    )


def _is_diarization_unsupported_error(status_code: int, message: str) -> bool:
    if status_code != 400:
        return False
    text = (message or "").lower()
    return "diarization" in text and "not supported" in text


def _is_invalid_locale_error(status_code: int, message: str) -> bool:
    if status_code != 400:
        return False
    text = (message or "").lower()
    return "invalidlocale" in text or "specified locale is not supported" in text


def _is_invalid_model_error(status_code: int, message: str) -> bool:
    if status_code != 400:
        return False
    text = (message or "").lower()
    return "invalidmodel" in text or "specified model is not supported" in text


def _invalid_model_error_message(*, endpoint: str, api_version: str) -> str:
    host = urlparse(endpoint).netloc or endpoint
    return (
        "Azure Fast Transcription is not supported by the current Speech resource, "
        f"region, or API version. Host={host}, api-version={api_version}. "
        "This is not a file-size failure. Use a Speech resource in a Fast "
        "Transcription supported region, or switch this task to local STT."
    )


def _is_transient_upload_error(reason: Any) -> bool:
    text = str(reason).lower()
    return any(
        marker in text
        for marker in (
            "eof occurred",
            "ssl",
            "connection reset",
            "connection aborted",
            "broken pipe",
            "remote end closed",
            "timed out",
            "timeout",
        )
    )


def _network_error_message(reason: Any, audio_path: Path, endpoint: str) -> str:
    size = file_size_mb(audio_path)
    host = urlparse(endpoint).netloc or endpoint
    size_text = f"{size:g} MB" if size is not None else "unknown size"
    return (
        "Azure fast transcription upload failed: "
        f"{reason}. Uploaded audio was {size_text} to {host}. "
        "This usually means the HTTPS upload was interrupted by the network or Azure edge service; "
        "it is not the same as a successful transcription failure. Try again, use local STT, "
        "or reduce the uploaded audio size."
    )


def _phrase_text(phrase: dict[str, Any]) -> str:
    for key in ("text", "display", "lexical"):
        value = phrase.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nbest = phrase.get("nBest") or phrase.get("n_best")
    if isinstance(nbest, list):
        for item in nbest:
            if isinstance(item, dict):
                text = _phrase_text(item)
                if text:
                    return text
    return ""


def _phrase_speaker(phrase: dict[str, Any]) -> str | None:
    value = phrase.get("speaker")
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.upper().startswith("SPEAKER"):
        return text
    return f"SPEAKER_{text}"


def _combined_text(payload: dict[str, Any]) -> str:
    combined = payload.get("combinedPhrases") or payload.get("combinedRecognizedPhrases") or payload.get("combined_phrases")
    if not isinstance(combined, list):
        return ""
    for item in combined:
        if not isinstance(item, dict):
            continue
        text = _phrase_text(item)
        if text:
            return text
    return ""


def _detected_locale(payload: dict[str, Any], *, fallback: str | None) -> str | None:
    phrases = payload.get("phrases") or payload.get("recognizedPhrases")
    if isinstance(phrases, list):
        for phrase in phrases:
            if not isinstance(phrase, dict):
                continue
            locale = phrase.get("locale")
            if isinstance(locale, str) and locale.strip():
                return locale.strip()
    return fallback


def _number_value(payload: dict[str, Any], milliseconds_key: str, ticks_key: str) -> float:
    value = payload.get(milliseconds_key)
    if isinstance(value, (int, float)):
        return float(value)
    ticks = payload.get(ticks_key)
    if isinstance(ticks, (int, float)):
        return float(ticks) / 10_000
    return 0.0


def _milliseconds_to_seconds(value: float) -> float:
    return round(max(value, 0.0) / 1000, 3)


def _duration_seconds(payload: dict[str, Any], segments: list[TranscriptSegment]) -> float | None:
    duration_ms = _number_value(payload, "durationMilliseconds", "durationInTicks")
    if duration_ms > 0:
        return _milliseconds_to_seconds(duration_ms)
    if segments:
        return max(segment.end for segment in segments)
    return None
