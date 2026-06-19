"""Plan FluentFlow note-generation strategy with an LLM-backed narrow agent."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Final

from .ai_summarizer import _chat, _get_client, _normalize_model, _normalize_provider


ALLOWED_PLAN_NOTE_MODES: Final[set[str]] = {"direct", "high_fidelity", "chapter_coverage"}
ALLOWED_PLAN_PROMPT_PRESETS: Final[set[str]] = {
    "autoTranscriptNotes",
    "default",
    "meeting",
    "research",
    "quickBullets",
}
ALLOWED_PLAN_CONFIDENCE: Final[set[str]] = {"low", "medium", "high"}
ALLOWED_MATERIAL_TYPES: Final[set[str]] = {
    "course",
    "interview",
    "career_talk",
    "meeting",
    "research",
    "competition_brief",
    "product_training",
    "other",
}

_PLANNER_SYSTEM: Final[str] = """你是 FluentFlow 的笔记任务策略 Agent。
你的职责是根据材料信息，为后续笔记生成推荐处理策略。你只做策略选择，不写笔记。

必须只输出一个 JSON 对象，不要输出 Markdown、解释或代码块。

允许值：
- material_type: course, interview, career_talk, meeting, research, competition_brief, product_training, other
- recommended_note_mode: direct, high_fidelity, chapter_coverage
- recommended_prompt_preset: autoTranscriptNotes, default, meeting, research, quickBullets
- confidence: low, medium, high

判断规则：
- 短材料或只需要快速浏览：direct。
- 中长材料、访谈、求职分享、课程分享：high_fidelity。
- 很长、信息密度高、要求尽量完整覆盖的课程/讲座/复杂资料：chapter_coverage。
- 会议纪要类材料优先 meeting。
- 论文、研究讲座、学术讨论优先 research。
- 只要点速览优先 quickBullets。
- 求职分享、企业参访、经验交流通常使用 autoTranscriptNotes 或 default，不要发明新模板 key。

JSON 字段：
{
  "material_type": "career_talk",
  "recommended_note_mode": "high_fidelity",
  "recommended_prompt_preset": "autoTranscriptNotes",
  "needs_qa_section": true,
  "needs_action_items": false,
  "confidence": "medium",
  "reason": "一句话说明为什么这样选",
  "warnings": ["可选，列出需要用户注意的风险"]
}
"""


@dataclass(frozen=True)
class NoteTaskPlan:
    material_type: str
    recommended_note_mode: str
    recommended_prompt_preset: str
    needs_qa_section: bool
    needs_action_items: bool
    confidence: str
    reason: str
    warnings: list[str]
    planner_provider: str
    planner_model: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("Planner did not return JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            raise ValueError("Planner returned malformed JSON")
    if not isinstance(parsed, dict):
        raise ValueError("Planner JSON must be an object")
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _clean_warnings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip()[:180] for item in value if str(item).strip()][:5]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:180]]
    return []


def _sanitize_plan_payload(payload: dict[str, Any], *, provider: str, model: str) -> NoteTaskPlan:
    material_type = str(payload.get("material_type") or "other").strip()
    if material_type not in ALLOWED_MATERIAL_TYPES:
        material_type = "other"

    note_mode = str(payload.get("recommended_note_mode") or "").strip()
    if note_mode not in ALLOWED_PLAN_NOTE_MODES:
        note_mode = "high_fidelity"

    prompt_preset = str(payload.get("recommended_prompt_preset") or "").strip()
    if prompt_preset not in ALLOWED_PLAN_PROMPT_PRESETS:
        prompt_preset = "autoTranscriptNotes"

    confidence = str(payload.get("confidence") or "medium").strip()
    if confidence not in ALLOWED_PLAN_CONFIDENCE:
        confidence = "medium"

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        reason = "根据材料类型、长度和用户目标选择较稳妥的笔记生成策略。"

    return NoteTaskPlan(
        material_type=material_type,
        recommended_note_mode=note_mode,
        recommended_prompt_preset=prompt_preset,
        needs_qa_section=_coerce_bool(payload.get("needs_qa_section")),
        needs_action_items=_coerce_bool(payload.get("needs_action_items")),
        confidence=confidence,
        reason=reason[:500],
        warnings=_clean_warnings(payload.get("warnings")),
        planner_provider=provider,
        planner_model=model,
    )


def plan_note_task(
    *,
    filename: str | None = None,
    transcript_preview: str | None = None,
    transcript_length: int | None = None,
    duration_seconds: float | None = None,
    user_goal: str | None = None,
    current_note_mode: str | None = None,
    current_prompt_preset: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> NoteTaskPlan:
    provider_name = _normalize_provider(provider)
    model_name = _normalize_model(provider_name, model)
    client = _get_client(provider=provider_name, api_key=api_key)
    preview = (transcript_preview or "").strip()
    if len(preview) > 8000:
        preview = preview[:8000]
    user_payload = {
        "filename": (filename or "").strip()[:240],
        "transcript_length": transcript_length,
        "duration_seconds": duration_seconds,
        "user_goal": (user_goal or "").strip()[:500],
        "current_note_mode": current_note_mode,
        "current_prompt_preset": current_prompt_preset,
        "transcript_preview": preview,
    }
    raw = _chat(
        client,
        model_name,
        _PLANNER_SYSTEM,
        json.dumps(user_payload, ensure_ascii=False),
        temperature=0.1,
    )
    parsed = _extract_json_object(raw)
    return _sanitize_plan_payload(parsed, provider=provider_name, model=model_name)
