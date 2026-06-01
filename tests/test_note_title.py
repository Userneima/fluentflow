"""Tests for backend.core.note_title."""

import unittest

from backend.core.note_title import (
    extract_note_title_from_markdown,
    resolve_lark_doc_title,
)


class TestNoteTitle(unittest.TestCase):
    def test_h1(self) -> None:
        md = "# 量子计算入门\n\n正文"
        self.assertEqual(extract_note_title_from_markdown(md), "量子计算入门")

    def test_h1_with_bold(self) -> None:
        md = "# **Bold Title** \n\nx"
        self.assertEqual(extract_note_title_from_markdown(md), "Bold Title")

    def test_overview_line(self) -> None:
        md = "1. 📌 **一句话概览**：用一句话总结本段视频的核心主题。\n\n## x"
        self.assertEqual(
            extract_note_title_from_markdown(md),
            "用一句话总结本段视频的核心主题。",
        )

    def test_skips_template_h2(self) -> None:
        md = "## 📌 **一句话概览**\n\nfoo"
        self.assertIsNone(extract_note_title_from_markdown(md))

    def test_h2_when_no_h1(self) -> None:
        md = "## 自定义章节标题\n\n内容"
        self.assertEqual(extract_note_title_from_markdown(md), "自定义章节标题")

    def test_resolve_prefers_extract_over_form(self) -> None:
        md = "# From MD\n\nx"
        r = resolve_lark_doc_title(md, filename_stem="file", form_title="ignored")
        self.assertEqual(r, "From MD")

    def test_resolve_fallback_chain(self) -> None:
        md = "no headings"
        self.assertEqual(
            resolve_lark_doc_title(md, filename_stem="stem", form_title="form"),
            "form",
        )
        self.assertEqual(
            resolve_lark_doc_title(md, filename_stem="stem", form_title=None),
            "stem",
        )
        self.assertEqual(
            resolve_lark_doc_title(md, filename_stem="", form_title=None),
            "FluentFlow Export",
        )


if __name__ == "__main__":
    unittest.main()
