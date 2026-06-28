"""Summarize Whisper transcripts with OpenAI-compatible chat providers."""

from __future__ import annotations

import os
import re
import json
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from dotenv import load_dotenv
from openai import OpenAI

DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
OPENAI_BASE_URL: Final[str] = "https://api.openai.com/v1"
QWEN_BASE_URL: Final[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DEEPSEEK_MODEL: Final[str] = "deepseek-reasoner"
DEFAULT_OPENAI_MODEL: Final[str] = "gpt-5.4-mini"
DEFAULT_QWEN_MODEL: Final[str] = "qwen3.7-plus"
DEFAULT_MODEL: Final[str] = DEFAULT_DEEPSEEK_MODEL
SUPPORTED_PROVIDERS: Final[set[str]] = {"deepseek", "openai", "qwen"}
SUPPORTED_NOTE_MODES: Final[set[str]] = {"auto", "direct", "fast", "high_fidelity", "chapter_coverage"}
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

_NOTE_OUTPUT_LANGUAGE: Final[str] = """

# Output Language
- 最终笔记默认使用中文输出。即使输入转录稿是英文，也应直接理解英文原文并写成中文笔记。
- 不要把英文原文整段翻译后再作为笔记；笔记应是基于原文的结构化中文整理。
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

_MULTIMODAL_NOTE_SYSTEM: Final[str] = """# Role: FluentFlow 多模态知识架构师

你将收到：
1. 完整的视频转录稿（文本）
2. 从视频中截取的若干画面（图片，每张带有时间戳和文件名标注）

你的任务：
- 仔细审阅所有截图，选出 3-8 张真正有信息量的画面：
  - 板书、PPT 幻灯片、代码片段、图表、流程图、数据表格
  - 关键演示画面、重要的实物展示、场景切换
  - 不要选：模糊画面、过渡动画中间帧、纯人物讲话且无明显视觉信息
- 按照「知识架构师」的标准，生成一份结构化中文笔记
- 在笔记最合适的位置，用 Markdown 图片语法插入选中的截图
- 每张截图配一句简短中文图注

截图引用格式（仅限文件名，不要写路径）：
![图注](filename.jpg)

只输出最终笔记正文，不要写任何解释说明。"""

_MULTIMODAL_CONTENT_POLICY: Final[str] = """

# Note Content Policy
- 笔记必须忠实于转录稿，只能基于原文内容组织、压缩和表达。
- 图片只用于辅助说明原文已有内容，不要在图片中阅读原文未提及的信息。
- 不确定的画面直接跳过不要选。
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

_CHAPTER_EVIDENCE_SYSTEM: Final[str] = f"""你是 FluentFlow 的长字幕证据抽取助手。
输入是带有 segment_id 的转录片段 JSON 数组。请抽取可用于完整覆盖笔记的证据。

输出严格 JSON 数组，不要输出 Markdown 或代码围栏。每项格式：
{{
  "evidence_id": "E001",
  "source_segment_ids": ["S001"],
  "type": "concept|argument|method|example|metric|action|detail",
  "text": "证据内容，必须忠实于原文",
  "importance": 1,
  "keywords": ["关键词"],
  "quote": "可选原文关键句"
}}

规则：
- evidence_id 可以先用临时编号，程序会重排成稳定编号。
- importance 使用 1-5；4-5 表示重要证据。
- 保留具体例子、数字、限制条件和老师强调。
- 不要为了整齐而编造分类或内容。
{_SOURCE_FAITHFULNESS_RULES}"""

_CHAPTER_OUTLINE_SYSTEM: Final[str] = """你是 FluentFlow 的章节规划助手。
输入是一组证据的压缩视图。请把证据分配到 3-8 个自然章节中。

输出严格 JSON 数组，不要输出 Markdown 或代码围栏。每项格式：
{
  "chapter_id": "CH01",
  "title": "章节标题",
  "purpose": "这一章解决什么问题",
  "used_evidence_ids": ["E001", "E002"]
}

规则：
- 每条重要证据应尽量分配到某个章节。
- 章节顺序应符合材料讲述顺序。
- 不要新增输入中不存在的主题。"""

_CHAPTER_NOTE_SYSTEM: Final[str] = f"""你是 FluentFlow 的章节笔记写作助手。
输入是某一章的标题、目的和证据清单。请只写这一章的 Markdown 内容。

要求：
- 用 `##` 作为本章标题。
- 必须吸收本章内的重要概念、案例、数字、步骤和限制条件。
- 只基于证据写作，不要补充外部知识。
- 不要写整篇总结，不要重复其他章节。
{_SOURCE_FAITHFULNESS_RULES}"""

_CHAPTER_STYLE_SYSTEM: Final[str] = f"""你是 FluentFlow 的长文档编校助手。
输入是按章节生成的 Markdown 草稿。请做轻量合并和统一风格，输出一份完整笔记。

只能做：
- 统一标题层级、编号和术语。
- 去除明显重复。
- 补自然过渡。

不能做：
- 大幅压缩章节。
- 删除具体例子、数字、步骤和限制条件。
- 新增原文没有的信息。
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

_SEGMENT_TRANSLATION_SYSTEM: Final[str] = """你是 FluentFlow 的字幕翻译助手。
请把输入 JSON 数组中的英文字幕逐条翻译为自然、准确、简洁的中文。

要求：
- 保留原意，不补充原文没有的信息。
- 不解释、不总结、不合并字幕。
- 输出严格 JSON 数组，每项格式为 {"index": 数字, "text_zh": "中文翻译"}。
- index 必须和输入一致；不要输出 Markdown 或代码围栏。"""

_BILINGUAL_SEGMENT_SYSTEM: Final[str] = """你是 FluentFlow 的英文字幕断句整理和中文对照助手。
输入是 Whisper 按音频时间切出来的英文字幕片段。它们可能不是完整句子。

请完成两件事：
1. 只合并相邻片段，把英文整理成更自然、完整的阅读字幕。
2. 为每条整理后的英文字幕生成自然、准确、简洁的中文翻译。

要求：
- 只能使用输入片段的原文信息，不要补充、总结或解释。
- 可以轻微修正大小写、标点和明显口语断裂，但不要改写原意。
- 每条输出必须覆盖连续的输入 index，不能跳跃、倒序或重叠。
- 不要为了变短而删除关键信息。
- 输出严格 JSON 数组，每项格式为：
  {"start_index": 数字, "end_index": 数字, "text_en": "整理后的英文", "text_zh": "中文翻译"}
- start_index 和 end_index 都是包含端点。
- 不要输出 Markdown 或代码围栏。"""

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
    segment_count: int | None = None
    evidence_count: int | None = None
    chapter_count: int | None = None
    important_evidence_count: int | None = None
    covered_important_evidence_count: int | None = None
    coverage_missing_count: int | None = None


@dataclass(frozen=True)
class MultimodalSummaryResult:
    markdown: str
    frame_count: int
    transcript_length: int


@dataclass(frozen=True)
class SegmentTranslationResult:
    segments: list[dict[str, Any]]
    translated_count: int
    chunk_count: int


@dataclass(frozen=True)
class BilingualSegmentResult:
    segments: list[dict[str, Any]]
    translated_count: int
    chunk_count: int


def _normalize_provider(provider: str | None) -> str:
    p = (provider or os.environ.get("AI_PROVIDER") or "deepseek").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {provider}")
    return p


def _provider_base_url(provider: str) -> str:
    if provider == "openai":
        return (os.environ.get("OPENAI_BASE_URL") or OPENAI_BASE_URL).rstrip("/")
    if provider == "qwen":
        return (os.environ.get("QWEN_BASE_URL") or QWEN_BASE_URL).rstrip("/")
    return (os.environ.get("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).rstrip("/")


def _provider_default_model(provider: str) -> str:
    if provider == "openai":
        return (os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()
    if provider == "qwen":
        return _normalize_model(provider, os.environ.get("QWEN_MODEL") or DEFAULT_QWEN_MODEL)
    return _normalize_model(provider, os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL)


def _normalize_model(provider: str, model: str | None) -> str:
    value = (model or "").strip()
    if provider == "deepseek" and (not value or value == "deepseek-chat"):
        return DEFAULT_DEEPSEEK_MODEL
    return value or _provider_default_model(provider)


def _provider_api_key(provider: str, api_key: str | None = None) -> str:
    load_dotenv()
    if provider == "openai":
        env_name = "OPENAI_API_KEY"
    elif provider == "qwen":
        env_name = "QWEN_API_KEY"
    else:
        env_name = "DEEPSEEK_API_KEY"
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


def _image_to_base64_data_url(image_path: str) -> str:
    path = Path(image_path)
    suffix = path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    if mime not in {"jpeg", "png", "webp"}:
        mime = "jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/{mime};base64,{encoded}"


def _vision_chat(
    client: OpenAI,
    model: str,
    system: str,
    user_text: str,
    image_paths: list[str],
    *,
    temperature: float = 0.3,
) -> str:
    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for path in image_paths:
        data_url = _image_to_base64_data_url(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url},
        })
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
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
        f"{_NOTE_OUTPUT_LANGUAGE}"
        f"{_FEISHU_NOTE_FORMATTING_PREFERENCES}"
        f"{_NOTE_OUTPUT_GUARDRAILS}"
    )


def _compose_multimodal_system_prompt(system_prompt: str | None) -> str:
    base = (system_prompt or "").strip() or _MULTIMODAL_NOTE_SYSTEM
    return (
        f"{base.rstrip()}"
        f"{_MULTIMODAL_CONTENT_POLICY}"
        f"{_NOTE_OUTPUT_LANGUAGE}"
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


def _chunk_indexed_segments(segments: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_len = 0
    for index, segment in enumerate(segments):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        item = {"index": index, "text": text}
        item_len = len(text) + 32
        if current and current_len + item_len > max_chars:
            chunks.append(current)
            current = [item]
            current_len = item_len
        else:
            current.append(item)
            current_len += item_len
    if current:
        chunks.append(current)
    return chunks


def _extract_json_array(text: str) -> list[Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("Translation response is not a JSON array")
    return parsed


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Response is not a JSON object")
    return parsed


def _normalize_note_mode(mode: str | None) -> str:
    value = (mode or os.environ.get("FLUENTFLOW_NOTE_MODE") or "auto").strip().lower()
    if value not in SUPPORTED_NOTE_MODES:
        raise ValueError(f"Unsupported note generation mode: {mode}")
    return "direct" if value == "fast" else value


def can_use_multimodal(provider: str | None) -> bool:
    return (provider or "").strip().lower() == "qwen"


def _resolve_note_mode(mode: str, transcript_length: int) -> str:
    if mode != "auto":
        return mode
    return "direct" if transcript_length <= DIRECT_MODE_MAX_CHARS else "high_fidelity"


def _chapter_segments(text: str, max_chars: int) -> list[dict[str, Any]]:
    chunks = _chunk_text(text, max_chars, overlap=0)
    return [
        {"segment_id": f"S{idx + 1:03d}", "order": idx + 1, "text": chunk}
        for idx, chunk in enumerate(chunks)
    ]


def _coerce_importance(value: Any) -> int:
    try:
        return min(max(int(value), 1), 5)
    except (TypeError, ValueError):
        return 3


def _normalize_string_list(value: Any, *, limit: int = 12) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:limit]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:240]]
    return []


def _normalize_evidence_items(
    raw_items: list[Any],
    valid_segment_ids: set[str],
    *,
    start_index: int = 0,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    allowed_types = {"concept", "argument", "method", "example", "metric", "action", "detail"}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        segment_ids = [
            segment_id
            for segment_id in _normalize_string_list(item.get("source_segment_ids") or item.get("sourceSegmentIds"))
            if segment_id in valid_segment_ids
        ]
        evidence_type = str(item.get("type") or "detail").strip()
        if evidence_type not in allowed_types:
            evidence_type = "detail"
        evidence.append({
            "evidence_id": f"E{start_index + len(evidence) + 1:03d}",
            "source_segment_ids": segment_ids,
            "type": evidence_type,
            "text": text[:1200],
            "importance": _coerce_importance(item.get("importance")),
            "keywords": _normalize_string_list(item.get("keywords"), limit=8),
            "quote": str(item.get("quote") or "").strip()[:500],
        })
    return evidence


def _compact_evidence_view(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item["evidence_id"],
            "order": idx + 1,
            "type": item.get("type"),
            "importance": item.get("importance"),
            "text": item.get("text"),
            "keywords": item.get("keywords") or [],
        }
        for idx, item in enumerate(evidence)
    ]


def _normalize_chapters(raw_items: list[Any], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_ids = {str(item.get("evidence_id")) for item in evidence}
    chapters: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        used_ids = [
            evidence_id
            for evidence_id in _normalize_string_list(item.get("used_evidence_ids") or item.get("usedEvidenceIds"), limit=200)
            if evidence_id in valid_ids
        ]
        if not used_ids:
            continue
        chapter_id = f"CH{len(chapters) + 1:02d}"
        chapters.append({
            "chapter_id": chapter_id,
            "title": title[:80],
            "purpose": str(item.get("purpose") or "").strip()[:240],
            "used_evidence_ids": used_ids,
        })
        assigned.update(used_ids)

    missing = [item["evidence_id"] for item in evidence if item["evidence_id"] not in assigned]
    if chapters and missing:
        chapters[-1]["used_evidence_ids"] = [*chapters[-1]["used_evidence_ids"], *missing]
    if chapters:
        return chapters

    return [{
        "chapter_id": "CH01",
        "title": "完整覆盖笔记",
        "purpose": "按原文顺序整理全部重要证据。",
        "used_evidence_ids": [item["evidence_id"] for item in evidence],
    }]


def _evidence_markdown(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in items:
        keywords = "、".join(item.get("keywords") or [])
        source = ", ".join(item.get("source_segment_ids") or [])
        parts = [
            f"- {item['evidence_id']} | importance={item.get('importance')} | type={item.get('type')}",
            f"  - 内容：{item.get('text')}",
        ]
        if keywords:
            parts.append(f"  - 关键词：{keywords}")
        if source:
            parts.append(f"  - 来源片段：{source}")
        if item.get("quote"):
            parts.append(f"  - 原文：{item.get('quote')}")
        lines.extend(parts)
    return "\n".join(lines)


def _run_chapter_coverage_mode(
    client: OpenAI,
    model: str,
    prompt: str,
    transcript_text: str,
    *,
    segment_chars: int,
    max_final_input_chars: int,
) -> SummaryResult:
    segments = _chapter_segments(transcript_text, segment_chars)
    valid_segment_ids = {segment["segment_id"] for segment in segments}
    evidence: list[dict[str, Any]] = []
    for batch in segments:
        payload = json.dumps([batch], ensure_ascii=False)
        raw_items = _extract_json_array(_chat(client, model, _CHAPTER_EVIDENCE_SYSTEM, payload, temperature=0.1))
        evidence.extend(_normalize_evidence_items(raw_items, valid_segment_ids, start_index=len(evidence)))

    if not evidence:
        raise ValueError("Chapter coverage evidence extraction returned no usable evidence")

    outline_payload = json.dumps(_compact_evidence_view(evidence), ensure_ascii=False)
    raw_chapters = _extract_json_array(_chat(client, model, _CHAPTER_OUTLINE_SYSTEM, outline_payload, temperature=0.1))
    chapters = _normalize_chapters(raw_chapters, evidence)
    evidence_by_id = {item["evidence_id"]: item for item in evidence}

    chapter_notes: list[str] = []
    covered_ids: set[str] = set()
    for chapter in chapters:
        chapter_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in chapter["used_evidence_ids"]
            if evidence_id in evidence_by_id
        ]
        covered_ids.update(item["evidence_id"] for item in chapter_evidence)
        user = json.dumps({
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "purpose": chapter.get("purpose") or "",
            "evidence": chapter_evidence,
        }, ensure_ascii=False)
        chapter_notes.append(_strip_prompt_leakage(_chat(client, model, _CHAPTER_NOTE_SYSTEM, user, temperature=0.2)))

    draft = "\n\n".join(note for note in chapter_notes if note.strip())
    final_note = _strip_prompt_leakage(_chat(client, model, _CHAPTER_STYLE_SYSTEM, draft, temperature=0.2))
    if not final_note:
        final_note = draft

    important_ids = {item["evidence_id"] for item in evidence if int(item.get("importance") or 0) >= 4}
    uncovered_important = sorted(important_ids - covered_ids)
    coverage_payload = {
        "total_evidence": len(evidence),
        "important_evidence": len(important_ids),
        "covered_important_evidence": len(important_ids) - len(uncovered_important),
        "unused_important_evidence_ids": uncovered_important,
    }
    coverage_input = (
        f"--- 覆盖矩阵 ---\n\n{json.dumps(coverage_payload, ensure_ascii=False, indent=2)}"
        f"\n\n--- 证据清单 ---\n\n{_evidence_markdown(evidence)}"
        f"\n\n--- 已生成笔记 ---\n\n{final_note}"
    )
    coverage_checked = len(coverage_input) <= max_final_input_chars
    coverage_revision_used = False
    missing_count = len(uncovered_important)
    if coverage_checked:
        coverage = _chat(client, model, _COVERAGE_SYSTEM, coverage_input, temperature=0.1).strip()
        if coverage and coverage != "COVERED":
            final_note = _strip_prompt_leakage(
                _chat(
                    client,
                    model,
                    prompt,
                    _REVISION_WRAPPER.format(draft=final_note, coverage=coverage),
                    temperature=0.2,
                )
            )
            coverage_revision_used = True
            missing_count = max(missing_count, 1)

    return SummaryResult(
        markdown=final_note,
        requested_mode="chapter_coverage",
        resolved_mode="chapter_coverage",
        transcript_length=len(transcript_text),
        chunk_count=len(segments),
        coverage_checked=coverage_checked,
        coverage_revision_used=coverage_revision_used,
        segment_count=len(segments),
        evidence_count=len(evidence),
        chapter_count=len(chapters),
        important_evidence_count=len(important_ids),
        covered_important_evidence_count=len(important_ids) - len(uncovered_important),
        coverage_missing_count=missing_count,
    )


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
    m = _normalize_model(provider_name, model)
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

    if resolved_mode == "chapter_coverage":
        return _run_chapter_coverage_mode(
            client,
            m,
            prompt,
            transcript_text,
            segment_chars=evidence_chunk_chars,
            max_final_input_chars=max_final_input_chars,
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


def summarize_transcript_with_frames(
    transcript: str,
    frame_paths: list[str],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    system_prompt: str | None = None,
) -> MultimodalSummaryResult:
    """Generate a structured note from transcript text and video frame images."""
    load_dotenv()
    provider_name = _normalize_provider(provider)
    if not can_use_multimodal(provider_name):
        raise ValueError(f"Provider {provider_name} does not support multimodal")
    client = _get_client(provider=provider_name, api_key=api_key)
    m = _normalize_model(provider_name, model)
    prompt = _compose_multimodal_system_prompt(system_prompt)
    transcript_text = transcript.strip()
    if not transcript_text:
        return MultimodalSummaryResult(markdown="", frame_count=0, transcript_length=0)
    if not frame_paths:
        return MultimodalSummaryResult(markdown="", frame_count=0, transcript_length=len(transcript_text))

    frame_lines = [f"- [{Path(p).name}] (截图)" for p in frame_paths]
    user = (
        f"请在以下 {len(frame_paths)} 张截图中挑选最有信息量的 3-8 张，生成结构化笔记：\n\n"
        + "\n".join(frame_lines)
        + f"\n\n--- 转录稿 ---\n\n{transcript_text}"
    )
    markdown = _strip_prompt_leakage(
        _vision_chat(client, m, prompt, user, frame_paths, temperature=0.2)
    )
    return MultimodalSummaryResult(
        markdown=markdown,
        frame_count=len(frame_paths),
        transcript_length=len(transcript_text),
    )


def translate_segments_to_zh(
    segments: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    max_chunk_chars: int = 8_000,
) -> SegmentTranslationResult:
    """Translate timestamped English transcript segments to Chinese while preserving indices."""
    load_dotenv()
    source_segments = [dict(segment) for segment in segments if isinstance(segment, dict)]
    if not source_segments:
        return SegmentTranslationResult(segments=[], translated_count=0, chunk_count=0)

    provider_name = _normalize_provider(provider)
    client = _get_client(provider=provider_name, api_key=api_key)
    m = _normalize_model(provider_name, model)
    translations: dict[int, str] = {}
    chunks = _chunk_indexed_segments(source_segments, max_chunk_chars)
    for chunk in chunks:
        payload = json.dumps(chunk, ensure_ascii=False)
        translated = _extract_json_array(_chat(client, m, _SEGMENT_TRANSLATION_SYSTEM, payload, temperature=0.1))
        for item in translated:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            text_zh = str(item.get("text_zh") or "").strip()
            if text_zh:
                translations[index] = text_zh

    translated_segments: list[dict[str, Any]] = []
    for index, segment in enumerate(source_segments):
        text_zh = translations.get(index, "")
        if not text_zh:
            continue
        translated_segment = {
            "start": segment.get("start"),
            "end": segment.get("end"),
            "text": text_zh,
            "source_text": str(segment.get("text") or ""),
        }
        if segment.get("speaker"):
            translated_segment["speaker"] = segment.get("speaker")
        translated_segments.append(translated_segment)
    return SegmentTranslationResult(
        segments=translated_segments,
        translated_count=len(translated_segments),
        chunk_count=len(chunks),
    )


def _int_from_any(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def generate_bilingual_segments_zh(
    segments: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    max_chunk_chars: int = 8_000,
) -> BilingualSegmentResult:
    """Merge adjacent English fragments into readable bilingual subtitle segments."""
    load_dotenv()
    source_segments = [dict(segment) for segment in segments if isinstance(segment, dict)]
    if not source_segments:
        return BilingualSegmentResult(segments=[], translated_count=0, chunk_count=0)

    provider_name = _normalize_provider(provider)
    client = _get_client(provider=provider_name, api_key=api_key)
    m = _normalize_model(provider_name, model)
    chunks = _chunk_indexed_segments(source_segments, max_chunk_chars)
    merged_segments: list[dict[str, Any]] = []
    consumed_until = -1

    for chunk in chunks:
        payload = json.dumps(chunk, ensure_ascii=False)
        generated = _extract_json_array(_chat(client, m, _BILINGUAL_SEGMENT_SYSTEM, payload, temperature=0.1))
        chunk_indices = [int(item["index"]) for item in chunk if "index" in item]
        if not chunk_indices:
            continue
        chunk_start = min(chunk_indices)
        chunk_end = max(chunk_indices)
        for item in generated:
            if not isinstance(item, dict):
                continue
            start_index = _int_from_any(
                item.get("start_index")
                if item.get("start_index") is not None
                else item.get("startIndex")
            )
            end_index = _int_from_any(
                item.get("end_index")
                if item.get("end_index") is not None
                else item.get("endIndex")
            )
            if start_index is None:
                continue
            if end_index is None:
                end_index = start_index
            start_index = max(chunk_start, start_index)
            end_index = min(chunk_end, end_index)
            if end_index < start_index or start_index <= consumed_until:
                continue
            source_slice = source_segments[start_index : end_index + 1]
            if not source_slice:
                continue
            text_en = str(item.get("text_en") or item.get("text") or "").strip()
            text_zh = str(item.get("text_zh") or item.get("zh") or "").strip()
            if not text_en:
                text_en = " ".join(str(segment.get("text") or "").strip() for segment in source_slice).strip()
            if not text_en or not text_zh:
                continue
            segment: dict[str, Any] = {
                "start": source_slice[0].get("start"),
                "end": source_slice[-1].get("end"),
                "text": text_en,
                "text_zh": text_zh,
                "source_start_index": start_index,
                "source_end_index": end_index,
            }
            speakers = [str(s.get("speaker")) for s in source_slice if s.get("speaker")]
            if speakers and len(set(speakers)) == 1:
                segment["speaker"] = speakers[0]
            merged_segments.append(segment)
            consumed_until = end_index

    return BilingualSegmentResult(
        segments=merged_segments,
        translated_count=len(merged_segments),
        chunk_count=len(chunks),
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
    "QWEN_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_DEEPSEEK_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_QWEN_MODEL",
    "FLUENTFLOW_SYSTEM_PROMPT",
    "DIRECT_MODE_MAX_CHARS",
    "HIGH_FIDELITY_NOTICE_CHARS",
    "SummaryResult",
    "MultimodalSummaryResult",
    "SegmentTranslationResult",
    "BilingualSegmentResult",
    "can_use_multimodal",
    "generate_bilingual_segments_zh",
    "translate_segments_to_zh",
    "summarize_transcript_with_metadata",
    "summarize_transcript_with_frames",
    "summarize_transcript_to_markdown",
]
