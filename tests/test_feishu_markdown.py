from __future__ import annotations

from backend.core.feishu_markdown import normalize_markdown_for_feishu


def test_normalize_markdown_for_feishu_converts_pipe_tables_to_labeled_lists() -> None:
    markdown = """## 四、Agent 构建层级

| 层级 | 比喻 | 说明 |
|------|------|------|
| LLM 大脑 | 初始阶段的语言模型核心 | Agent 的基础 |
| **Tool Calling** | 装上手脚 | Agent 获得调用工具的能力 |

继续说明。
"""

    converted = normalize_markdown_for_feishu(markdown)

    assert "|------|" not in converted
    assert "| 层级 | 比喻 | 说明 |" not in converted
    assert "- **层级**：LLM 大脑" in converted
    assert "  - **比喻**：初始阶段的语言模型核心" in converted
    assert "  - **说明**：Agent 的基础" in converted
    assert "- **层级**：Tool Calling" in converted
    assert "继续说明。" in converted


def test_normalize_markdown_for_feishu_ignores_non_table_pipe_text() -> None:
    markdown = "这不是表格：A | B | C\n下一行没有 Markdown 表格分隔线。"

    assert normalize_markdown_for_feishu(markdown) == markdown


def test_normalize_markdown_for_feishu_converts_loose_pipe_tables() -> None:
    # A pipe table without the `| --- |` alignment row. The frontend Word/PDF
    # exporters already render this as a table, so the Feishu fallback must not
    # leak the raw pipe source either.
    markdown = "| 概念 | 说明 |\n| Agent | 智能体 |\n| Tool | 工具 |\n"

    converted = normalize_markdown_for_feishu(markdown)

    assert not any(line.strip().startswith("|") for line in converted.split("\n"))
    assert "- **概念**：Agent" in converted
    assert "  - **说明**：智能体" in converted
    assert "- **概念**：Tool" in converted
    assert "  - **说明**：工具" in converted


def test_normalize_markdown_for_feishu_keeps_single_pipe_line_as_text() -> None:
    # A lone pipe row is not a table (the frontend needs >= 2 rows too); leave
    # it untouched instead of guessing a one-row table.
    markdown = "| 只有一行 | 不是表格 |"

    assert normalize_markdown_for_feishu(markdown) == markdown
