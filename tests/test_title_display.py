from __future__ import annotations

from backend.core.title_display import display_title_for_user, strip_generated_video_prefix


def test_display_title_removes_generated_video_id_prefix() -> None:
    assert (
        display_title_for_user("7651613998131006774-四大核心Skill架构与配置指南详解.mp4")
        == "四大核心Skill架构与配置指南详解"
    )


def test_display_title_does_not_remove_short_date_prefix() -> None:
    assert strip_generated_video_prefix("20260624-会议记录.mp4") == "20260624-会议记录"


def test_display_title_uses_fallback() -> None:
    assert display_title_for_user("", "7651613998131006774-标题.mp4") == "标题"
