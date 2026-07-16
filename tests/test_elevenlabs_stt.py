from __future__ import annotations

import pytest

from backend.core.elevenlabs_stt import parse_scribe_transcription_result


def test_parse_scribe_result_builds_segments_with_speakers() -> None:
    result = parse_scribe_transcription_result({
        "language_code": "zho",
        "language_probability": 0.98,
        "text": "你好世界。第二位老师来了。",
        "words": [
            {"text": "你好", "start": 0.0, "end": 0.4, "speaker_id": "speaker_0"},
            {"text": "世界", "start": 0.4, "end": 0.9, "speaker_id": "speaker_0"},
            {"text": "。", "start": 0.9, "end": 1.0, "speaker_id": "speaker_0"},
            {"text": "第二位", "start": 2.4, "end": 2.9, "speaker_id": "speaker_1"},
            {"text": "老师", "start": 2.9, "end": 3.2, "speaker_id": "speaker_1"},
            {"text": "来了", "start": 3.2, "end": 3.6, "speaker_id": "speaker_1"},
        ],
    })

    assert result.text == "你好世界。第二位老师来了。"
    assert result.language == "zho"
    assert result.language_probability == 0.98
    assert result.model_source == "elevenlabs_scribe"
    assert len(result.segments) == 2
    assert result.segments[0].text == "你好世界。"
    assert result.segments[0].speaker == "SPEAKER_0"
    assert result.segments[1].speaker == "SPEAKER_1"


def test_parse_scribe_result_rejects_empty_provider_response() -> None:
    with pytest.raises(RuntimeError, match="returned no usable speech"):
        parse_scribe_transcription_result({"text": "", "words": []})
