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
            return_value='{"material_type":"career_talk","recommended_note_mode":"high_fidelity","recommended_prompt_preset":"career","needs_qa_section":true,"needs_action_items":false,"confidence":"high","reason":"求职分享内容较长，适合高保真整理。"}',
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
        recommended_note_mode="chapter_coverage",
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
    assert events[0]["metadata"]["recommended_note_mode"] == "chapter_coverage"
