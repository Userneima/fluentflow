from __future__ import annotations

from backend.core.decision_log import build_decision_log


def test_decision_log_explains_material_route_note_and_export_choices() -> None:
    job = {
        "task_id": "task-decision",
        "status": "completed",
        "stage": "done",
        "source_type": "video",
        "source_filename": "career-talk.mp4",
        "source_duration_seconds": 3600,
        "summary_status": "completed",
        "metadata": {
            "queue_options": {
                "stt_provider": "local",
                "stt_model": "medium",
                "note_mode": "auto",
                "export_to_lark": "true",
                "lark_export_route": "local_cli",
            },
        },
    }
    result = {
        "transcript_text": "今天聊求职准备。第一，简历。第二，面试。",
        "audio_duration_seconds": 3600,
        "source_language": "zh",
        "stt_provider": "local",
        "stt_model": "medium",
        "subtitle_mode": "bilingual_zh",
        "translation_status": "completed",
        "requested_note_mode": "auto",
        "resolved_note_mode": "high_fidelity",
        "note_mode_plan_selected_mode": "high_fidelity",
        "note_mode_plan_reason": "材料较长，且包含结构化求职经验，适合高保真整理。",
        "note_mode_plan_confidence": "high",
        "note_mode_plan_provider": "deepseek",
        "note_mode_plan_model": "deepseek-reasoner",
        "summary_status": "completed",
        "summary_markdown": "# 求职笔记",
        "note_mode_evidence_count": 12,
        "note_mode_important_evidence_count": 6,
        "note_mode_covered_important_evidence_count": 5,
        "lark_response": {"url": "https://example.feishu.cn/docx/demo"},
    }

    log = build_decision_log(result, job=job)
    entries = {entry["id"]: entry for entry in log["entries"]}

    assert log["decision_log_version"] == "1"
    assert entries["material_classification"]["decision"] in {"讲座材料", "课程材料"}
    assert entries["execution_route"]["decision"] == "本机处理"
    assert entries["execution_route"]["source"] == "recorded"
    assert entries["subtitle_strategy"]["decision"] == "生成中文对照字幕"
    assert entries["note_mode_selection"]["decision"] == "高保真笔记"
    assert entries["note_mode_selection"]["source"] == "recorded"
    assert "材料较长" in entries["note_mode_selection"]["reason"]
    assert entries["note_generation_outcome"]["decision"] == "笔记已生成"
    assert entries["feishu_export"]["decision"] == "已同步至飞书"


def test_decision_log_marks_note_planner_fallback_as_recorded_warning() -> None:
    result = {
        "transcript_text": "课程内容",
        "requested_note_mode": "auto",
        "summary_status": "failed",
        "summary_error": "AI timeout",
        "note_mode_plan_reason": "AI 规划失败，已按长度规则自动选择。",
        "note_mode_plan_fallback": True,
        "note_mode_plan_error": "planner down",
    }

    log = build_decision_log(result, job={"task_id": "task-fallback", "status": "completed"})
    entries = {entry["id"]: entry for entry in log["entries"]}

    assert entries["note_mode_selection"]["source"] == "recorded"
    assert "按长度规则" in entries["note_mode_selection"]["reason"]
    assert entries["note_generation_outcome"]["status"] == "failed"
    assert entries["note_generation_outcome"]["reason"] == "AI timeout"
