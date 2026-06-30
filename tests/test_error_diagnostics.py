from __future__ import annotations

from backend.core.error_diagnostics import diagnose_error


def test_error_diagnostics_classifies_common_failures() -> None:
    cases = [
        (
            'Queued transcript summary request failed: HTTP 401 {"detail":"FluentFlow account login is required."}',
            "auth_required",
            "重新登录",
        ),
        ("InsufficientBalanceError: required quota balance", "quota_insufficient", "补足额度"),
        ("HTTP Error 403: Forbidden", "platform_forbidden", "cookies"),
        ("HTTP Error 429: Too Many Requests", "platform_rate_limited", "稍后重试"),
        ("Queued source file is missing", "source_file_missing", "重新上传"),
        ("Unsupported note generation mode: chapter_coverage", "unsupported_note_mode", "自动"),
        ("AI summarization returned empty result", "empty_ai_note", "重生笔记"),
        ("Feishu 图片上传失败: storage error", "feishu_image_upload_failed", "Markdown"),
    ]

    for raw, code, action_text in cases:
        diagnosis = diagnose_error(raw)
        assert diagnosis["code"] == code
        assert action_text in diagnosis["next_action"]
        assert diagnosis["detail"]


def test_error_diagnostics_keeps_unknown_raw_detail() -> None:
    diagnosis = diagnose_error("vendor exploded with code 999")

    assert diagnosis["code"] == "unknown_error"
    assert diagnosis["detail"] == "vendor exploded with code 999"
    assert diagnosis["next_action"]
