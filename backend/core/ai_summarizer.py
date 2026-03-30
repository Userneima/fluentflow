"""Summarize Whisper transcripts with DeepSeek (OpenAI-compatible API)."""

from __future__ import annotations

import os
from typing import Final

from dotenv import load_dotenv
from openai import OpenAI

DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
DEFAULT_MODEL: Final[str] = "deepseek-chat"

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
- 输出为可直接粘贴飞书云文档的 Markdown，不要使用代码围栏包裹整篇文档。"""

# 分段提炼时使用（减轻最终合并输入长度）
_INTERIM_SYSTEM: Final[str] = """你是 FluentFlow 的预处理助手。输入为 Whisper 转录的一小段原文。
请用简洁的中文 Markdown 输出：
- 本段关键事实、术语与数字
- 本段讲解主线（短句列表即可）
不要编造；可忽略无意义口头语。输出将用于后续合并，无需五大板块的完整成品格式。"""

_BATCH_CONDENSE_SYSTEM: Final[str] = """你是 FluentFlow 的编校助手。下面若干段是同一课程不同时间段的「分段要点草稿」。
请合并去重，保留重要术语与逻辑顺序，输出一份连贯的「合并要点稿」（仍用 Markdown，可多级列表），不要套用五大板块终稿格式。"""

_FINAL_WRAPPER: Final[str] = (
    "以下内容来自**同一门课程**转录文本的分段提炼（按时间顺序）。"
    "请**整理为一份完整**、可直接用于飞书云文档的 Markdown 笔记，"
    "严格遵循系统说明中的角色、版式与五大板块结构，理顺逻辑并去重。\n\n---\n\n"
)


def _get_client(*, api_key: str | None = None) -> OpenAI:
    load_dotenv()
    key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        raise ValueError("DEEPSEEK_API_KEY 未设置：请在 .env 中配置或传入 api_key。")
    return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)


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


def summarize_transcript_to_markdown(
    transcript: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    system_prompt: str | None = None,
    max_chunk_chars: int = 10_000,
    chunk_overlap: int = 400,
    max_final_input_chars: int = 55_000,
    interim_batch_cap: int = 28_000,
) -> str:
    """
    将整段转录稿总结为飞书友好的结构化 Markdown。

    Args:
        system_prompt: Custom system prompt; uses the default FluentFlow prompt if empty.
    """
    load_dotenv()
    client = _get_client(api_key=api_key)
    m = (model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL).strip()
    prompt = (system_prompt or "").strip() or FLUENTFLOW_SYSTEM_PROMPT

    chunks = _chunk_text(transcript, max_chunk_chars, chunk_overlap)
    if not chunks:
        return ""

    if len(chunks) == 1:
        return _chat(client, m, prompt, chunks[0])

    drafts: list[str] = []
    total = len(chunks)
    for idx, ch in enumerate(chunks):
        user = f"这是整段转录的第 {idx + 1}/{total} 部分。\n\n{ch}"
        drafts.append(_chat(client, m, _INTERIM_SYSTEM, user))

    merged_body = "\n\n---\n\n".join(
        f"## 分段 {i + 1}\n{d}" for i, d in enumerate(drafts)
    )
    final_user = _FINAL_WRAPPER + merged_body
    if len(final_user) > max_final_input_chars:
        merged_body = _condense_interim_drafts(
            client, m, drafts, max_batch_chars=interim_batch_cap
        )
        final_user = _FINAL_WRAPPER + merged_body

    return _chat(client, m, prompt, final_user)


__all__ = [
    "DEEPSEEK_BASE_URL",
    "DEFAULT_MODEL",
    "FLUENTFLOW_SYSTEM_PROMPT",
    "summarize_transcript_to_markdown",
]
