from __future__ import annotations

import json
import asyncio

from backend.core import transcript_correction
from backend.core.transcript_correction import correct_transcript_segments, correction_result_fields, transcript_correction_enabled
from backend.routers.processing import _run_transcript_correction_stage


def test_transcript_correction_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_TRANSCRIPT_CORRECTION_ENABLED", raising=False)
    monkeypatch.delenv("FLUENTFLOW_TRANSCRIPT_CORRECTION", raising=False)

    assert transcript_correction_enabled() is False


def test_transcript_correction_can_be_enabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_TRANSCRIPT_CORRECTION_ENABLED", "1")

    assert transcript_correction_enabled() is True


def test_disabled_transcript_correction_stage_does_not_call_model(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_TRANSCRIPT_CORRECTION_ENABLED", raising=False)
    monkeypatch.delenv("FLUENTFLOW_TRANSCRIPT_CORRECTION", raising=False)

    def fail_chat(*_args, **_kwargs):
        raise AssertionError("correction model should not be called when disabled")

    monkeypatch.setattr(transcript_correction, "_chat", fail_chat)

    async def run_stage():
        return await _run_transcript_correction_stage(
            loop=asyncio.get_running_loop(),
            task_id="task-disabled",
            route="/process",
            source_type="video",
            source_filename="lesson.mp4",
            source_duration_seconds=10,
            source_file_size_mb=1,
            transcript_text="原始字幕",
            segments=[{"start": 0, "end": 1, "text": "原始字幕"}],
            deepseek_api_key="test-key",
        )

    fields, note_text, note_segments = asyncio.run(run_stage())

    assert fields == {"note_generation_transcript_source": "transcript_text"}
    assert note_text == "原始字幕"
    assert note_segments == [{"start": 0, "end": 1, "text": "原始字幕"}]


def test_high_confidence_correction_is_saved(monkeypatch) -> None:
    segments = [
        {"start": 0, "end": 2, "text": "我们今天讲大语言模形的上下文窗口。"},
        {"start": 2, "end": 4, "text": "下一步看训练数据。"},
    ]

    monkeypatch.setattr(
        transcript_correction,
        "_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "corrections": [
                    {
                        "segment_index": 0,
                        "original_text": "我们今天讲大语言模形的上下文窗口。",
                        "corrected_text": "我们今天讲大语言模型的上下文窗口。",
                        "reason": "“大语言模型”是课程上下文中的确定术语。",
                        "confidence": 0.94,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = correct_transcript_segments(segments, api_key="test-key")
    fields = correction_result_fields(result, note_input_applied=True)

    assert result.status == "completed"
    assert result.corrections[0]["segment_index"] == 0
    assert result.corrected_segments[0]["text"] == "我们今天讲大语言模型的上下文窗口。"
    assert result.corrected_segments[1]["text"] == "下一步看训练数据。"
    assert fields["transcript_correction"]["note_input_applied"] is True
    assert fields["corrected_transcript_text"].startswith("我们今天讲大语言模型")


def test_low_confidence_correction_is_rejected(monkeypatch) -> None:
    segments = [{"start": 0, "end": 2, "text": "这里可能是在讲向量数据库。"}]
    monkeypatch.setattr(
        transcript_correction,
        "_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "corrections": [
                    {
                        "segment_index": 0,
                        "original_text": "这里可能是在讲向量数据库。",
                        "corrected_text": "这里是在讲向量检索库。",
                        "reason": "不确定术语。",
                        "confidence": 0.52,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = correct_transcript_segments(segments, api_key="test-key")
    fields = correction_result_fields(result)

    assert result.status == "no_changes"
    assert result.corrections == []
    assert result.rejected_count == 1
    assert "corrected_transcript_text" not in fields


def test_mismatched_original_text_is_rejected(monkeypatch) -> None:
    segments = [{"start": 0, "end": 2, "text": "课程里提到 MCP 工具。"}]
    monkeypatch.setattr(
        transcript_correction,
        "_chat",
        lambda *_args, **_kwargs: json.dumps(
            {
                "corrections": [
                    {
                        "segment_index": 0,
                        "original_text": "课程里提到 API 工具。",
                        "corrected_text": "课程里提到 MCP 工具。",
                        "reason": "原文不匹配，不能应用。",
                        "confidence": 0.99,
                    }
                ]
            },
            ensure_ascii=False,
        ),
    )

    result = correct_transcript_segments(segments, api_key="test-key")

    assert result.status == "no_changes"
    assert result.corrections == []
    assert result.rejected_count == 1


def test_model_failure_does_not_raise(monkeypatch) -> None:
    segments = [{"start": 0, "end": 2, "text": "课程字幕。"}]

    def fail_chat(*_args, **_kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(transcript_correction, "_chat", fail_chat)

    result = correct_transcript_segments(segments, api_key="test-key")

    assert result.status == "failed"
    assert result.corrections == []
    assert "provider timeout" in (result.error or "")


def test_missing_key_marks_correction_unavailable() -> None:
    result = correct_transcript_segments([{"start": 0, "end": 1, "text": "hello"}], api_key=None)

    assert result.status == "unavailable"
    assert result.corrected_text == ""
