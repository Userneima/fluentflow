from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend.core import frame_extractor


def test_scene_frames_use_ffmpeg_pts_time_and_even_selection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(frame_extractor, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(frame_extractor, "_ffprobe_path", lambda: "ffprobe")

    def fake_run(cmd, **kwargs):
        if "-show_entries" in cmd:
            return SimpleNamespace(stdout="20.0", stderr="")
        for index in range(1, 4):
            (tmp_path / f"scene_{index:04d}.jpg").write_bytes(f"jpg-{index}".encode())
        return SimpleNamespace(
            stdout="",
            stderr=(
                "[Parsed_showinfo_1] n:0 pts:2500 pts_time:2.5\n"
                "[Parsed_showinfo_1] n:1 pts:8000 pts_time:8\n"
                "[Parsed_showinfo_1] n:2 pts:12200 pts_time:12.2\n"
            ),
        )

    monkeypatch.setattr(frame_extractor.subprocess, "run", fake_run)

    frames = frame_extractor.extract_candidate_frames(
        "lesson.mp4",
        tmp_path,
        scene_threshold=0.3,
        max_scene_frames=2,
    )

    assert [frame["timestamp_seconds"] for frame in frames] == [2.5, 12.2]
    assert [frame["source"] for frame in frames] == ["scene", "scene"]
    assert (tmp_path / "scene_0001.jpg").is_file()
    assert not (tmp_path / "scene_0002.jpg").exists()
    assert (tmp_path / "scene_0003.jpg").is_file()


def test_scene_frame_timestamps_fallback_to_duration_when_showinfo_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(frame_extractor, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(frame_extractor, "_ffprobe_path", lambda: "ffprobe")

    def fake_run(cmd, **kwargs):
        if "-show_entries" in cmd:
            return SimpleNamespace(stdout="10.0", stderr="")
        for index in range(1, 3):
            (tmp_path / f"scene_{index:04d}.jpg").write_bytes(f"jpg-{index}".encode())
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(frame_extractor.subprocess, "run", fake_run)

    frames = frame_extractor.extract_candidate_frames(
        "lesson.mp4",
        tmp_path,
        scene_threshold=0.3,
        max_scene_frames=10,
    )

    assert [frame["timestamp_seconds"] for frame in frames] == [0.0, 5.0]


def test_fallback_frames_are_used_when_scene_detection_finds_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(frame_extractor, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(frame_extractor, "_ffprobe_path", lambda: "ffprobe")

    def fake_run(cmd, **kwargs):
        if "-show_entries" in cmd:
            return SimpleNamespace(stdout="12.0", stderr="")
        if "-ss" in cmd:
            output = tmp_path / cmd[-1]
            output.write_bytes(b"jpg")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(frame_extractor.subprocess, "run", fake_run)

    frames = frame_extractor.extract_candidate_frames(
        "low-motion-lesson.mp4",
        tmp_path,
        scene_threshold=0.99,
        max_scene_frames=3,
    )

    assert [frame["source"] for frame in frames] == ["fallback", "fallback", "fallback"]
    assert [frame["timestamp_seconds"] for frame in frames] == [3.0, 6.0, 9.0]


def test_transcript_timepoint_frames_win_over_nearby_scene_frames() -> None:
    frames = frame_extractor._deduplicate_frames(
        [{"path": "scene.jpg", "timestamp_seconds": 10.0, "source": "scene"}],
        [{"path": "segment.jpg", "timestamp_seconds": 10.8, "source": "timepoint"}],
        min_gap_seconds=2.0,
    )

    assert frames == [{"path": "segment.jpg", "timestamp_seconds": 10.8, "source": "timepoint"}]


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe are required for integration frame extraction",
)
def test_extract_candidate_frames_from_generated_video_at_transcript_timepoint(tmp_path) -> None:
    video = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=2:size=160x90:rate=5",
            "-pix_fmt", "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    frames = frame_extractor.extract_candidate_frames(
        str(video),
        tmp_path / "frames",
        segments=[{"start": 0.5, "end": 1.2, "text": "关键段落"}],
        scene_threshold=0.99,
        max_scene_frames=0,
    )

    timepoint_frames = [frame for frame in frames if frame["source"] == "timepoint"]
    assert timepoint_frames
    assert timepoint_frames[0]["timestamp_seconds"] == 0.5
    assert (tmp_path / "frames" / "ts_0000.jpg").is_file()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg and ffprobe are required for integration frame extraction",
)
def test_extract_candidate_frames_from_low_motion_video_with_fallback(tmp_path) -> None:
    video = tmp_path / "low_motion.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=160x90:d=2:r=5",
            "-pix_fmt", "yuv420p",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    frames = frame_extractor.extract_candidate_frames(
        str(video),
        tmp_path / "fallback_frames",
        scene_threshold=0.99,
        max_scene_frames=3,
    )

    assert frames
    assert frames[0]["source"] == "fallback"
    assert (tmp_path / "fallback_frames" / "fallback_0001.jpg").is_file()
