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
    assert job_has_transcript_result({"result": {"raw_segments": [{"text": "hello"}]}}) is True
    assert job_has_transcript_result({"result": {"display_segments": [{"text": "hello"}]}}) is True
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
        {
            "task_id": "task-1",
            "transcript_text": "text",
            "raw_segments": [{"start": 1.0, "end": 2.0, "text": "text"}],
        },
        "## Note",
        requested_note_mode="auto",
        resolved_note_mode="high_fidelity",
        note_mode_chunk_count=3,
        note_mode_segment_count=3,
        note_mode_evidence_count=12,
        note_mode_chapter_count=4,
        note_mode_important_evidence_count=6,
        note_mode_covered_important_evidence_count=5,
        note_mode_coverage_missing_count=1,
        chapter_coverage={
            "chapter_coverage_version": "1",
            "summary": {},
            "evidence": [{"evidence_id": "E001", "char_start": 0, "char_end": 4}],
        },
        note_mode_plan_reason="材料较长，适合高保真整理。",
        note_mode_plan_confidence="high",
        note_mode_plan_warnings=["会更慢。"],
        note_mode_plan_provider="deepseek",
        note_mode_plan_model="deepseek-reasoner",
        note_mode_plan_fallback=False,
        note_mode_plan_selected_mode="high_fidelity",
        prompt_preset="autoTranscriptNotes",
        prompt_preset_label="语音转字幕笔记（推荐）",
    )

    assert result["status"] == "completed"
    assert result["summary_status"] == "completed"
    assert result["summary_markdown"] == "## Note"
    assert result["summary_skipped"] is False
    assert result["resolved_note_mode"] == "high_fidelity"
    assert result["note_mode_chunk_count"] == 3
    assert result["note_mode_segment_count"] == 3
    assert result["note_mode_evidence_count"] == 12
    assert result["note_mode_chapter_count"] == 4
    assert result["note_mode_covered_important_evidence_count"] == 5
    assert result["note_mode_coverage_missing_count"] == 1
    assert result["chapter_coverage"]["evidence"][0]["evidence_id"] == "E001"
    assert result["chapter_coverage"]["evidence"][0]["start_seconds"] == 1.0
    assert result["chapter_coverage"]["evidence"][0]["end_seconds"] == 2.0
    assert result["note_mode_plan_reason"] == "材料较长，适合高保真整理。"
    assert result["note_mode_plan_confidence"] == "high"
    assert result["note_mode_plan_warnings"] == ["会更慢。"]
    assert result["note_mode_plan_provider"] == "deepseek"
    assert result["note_mode_plan_model"] == "deepseek-reasoner"
    assert result["note_mode_plan_fallback"] is False
    assert result["note_mode_plan_selected_mode"] == "high_fidelity"
    assert result["prompt_preset"] == "autoTranscriptNotes"
    assert result["prompt_preset_label"] == "语音转字幕笔记（推荐）"
