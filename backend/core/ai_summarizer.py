"""Summarize Whisper transcripts with OpenAI-compatible chat providers."""

from __future__ import annotations

import os
import re
import json
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
OPENAI_BASE_URL: Final[str] = "https://api.openai.com/v1"
QWEN_BASE_URL: Final[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DEEPSEEK_MODEL: Final[str] = "deepseek-reasoner"
DEFAULT_OPENAI_MODEL: Final[str] = "gpt-5.4-mini"
DEFAULT_QWEN_MODEL: Final[str] = "qwen3.7-plus"
DEFAULT_MODEL: Final[str] = DEFAULT_DEEPSEEK_MODEL
SUPPORTED_PROVIDERS: Final[set[str]] = {"deepseek", "openai", "qwen"}
SUPPORTED_NOTE_MODES: Final[set[str]] = {"auto", "direct", "fast", "high_fidelity", "chapter_coverage"}
CHAPTER_COVERAGE_VERSION: Final[str] = "1"
DIRECT_MODE_MAX_CHARS: Final[int] = 20_000
HIGH_FIDELITY_NOTICE_CHARS: Final[int] = 60_000

# Full system prompt: FluentFlow 知识架构师（飞书云文档 Markdown）
FLUENTFLOW_SYSTEM_PROMPT: Final[str] = """# Role: FluentFlow 知识架构师

# Task: 你将接收一段由 Whisper 转录的课程、讲座、录屏或长视频文本。这段文本可能包含口癖、重复和错别字。你的任务是把它整理成一份适合边看视频边学习、后续复习和少量修正的高质量中文笔记。

# Note Design Principles:
- 先判断材料本身的讲述结构，再设计笔记结构；不要把所有内容硬套成固定模板。
- 优先保留学习者真正需要回看的内容：核心问题、概念定义、论证链路、关键步骤、案例、数字、限制条件、老师强调和容易漏掉的细节。
- 标题应来自原文主题或自然章节，而不是机械使用「概览」「核心概念」「深度拆解」等固定栏目。
- 对教程/操作类材料，按目标、前置条件、步骤、关键参数、常见错误和结果检查组织。
- 对理论/课程类材料，按问题、概念、机制、例子、应用边界和总结组织。
- 对访谈/观点类材料，按议题、观点、依据、案例和分歧/限制组织。
- 如果原文很短，可以输出紧凑笔记；如果原文很长，应保留章节层次和具体例子，不要压成几条抽象总结。

# Writing Style:
- 清楚、克制、像一份认真整理过的学习笔记，不像宣传文案或模板填空。
- 使用二级和三级标题建立层级感，但不要制造过多层级。
- 重点术语、字段名和可扫描标签可以 **加粗**；不要整句整段加粗。
- 原文中真正有价值的原话或判断可以使用 > 引用块；不要为了形式强行添加金句。

# Constraints:
- 保持原意，不要虚构事实。
- 剔除「呃」、「那个」、「其实」等口头语。
- 去除冗余解释，但不要删掉理解课程所需的具体例子、步骤、数字和限制。
- 不要输出固定数量的板块；只保留对这份材料有用的结构。
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
- 正文标题使用少量清晰层级。长材料可用类似 `## 一、活动背景与资源` 的编号标题；短材料可以使用更自然的主题标题，不必强行编号。
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
- 仔细审阅所有截图，选出 0-8 张真正有信息量的画面；宁可不插图，也不要为了凑数插图。
- 全局密度要克制：短笔记通常 1-2 张即可，长笔记也优先选择少量高价值截图；同一页 PPT 或近似画面只选第一次出现的位置。
- 优先选择能解释核心知识点的画面：
  - 一级 / 二级章节开头、核心定义、公式、流程图、代码片段、图表、数据表格、方法步骤、关键对比
  - 关键演示画面、产品界面、重要实物展示
- 不要选择低价值画面，即使字很多也不要选：
  - 纯封面、纯目录、纯标题页、致谢页、结束页、过渡动画中间帧
  - 模糊画面、黑屏/白屏、纯人物讲话、纯字幕条、与笔记段落无关的画面
- 按照「知识架构师」的标准，生成一份结构化中文笔记
- 在笔记最合适的位置，用 Markdown 图片语法插入选中的截图：
  - 章节引导图放在相关标题后
  - 具体知识点、公式、流程或案例截图放在对应段落后
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

_VISUAL_REQUEST_PLANNER_SYSTEM: Final[str] = """# Role: FluentFlow 视觉证据规划器

你会收到：
1. 已生成的结构化笔记
2. 带时间戳的转录片段

你的任务不是选图，而是判断哪些笔记段落或复查需求值得检查视频画面，并给出最小时间窗。

请求分两类目的：
- inline_evidence：画面很可能能直接解释或证明某个具体笔记段落，适合少量插入正文。
- key_moment：画面对学习复查有价值，能帮助用户定位图表、代码、UI、公式、流程或演示步骤，但不一定适合插入正文。

只在截图能明显帮助用户复习时提出请求，例如：流程图、架构图、公式、代码、表格、PPT 关键页、产品界面、演示步骤、数据图表、关键对比。
不要为封面、目录、纯标题页、人物讲话、字幕条或普通口播段落提出请求。

输出严格 JSON，不要写解释：
{
  "requests": [
    {
      "note_section": "笔记中的相关标题或段落名",
      "start_seconds": 12.3,
      "end_seconds": 28.0,
      "reason": "为什么这里需要截图，面向用户",
      "query": "给视觉模型看的画面筛选目标",
      "purpose": "inline_evidence|key_moment",
      "priority": "high|medium|low",
      "max_images": 1
    }
  ]
}

最多 8 个请求。正文插图请求要克制；关键画面请求可以更积极召回，但仍然不要为低信息画面凑数。"""

_VISUAL_FRAME_SELECTOR_SYSTEM: Final[str] = """# Role: FluentFlow 局部截图选择器

你会收到一个截图需求和该时间窗内的少量候选帧。请选择最能帮助用户学习或复查的 0-1 张，并判断它应该进入哪一层结果。

优先选择：流程图、架构图、公式、代码、表格、数据图、关键界面、演示步骤、清晰的 PPT 正文页。
排除：封面、目录、纯标题页、过渡页、纯人物讲话、字幕条、模糊/黑屏/白屏、重复或与需求无关的画面。

分层规则：
- inline_evidence：只有高置信、与具体笔记段落强相关、能直接解释/证明该段内容的画面。
- key_moment：中高置信、对学习复查有用但不适合直接插入正文的画面。
- low：低置信、低信息或无关画面；不要进入用户结果。

输出严格 JSON，不要写解释：
{
  "selected": [
    {
      "filename": "ts_0004_0.jpg",
      "caption": "一句中文图注，说明这张图支持的知识点",
      "reason": "为什么选它，面向用户",
      "purpose": "inline_evidence|key_moment",
      "confidence": "high|medium|low"
    }
  ]
}

如果候选帧都没有学习或复查价值，返回 {"selected": []}。"""

# 分段提炼时使用（减轻最终合并输入长度）
_INTERIM_SYSTEM: Final[str] = f"""你是 FluentFlow 的预处理助手。输入为 Whisper 转录的一小段原文。
请用简洁的中文 Markdown 输出：
- 本段关键事实、术语与数字
- 本段讲解主线（短句列表即可）
输出将用于后续合并，无需套用最终笔记结构。
{_SOURCE_FAITHFULNESS_RULES}"""

_BATCH_CONDENSE_SYSTEM: Final[str] = f"""你是 FluentFlow 的编校助手。下面若干段是同一课程不同时间段的「分段要点草稿」。
请合并去重，保留重要术语与逻辑顺序，输出一份连贯的「合并要点稿」（仍用 Markdown，可多级列表），不要套用固定终稿模板。
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
    "以下内容来自**同一份长视频或音频材料**转录文本的分段提炼（按时间顺序）。"
    "请**整理为一份完整**、可直接用于飞书云文档的 Markdown 笔记，"
    "严格遵循系统说明中的角色、内容边界与格式偏好，按材料本身的结构理顺逻辑并去重。\n\n---\n\n"
)

_HIGH_FIDELITY_FINAL_WRAPPER: Final[str] = (
    "以下内容是从同一份长视频或音频材料转录文本中按时间顺序提取的「证据清单」。"
    "请基于这些证据整理为一份完整、可复习、可直接放入飞书云文档的 Markdown 学习笔记。"
    "不要只写抽象总结；必须吸收重要概念、例子、数字、方法步骤和老师强调。"
    "严格遵循系统说明中的角色、内容边界与格式偏好，按材料本身的结构组织章节。\n\n---\n\n"
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

_REVISION_WRAPPER: Final[str] = """下面是已生成的学习笔记，以及覆盖率审查发现的遗漏点。
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

# Internal evidence IDs (E001, E003、E055 …) are a chapter-coverage pipeline
# artifact and must never appear in the finished note. The model copies them
# inline in several shapes — parenthesized, bracketed, or bare, sometimes as
# 、/逗号 lists. IDs are always "E"+>=3 digits (see _normalize_evidence_items),
# so matching that shape leaves ordinary text (e.g. "E5", "H100") untouched.
_EVIDENCE_BRACKET_RE = re.compile(
    r"[ \t]*[（(【\[]\s*E\d{3,}(?:\s*[、,，]\s*E?\d{2,})*\s*[)）】\]][ \t]*"
)
_EVIDENCE_BARE_RE = re.compile(
    r"[ \t]*(?<![A-Za-z0-9])E\d{3,}(?:\s*[、,，]\s*E?\d{2,})*[ \t]*"
)
_EMPTY_BRACKETS_RE = re.compile(r"[（(【\[]\s*[)）】\]]")


def _strip_evidence_ids(text: str) -> str:
    text = _EVIDENCE_BRACKET_RE.sub("", text)
    text = _EVIDENCE_BARE_RE.sub("", text)
    text = _EMPTY_BRACKETS_RE.sub("", text)  # tidy any bracket left empty
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([，。、；：！？）】\]])", r"\1", text)  # drop space before punctuation
    return text


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
    chapter_coverage: dict[str, Any] | None = None


@dataclass(frozen=True)
class MultimodalSummaryResult:
    markdown: str
    frame_count: int
    transcript_length: int


@dataclass(frozen=True)
class VisualRequestPlanResult:
    requests: list[dict[str, Any]]
    raw_response: str
    provider: str
    model: str


@dataclass(frozen=True)
class VisualFrameSelectionResult:
    selections: list[dict[str, Any]]
    provider: str
    model: str


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
        env_names = (env_name,)
    elif provider == "qwen":
        env_name = "DASHSCOPE_API_KEY"
        env_names = ("DASHSCOPE_API_KEY", "QWEN_API_KEY")
    else:
        env_name = "DEEPSEEK_API_KEY"
        env_names = (env_name,)
    env_key = next(
        ((os.environ.get(name) or "").strip() for name in env_names if (os.environ.get(name) or "").strip()),
        "",
    )
    key = (api_key or env_key).strip()
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

    return _strip_evidence_ids("\n".join(cleaned)).strip()


# Independent per-chunk / per-chapter model calls are I/O-bound and order-safe,
# so they can run concurrently instead of one-after-another. Cap concurrency to
# stay well under provider rate limits.
_MAX_PARALLEL_CALLS: Final[int] = 6


def _parallel_map(fn: Callable[[Any], Any], items: list[Any]) -> list[Any]:
    """Run fn over items concurrently, preserving input order. Exceptions
    propagate (first failure surfaces), matching the previous serial behavior."""
    if len(items) <= 1:
        return [fn(item) for item in items]
    workers = min(_MAX_PARALLEL_CALLS, len(items))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(fn, items))


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


def _chat_json_array(
    client: OpenAI,
    model: str,
    system: str,
    user: str,
    *,
    temperature: float,
    retries: int = 1,
) -> list[Any]:
    """_chat + parse a JSON array, retrying on malformed model output. Models
    occasionally emit invalid JSON; a retry with slightly higher temperature
    usually breaks out of the bad pattern. Raises ValueError if all attempts
    fail so callers can decide whether to skip or abort."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        temp = temperature if attempt == 0 else min(0.6, temperature + 0.3)
        try:
            return _extract_json_array(_chat(client, model, system, user, temperature=temp))
        except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
            last_exc = exc
    raise last_exc if last_exc else ValueError("empty JSON array response")


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


def _seconds(value: Any, fallback: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return fallback


def _compact_timestamped_segments(
    segments: list[dict[str, Any]],
    *,
    max_chars: int = 45_000,
) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    total_chars = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text_zh") or segment.get("text") or "").strip()
        if not text:
            continue
        start = _seconds(segment.get("start"))
        end = _seconds(segment.get("end"), start)
        item = {
            "index": index,
            "start_seconds": round(start, 1),
            "end_seconds": round(max(start, end), 1),
            "text": text[:260],
        }
        item_len = len(item["text"]) + 48
        if compacted and total_chars + item_len > max_chars:
            break
        compacted.append(item)
        total_chars += item_len
    return compacted


def _segment_bounds(segments: list[dict[str, Any]]) -> tuple[float, float]:
    starts: list[float] = []
    ends: list[float] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        starts.append(_seconds(segment.get("start")))
        ends.append(_seconds(segment.get("end"), starts[-1]))
    return (min(starts) if starts else 0.0, max(ends) if ends else 0.0)


def _coerce_visual_requests(
    payload: dict[str, Any],
    segments: list[dict[str, Any]],
    *,
    max_requests: int,
) -> list[dict[str, Any]]:
    raw_items = payload.get("requests") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return []
    min_bound, max_bound = _segment_bounds(segments)
    requests: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        note_section = str(item.get("note_section") or item.get("section") or "").strip()
        reason = str(item.get("reason") or "").strip()
        query = str(item.get("query") or reason).strip()
        if not reason or not query:
            continue
        start = _seconds(item.get("start_seconds") or item.get("start"))
        end = _seconds(item.get("end_seconds") or item.get("end"), start + 8.0)
        if max_bound > 0:
            start = min(max(start, min_bound), max_bound)
            end = min(max(end, start + 1.0), max_bound)
        if end <= start:
            end = start + 8.0
        if end - start > 60.0:
            midpoint = start + (end - start) / 2
            start = max(0.0, midpoint - 20.0)
            end = midpoint + 20.0
        priority = str(item.get("priority") or "medium").strip().lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        purpose = str(item.get("purpose") or item.get("visual_purpose") or "").strip().lower()
        if purpose not in {"inline_evidence", "key_moment"}:
            purpose = "inline_evidence" if priority == "high" else "key_moment"
        try:
            max_images = min(max(int(item.get("max_images") or 1), 0), 2)
        except (TypeError, ValueError):
            max_images = 1
        if max_images <= 0:
            continue
        requests.append({
            "id": f"vr_{len(requests) + 1:03d}",
            "note_section": note_section[:120],
            "start_seconds": round(start, 1),
            "end_seconds": round(end, 1),
            "reason": reason[:240],
            "query": query[:240],
            "purpose": purpose,
            "priority": priority,
            "max_images": max_images,
        })
        if len(requests) >= max_requests:
            break
    return requests


def visual_requests_to_frame_segments(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert semantic screenshot requests into mechanical frame extraction windows."""
    segments: list[dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict):
            continue
        segments.append({
            "start": request.get("start_seconds"),
            "end": request.get("end_seconds"),
            "text": request.get("query") or request.get("reason") or "",
            "visual_request_id": request.get("id"),
            "note_section": request.get("note_section"),
            "query": request.get("query"),
            "reason": request.get("reason"),
            "purpose": request.get("purpose"),
        })
    return segments


def plan_visual_evidence_requests(
    summary_markdown: str,
    transcript_segments: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    max_requests: int = 8,
) -> VisualRequestPlanResult:
    """Ask the text model where screenshots would materially improve the note."""
    provider_name = _normalize_provider(provider)
    client = _get_client(provider=provider_name, api_key=api_key)
    m = _normalize_model(provider_name, model)
    compact_segments = _compact_timestamped_segments(transcript_segments)
    if not summary_markdown.strip() or not compact_segments:
        return VisualRequestPlanResult(requests=[], raw_response="", provider=provider_name, model=m)
    user = json.dumps(
        {
            "summary_markdown": summary_markdown[:35_000],
            "timestamped_segments": compact_segments,
        },
        ensure_ascii=False,
    )
    raw = _chat(client, m, _VISUAL_REQUEST_PLANNER_SYSTEM, user, temperature=0.1)
    payload = _extract_json_object(raw)
    return VisualRequestPlanResult(
        requests=_coerce_visual_requests(payload, transcript_segments, max_requests=max_requests),
        raw_response=raw,
        provider=provider_name,
        model=m,
    )


def _candidate_frames_for_request(
    request: dict[str, Any],
    frame_metadata: list[dict[str, Any]],
    *,
    max_frames: int = 8,
) -> list[dict[str, Any]]:
    request_id = str(request.get("id") or "")
    start = _seconds(request.get("start_seconds"))
    end = _seconds(request.get("end_seconds"), start)
    candidates: list[dict[str, Any]] = []
    for frame in frame_metadata:
        if not isinstance(frame, dict) or not frame.get("path"):
            continue
        frame_request_id = str(frame.get("visual_request_id") or "")
        timestamp = _seconds(frame.get("timestamp_seconds"))
        if frame_request_id and request_id and frame_request_id == request_id:
            candidates.append(frame)
        elif start <= timestamp <= max(start, end):
            candidates.append(frame)
    candidates = sorted(candidates, key=lambda item: _seconds(item.get("timestamp_seconds")))
    if len(candidates) <= max_frames:
        return candidates
    indices = [round(i * (len(candidates) - 1) / (max_frames - 1)) for i in range(max_frames)]
    return [candidates[index] for index in indices]


def _coerce_visual_frame_selection(
    payload: dict[str, Any],
    request: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_items = payload.get("selected") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return []
    filenames = {Path(str(frame.get("path"))).name: frame for frame in candidates}
    selections: list[dict[str, Any]] = []
    max_images = int(request.get("max_images") or 1)
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        filename = Path(str(item.get("filename") or "")).name
        frame = filenames.get(filename)
        if not frame:
            continue
        caption = str(item.get("caption") or item.get("reason") or request.get("reason") or "").strip()
        if not caption:
            continue
        confidence = str(item.get("confidence") or "medium").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"
        if confidence == "low":
            continue
        purpose = str(item.get("purpose") or item.get("visual_purpose") or request.get("purpose") or "").strip().lower()
        if purpose not in {"inline_evidence", "key_moment"}:
            purpose = "inline_evidence" if confidence == "high" else "key_moment"
        if purpose == "inline_evidence" and confidence != "high":
            purpose = "key_moment"
        selections.append({
            "request_id": request.get("id"),
            "note_section": request.get("note_section") or "",
            "filename": filename,
            "caption": caption[:140],
            "reason": str(item.get("reason") or request.get("reason") or caption).strip()[:240],
            "confidence": confidence,
            "purpose": purpose,
            "timestamp_seconds": frame.get("timestamp_seconds"),
        })
        if len(selections) >= max_images:
            break
    return selections


def select_visual_evidence_frames(
    visual_requests: list[dict[str, Any]],
    frame_metadata: list[dict[str, Any]],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = "qwen",
    max_total_images: int = 8,
) -> VisualFrameSelectionResult:
    """Ask the vision model to choose frames inside each requested time window."""
    provider_name = _normalize_provider(provider)
    if not can_use_multimodal(provider_name):
        raise ValueError(f"Provider {provider_name} does not support multimodal")
    client = _get_client(provider=provider_name, api_key=api_key)
    m = _normalize_model(provider_name, model)
    selections: list[dict[str, Any]] = []
    for request in visual_requests:
        if len(selections) >= max_total_images:
            break
        candidates = _candidate_frames_for_request(request, frame_metadata)
        image_paths = [str(frame["path"]) for frame in candidates if frame.get("path")]
        if not image_paths:
            continue
        user = json.dumps(
            {
                "request": request,
                "candidate_frames": [
                    {
                        "filename": Path(str(frame.get("path"))).name,
                        "timestamp_seconds": frame.get("timestamp_seconds"),
                    }
                    for frame in candidates
                ],
            },
            ensure_ascii=False,
        )
        raw = _vision_chat(client, m, _VISUAL_FRAME_SELECTOR_SYSTEM, user, image_paths, temperature=0.1)
        payload = _extract_json_object(raw)
        selections.extend(_coerce_visual_frame_selection(payload, request, candidates))
    return VisualFrameSelectionResult(
        selections=selections[:max_total_images],
        provider=provider_name,
        model=m,
    )


def _resolve_note_mode(mode: str, transcript_length: int) -> str:
    if mode != "auto":
        return mode
    return "direct" if transcript_length <= DIRECT_MODE_MAX_CHARS else "high_fidelity"


def _chapter_segments(text: str, max_chars: int) -> list[dict[str, Any]]:
    t = text.strip()
    if not t:
        return []
    segments: list[dict[str, Any]] = []
    i = 0
    n = len(t)
    while i < n:
        j = min(i + max_chars, n)
        if j < n:
            br = t.rfind("\n", i + max_chars // 2, j)
            if br != -1:
                j = br + 1
        raw_piece = t[i:j]
        piece = raw_piece.strip()
        if piece:
            leading = len(raw_piece) - len(raw_piece.lstrip())
            trailing = len(raw_piece) - len(raw_piece.rstrip())
            segments.append({
                "segment_id": f"S{len(segments) + 1:03d}",
                "order": len(segments) + 1,
                "char_start": i + leading,
                "char_end": j - trailing,
                "text": piece,
            })
        if j >= n:
            break
        i = max(i + 1, j)
    return segments


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


def _range_from_source_segments(source_segment_ids: list[str], segments_by_id: dict[str, dict[str, Any]]) -> dict[str, int | None]:
    starts: list[int] = []
    ends: list[int] = []
    for segment_id in source_segment_ids:
        segment = segments_by_id.get(segment_id)
        if not segment:
            continue
        if isinstance(segment.get("char_start"), int):
            starts.append(segment["char_start"])
        if isinstance(segment.get("char_end"), int):
            ends.append(segment["char_end"])
    return {
        "char_start": min(starts) if starts else None,
        "char_end": max(ends) if ends else None,
    }


def _build_chapter_coverage_table(
    *,
    segments: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
    covered_ids: set[str],
    important_ids: set[str],
    uncovered_important: list[str],
    coverage_checked: bool,
    coverage_revision_used: bool,
    coverage_missing_count: int,
) -> dict[str, Any]:
    segments_by_id = {str(segment.get("segment_id")): segment for segment in segments}
    chapter_ids_by_evidence: dict[str, list[str]] = {}
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        for evidence_id in chapter.get("used_evidence_ids") or []:
            chapter_ids_by_evidence.setdefault(str(evidence_id), []).append(chapter_id)

    segment_table = [
        {
            "segment_id": segment.get("segment_id"),
            "order": segment.get("order"),
            "char_start": segment.get("char_start"),
            "char_end": segment.get("char_end"),
            "char_count": len(str(segment.get("text") or "")),
            "text_preview": str(segment.get("text") or "").strip()[:240],
        }
        for segment in segments
    ]

    evidence_table: list[dict[str, Any]] = []
    evidence_by_id = {str(item.get("evidence_id")): item for item in evidence}
    for order, item in enumerate(evidence, 1):
        evidence_id = str(item.get("evidence_id") or f"E{order:03d}")
        source_ids = [str(value) for value in item.get("source_segment_ids") or [] if str(value)]
        source_range = _range_from_source_segments(source_ids, segments_by_id)
        evidence_table.append({
            "evidence_id": evidence_id,
            "order": order,
            "type": item.get("type") or "detail",
            "importance": _coerce_importance(item.get("importance")),
            "text": str(item.get("text") or "").strip(),
            "keywords": item.get("keywords") or [],
            "quote": str(item.get("quote") or "").strip(),
            "source_segment_ids": source_ids,
            "char_start": source_range["char_start"],
            "char_end": source_range["char_end"],
            "covered": evidence_id in covered_ids,
            "covered_by_chapter_ids": chapter_ids_by_evidence.get(evidence_id, []),
        })

    chapter_table: list[dict[str, Any]] = []
    for order, chapter in enumerate(chapters, 1):
        used_ids = [str(value) for value in chapter.get("used_evidence_ids") or [] if str(value) in evidence_by_id]
        source_ids: list[str] = []
        for evidence_id in used_ids:
            source_ids.extend(str(value) for value in evidence_by_id[evidence_id].get("source_segment_ids") or [] if str(value))
        source_ids = list(dict.fromkeys(source_ids))
        source_range = _range_from_source_segments(source_ids, segments_by_id)
        important_count = sum(1 for evidence_id in used_ids if evidence_id in important_ids)
        chapter_table.append({
            "chapter_id": chapter.get("chapter_id") or f"CH{order:02d}",
            "order": order,
            "title": str(chapter.get("title") or "").strip(),
            "purpose": str(chapter.get("purpose") or "").strip(),
            "evidence_ids": used_ids,
            "evidence_count": len(used_ids),
            "important_evidence_count": important_count,
            "source_segment_ids": source_ids,
            "char_start": source_range["char_start"],
            "char_end": source_range["char_end"],
        })

    return {
        "chapter_coverage_version": CHAPTER_COVERAGE_VERSION,
        "summary": {
            "segment_count": len(segments),
            "evidence_count": len(evidence),
            "chapter_count": len(chapters),
            "important_evidence_count": len(important_ids),
            "covered_important_evidence_count": len(important_ids) - len(uncovered_important),
            "coverage_missing_count": coverage_missing_count,
            "coverage_checked": coverage_checked,
            "coverage_revision_used": coverage_revision_used,
        },
        "segments": segment_table,
        "evidence": evidence_table,
        "chapters": chapter_table,
        "missing_important_evidence_ids": uncovered_important,
    }


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


_CN_DIGITS: Final[str] = "零一二三四五六七八九"

# Only strips a leading heading NUMBER prefix (一、/ 第一、/ 3. / 3.1), never a
# title that merely starts with a number word like "十亿美金".
_LEADING_HEADING_NUMBER_RE = re.compile(
    r"^\s*(?:"
    r"第?\s*[一二三四五六七八九十百零]+\s*[、.．)）]\s*"
    r"|\d+(?:[.．]\d+)+\s*"
    r"|\d+\s*[、.．)）]\s*"
    r")"
)


def _cn_number(n: int) -> str:
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + (_CN_DIGITS[n - 10] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")


def _renumber_chapter_headings(markdown: str) -> str:
    """Give chapter-coverage notes one consistent numbered hierarchy: top-level
    chapters become '## 一、…', their sub-sections '### x.y …'. The mode builds
    chapters independently, so it otherwise loses unified numbering (uses bare
    '#' per chapter with no numbers). Deterministic, so it never depends on the
    model getting numbering right."""
    lines = markdown.splitlines()
    depths = [len(m.group(1)) for line in lines if (m := re.match(r"^(#{1,6})\s+\S", line))]
    if not depths:
        return markdown
    top = min(depths)
    # A single top-level heading above deeper ones is the document title, not a
    # chapter — keep it as '#' and treat the next level as the chapters.
    has_deeper = any(d > top for d in depths)
    title_depth = top if (depths.count(top) == 1 and has_deeper) else None
    section_depth = min((d for d in depths if d > top), default=top) if title_depth else top
    sec = 0
    sub = 0
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if not m:
            out.append(line)
            continue
        depth = len(m.group(1))
        title = _LEADING_HEADING_NUMBER_RE.sub("", m.group(2)).strip()
        if title_depth is not None and depth == title_depth:
            out.append(f"# {title}")
        elif depth <= section_depth:
            sec += 1
            sub = 0
            out.append(f"## {_cn_number(sec)}、{title}")
        else:
            if sec == 0:
                sec = 1
            sub += 1
            out.append(f"### {sec}.{sub} {title}")
    return "\n".join(out)


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

    def _extract_segment_evidence(batch: dict[str, Any]) -> list[Any]:
        payload = json.dumps([batch], ensure_ascii=False)
        try:
            return _chat_json_array(client, model, _CHAPTER_EVIDENCE_SYSTEM, payload, temperature=0.1)
        except ValueError:
            # One malformed chunk must not sink the whole note — skip it and keep
            # the rest. Logged (not silent) so lost coverage is visible.
            logger.warning(
                "Chapter-coverage evidence extraction returned unparseable JSON for "
                "segment %s; skipping it.", batch.get("segment_id"),
            )
            return []

    # Extract each segment's evidence concurrently, then assign stable sequential
    # IDs in the original order so downstream references stay deterministic.
    raw_batches = _parallel_map(_extract_segment_evidence, segments)
    evidence: list[dict[str, Any]] = []
    for raw_items in raw_batches:
        evidence.extend(_normalize_evidence_items(raw_items, valid_segment_ids, start_index=len(evidence)))

    if not evidence:
        raise ValueError("Chapter coverage evidence extraction returned no usable evidence")

    outline_payload = json.dumps(_compact_evidence_view(evidence), ensure_ascii=False)
    raw_chapters = _chat_json_array(client, model, _CHAPTER_OUTLINE_SYSTEM, outline_payload, temperature=0.1)
    chapters = _normalize_chapters(raw_chapters, evidence)
    evidence_by_id = {item["evidence_id"]: item for item in evidence}

    def _chapter_evidence_for(chapter: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            evidence_by_id[evidence_id]
            for evidence_id in chapter["used_evidence_ids"]
            if evidence_id in evidence_by_id
        ]

    covered_ids: set[str] = set()
    for chapter in chapters:
        covered_ids.update(item["evidence_id"] for item in _chapter_evidence_for(chapter))

    def _write_chapter(chapter: dict[str, Any]) -> str:
        user = json.dumps({
            "chapter_id": chapter["chapter_id"],
            "title": chapter["title"],
            "purpose": chapter.get("purpose") or "",
            "evidence": _chapter_evidence_for(chapter),
        }, ensure_ascii=False)
        return _strip_prompt_leakage(_chat(client, model, _CHAPTER_NOTE_SYSTEM, user, temperature=0.2))

    # Each chapter is written independently from its own evidence; run concurrently, keep order.
    chapter_notes: list[str] = _parallel_map(_write_chapter, chapters)

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

    # Chapters are written independently, so normalize the assembled note into
    # one consistent numbered hierarchy (## 一、 + ### x.y).
    final_note = _renumber_chapter_headings(final_note)

    chapter_coverage = _build_chapter_coverage_table(
        segments=segments,
        evidence=evidence,
        chapters=chapters,
        covered_ids=covered_ids,
        important_ids=important_ids,
        uncovered_important=uncovered_important,
        coverage_checked=coverage_checked,
        coverage_revision_used=coverage_revision_used,
        coverage_missing_count=missing_count,
    )

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
        chapter_coverage=chapter_coverage,
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
    total = len(chunks)

    def _extract_evidence(indexed_chunk: tuple[int, str]) -> str:
        idx, chunk = indexed_chunk
        user = f"这是整段转录的第 {idx + 1}/{total} 部分，请提取证据。\n\n{chunk}"
        return _chat(client, m, _EVIDENCE_SYSTEM, user, temperature=0.2)

    # Each chunk's extraction is independent; run them concurrently but keep order.
    evidence_items: list[str] = _parallel_map(_extract_evidence, list(enumerate(chunks)))

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

    frame_lines = [f"- [{Path(p).name}] (候选截图)" for p in frame_paths]
    user = (
        f"请在以下 {len(frame_paths)} 张候选截图中挑选最有信息量的 0-8 张，生成结构化笔记。"
        "图片必须服务具体知识点，不要插入封面、目录、纯标题页、纯人物讲话或重复画面：\n\n"
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
    "VisualRequestPlanResult",
    "VisualFrameSelectionResult",
    "SegmentTranslationResult",
    "BilingualSegmentResult",
    "can_use_multimodal",
    "generate_bilingual_segments_zh",
    "plan_visual_evidence_requests",
    "select_visual_evidence_frames",
    "translate_segments_to_zh",
    "summarize_transcript_with_metadata",
    "summarize_transcript_with_frames",
    "summarize_transcript_to_markdown",
    "visual_requests_to_frame_segments",
]
