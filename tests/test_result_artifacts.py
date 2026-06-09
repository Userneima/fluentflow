from __future__ import annotations

from pathlib import Path

from backend.main import _attach_result_artifacts


def test_attach_result_artifacts_writes_transcript_and_subtitle_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {
        "filename": "lesson.mp4",
        "transcript_text": "第一句\n第二句",
        "segments": [
            {"start": 0.0, "end": 1.25, "text": "第一句"},
            {"start": 1.25, "end": 3.5, "text": "第二句"},
        ],
        "summary_markdown": "# 摘要\n\n- 要点",
    }

    next_result = _attach_result_artifacts("task_artifact_test", result)

    artifacts = next_result["artifacts"]
    assert set(artifacts) == {"transcript_txt", "transcript_srt", "transcript_vtt", "summary_md"}
    for artifact in artifacts.values():
        assert artifact["url"].startswith("/jobs/task_artifact_test/artifacts/")
        assert (tmp_path / "task_artifact_test" / artifact["filename"]).is_file()

    srt = (tmp_path / "task_artifact_test" / artifacts["transcript_srt"]["filename"]).read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,250" in srt
    assert "第一句" in srt

    vtt = (tmp_path / "task_artifact_test" / artifacts["transcript_vtt"]["filename"]).read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.250 --> 00:00:03.500" in vtt

    summary = (tmp_path / "task_artifact_test" / artifacts["summary_md"]["filename"]).read_text(encoding="utf-8")
    assert summary.startswith("# 摘要")


def test_attach_result_artifacts_preserves_result_when_nothing_to_write(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {"filename": "empty.mp4"}

    next_result = _attach_result_artifacts("task_empty", result)

    assert next_result == result
    assert not (tmp_path / "task_empty").exists()
