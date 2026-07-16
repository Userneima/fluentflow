from __future__ import annotations

from backend.core import media_preflight


def test_preflight_rejects_empty_file_before_probe(tmp_path) -> None:
    source = tmp_path / "empty.mp4"
    source.touch()

    try:
        media_preflight.preflight_media_file(source)
    except media_preflight.MediaPreflightError as exc:
        assert exc.code == "media_file_empty"
    else:
        raise AssertionError("Expected empty media to be rejected")


def test_preflight_rejects_media_without_audio_stream(monkeypatch, tmp_path) -> None:
    source = tmp_path / "silent-screen.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr(
        media_preflight,
        "_probe_media",
        lambda path: {"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.5"}, "streams": [{"codec_type": "video"}]},
    )

    try:
        media_preflight.preflight_media_file(source)
    except media_preflight.MediaPreflightError as exc:
        assert exc.code == "media_audio_stream_missing"
    else:
        raise AssertionError("Expected media without an audio stream to be rejected")


def test_preflight_records_safe_metadata_for_readable_media(monkeypatch, tmp_path) -> None:
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr(
        media_preflight,
        "_probe_media",
        lambda path: {"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.5"}, "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]},
    )
    decoded: list[str] = []
    monkeypatch.setattr(media_preflight, "_verify_first_audio_segment", lambda path: decoded.append(str(path)))

    result = media_preflight.preflight_media_file(source)

    assert result.duration_seconds == 12.5
    assert result.audio_stream_count == 1
    assert result.as_metadata()["format_name"] == "mov,mp4,m4a,3gp,3g2,mj2"
    assert decoded == [str(source.resolve())]


def test_preflight_rejects_mismatched_media_extension(monkeypatch, tmp_path) -> None:
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr(
        media_preflight,
        "_probe_media",
        lambda path: {"format": {"format_name": "mp3", "duration": "12.5"}, "streams": [{"codec_type": "audio"}]},
    )

    try:
        media_preflight.preflight_media_file(source)
    except media_preflight.MediaPreflightError as exc:
        assert exc.code == "media_extension_mismatch"
        assert exc.metadata == {"suffix": ".mp4", "format_name": "mp3"}
    else:
        raise AssertionError("Expected a mismatched extension to be rejected")


def test_master_preflight_switch_disables_individual_media_guards(monkeypatch, tmp_path) -> None:
    source = tmp_path / "empty.mp4"
    source.touch()
    monkeypatch.setenv(media_preflight.MEDIA_PREFLIGHT_ENABLED_ENV, "0")

    result = media_preflight.preflight_media_file(source)

    assert result.enabled_guards == ()
    assert result.audio_stream_count is None


def test_individual_silence_guard_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv(media_preflight.SILENCE_GUARD_ENV, "0")

    assert media_preflight.media_guard_enabled(media_preflight.SILENCE_GUARD_ENV) is False
