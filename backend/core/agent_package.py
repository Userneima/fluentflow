"""Agent-facing task package helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.result_schema import canonical_display_segments, canonical_raw_segments
from backend.core.processing_plan import build_processing_plan, ensure_processing_plan
from backend.core.title_display import display_title_for_user
from backend.core.tool_trace import build_tool_trace


AGENT_TASK_PACKAGE_VERSION = "1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def note_generation_diagnosis(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    summary = _text(result.get("summary_markdown"))
    status = _text(result.get("summary_status") or job.get("summary_status")).lower()
    stage = _text(result.get("stage") or job.get("stage")).lower()
    raw_error = _text(result.get("summary_error") or job.get("error_reason"))
    error_text = raw_error.lower()
    has_transcript = bool(_text(result.get("transcript_text") or result.get("transcript_text_preview")))
    has_transcript = has_transcript or bool(canonical_raw_segments(result) or canonical_display_segments(result))

    base = {
        "status": "pending",
        "code": "note_pending",
        "severity": "info",
        "title": "笔记还在生成",
        "detail": "转录已进入摘要阶段，等待 AI 返回笔记。",
        "next_action": "稍等片刻；如果长时间没有变化，再刷新任务状态。",
        "retryable": False,
    }
    if summary:
        return {
            **base,
            "status": "completed",
            "code": "note_completed",
            "severity": "success",
            "title": "笔记已生成",
            "detail": "当前结果包含可用的 AI 笔记。",
            "next_action": "",
            "retryable": True,
        }
    if not has_transcript:
        return {
            **base,
            "status": "unavailable",
            "code": "transcript_missing",
            "severity": "warning",
            "title": "还没有可用于生成笔记的转录",
            "detail": "需要先完成转录，AI 才能生成笔记。",
            "next_action": "先等待或重新提交转录任务。",
        }
    if result.get("summary_skipped") or status == "skipped":
        return {
            **base,
            "status": "skipped",
            "code": "transcript_only_mode",
            "severity": "neutral",
            "title": "本次开启了仅转录模式",
            "detail": "系统按设置跳过了 AI 笔记，转录和字幕已保留。",
            "next_action": "需要笔记时，打开结果并重新生成。",
            "retryable": True,
        }
    if status == "failed" or raw_error:
        code = "ai_note_failed"
        title = "AI 笔记生成失败"
        next_action = "重新生成；如果仍失败，换一个笔记模式或缩短材料。"
        if any(token in error_text for token in ("quota", "balance", "额度", "余额")):
            code = "quota_insufficient"
            title = "额度不足，笔记未生成"
            next_action = "补足额度后重新生成，或降低本次处理成本。"
        elif any(token in error_text for token in ("401", "login", "auth", "account")):
            code = "auth_required"
            title = "账号状态阻止了笔记生成"
            next_action = "重新登录后再重新生成。"
        elif any(token in error_text for token in ("404", "job not found", "not found")):
            code = "job_scope_mismatch"
            title = "任务归属不一致，笔记未生成"
            next_action = "刷新任务列表后从同一条记录继续；如果仍失败，重新提交任务。"
        elif "empty" in error_text:
            code = "empty_ai_note"
            title = "AI 返回了空笔记"
            next_action = "重新生成；如果重复出现，换用直接生成模式或调整提示词。"
        elif "unsupported note generation mode" in error_text or "chapter_coverage" in error_text:
            code = "unsupported_note_mode"
            title = "笔记模式不受当前版本支持"
            next_action = "选择“自动”或“高保真”后重新提交任务。"
        return {
            **base,
            "status": "failed",
            "code": code,
            "severity": "error",
            "title": title,
            "detail": raw_error or "处理失败，但没有返回具体原因。",
            "next_action": next_action,
            "retryable": True,
        }
    if status == "pending" or stage == "summary":
        return base
    return {
        **base,
        "code": "note_missing_unknown",
        "severity": "warning",
        "title": "暂时没有可见笔记",
        "detail": "转录已存在，但结果里没有记录明确的笔记状态。",
        "next_action": "重新生成；如果失败，再查看任务详情。",
        "retryable": True,
    }


def _artifact_local_path(task_id: str, artifact: dict[str, Any], artifact_root: Path | None) -> str | None:
    if artifact_root is None:
        return None
    filename = Path(_text(artifact.get("filename"))).name
    if not filename:
        return None
    return str((artifact_root / task_id / filename).expanduser())


def _agent_artifacts(task_id: str, result: dict[str, Any], artifact_root: Path | None) -> dict[str, dict[str, Any]]:
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    payload: dict[str, dict[str, Any]] = {}
    for kind, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        url = _text(artifact.get("url")) or f"/jobs/{task_id}/artifacts/{kind}"
        item = {
            "kind": str(kind),
            "filename": _text(artifact.get("filename")),
            "url": url,
            "download_url": url,
            "content_type": artifact.get("content_type"),
            "size_bytes": artifact.get("size_bytes"),
        }
        local_path = _artifact_local_path(task_id, artifact, artifact_root)
        if local_path:
            item["local_path"] = local_path
        payload[str(kind)] = {key: value for key, value in item.items() if value is not None and value != ""}
    return payload


def _next_actions(job: dict[str, Any], diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if diagnosis.get("retryable") and diagnosis.get("code") != "note_completed":
        actions.append({
            "action": "regenerate_note",
            "method": "POST",
            "path": f"/agent/v1/tasks/{job.get('task_id')}/note/regenerate",
            "reason": diagnosis.get("next_action") or diagnosis.get("title"),
        })
    if job.get("status") in {"queued", "running"}:
        actions.append({
            "action": "wait",
            "method": "GET",
            "path": f"/agent/v1/tasks/{job.get('task_id')}/package",
            "reason": "任务仍在处理，稍后再次读取任务包。",
        })
    return actions


def build_agent_task_package(job: dict[str, Any], *, artifact_root: Path | None = None) -> dict[str, Any]:
    task_id = _text(job.get("task_id"))
    raw_result = job.get("result")
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_metadata = job.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
    result = ensure_processing_plan(result, job=job, metadata=metadata)
    raw_video_source = metadata.get("video_source")
    video_source = raw_video_source if isinstance(raw_video_source, dict) else {}
    raw_segments = canonical_raw_segments(result)
    display_segments = canonical_display_segments(result)
    transcript_text = _text(result.get("transcript_text"))
    diagnosis = note_generation_diagnosis(job, result)
    title = (
        _text(result.get("display_title"))
        or _text(metadata.get("display_title"))
        or _text(video_source.get("display_title"))
        or display_title_for_user(video_source.get("title"), result.get("filename") or job.get("source_filename"))
        or display_title_for_user(job.get("source_filename"), task_id)
        or task_id
    )
    artifacts = _agent_artifacts(task_id, result, artifact_root)
    note_status = diagnosis["status"]
    if result.get("summary_skipped"):
        note_status = "skipped"
    elif _text(result.get("summary_markdown")):
        note_status = "completed"

    package = {
        "agent_task_package_version": AGENT_TASK_PACKAGE_VERSION,
        "task": {
            "task_id": task_id,
            "status": job.get("status"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        },
        "title": title,
        "source": {
            "type": job.get("source_type") or result.get("source"),
            "filename": result.get("filename") or job.get("source_filename"),
            "raw_title": result.get("raw_title") or metadata.get("raw_title") or video_source.get("raw_title"),
            "display_title": title,
            "url": video_source.get("url") or video_source.get("webpage_url"),
            "duration_seconds": result.get("audio_duration_seconds") or job.get("source_duration_seconds"),
            "file_size_mb": job.get("source_file_size_mb"),
            "video_source": video_source or None,
        },
        "transcript": {
            "available": bool(transcript_text or raw_segments or display_segments),
            "text": transcript_text,
            "preview": _text(result.get("transcript_text_preview") or transcript_text[:300]),
            "raw_segments": raw_segments,
            "display_segments": display_segments,
            "raw_segment_count": len(raw_segments),
            "display_segment_count": len(display_segments),
            "source_language": result.get("source_language"),
            "detected_language": result.get("detected_language"),
            "subtitle_mode": result.get("subtitle_mode"),
            "translation_status": result.get("translation_status"),
        },
        "note": {
            "status": note_status,
            "markdown": _text(result.get("summary_markdown")),
            "markdown_chars": len(_text(result.get("summary_markdown"))),
            "diagnosis": diagnosis,
            "requested_mode": result.get("requested_note_mode"),
            "resolved_mode": result.get("resolved_note_mode"),
            "prompt_preset": result.get("prompt_preset"),
            "prompt_preset_label": result.get("prompt_preset_label"),
            "stats": {
                "chunk_count": result.get("note_mode_chunk_count"),
                "segment_count": result.get("note_mode_segment_count"),
                "evidence_count": result.get("note_mode_evidence_count"),
                "chapter_count": result.get("note_mode_chapter_count"),
                "important_evidence_count": result.get("note_mode_important_evidence_count"),
                "covered_important_evidence_count": result.get("note_mode_covered_important_evidence_count"),
                "coverage_missing_count": result.get("note_mode_coverage_missing_count"),
            },
        },
        "artifacts": artifacts,
        "usage": {
            "estimated_processing_units": job.get("estimated_processing_units") or result.get("estimated_processing_units"),
            "billable_processing_units": job.get("billable_processing_units") or result.get("billable_processing_units"),
        },
    }
    package["processing_plan"] = result.get("processing_plan") or build_processing_plan(result, job=job, metadata=metadata)
    package["tool_trace"] = build_tool_trace(result, job=job)
    package["next_actions"] = _next_actions(job, diagnosis)
    return package
