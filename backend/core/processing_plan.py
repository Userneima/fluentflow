"""Deterministic Processing Plan helpers for Agent-facing task explanations."""

from __future__ import annotations

from typing import Any

PROCESSING_PLAN_VERSION = "1"
SUPPORTED_GOALS = {"course_notes", "lecture_notes"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _source_type(result: dict[str, Any], job: dict[str, Any] | None) -> str:
    return _text(result.get("source") or (job or {}).get("source_type") or "unknown")


def _filename(result: dict[str, Any], job: dict[str, Any] | None) -> str:
    return _text(result.get("display_title") or result.get("filename") or (job or {}).get("source_filename"))


def _duration_seconds(result: dict[str, Any], job: dict[str, Any] | None) -> float | None:
    return _number(result.get("audio_duration_seconds") or (job or {}).get("source_duration_seconds"))


def _transcript_text(result: dict[str, Any]) -> str:
    return _text(result.get("transcript_text") or result.get("transcript_text_preview")).lower()


def _has_transcript(result: dict[str, Any]) -> bool:
    if _transcript_text(result):
        return True
    for key in ("raw_segments", "display_segments", "segments"):
        value = result.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _content_learning_signals(transcript: str) -> list[str]:
    if not transcript:
        return []
    checks = [
        ("content mentions course/class", ("课程", "这节课", "本节课", "课堂", "course", "lecture")),
        ("content mentions explanation", ("讲解", "解释", "概念", "原理", "案例", "example", "concept")),
        ("content has structured learning markers", ("第一", "第二", "第三", "首先", "然后", "最后", "part one", "first", "second")),
    ]
    signals = []
    for label, tokens in checks:
        if any(token in transcript for token in tokens):
            signals.append(label)
    return signals


def _material_type(
    source_type: str,
    filename: str,
    duration_seconds: float | None,
    result: dict[str, Any],
) -> tuple[str, str, list[str]]:
    name = filename.lower()
    evidence: list[str] = []
    content_signals = _content_learning_signals(_transcript_text(result))
    if content_signals:
        evidence.extend(content_signals)
        if duration_seconds and duration_seconds >= 1800:
            evidence.append("duration>=30min")
            return "lecture_material", "high", evidence
        return "course_material", "high", evidence
    if source_type == "transcript_file":
        evidence.append("source_type=transcript_file")
        return "course_transcript_file", "medium", evidence
    if source_type in {"video_link", "douyin", "youtube"}:
        evidence.append(f"source_type={source_type}")
        if duration_seconds and duration_seconds >= 1800:
            evidence.append("duration>=30min")
            return "lecture_video_pending_content", "medium", evidence
        return "course_video_pending_content", "medium", evidence
    if any(token in name for token in ("course", "lecture", "lesson", "课程", "讲座", "课堂", "课")):
        evidence.append("weak filename hint: course_or_lecture")
        return "course_or_lecture_pending_content", "low", evidence
    if source_type in {"video", "audio"}:
        evidence.append(f"source_type={source_type}")
        return "course_or_lecture_pending_content", "medium", evidence
    return "course_or_lecture_pending_content", "low", evidence or ["fallback route"]


def _learning_goal(material_type: str, source_type: str) -> tuple[str, str]:
    if material_type in {"lecture_material", "lecture_video_pending_content"}:
        return "lecture_notes", "按讲座材料处理，优先保留主题结构、论证线索和可复用观点。"
    if source_type == "transcript_file":
        return "course_notes", "已有字幕/转录，整理为可复用课程笔记。"
    return "course_notes", "默认把学习材料整理成可回看的课程笔记。"


def _execution_scope(result: dict[str, Any], job: dict[str, Any] | None, metadata: dict[str, Any]) -> str:
    provider = _text(result.get("stt_provider") or metadata.get("stt_provider"))
    queue_options = metadata.get("queue_options") if isinstance(metadata.get("queue_options"), dict) else {}
    provider = provider or _text(queue_options.get("stt_provider"))
    if provider == "local":
        return "local"
    if provider in {"elevenlabs_scribe", "azure_batch", "azure_fast"}:
        return "cloud"
    if _source_type(result, job) == "transcript_file":
        return "local"
    return "unknown"


def _tool_for_transcription(scope: str, source_type: str) -> str:
    if source_type == "transcript_file":
        return "transcript_parser"
    if scope == "local":
        return "local_whisper"
    if scope == "cloud":
        return "cloud_stt"
    return "stt_provider"


def note_strategy_from_result(result: dict[str, Any]) -> dict[str, Any]:
    requested = _text(result.get("requested_note_mode"))
    selected = _text(result.get("note_mode_plan_selected_mode"))
    resolved = _text(result.get("resolved_note_mode"))
    strategy = {
        "requested_mode": requested or None,
        "selected_mode": selected or resolved or None,
        "resolved_mode": resolved or selected or requested or None,
        "reason": _text(result.get("note_mode_plan_reason")) or None,
        "confidence": _text(result.get("note_mode_plan_confidence")) or None,
        "warnings": result.get("note_mode_plan_warnings") if isinstance(result.get("note_mode_plan_warnings"), list) else [],
        "fallback": result.get("note_mode_plan_fallback") if result.get("note_mode_plan_fallback") is not None else None,
        "error": _text(result.get("note_mode_plan_error")) or None,
        "planner_provider": _text(result.get("note_mode_plan_provider")) or None,
        "planner_model": _text(result.get("note_mode_plan_model")) or None,
    }
    return {key: value for key, value in strategy.items() if value not in (None, "", [])}


def build_processing_plan(
    result: dict[str, Any] | None,
    *,
    job: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    job = job if isinstance(job, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    source_type = _source_type(result, job)
    filename = _filename(result, job)
    duration = _duration_seconds(result, job)
    has_transcript = _has_transcript(result)
    planning_stage = "completed" if has_transcript else "initial"
    material_type, material_confidence, evidence = _material_type(source_type, filename, duration, result)
    goal, goal_reason = _learning_goal(material_type, source_type)
    scope = _execution_scope(result, job, metadata)
    tool = _tool_for_transcription(scope, source_type)
    summary_skipped = bool(result.get("summary_skipped") or result.get("summary_status") == "skipped")
    translation_status = _text(result.get("translation_status"))
    note_strategy = note_strategy_from_result(result)

    steps = [
        {
            "id": "ingest",
            "label": "获取材料",
            "tool": "video_link_resolver" if source_type == "video_link" else ("transcript_parser" if source_type == "transcript_file" else "media_upload"),
            "reason": "把输入材料转换为后续可处理的任务来源。",
        },
        {
            "id": "transcribe",
            "label": "生成或读取转录",
            "tool": tool,
            "reason": "先得到稳定转录，再进入字幕、笔记和导出。",
        },
        {
            "id": "prepare_subtitles",
            "label": "整理字幕",
            "tool": "segment_normalizer",
            "reason": "保留原始可编辑字幕，并生成阅读/导出字幕。",
        },
    ]
    if not summary_skipped:
        steps.append({
            "id": "generate_note",
            "label": "生成学习笔记",
            "tool": "ai_note_generator",
            "note_mode": note_strategy.get("resolved_mode") or note_strategy.get("selected_mode") or note_strategy.get("requested_mode") or "auto",
            "reason": note_strategy.get("reason") or "根据转录长度和任务设置选择笔记生成路线。",
        })
    steps.append({
        "id": "export",
        "label": "保存和导出产物",
        "tool": "artifact_writer",
        "optional": True,
        "reason": "把转录、字幕和笔记保存为可下载产物；飞书导出按设置触发。",
    })

    expected_outputs = ["transcript", "source_subtitles", "artifacts"]
    if translation_status == "completed" or result.get("subtitle_mode") == "bilingual_zh":
        expected_outputs.append("bilingual_subtitles")
    if not summary_skipped:
        expected_outputs.append("markdown_note")

    risk_notes = []
    if material_confidence == "low":
        risk_notes.append("材料类型只基于来源/文件名/时长判断，文件名仅作为弱信号。")
    if planning_stage == "initial":
        risk_notes.append("当前是任务创建时的初始计划，转录完成后会基于正文补全判断。")
    if scope == "unknown":
        risk_notes.append("执行通道无法从当前结果确定，前端应按任务来源继续展示。")
    if note_strategy.get("fallback"):
        risk_notes.append("笔记策略规划曾降级，最终模式可能来自长度规则。")

    return {
        "processing_plan_version": PROCESSING_PLAN_VERSION,
        "generated_by": "deterministic_runtime_plan",
        "planning_stage": planning_stage,
        "execution_mode": "automatic",
        "requires_user_confirmation": False,
        "goal": {
            "primary": goal,
            "reason": goal_reason,
            "supported_goals": sorted(SUPPORTED_GOALS),
        },
        "material": {
            "type": material_type,
            "confidence": material_confidence,
            "source_type": source_type,
            "filename": filename or None,
            "duration_seconds": duration,
            "language": result.get("source_language") or result.get("detected_language"),
            "evidence": evidence,
            "evidence_policy": {
                "transcript_content": "primary" if has_transcript else "pending",
                "filename": "weak",
            },
        },
        "execution": {
            "scope": scope,
            "transcription_tool": tool,
        },
        "steps": steps,
        "note_strategy": note_strategy,
        "expected_outputs": expected_outputs,
        "risk_notes": risk_notes,
    }


def ensure_processing_plan(
    result: dict[str, Any] | None,
    *,
    job: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    existing = result.get("processing_plan") if isinstance(result.get("processing_plan"), dict) else {}
    generated = build_processing_plan(result, job=job, metadata=metadata)
    note_strategy = {
        **dict(existing.get("note_strategy") or {}),
        **generated.get("note_strategy", {}),
    }
    next_plan = {
        **existing,
        **generated,
        "processing_plan_version": PROCESSING_PLAN_VERSION,
        "note_strategy": note_strategy,
    }
    return {**result, "processing_plan": next_plan}
