from __future__ import annotations

from dataclasses import asdict
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main
from backend.core.note_planner import NoteTaskPlan, plan_note_task
import backend.core.server_helpers as _H


def test_plan_note_task_sanitizes_llm_json() -> None:
    with (
        patch("backend.core.note_planner._get_client", return_value=object()),
        patch("backend.core.note_planner._normalize_provider", return_value="deepseek"),
        patch("backend.core.note_planner._normalize_model", return_value="deepseek-reasoner"),
        patch(
            "backend.core.note_planner._chat",
            return_value='{"material_type":"career_talk","recommended_note_mode":"chapter_coverage","recommended_prompt_preset":"career","needs_qa_section":true,"needs_action_items":false,"confidence":"high","reason":"求职分享内容较长，适合高保真整理。"}',
        ),
    ):
        plan = plan_note_task(
            filename="求职经验分享.m4a",
            transcript_preview="今天主要聊求职准备和面试经验。",
            transcript_length=2000,
        )

    assert plan.material_type == "career_talk"
    assert plan.recommended_note_mode == "high_fidelity"
    assert plan.recommended_prompt_preset == "autoTranscriptNotes"
    assert plan.needs_qa_section is True
    assert plan.confidence == "high"


def test_plan_note_task_endpoint_returns_plan(monkeypatch) -> None:
    fake_plan = NoteTaskPlan(
        material_type="course",
        recommended_note_mode="high_fidelity",
        recommended_prompt_preset="default",
        needs_qa_section=False,
        needs_action_items=True,
        confidence="medium",
        reason="长课程需要更完整覆盖。",
        warnings=[],
        planner_provider="deepseek",
        planner_model="deepseek-reasoner",
    )
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(_H, "plan_note_task", lambda **_kwargs: fake_plan)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: events.append(kwargs))

    with TestClient(main.app) as client:
        response = client.post(
            "/plan-note-task",
            json={
                "task_id": "task-1",
                "filename": "course.mp4",
                "transcript_preview": "课程内容",
                "transcript_length": 120000,
            },
        )

    assert response.status_code == 200
    assert response.json()["plan"] == asdict(fake_plan)
    assert events[0]["event_name"] == "agent_plan_generated"
    assert events[0]["metadata"]["recommended_note_mode"] == "high_fidelity"


def test_planning_transcript_preview_samples_beginning_middle_and_end() -> None:
    transcript = "开头寒暄" * 700 + "中段高密度课程内容？" * 700 + "结尾行动清单" * 700

    preview = _H._planning_transcript_preview(transcript, sample_chars=1200)

    assert "【材料统计】" in preview
    assert "total_chars" in preview
    assert "question_marks" in preview
    assert "【开头样本】" in preview
    assert "开头寒暄" in preview
    assert "【中段样本】" in preview
    assert "中段高密度课程内容" in preview
    assert "【结尾样本】" in preview
    assert "结尾行动清单" in preview


def test_auto_note_mode_planning_selects_concrete_mode(monkeypatch) -> None:
    fake_plan = NoteTaskPlan(
        material_type="course",
        recommended_note_mode="high_fidelity",
        recommended_prompt_preset="default",
        needs_qa_section=False,
        needs_action_items=False,
        confidence="high",
        reason="材料特别长，适合完整覆盖。",
        warnings=["会多花一些时间。"],
        planner_provider="deepseek",
        planner_model="deepseek-reasoner",
    )
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(_H, "plan_note_task", lambda **_kwargs: fake_plan)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: events.append(kwargs))

    kwargs, metadata = _H._plan_note_mode_for_summary(
        {"note_mode": "auto", "provider": "deepseek", "model": "deepseek-reasoner", "api_key": "test"},
        "课程内容" * 200,
        task_id="task-1",
        route="/process",
        filename="course.mp4",
        current_prompt_preset="default",
    )

    assert kwargs["note_mode"] == "high_fidelity"
    assert metadata["requested_note_mode"] == "auto"
    assert metadata["note_mode_plan_selected_mode"] == "high_fidelity"
    assert metadata["note_mode_plan_reason"] == "材料特别长，适合完整覆盖。"
    assert metadata["note_mode_plan_fallback"] is False
    assert events[0]["event_name"] == "note_mode_planned"


def test_auto_note_mode_planning_falls_back_to_length_rule(monkeypatch) -> None:
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(_H, "plan_note_task", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("planner down")))
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: events.append(kwargs))

    kwargs, metadata = _H._plan_note_mode_for_summary(
        {"note_mode": "auto", "provider": "deepseek"},
        "课程内容" * 200,
        task_id="task-1",
        route="/process",
        filename="course.mp4",
    )

    assert kwargs["note_mode"] == "auto"
    assert metadata["requested_note_mode"] == "auto"
    assert metadata["note_mode_plan_fallback"] is True
    assert "按长度规则" in metadata["note_mode_plan_reason"]
    assert events[0]["event_name"] == "note_mode_plan_failed"
