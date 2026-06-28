from __future__ import annotations

from backend.core.processing_plan import build_processing_plan, ensure_processing_plan


def test_processing_plan_explains_transcript_file_route() -> None:
    result = {
        "source": "transcript_file",
        "filename": "lesson.srt",
        "transcript_text": "字幕内容\n继续内容",
        "summary_status": "completed",
        "requested_note_mode": "auto",
        "resolved_note_mode": "direct",
        "note_mode_plan_reason": "材料较短，直接整理即可。",
        "note_mode_plan_confidence": "high",
    }

    plan = build_processing_plan(result)

    assert plan["processing_plan_version"] == "1"
    assert plan["planning_stage"] == "completed"
    assert plan["execution_mode"] == "automatic"
    assert plan["goal"]["primary"] == "course_notes"
    assert plan["material"]["type"] == "course_transcript_file"
    assert plan["material"]["evidence_policy"]["filename"] == "weak"
    assert plan["material"]["evidence_policy"]["transcript_content"] == "primary"
    assert plan["execution"]["scope"] == "local"
    assert plan["execution"]["transcription_tool"] == "transcript_parser"
    assert plan["note_strategy"]["resolved_mode"] == "direct"
    assert plan["note_strategy"]["reason"] == "材料较短，直接整理即可。"
    assert [step["id"] for step in plan["steps"]] == [
        "ingest",
        "transcribe",
        "prepare_subtitles",
        "generate_note",
        "export",
    ]


def test_processing_plan_uses_runtime_tool_and_honest_confidence() -> None:
    result = {
        "source": "video_link",
        "filename": "course.mp4",
        "audio_duration_seconds": 2400,
        "transcript_text": "这节课第一部分讲解 Agent 的概念，第二部分解释工具调用。",
        "source_language": "en",
        "stt_provider": "local",
        "subtitle_mode": "bilingual_zh",
        "translation_status": "completed",
        "summary_status": "skipped",
    }

    plan = build_processing_plan(result)

    assert plan["planning_stage"] == "completed"
    assert plan["material"]["type"] == "lecture_material"
    assert plan["material"]["confidence"] == "high"
    assert plan["goal"]["primary"] == "lecture_notes"
    assert plan["execution"]["scope"] == "local"
    assert plan["execution"]["transcription_tool"] == "local_whisper"
    assert "bilingual_subtitles" in plan["expected_outputs"]
    assert "markdown_note" not in plan["expected_outputs"]
    assert "generate_note" not in [step["id"] for step in plan["steps"]]


def test_ensure_processing_plan_replaces_out_of_scope_goal_and_merges_note_strategy() -> None:
    result = {
        "filename": "interview.mp4",
        "processing_plan": {
            "processing_plan_version": "1",
            "goal": {"primary": "learning_interview"},
            "note_strategy": {"requested_mode": "auto"},
        },
        "resolved_note_mode": "high_fidelity",
        "note_mode_plan_selected_mode": "high_fidelity",
    }

    next_result = ensure_processing_plan(result)

    plan = next_result["processing_plan"]
    assert plan["goal"]["primary"] == "course_notes"
    assert plan["note_strategy"]["requested_mode"] == "auto"
    assert plan["note_strategy"]["resolved_mode"] == "high_fidelity"


def test_processing_plan_treats_filename_as_weak_signal_until_transcript_exists() -> None:
    initial = build_processing_plan({
        "source": "video",
        "filename": "interview-course.mp4",
        "audio_duration_seconds": 900,
    })

    completed = build_processing_plan({
        "source": "video",
        "filename": "interview-course.mp4",
        "audio_duration_seconds": 900,
        "transcript_text": "今天这节课首先解释设计方法，然后讲解案例。",
    })

    assert initial["planning_stage"] == "initial"
    assert initial["material"]["confidence"] == "low"
    assert initial["material"]["evidence_policy"]["transcript_content"] == "pending"
    assert "weak filename hint: course_or_lecture" in initial["material"]["evidence"]
    assert completed["planning_stage"] == "completed"
    assert completed["material"]["confidence"] == "high"
    assert completed["material"]["evidence_policy"]["transcript_content"] == "primary"
