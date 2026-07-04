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
