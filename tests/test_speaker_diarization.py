from __future__ import annotations

from types import SimpleNamespace

from backend.core.speaker_diarization import (
    SpeakerTurn,
    _load_pyannote_pipeline,
    assign_speakers_to_segments,
    diarization_status,
)


def test_assign_speakers_by_largest_time_overlap() -> None:
    segments = [
        {"start": 0.0, "end": 2.0, "text": "hello"},
        {"start": 2.0, "end": 4.0, "text": "world"},
    ]
    turns = [
        SpeakerTurn(start=0.0, end=1.5, speaker="SPEAKER_00"),
        SpeakerTurn(start=1.5, end=4.0, speaker="SPEAKER_01"),
    ]

    assigned = assign_speakers_to_segments(segments, turns)

    assert assigned[0]["speaker"] == "SPEAKER_00"
    assert assigned[1]["speaker"] == "SPEAKER_01"


def test_diarization_status_is_safe_without_optional_dependency() -> None:
    status = diarization_status()
    assert "available" in status
    assert status["backend"] == "pyannote.audio"


def test_load_pyannote_pipeline_prefers_new_token_argument() -> None:
    class Pipeline:
        @classmethod
        def from_pretrained(cls, model: str, **kwargs):
            return {"model": model, "kwargs": kwargs}

    pipeline = _load_pyannote_pipeline(Pipeline, "hf_token")

    assert pipeline["kwargs"] == {"token": "hf_token"}


def test_load_pyannote_pipeline_compat_translates_legacy_hf_token(monkeypatch) -> None:
    calls = []

    def hf_hub_download(*args, **kwargs):
        calls.append(kwargs)
        if "use_auth_token" in kwargs:
            raise TypeError("hf_hub_download() got an unexpected keyword argument 'use_auth_token'")
        return "downloaded"

    fake_hub = SimpleNamespace(hf_hub_download=hf_hub_download)
    monkeypatch.setitem(__import__("sys").modules, "huggingface_hub", fake_hub)

    class Pipeline:
        @classmethod
        def from_pretrained(cls, model: str, **kwargs):
            if "token" in kwargs:
                raise TypeError("from_pretrained() got an unexpected keyword argument 'token'")
            fake_hub.hf_hub_download(repo_id=model, use_auth_token=kwargs.get("use_auth_token"))
            return {"model": model}

    pipeline = _load_pyannote_pipeline(Pipeline, "hf_token")

    assert pipeline["model"] == "pyannote/speaker-diarization-3.1"
    assert calls == [{"repo_id": "pyannote/speaker-diarization-3.1", "token": "hf_token"}]
