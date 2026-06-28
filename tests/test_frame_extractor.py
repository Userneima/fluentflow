from __future__ import annotations

from types import SimpleNamespace

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
