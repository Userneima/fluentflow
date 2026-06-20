"""Shared job/result lifecycle semantics for FluentFlow."""

from __future__ import annotations

from typing import Any


def result_has_transcript(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    return bool(
        str(result.get("transcript_text") or result.get("transcript_text_preview") or "").strip()
        or (isinstance(result.get("segments"), list) and len(result.get("segments") or []) > 0)
        or (isinstance(result.get("cleaned_segments"), list) and len(result.get("cleaned_segments") or []) > 0)
        or (isinstance(result.get("raw_segments"), list) and len(result.get("raw_segments") or []) > 0)
    )


def job_has_transcript_result(job: dict[str, Any] | None) -> bool:
    if not isinstance(job, dict):
        return False
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return result_has_transcript(result)


def result_for_transcript_only(base_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **base_result,
        "status": "completed",
        "summary_markdown": base_result.get("summary_markdown") or "",
        "summary_skipped": True,
        "summary_status": "skipped",
    }


def result_for_summary_failure(base_result: dict[str, Any], summary_error: str) -> dict[str, Any]:
    return {
        **base_result,
        "status": "completed",
        "summary_markdown": "",
        "summary_skipped": False,
        "summary_status": "failed",
        "summary_error": summary_error,
    }


def result_for_summary_success(
    base_result: dict[str, Any],
    summary_markdown: str,
    *,
    requested_note_mode: str | None = None,
    resolved_note_mode: str | None = None,
    note_mode_chunk_count: int | None = None,
    prompt_preset: str | None = None,
    prompt_preset_label: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        **base_result,
        "status": "completed",
        "summary_markdown": summary_markdown,
        "summary_skipped": False,
        "summary_status": "completed",
    }
    if requested_note_mode is not None:
        result["requested_note_mode"] = requested_note_mode
    if resolved_note_mode is not None:
        result["resolved_note_mode"] = resolved_note_mode
    if note_mode_chunk_count is not None:
        result["note_mode_chunk_count"] = note_mode_chunk_count
    if prompt_preset is not None:
        result["prompt_preset"] = prompt_preset
    if prompt_preset_label is not None:
        result["prompt_preset_label"] = prompt_preset_label
    return result
