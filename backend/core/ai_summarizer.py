"""Summarize Whisper transcripts with OpenAI-compatible chat providers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Final

from dotenv import load_dotenv
from openai import OpenAI

DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
OPENAI_BASE_URL: Final[str] = "https://api.openai.com/v1"
DEFAULT_DEEPSEEK_MODEL: Final[str] = "deepseek-chat"
DEFAULT_OPENAI_MODEL: Final[str] = "gpt-5.4-mini"
DEFAULT_MODEL: Final[str] = DEFAULT_DEEPSEEK_MODEL
SUPPORTED_PROVIDERS: Final[set[str]] = {"deepseek", "openai"}
SUPPORTED_NOTE_MODES: Final[set[str]] = {"auto", "direct", "fast", "high_fidelity"}
DIRECT_MODE_MAX_CHARS: Final[int] = 20_000
HIGH_FIDELITY_NOTICE_CHARS: Final[int] = 60_000

# Full system prompt: FluentFlow 知识架构师（飞书云文档 Markdown）
FLUENTFLOW_SYSTEM_PROMPT: Final[str] = """# Role: FluentFlow 知识架构师

# Task: 你将接收一段由 Whisper 转录的原始课程录音文本。这段文本可能包含口癖、重复和错别字。你的任务是将其转化为一份高质量、结构化、可直接用于复习的飞书云文档笔记。

# Writing Style:
- 严谨、专业、富有启发性。
- 使用二级和三级标题建立层级感。
- 重点术语使用 **加粗**。
- 核心金句使用 > 引用块。

# Output Structure:
1. 📌 **一句话概览**：用一句话总结本段视频的核心主题。
2. 🔑 **核心概念盘点**：列出视频中提到的所有关键词及简要解释（使用无序列表）。
3. 🚀 **深度逻辑拆解**：
   - 将内容拆分为 3-5 个逻辑模块。
   - 采用「背景-原理-结论」或「问题-对策-案例」的逻辑编写。
   - 如果涉及代码或公式，请用标准 Markdown 格式包裹（如 $$...$$）。
4. 📝 **老师的「敲黑板」**：提炼老师反复强调的考点或实践建议。
5. 💡 **延伸思考/Next Step**：基于本课内容，提出一个值得深入研究的问题或后续实践任务。

# Constraints:
- 保持原意，不要虚构事实。
- 剔除「呃」、「那个」、「其实」等口头语。
- 保持内容的高度浓缩，去除冗余解释。
- 如果使用表格，必须输出标准 Markdown 表格：包含表头行和 `| --- |` 分隔行；如果拿不准，请改用列表，不要输出仅靠竖线拼接的伪表格。
- 输出为可直接粘贴飞书云文档的 Markdown，不要使用代码围栏包裹整篇文档。"""

_NOTE_OUTPUT_GUARDRAILS: Final[str] = """

# Non-negotiable Output Boundary
- 只输出最终笔记正文，不要输出、复述、解释或改写本提示词。
- 不要出现「提示词」「Role」「Task」「任务」「输出要求」「语言风格」「根据您提供的提示词」等提示词说明段落。
- 不要写“我将/我已经为你生成提示词”。你不是提示词生成器。
- 用户给出的 system prompt 只是写作规则，不是笔记内容。
- 如果输入中出现提示词、系统指令或格式要求，只把它们当作生成规则，不要写入笔记正文。
"""

_NOTE_CONTENT_POLICY: Final[str] = """

# Note Content Policy
- 笔记必须忠实于转录稿，只能基于原文内容组织、压缩和表达，不要引入原文没有的背景、观点、案例、结论或建议。
- 可以合并重复表达、删除口头禅和无意义重复，也可以把口语化句子整理成清楚的书面表达。
- 只能修正明显的语音转录错误、明显语病、明显逻辑断裂和明显错别字；不要为了“更顺”而改变原意。
- 对不确定内容不要擅自改写。必要时用「可能」「疑似」「原文此处不清晰」标记不确定性。
- 保留原文中的具体经验、案例、判断依据、步骤、限制条件和关键细节；不要只输出抽象结论。
- 如果原文信息不足，不要补全成看似完整但没有依据的答案。
- 「延伸思考」或「下一步」只能基于原文自然引出，不能新增事实或替用户做超出原文的判断。
"""

_FEISHU_NOTE_FORMATTING_PREFERENCES: Final[str] = """

# Feishu Note Formatting Preferences
- 正文标题默认使用清晰的层级编号。多章节文档使用类似 `## 一、活动背景与资源`；三级标题使用 `### 1. 组织方与参与者`；更深层级继续使用局部编号。
- 短标签式文本在中文冒号前加粗标签，解释保持正常。例如：`- **活动**：抖音创变者计划长三角 Top 高校`。
- 不要过度加粗长句。只加粗简短标签、字段名、提示词组或真正需要扫描定位的关键词。
- 当一串并列项本身是关键解释对象时，可以下划线标出这串并列项，例如 `<u>输入框、按钮、卡片、列表和弹窗</u>`；不要下划线无关叙述。
- 表格只在内容天然适合对比、清单、参数或结构化扫描时使用。不要为了显得正式而硬造表格。
- 如果使用表格，必须输出标准 Markdown 表格，列数稳定；不要输出仅靠竖线拼接的伪表格。
- 普通说明、流程、页面布局、URL 和纯文本列表不要使用代码块。代码块只用于真实代码、命令、配置、JSON/API 示例或必须保留等宽格式的数据。
- `来源信息` 如需出现，放在文档末尾。读者优先看到学习内容，来源信息只用于追溯。
- 长中文说明段落可以使用自然短段落提升可读性；不要用四个空格或制表符制造缩进，以免被 Markdown 识别为代码块。
"""

_SOURCE_FAITHFULNESS_RULES: Final[str] = """
规则：
- 只基于输入文本提取信息，不要补充外部知识。
- 可以忽略口头禅、重复和无意义噪声。
- 只能修正明显转录错误；不确定就标注「疑似」或「原文不清晰」。
- 保留具体例子、数字、步骤、限制条件和判断依据。
"""

# 分段提炼时使用（减轻最终合并输入长度）
_INTERIM_SYSTEM: Final[str] = f"""你是 FluentFlow 的预处理助手。输入为 Whisper 转录的一小段原文。
请用简洁的中文 Markdown 输出：
- 本段关键事实、术语与数字
- 本段讲解主线（短句列表即可）
输出将用于后续合并，无需五大板块的完整成品格式。
{_SOURCE_FAITHFULNESS_RULES}"""

_BATCH_CONDENSE_SYSTEM: Final[str] = f"""你是 FluentFlow 的编校助手。下面若干段是同一课程不同时间段的「分段要点草稿」。
请合并去重，保留重要术语与逻辑顺序，输出一份连贯的「合并要点稿」（仍用 Markdown，可多级列表），不要套用五大板块终稿格式。
{_SOURCE_FAITHFULNESS_RULES}"""

_EVIDENCE_SYSTEM: Final[str] = f"""你是 FluentFlow 的课程证据提取助手。输入是同一课程转录文本的一段。
你的任务不是写最终笔记，而是尽量完整地提取可用于笔记的「证据清单」。

请按以下 Markdown 结构输出，保留细节，不要过度概括：
## 本段主题
- ...

## 概念与术语
- 术语：解释

## 关键观点
- ...

## 方法、步骤或框架
- ...

## 例子、案例、类比
- ...

## 数字、条件、限制
- ...

## 老师强调/容易漏掉的细节
- ...

规则：
- 不要编造，不确定就标注「疑似」。
- 如果某一栏没有内容，写「无」。
- 目标是保留信息，而不是写得漂亮。
{_SOURCE_FAITHFULNESS_RULES}"""

_EVIDENCE_CONDENSE_SYSTEM: Final[str] = f"""你是 FluentFlow 的证据合并助手。输入是同一课程多个片段的证据清单。
请合并去重，但必须尽量保留概念、例子、数字、步骤和老师强调的细节。
输出仍然是 Markdown 证据清单，不要写成最终笔记。
{_SOURCE_FAITHFULNESS_RULES}"""

_FINAL_WRAPPER: Final[str] = (
    "以下内容来自**同一门课程**转录文本的分段提炼（按时间顺序）。"
    "请**整理为一份完整**、可直接用于飞书云文档的 Markdown 笔记，"
    "严格遵循系统说明中的角色、版式与五大板块结构，理顺逻辑并去重。\n\n---\n\n"
)

_HIGH_FIDELITY_FINAL_WRAPPER: Final[str] = (
    "以下内容是从同一门课程转录文本中按时间顺序提取的「证据清单」。"
    "请基于这些证据整理为一份完整、可复习、可直接放入飞书云文档的 Markdown 课程笔记。"
    "不要只写抽象总结；必须吸收重要概念、例子、数字、方法步骤和老师强调。"
    "严格遵循系统说明中的角色、版式与五大板块结构。\n\n---\n\n"
)

_COVERAGE_SYSTEM: Final[str] = """你是 FluentFlow 的笔记覆盖率审查助手。
请对照「证据清单」和「已生成笔记」，检查笔记是否遗漏了重要概念、例子、数字、步骤、限制条件或老师强调。
如果没有明显遗漏，只输出：COVERED
如果有遗漏，请用 Markdown 列出「需要补入的遗漏点」，不要重写整篇笔记。"""

_REVISION_WRAPPER: Final[str] = """下面是已生成的课程笔记，以及覆盖率审查发现的遗漏点。
请在不推翻原结构的前提下，把遗漏点自然补入笔记，输出完整修订版 Markdown。

--- 已生成笔记 ---

{draft}

--- 需要补入的遗漏点 ---

{coverage}
"""

_PROMPT_SECTION_HEADING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*)?(?:\*\*)?(提示词|系统提示词|prompt|system prompt)(?:\*\*)?\s*[:：]?\s*$",
    re.IGNORECASE,
)
_PROMPT_META_LINE_RE = re.compile(
    r"^\s{0,3}(?:[-*]\s*)?(?:\*\*)?"
    r"(角色|任务|输出要求|语言风格|writing style|output structure|constraints|role|task)"
    r"(?:\*\*)?\s*[:：]",
    re.IGNORECASE,
)
_ASSISTANT_PREFACE_RE = re.compile(
    r"^\s*(好的，?)?根据.*?(提示词|字幕|转录|语音转文字).*?(生成|整理|产出).*?(笔记|提示词).*?$"
)


@dataclass(frozen=True)
class SummaryResult:
    markdown: str
    requested_mode: str
    resolved_mode: str
    transcript_length: int
    chunk_count: int
    coverage_checked: bool = False
    coverage_revision_used: bool = False


def _normalize_provider(provider: str | None) -> str:
    p = (provider or os.environ.get("AI_PROVIDER") or "deepseek").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {provider}")
    return p


def _provider_base_url(provider: str) -> str:
    if provider == "openai":
        return (os.environ.get("OPENAI_BASE_URL") or OPENAI_BASE_URL).rstrip("/")
    return (os.environ.get("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).rstrip("/")


def _provider_default_model(provider: str) -> str:
    if provider == "openai":
        return (os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()
    return (os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL).strip()


def _provider_api_key(provider: str, api_key: str | None = None) -> str:
    load_dotenv()
    env_name = "OPENAI_API_KEY" if provider == "openai" else "DEEPSEEK_API_KEY"
    key = (api_key or os.environ.get(env_name, "")).strip()
    if not key:
        raise ValueError(f"{env_name} 未设置：请在 .env 中配置或在设置页填写 API Key。")
    return key


def _get_client(*, provider: str, api_key: str | None = None) -> OpenAI:
    key = _provider_api_key(provider, api_key)
    return OpenAI(api_key=key, base_url=_provider_base_url(provider))


def _chat(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    msg = resp.choices[0].message
    return (msg.content or "").strip()


def _compose_note_system_prompt(system_prompt: str | None) -> str:
    base = (system_prompt or "").strip() or FLUENTFLOW_SYSTEM_PROMPT
    return (
        f"{base.rstrip()}"
        f"{_NOTE_CONTENT_POLICY}"
        f"{_FEISHU_NOTE_FORMATTING_PREFERENCES}"
        f"{_NOTE_OUTPUT_GUARDRAILS}"
    )


def _looks_like_real_note_heading(line: str) -> bool:
    stripped = line.strip().lstrip("#").strip()
    if not stripped:
        return False
    blocked = {
        "提示词",
        "系统提示词",
        "prompt",
        "system prompt",
        "角色",
        "任务",
        "输出要求",
        "语言风格",
    }
    lowered = stripped.rstrip(":：").lower()
    return lowered not in blocked and not _PROMPT_META_LINE_RE.match(stripped)


def _strip_prompt_leakage(markdown: str) -> str:
    """Remove obvious prompt-template leakage while keeping the generated note."""
    lines = (markdown or "").strip().splitlines()
    if not lines:
        return ""

    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _ASSISTANT_PREFACE_RE.match(lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)

    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _PROMPT_SECTION_HEADING_RE.match(line):
            i += 1
            while i < len(lines):
                candidate = lines[i]
                stripped = candidate.strip()
                if stripped in {"---", "***", "___"}:
                    i += 1
                    break
                if stripped.startswith("#") and _looks_like_real_note_heading(stripped):
                    break
                i += 1
            continue
        if _PROMPT_META_LINE_RE.match(line):
            i += 1
            continue
        cleaned.append(line)
        i += 1

    return "\n".join(cleaned).strip()


def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """按长度分段，优先在换行处断开；段间带 overlap 以减少句首截断。"""
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]

    chunks: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        j = min(i + max_chars, n)
        if j < n:
            br = t.rfind("\n", i + max_chars // 2, j)
            if br != -1:
                j = br + 1
        piece = t[i:j].strip()
        if piece:
            chunks.append(piece)
        if j >= n:
            break
        i = max(i + 1, j - max(0, overlap))
    return chunks


def _normalize_note_mode(mode: str | None) -> str:
    value = (mode or os.environ.get("FLUENTFLOW_NOTE_MODE") or "auto").strip().lower()
    if value not in SUPPORTED_NOTE_MODES:
        raise ValueError(f"Unsupported note generation mode: {mode}")
    return "direct" if value == "fast" else value


def _resolve_note_mode(mode: str, transcript_length: int) -> str:
    if mode != "auto":
        return mode
    return "direct" if transcript_length <= DIRECT_MODE_MAX_CHARS else "high_fidelity"


def _condense_interim_drafts(
    client: OpenAI,
    model: str,
    drafts: list[str],
    *,
    max_batch_chars: int,
) -> str:
    """当中间稿总长过大时，分批压缩为一份合并要点，再交给终稿系统提示。"""
    if not drafts:
        return ""
    if len(drafts) == 1:
        return drafts[0]

    batches: list[str] = []
    buf: list[str] = []
    size = 0
    sep = "\n\n---\n\n"
    for d in drafts:
        add = len(d) + (len(sep) if buf else 0)
        if buf and size + add > max_batch_chars:
            batches.append(sep.join(buf))
            buf = [d]
            size = len(d)
        else:
            buf.append(d)
            size += add
    if buf:
        batches.append(sep.join(buf))

    condensed = [_chat(client, model, _BATCH_CONDENSE_SYSTEM, b) for b in batches]
    if len(condensed) == 1:
        return condensed[0]
    joined = "\n\n===\n\n".join(condensed)
    if len(joined) <= max_batch_chars:
        return _chat(client, model, _BATCH_CONDENSE_SYSTEM, joined)
    # 最后一层：再压一次
    return _chat(client, model, _BATCH_CONDENSE_SYSTEM, joined[: max_batch_chars])


def _condense_evidence(
    client: OpenAI,
    model: str,
    evidence_items: list[str],
    *,
    max_batch_chars: int,
) -> str:
    if not evidence_items:
        return ""
    joined = "\n\n---\n\n".join(evidence_items)
    if len(joined) <= max_batch_chars:
        return joined
    condensed = _condense_interim_drafts(
        client,
        model,
        evidence_items,
        max_batch_chars=max_batch_chars,
    )
    return _chat(client, model, _EVIDENCE_CONDENSE_SYSTEM, condensed)


def summarize_transcript_with_metadata(
    transcript: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    system_prompt: str | None = None,
    note_mode: str | None = None,
    max_chunk_chars: int = 10_000,
    chunk_overlap: int = 400,
    max_final_input_chars: int = 55_000,
    interim_batch_cap: int = 28_000,
    evidence_chunk_chars: int = 8_000,
    evidence_overlap: int = 300,
) -> SummaryResult:
    """Generate a note and return mode/chunk metadata for product analysis."""
    load_dotenv()
    provider_name = _normalize_provider(provider)
    client = _get_client(provider=provider_name, api_key=api_key)
    m = (model or _provider_default_model(provider_name)).strip()
    prompt = _compose_note_system_prompt(system_prompt)
    normalized_mode = _normalize_note_mode(note_mode)
    transcript_text = transcript.strip()
    transcript_length = len(transcript_text)
    resolved_mode = _resolve_note_mode(normalized_mode, transcript_length)
    if not transcript_text:
        return SummaryResult(
            markdown="",
            requested_mode=normalized_mode,
            resolved_mode=resolved_mode,
            transcript_length=0,
            chunk_count=0,
        )

    if resolved_mode == "direct":
        return SummaryResult(
            markdown=_strip_prompt_leakage(_chat(client, m, prompt, transcript_text)),
            requested_mode=normalized_mode,
            resolved_mode=resolved_mode,
            transcript_length=transcript_length,
            chunk_count=1,
        )

    chunks = _chunk_text(transcript_text, evidence_chunk_chars, evidence_overlap)
    evidence_items: list[str] = []
    total = len(chunks)
    for idx, chunk in enumerate(chunks):
        user = f"这是整段转录的第 {idx + 1}/{total} 部分，请提取证据。\n\n{chunk}"
        evidence_items.append(_chat(client, m, _EVIDENCE_SYSTEM, user, temperature=0.2))

    evidence = "\n\n---\n\n".join(
        f"## 片段 {idx + 1}/{total}\n{item}" for idx, item in enumerate(evidence_items)
    )
    if len(_HIGH_FIDELITY_FINAL_WRAPPER + evidence) > max_final_input_chars:
        evidence = _condense_evidence(
            client,
            m,
            evidence_items,
            max_batch_chars=interim_batch_cap,
        )

    draft = _strip_prompt_leakage(_chat(client, m, prompt, _HIGH_FIDELITY_FINAL_WRAPPER + evidence))
    coverage_input = f"--- 证据清单 ---\n\n{evidence}\n\n--- 已生成笔记 ---\n\n{draft}"
    coverage_checked = len(coverage_input) <= max_final_input_chars
    coverage_revision_used = False
    final_note = draft
    if coverage_checked:
        coverage = _chat(client, m, _COVERAGE_SYSTEM, coverage_input, temperature=0.1).strip()
        if coverage and coverage != "COVERED":
            final_note = _strip_prompt_leakage(
                _chat(
                    client,
                    m,
                    prompt,
                    _REVISION_WRAPPER.format(draft=draft, coverage=coverage),
                    temperature=0.2,
                )
            )
            coverage_revision_used = True

    return SummaryResult(
        markdown=final_note,
        requested_mode=normalized_mode,
        resolved_mode=resolved_mode,
        transcript_length=transcript_length,
        chunk_count=total,
        coverage_checked=coverage_checked,
        coverage_revision_used=coverage_revision_used,
    )


def summarize_transcript_to_markdown(
    transcript: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    system_prompt: str | None = None,
    note_mode: str | None = None,
    max_chunk_chars: int = 10_000,
    chunk_overlap: int = 400,
    max_final_input_chars: int = 55_000,
    interim_batch_cap: int = 28_000,
) -> str:
    """将整段转录稿总结为飞书友好的结构化 Markdown。"""
    return summarize_transcript_with_metadata(
        transcript,
        api_key=api_key,
        model=model,
        provider=provider,
        system_prompt=system_prompt,
        note_mode=note_mode,
        max_chunk_chars=max_chunk_chars,
        chunk_overlap=chunk_overlap,
        max_final_input_chars=max_final_input_chars,
        interim_batch_cap=interim_batch_cap,
    ).markdown


__all__ = [
    "DEEPSEEK_BASE_URL",
    "OPENAI_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_DEEPSEEK_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "FLUENTFLOW_SYSTEM_PROMPT",
    "DIRECT_MODE_MAX_CHARS",
    "HIGH_FIDELITY_NOTICE_CHARS",
    "SummaryResult",
    "summarize_transcript_with_metadata",
    "summarize_transcript_to_markdown",
]
