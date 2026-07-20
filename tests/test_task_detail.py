from __future__ import annotations

from backend.core.task_detail import build_task_detail, build_task_snapshot


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
    assert detail["task_snapshot"]["overall_status"] == "running"
    assert detail["task_snapshot"]["current_step"] == "source_fetch"
    assert detail["task_snapshot"]["step_statuses"]["source_fetch"] == "running"
    assert detail["task_snapshot"]["route"]["transcription"] == "local"
    assert detail["task_snapshot"]["route"]["stt_provider"] == "local"
    assert detail["task_snapshot"]["route"]["ai_note_requires_account"] is True


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
            "requested_note_mode": "auto",
            "resolved_note_mode": "high_fidelity",
            "chapter_coverage": {
                "chapter_coverage_version": "1",
                "evidence": [{"evidence_id": "E001", "text": "证据"}],
            },
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
    assert detail["chapter_coverage"]["evidence"][0]["evidence_id"] == "E001"
    assert detail["note"]["status"] == "completed"
    assert detail["note"]["resolved_mode"] == "high_fidelity"
    assert detail["note"]["markdown_chars"] == len("# Note")
    assert any(action["id"] == "open_result" for action in detail["actions"])
    assert detail["task_snapshot"]["overall_status"] == "completed"
    assert detail["task_snapshot"]["current_step"] == "result_save"
    assert detail["task_snapshot"]["route"]["transcription"] == "transcript_file"


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
    assert detail["task_snapshot"]["overall_status"] == "completed"
    assert detail["task_snapshot"]["current_step"] == "note_generation"
    assert "当前版本不支持这类笔记生成模式" in detail["task_snapshot"]["failure_reason"]
    assert detail["task_snapshot"]["next_action"]
    decision_entries = {entry["id"]: entry for entry in detail["decision_log"]["entries"]}
    assert decision_entries["note_generation_outcome"]["status"] == "failed"
    assert any(action["id"] == "regenerate_note" for action in detail["actions"])


def test_task_detail_auth_failure_suggests_login_before_retry() -> None:
    job = {
        "task_id": "task-auth-failed",
        "status": "failed",
        "stage": "failed",
        "progress": 100,
        "source_type": "video_link",
        "source_filename": "YouTube Demo",
        "error_reason": "账号未登录或登录态已失效，AI 笔记没有生成。请重新登录后重试；已完成的转录不会因此损坏。",
        "result": {},
    }

    detail = build_task_detail(job)

    assert detail["diagnosis"]["visible"] is True
    assert "账号未登录或登录态已失效" in detail["diagnosis"]["detail"]
    assert detail["diagnosis"]["next_action"] == "重新登录后重试；如果转录已保存，打开结果后重生笔记。"


def test_task_detail_surfaces_failed_oss_download_with_direct_retry() -> None:
    job = {
        "task_id": "task-oss-failed",
        "status": "failed",
        "stage": "oss_source_download",
        "progress": 0,
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "error_reason": "云端文件下载失败。请在处理记录中点击“重新处理”；如果仍失败，请重新上传。",
        "metadata": {"source_storage": "oss", "oss_upload_session_id": "session-1"},
        "result": {},
    }
    detail = build_task_detail(job, job_steps=[{
        "task_id": "task-oss-failed",
        "step_type": "oss_source_download",
        "status": "failed",
        "error_reason": job["error_reason"],
    }])
    timeline = {step["id"]: step for step in detail["timeline"]}

    assert timeline["source_fetch"]["status"] == "failed"
    assert detail["diagnosis"]["next_action"] == "文件仍保留在云端，可以在处理记录中点击“重新处理”，无需再次上传。"
    assert any(action["id"] == "retry" and action["path"] == "/jobs/task-oss-failed/retry" for action in detail["actions"])
    assert detail["task_snapshot"]["current_step"] == "source_fetch"


def test_task_snapshot_keeps_transcript_only_route_without_ai_requirement() -> None:
    job = {
        "task_id": "task-transcript-only",
        "status": "completed",
        "stage": "done",
        "progress": 100,
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "metadata": {"queue_options": {"stt_provider": "local", "stt_model": "medium"}},
        "result": {
            "task_id": "task-transcript-only",
            "transcript_text": "finished transcript",
            "summary_status": "skipped",
            "summary_skipped": True,
        },
    }

    snapshot = build_task_snapshot(job)

    assert snapshot["task_snapshot_version"] == "1"
    assert snapshot["overall_status"] == "completed"
    assert snapshot["route"]["transcription"] == "local"
    assert snapshot["route"]["ai_note_requires_account"] is False
    assert snapshot["step_statuses"]["note_generation"] == "skipped"
