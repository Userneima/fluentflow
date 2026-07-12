from __future__ import annotations

import json
from types import SimpleNamespace

from backend.core import lark_cli_exporter


def test_lark_cli_export_normalizes_markdown_before_create(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(lark_cli_exporter, "_resolve_lark_cli_bin", lambda explicit=None: "/usr/local/bin/lark-cli")

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "data": {"doc_url": "https://feishu.cn/docx/demo", "doc_id": "demo"}}),
            stderr="",
        )

    monkeypatch.setattr(lark_cli_exporter.subprocess, "run", fake_run)

    result = lark_cli_exporter.export_markdown_via_lark_cli(
        "Demo",
        "| 层级 | 说明 |\n|------|------|\n| LLM 大脑 | Agent 的基础 |",
    )

    markdown = captured["cmd"][captured["cmd"].index("--markdown") + 1]
    assert "|------|" not in markdown
    assert "- **层级**：LLM 大脑" in markdown
    assert "  - **说明**：Agent 的基础" in markdown
    assert result["markdown_format"] == "feishu_normalized"
