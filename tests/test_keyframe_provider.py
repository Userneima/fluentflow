from __future__ import annotations

from backend.core import keyframe_provider


def test_keyframe_provider_defaults_to_local_ffmpeg(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_KEYFRAME_EXTRACTION", raising=False)
    monkeypatch.delenv("FLUENTFLOW_KEYFRAME_PROVIDER", raising=False)

    assert keyframe_provider.configured_keyframe_provider() == "local_ffmpeg"


def test_keyframe_provider_can_be_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_KEYFRAME_EXTRACTION", "0")

    result = keyframe_provider.extract_keyframes("demo.mp4", tmp_path)

    assert result.provider == "disabled"
    assert result.frames == []
    assert result.skipped_reason == "disabled"


def test_cloud_worker_without_url_skips_without_failing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_KEYFRAME_PROVIDER", "cloud_ffmpeg_worker")
    monkeypatch.delenv("FLUENTFLOW_KEYFRAME_WORKER_URL", raising=False)

    result = keyframe_provider.extract_keyframes("demo.mp4", tmp_path)

    assert result.provider == "cloud_ffmpeg_worker"
    assert result.frames == []
    assert result.skipped_reason == "cloud_worker_not_configured"


def test_local_provider_tags_frames(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        keyframe_provider,
        "extract_candidate_frames",
        lambda *args, **kwargs: [{"path": str(tmp_path / "frame.jpg"), "timestamp_seconds": 1.2, "source": "timepoint"}],
    )

    result = keyframe_provider.extract_keyframes("demo.mp4", tmp_path, provider="local_ffmpeg")

    assert result.provider == "local_ffmpeg"
    assert result.frames[0]["provider"] == "local_ffmpeg"
