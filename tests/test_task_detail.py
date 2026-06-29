from __future__ import annotations

from backend.core.task_detail import build_task_detail


def test_task_detail_builds_live_video_link_timeline_from_recorded_steps() -> None:
    job = {
        "task_id": "task-link",
        "status": "running",
        "stage": "downloading",
        "progress": 28,
        "source_type": "video_link",
        "source_filename": "https://www.bilibili.com/video/BVdemo/",
        "metadata": {
            "video_source_progress": {
                "message": "正在下载并合并 B 站音视频",
                "loaded_bytes": 1024 * 1024,
                "total_bytes": 10 * 1024 * 1024,
            },
            "queue_options": {"stt_provider": "local", "stt_model": "medium"},
        },
        "result": None,
    }
    steps = [{
        "task_id": "task-link",
        "step_type": "video_source",
        "status": "running",
        "started_at": "2026-01-01T00:00:00+00:00",
    }]

    detail = build_task_detail(job, job_steps=steps)
    timeline = {step["id"]: step for step in detail["timeline"]}

    assert detail["task"]["title"] == "BVdemo"
    assert timeline["source_fetch"]["status"] == "running"
    assert timeline["source_fetch"]["source"] == "recorded"
    assert "正在下载并合并 B 站音视频" in timeline["source_fetch"]["detail"]
    assert timeline["transcription"]["status"] == "pending"
    assert detail["decision_log"]["entry_count"] >= 4
    assert detail["actions"][0]["id"] == "cancel"
    assert detail["data_quality"]["has_recorded_steps"] is True


def test_task_detail_uses_shorter_timeline_for_transcript_file() -> None:
    job = {
        "task_id": "task-subtitle",
        "status": "completed",
        "stage": "done",
        "progress": 100,
        "source_type": "transcript_file",
        "source_filename": "字幕.srt",
        "summary_status": "completed",
        "result": {
            "task_id": "task-subtitle",
            "filename": "字幕.srt",
            "transcript_text": "hello",
            "summary_markdown": "# Note",
            "artifacts": {
                "transcript_txt": {"filename": "字幕.txt", "url": "/jobs/task-subtitle/artifacts/transcript_txt"},
                "summary_md": {"filename": "笔记.md", "url": "/jobs/task-subtitle/artifacts/summary_md"},
            },
        },
    }

    detail = build_task_detail(job)
    step_ids = [step["id"] for step in detail["timeline"]]

    assert step_ids == ["subtitle_parse", "subtitle_prepare", "note_generation", "result_save"]
    assert all(step["status"] == "completed" for step in detail["timeline"])
    assert [artifact["kind"] for artifact in detail["artifacts"]] == ["transcript_txt", "summary_md"]
    assert any(action["id"] == "open_result" for action in detail["actions"])


def test_task_detail_does_not_claim_audio_prepared_while_job_is_only_queued() -> None:
    job = {
        "task_id": "task-queued",
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "result": {},
    }

    detail = build_task_detail(job)
    timeline = {step["id"]: step for step in detail["timeline"]}

    assert timeline["source_fetch"]["status"] == "completed"
    assert timeline["audio_prepare"]["status"] == "pending"
    assert timeline["transcription"]["status"] == "pending"


def test_task_detail_surfaces_note_failure_without_marking_transcription_failed() -> None:
    job = {
        "task_id": "task-note-failed",
        "status": "completed",
        "stage": "done",
        "progress": 100,
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "summary_status": "failed",
        "result": {
            "task_id": "task-note-failed",
            "filename": "lesson.mp4",
            "transcript_text": "finished transcript",
            "summary_status": "failed",
            "summary_error": "Unsupported note generation mode: chapter_coverage",
            "artifacts": {
                "transcript_srt": {"filename": "lesson.srt"},
            },
        },
    }

    detail = build_task_detail(job)
    timeline = {step["id"]: step for step in detail["timeline"]}

    assert timeline["transcription"]["status"] == "completed"
    assert timeline["note_generation"]["status"] == "failed"
    assert detail["diagnosis"]["visible"] is True
    assert detail["diagnosis"]["step_id"] == "note_generation"
    assert "笔记模式不受当前版本支持" in detail["diagnosis"]["title"]
    decision_entries = {entry["id"]: entry for entry in detail["decision_log"]["entries"]}
    assert decision_entries["note_generation_outcome"]["status"] == "failed"
    assert any(action["id"] == "regenerate_note" for action in detail["actions"])
