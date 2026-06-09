from __future__ import annotations

import io
import urllib.error

import pytest

from backend.core.azure_stt import (
    DEFAULT_FAST_TRANSCRIPTION_API_VERSION,
    FALLBACK_FAST_TRANSCRIPTION_API_VERSION,
    azure_locale_from_language,
    azure_locales_from_language,
    recognize_short_audio,
    normalize_azure_speech_address,
    parse_fast_transcription_result,
    run_short_audio_smoke_test,
    transcribe_audio_fast,
)


def test_azure_locale_from_language_maps_fluentflow_values() -> None:
    assert azure_locales_from_language("auto") == []
    assert azure_locale_from_language("auto") == "auto"
    assert azure_locale_from_language("zh") == "zh-CN"
    assert azure_locale_from_language("en") == "en-US"


def test_normalize_azure_speech_address_accepts_region_or_address() -> None:
    assert normalize_azure_speech_address("eastasia") == "https://eastasia.api.cognitive.microsoft.com"
    assert normalize_azure_speech_address("eastaisa") == "https://eastasia.api.cognitive.microsoft.com"
    assert normalize_azure_speech_address("eastasia.api.cognitive.microsoft.com") == "https://eastasia.api.cognitive.microsoft.com"
    assert normalize_azure_speech_address("https://eastasia.api.cognitive.microsoft.com/") == "https://eastasia.api.cognitive.microsoft.com"
    assert (
        normalize_azure_speech_address(
            f"https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version={DEFAULT_FAST_TRANSCRIPTION_API_VERSION}"
        )
        == "https://eastasia.api.cognitive.microsoft.com"
    )


def test_recognize_short_audio_uses_regional_stt_endpoint(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"RecognitionStatus":"Success","DisplayText":"Hello."}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["data"] = request.data
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = recognize_short_audio(audio, endpoint="eastasia", api_key="key", language="en-US")

    assert result["RecognitionStatus"] == "Success"
    assert captured["url"].startswith("https://eastasia.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1")
    assert "language=en-US" in captured["url"]
    assert captured["headers"]["Content-type"] == "audio/wav; codecs=audio/pcm; samplerate=16000"
    assert captured["headers"]["Ocp-apim-subscription-key"] == "key"
    assert captured["data"] == b"RIFFfake"


def test_run_short_audio_smoke_test_reports_success(tmp_path, monkeypatch) -> None:
    def fake_create_local_tts_wav(phrase, output_path):
        output_path.write_bytes(b"RIFFfake")

    def fake_recognize_short_audio(audio_path, **kwargs):
        return {"RecognitionStatus": "Success", "DisplayText": "Hello FluentFlow."}

    monkeypatch.setattr("backend.core.azure_stt._create_local_tts_wav", fake_create_local_tts_wav)
    monkeypatch.setattr("backend.core.azure_stt.recognize_short_audio", fake_recognize_short_audio)

    result = run_short_audio_smoke_test(endpoint="eastasia", api_key="key")

    assert result["ok"] is True
    assert result["display_text"] == "Hello FluentFlow."
    assert result["endpoint_host"] == "eastasia.api.cognitive.microsoft.com"


def test_parse_fast_transcription_result_combines_phrases_and_timestamps() -> None:
    result = parse_fast_transcription_result(
        {
            "durationMilliseconds": 5000,
            "combinedPhrases": [{"text": "今天我们讨论产品经理岗位。"}],
            "phrases": [
                {
                    "offsetMilliseconds": 0,
                    "durationMilliseconds": 2100,
                    "text": "今天我们讨论",
                },
                {
                    "offsetMilliseconds": 2100,
                    "durationMilliseconds": 2900,
                    "text": "产品经理岗位。",
                    "speaker": 2,
                },
            ],
        },
        locale="zh-CN",
    )

    assert result.text == "今天我们讨论产品经理岗位。"
    assert result.language == "zh-CN"
    assert result.duration == 5
    assert result.model_source == "azure_speech_fast_transcription"
    assert result.device_requested == "cloud"
    assert [(segment.start, segment.end, segment.text) for segment in result.segments] == [
        (0, 2.1, "今天我们讨论"),
        (2.1, 5.0, "产品经理岗位。"),
    ]
    assert result.segments[1].speaker == "SPEAKER_2"


def test_parse_fast_transcription_result_supports_tick_offsets() -> None:
    result = parse_fast_transcription_result(
        {
            "phrases": [
                {
                    "offsetInTicks": 10_000_000,
                    "durationInTicks": 20_000_000,
                    "display": "hello world",
                }
            ]
        },
        locale="en-US",
    )

    assert result.text == "hello world"
    assert [(segment.start, segment.end) for segment in result.segments] == [(1.0, 3.0)]


def test_parse_fast_transcription_result_uses_detected_phrase_locale() -> None:
    result = parse_fast_transcription_result(
        {
            "combinedPhrases": [{"text": "hello"}],
            "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "hello", "locale": "en-US"}],
        },
        locale="auto",
    )

    assert result.language == "en-US"


def test_transcribe_audio_fast_sends_diarization_definition(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        captured["body"] = request.data
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    transcribe_audio_fast(
        audio,
        endpoint="eastus",
        api_key="key",
        locales=["zh-CN", "en-US"],
        diarization_enabled=True,
    )

    assert captured["timeout"] == 600
    assert captured["url"].startswith("https://eastus.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe")
    assert f"api-version={DEFAULT_FAST_TRANSCRIPTION_API_VERSION}" in captured["url"]
    assert b'"locales": ["zh-CN", "en-US"]' in captured["body"]
    assert b'"diarization": {"enabled": true, "maxSpeakers": 5}' in captured["body"]


def test_transcribe_audio_fast_falls_back_when_diarization_is_unsupported(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        bodies.append(request.data)
        if len(bodies) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"code":"InvalidRequest","message":"Diarization is currently not supported."}'
                ),
            )
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = transcribe_audio_fast(
        audio,
        endpoint="eastus",
        api_key="key",
        locales=["zh-CN", "en-US"],
        diarization_enabled=True,
    )

    assert result.text == "hello"
    assert result.diarization_error
    assert b'"diarization": {"enabled": true, "maxSpeakers": 5}' in bodies[0]
    assert b'"diarization"' not in bodies[1]


def test_transcribe_audio_fast_falls_back_when_locale_is_unsupported(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        bodies.append(request.data)
        if len(bodies) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"code":"InvalidArgument","message":"The specified locale is not supported.","innerError":{"code":"InvalidLocale"}}'
                ),
            )
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = transcribe_audio_fast(
        audio,
        endpoint="eastus",
        api_key="key",
        locales=["zh-CN"],
    )

    assert result.text == "hello"
    assert b'"locales": ["zh-CN"]' in bodies[0]
    assert b'"locales"' not in bodies[1]
    assert result.language == "auto"


def test_transcribe_audio_fast_falls_back_to_older_api_when_model_is_unsupported(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")
    urls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        if len(urls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(
                    b'{"code":"InvalidArgument","message":"The specified model is not supported.","innerError":{"code":"InvalidModel"}}'
                ),
            )
        return Response()

    monkeypatch.setattr("backend.core.azure_stt.FAST_TRANSCRIPTION_API_VERSION", DEFAULT_FAST_TRANSCRIPTION_API_VERSION)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = transcribe_audio_fast(audio, endpoint="eastus", api_key="key")

    assert result.text == "hello"
    assert f"api-version={DEFAULT_FAST_TRANSCRIPTION_API_VERSION}" in urls[0]
    assert f"api-version={FALLBACK_FAST_TRANSCRIPTION_API_VERSION}" in urls[1]


def test_transcribe_audio_fast_reports_invalid_model_as_resource_or_region_issue(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFFfake")

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(
                b'{"code":"InvalidArgument","message":"The specified model is not supported.","innerError":{"code":"InvalidModel"}}'
            ),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="not a file-size failure"):
        transcribe_audio_fast(audio, endpoint="eastasia", api_key="key")


def test_transcribe_audio_fast_retries_transient_upload_errors(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("EOF occurred in violation of protocol")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda delay: None)

    result = transcribe_audio_fast(audio, endpoint="eastus", api_key="key")

    assert result.text == "hello"
    assert calls["count"] == 2


def test_transcribe_audio_fast_retries_broken_pipe_upload_errors(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"combinedPhrases":[{"text":"hello"}],"phrases":[]}'

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError(OSError(32, "Broken pipe"))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda delay: None)

    result = transcribe_audio_fast(audio, endpoint="eastus", api_key="key")

    assert result.text == "hello"
    assert calls["count"] == 2


def test_transcribe_audio_fast_reports_upload_size_on_network_error(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("EOF occurred in violation of protocol")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda delay: None)

    with pytest.raises(RuntimeError, match="Uploaded audio was"):
        transcribe_audio_fast(audio, endpoint="eastus", api_key="key", max_retries=0)
