from __future__ import annotations

import subprocess

import pytest

from backend.core import audio_handler


def test_require_audible_audio_rejects_digital_silence(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "silent.mp3"
    audio_path.touch()
    monkeypatch.setattr(audio_handler, "_require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        audio_handler.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="[Parsed_volumedetect] max_volume: -91.0 dB\\n",
        ),
    )

    with pytest.raises(RuntimeError, match="没有检测到可转录的声音"):
        audio_handler.require_audible_audio(audio_path)


def test_require_audible_audio_returns_peak_for_voice_input(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "voice.mp3"
    audio_path.touch()
    monkeypatch.setattr(audio_handler, "_require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        audio_handler.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="",
            stderr="[Parsed_volumedetect] max_volume: -12.5 dB\\n",
        ),
    )

    assert audio_handler.require_audible_audio(audio_path) == -12.5
