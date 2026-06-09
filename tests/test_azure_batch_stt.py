from __future__ import annotations

import json

from backend.core.azure_stt import (
    DEFAULT_BATCH_TRANSCRIPTION_API_VERSION,
    parse_batch_transcription_result,
    submit_batch_transcription,
    transcribe_audio_batch,
    upload_audio_to_blob_sas,
)


class Response:
    def __init__(self, payload: dict | bytes, *, status: int = 200, headers: dict[str, str] | None = None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


def test_upload_audio_to_blob_sas_puts_block_blob(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["data"] = request.data
        captured["timeout"] = timeout
        return Response(b"", status=201)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    url = upload_audio_to_blob_sas(
        audio,
        "https://acct.blob.core.windows.net/fluentflow?sp=racw&sig=secret",
        blob_name="fluentflow/task/sample.mp3",
    )

    assert url == "https://acct.blob.core.windows.net/fluentflow/fluentflow/task/sample.mp3?sp=racw&sig=secret"
    assert captured["method"] == "PUT"
    assert captured["headers"]["X-ms-blob-type"] == "BlockBlob"
    assert captured["data"] == b"audio"


def test_submit_batch_transcription_posts_content_urls(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return Response(
            {
                "self": f"https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job?api-version={DEFAULT_BATCH_TRANSCRIPTION_API_VERSION}",
                "links": {
                    "files": f"https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job/files?api-version={DEFAULT_BATCH_TRANSCRIPTION_API_VERSION}"
                },
                "status": "NotStarted",
            },
            status=201,
            headers={"Location": "https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job"},
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = submit_batch_transcription(
        endpoint="eastasia",
        api_key="key",
        content_urls=["https://acct.blob.core.windows.net/fluentflow/sample.mp3?sp=r"],
        locale="zh-CN",
        display_name="sample",
        language_identification={"candidateLocales": ["zh-CN", "en-US"], "mode": "Continuous"},
        diarization_enabled=True,
    )

    assert "transcriptions:submit" in captured["url"]
    assert f"api-version={DEFAULT_BATCH_TRANSCRIPTION_API_VERSION}" in captured["url"]
    assert captured["headers"]["Ocp-apim-subscription-key"] == "key"
    assert captured["body"]["contentUrls"] == ["https://acct.blob.core.windows.net/fluentflow/sample.mp3?sp=r"]
    assert captured["body"]["properties"]["wordLevelTimestampsEnabled"] is True
    assert captured["body"]["properties"]["displayFormWordLevelTimestampsEnabled"] is True
    assert captured["body"]["properties"]["diarization"] == {"enabled": True, "maxSpeakers": 5}
    assert result["location"] == "https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job"


def test_transcribe_audio_batch_polls_and_downloads_result(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    calls = []

    def fake_urlopen(request_or_url, timeout):
        url = request_or_url.full_url if hasattr(request_or_url, "full_url") else request_or_url
        calls.append(url)
        if "blob.core.windows.net" in url:
            return Response(b"", status=201)
        if "transcriptions:submit" in url:
            return Response(
                {
                    "self": "https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job?api-version=2025-10-15",
                    "links": {
                        "files": "https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job/files?api-version=2025-10-15"
                    },
                    "status": "NotStarted",
                },
                status=201,
            )
        if "/files?" in url:
            return Response({
                "values": [
                    {
                        "kind": "Transcription",
                        "links": {"contentUrl": "https://download.example/result.json"},
                    }
                ]
            })
        if "download.example" in url:
            return Response({
                "combinedRecognizedPhrases": [{"display": "你好世界。"}],
                "recognizedPhrases": [
                    {
                        "offsetInTicks": 0,
                        "durationInTicks": 10_000_000,
                        "nBest": [{"display": "你好世界。"}],
                        "speaker": 1,
                    }
                ],
                "durationMilliseconds": 1000,
            })
        return Response(
            {
                "self": url,
                "links": {
                    "files": "https://eastasia.api.cognitive.microsoft.com/speechtotext/transcriptions/job/files?api-version=2025-10-15"
                },
                "status": "Succeeded",
            }
        )

    statuses = []
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda delay: None)

    result = transcribe_audio_batch(
        audio,
        endpoint="eastasia",
        api_key="key",
        container_sas_url="https://acct.blob.core.windows.net/fluentflow?sp=racw&sig=secret",
        locale="auto",
        diarization_enabled=True,
        progress_callback=lambda status, metadata: statuses.append(status),
    )

    assert result.text == "你好世界。"
    assert result.model_source == "azure_speech_batch_transcription"
    assert result.segments[0].speaker == "SPEAKER_1"
    assert "azure_batch_uploading" in statuses
    assert "azure_batch_waiting" in statuses
    assert any("transcriptions:submit" in call for call in calls)


def test_parse_batch_transcription_result_supports_recognized_phrases() -> None:
    result = parse_batch_transcription_result(
        {
            "combinedRecognizedPhrases": [{"display": "hello world"}],
            "recognizedPhrases": [
                {
                    "offsetInTicks": 10_000_000,
                    "durationInTicks": 20_000_000,
                    "nBest": [{"display": "hello world"}],
                    "locale": "en-US",
                }
            ],
        },
        locale="zh-CN",
    )

    assert result.text == "hello world"
    assert result.language == "en-US"
    assert [(segment.start, segment.end) for segment in result.segments] == [(1.0, 3.0)]


def test_parse_batch_transcription_result_splits_long_phrase_with_word_times(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_SECONDS", "12")
    monkeypatch.setenv("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_CHARS", "80")

    result = parse_batch_transcription_result(
        {
            "combinedRecognizedPhrases": [{"display": "第一句。第二句。第三句。"}],
            "recognizedPhrases": [
                {
                    "offsetMilliseconds": 0,
                    "durationMilliseconds": 30000,
                    "nBest": [
                        {
                            "display": "第一句。第二句。第三句。",
                            "words": [
                                {"word": "第一句", "offsetMilliseconds": 0, "durationMilliseconds": 9000},
                                {"word": "第二句", "offsetMilliseconds": 10000, "durationMilliseconds": 9000},
                                {"word": "第三句", "offsetMilliseconds": 20000, "durationMilliseconds": 9000},
                            ],
                        }
                    ],
                }
            ],
        }
    )

    assert result.text == "第一句。第二句。第三句。"
    assert [segment.text for segment in result.segments] == ["第一句。", "第二句。", "第三句。"]
    assert [(segment.start, segment.end) for segment in result.segments] == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_parse_batch_transcription_result_splits_long_phrase_without_word_times(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_SECONDS", "12")
    monkeypatch.setenv("FLUENTFLOW_AZURE_DISPLAY_SEGMENT_MAX_CHARS", "80")

    result = parse_batch_transcription_result(
        {
            "combinedRecognizedPhrases": [{"display": "第一句。第二句。"}],
            "recognizedPhrases": [
                {
                    "offsetMilliseconds": 0,
                    "durationMilliseconds": 24000,
                    "nBest": [{"display": "第一句。第二句。"}],
                }
            ],
        }
    )

    assert [segment.text for segment in result.segments] == ["第一句。", "第二句。"]
    assert [(segment.start, segment.end) for segment in result.segments] == [(0.0, 12.0), (12.0, 24.0)]
