from __future__ import annotations

import backend.core.server_helpers as _H


def test_note_mode_planner_removed_auto_passes_through(monkeypatch) -> None:
    # Regression guard: the AI note-mode planner was removed (2026-07-09).
    # _plan_note_mode_for_summary must be a pass-through — it leaves "auto" for
    # the length rule in summarize_transcript_with_metadata and must never spend
    # a model call to pick the mode. (The note_planner module and the
    # /plan-note-task endpoint were deleted along with it.)
    def _fail_if_called(**_kwargs):
        raise AssertionError("planner should not be invoked after removal")

    # If a plan_note_task shim somehow returns, this would surface it.
    monkeypatch.setattr(_H, "plan_note_task", _fail_if_called, raising=False)

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
