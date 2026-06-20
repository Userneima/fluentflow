from __future__ import annotations

from backend.core.job_lifecycle import (
    job_has_transcript_result,
    result_for_summary_failure,
    result_for_summary_success,
    result_for_transcript_only,
)


def test_job_has_transcript_result_accepts_text_or_segments() -> None:
    assert job_has_transcript_result({"result": {"transcript_text": "hello"}}) is True
    assert job_has_transcript_result({"result": {"segments": [{"text": "hello"}]}}) is True
    assert job_has_transcript_result({"result": {"summary_markdown": "note only"}}) is False


def test_result_for_transcript_only_marks_summary_skipped() -> None:
    result = result_for_transcript_only({"task_id": "task-1", "summary_skipped": False})

    assert result["status"] == "completed"
    assert result["summary_status"] == "skipped"
    assert result["summary_skipped"] is True
    assert result["summary_markdown"] == ""


def test_result_for_summary_failure_keeps_transcript_deliverable_completed() -> None:
    result = result_for_summary_failure({"task_id": "task-1", "transcript_text": "text"}, "bad key")

    assert result["status"] == "completed"
    assert result["summary_status"] == "failed"
    assert result["summary_error"] == "bad key"
    assert result["summary_markdown"] == ""


def test_result_for_summary_success_adds_note_mode_metadata() -> None:
    result = result_for_summary_success(
        {"task_id": "task-1", "transcript_text": "text"},
        "## Note",
        requested_note_mode="auto",
        resolved_note_mode="high_fidelity",
        note_mode_chunk_count=3,
        prompt_preset="autoTranscriptNotes",
        prompt_preset_label="语音转字幕笔记（推荐）",
    )

    assert result["status"] == "completed"
    assert result["summary_status"] == "completed"
    assert result["summary_markdown"] == "## Note"
    assert result["summary_skipped"] is False
    assert result["resolved_note_mode"] == "high_fidelity"
    assert result["note_mode_chunk_count"] == 3
    assert result["prompt_preset"] == "autoTranscriptNotes"
    assert result["prompt_preset_label"] == "语音转字幕笔记（推荐）"
