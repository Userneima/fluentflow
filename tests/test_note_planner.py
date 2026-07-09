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


def test_note_mode_planner_removed_auto_passes_through(monkeypatch) -> None:
    # Regression guard: the AI note-mode planner was removed (2026-07-09).
    # _plan_note_mode_for_summary must be a pass-through — it leaves "auto" for
    # the length rule in summarize_transcript_with_metadata and must never spend
    # a model call to pick the mode.
    planner_called = {"hit": False}

    def _fail_if_called(**_kwargs):
        planner_called["hit"] = True
        raise AssertionError("planner should not be invoked after removal")

    monkeypatch.setattr(_H, "plan_note_task", _fail_if_called)

    kwargs, metadata = _H._plan_note_mode_for_summary(
        {"note_mode": "auto", "provider": "deepseek", "model": "deepseek-chat", "api_key": "test"},
        "课程内容" * 200,
        task_id="task-1",
        route="/process",
        filename="course.mp4",
        current_prompt_preset="default",
    )

    assert kwargs["note_mode"] == "auto"  # left for the length rule downstream
    assert metadata == {}  # no planner metadata is produced anymore
    assert planner_called["hit"] is False
