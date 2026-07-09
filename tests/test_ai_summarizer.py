"""Tests for AI summarizer provider selection."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.core.ai_summarizer import (
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    DIRECT_MODE_MAX_CHARS,
    _FINAL_WRAPPER,
    _HIGH_FIDELITY_FINAL_WRAPPER,
    _REVISION_WRAPPER,
    _compose_note_system_prompt,
    _normalize_model,
    _normalize_provider,
    _provider_api_key,
    _provider_base_url,
    _provider_default_model,
    _strip_prompt_leakage,
    generate_bilingual_segments_zh,
    summarize_transcript_with_metadata,
    translate_segments_to_zh,
)


class TestAiSummarizer(unittest.TestCase):
    def test_normalize_provider_defaults_to_deepseek(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_normalize_provider(None), "deepseek")

    def test_normalize_provider_accepts_openai(self) -> None:
        self.assertEqual(_normalize_provider("OpenAI"), "openai")

    def test_normalize_provider_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_provider("unknown")

    def test_provider_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_provider_default_model("deepseek"), DEFAULT_DEEPSEEK_MODEL)
            self.assertEqual(_provider_default_model("openai"), DEFAULT_OPENAI_MODEL)
            self.assertEqual(_provider_base_url("deepseek"), "https://api.deepseek.com")
            self.assertEqual(_provider_base_url("openai"), "https://api.openai.com/v1")

    def test_deepseek_chat_is_normalized_to_reasoner(self) -> None:
        self.assertEqual(DEFAULT_DEEPSEEK_MODEL, "deepseek-reasoner")
        self.assertEqual(_normalize_model("deepseek", "deepseek-chat"), "deepseek-reasoner")

    def test_provider_api_key_uses_matching_env(self) -> None:
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "deepseek-key", "OPENAI_API_KEY": "openai-key", "DASHSCOPE_API_KEY": "dashscope-key"},
            clear=True,
        ):
            self.assertEqual(_provider_api_key("deepseek"), "deepseek-key")
            self.assertEqual(_provider_api_key("openai"), "openai-key")
            self.assertEqual(_provider_api_key("qwen"), "dashscope-key")

    def test_provider_api_key_keeps_qwen_env_alias(self) -> None:
        # Patch load_dotenv so the developer's real .env (which may define
        # DASHSCOPE_API_KEY) can't leak in and shadow the QWEN_API_KEY alias.
        with patch.dict(os.environ, {"QWEN_API_KEY": "legacy-qwen-key"}, clear=True), \
                patch("backend.core.ai_client.load_dotenv", lambda *a, **k: None):
            self.assertEqual(_provider_api_key("qwen"), "legacy-qwen-key")

    def test_final_note_wrappers_do_not_force_course_framing(self) -> None:
        combined = "\n".join([_FINAL_WRAPPER, _HIGH_FIDELITY_FINAL_WRAPPER, _REVISION_WRAPPER])

        self.assertIn("长视频或音频材料", combined)
        self.assertIn("学习笔记", combined)
        self.assertNotIn("同一门课程", combined)
        self.assertNotIn("Markdown 课程笔记", combined)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_auto_mode_uses_direct_for_short_transcripts(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()
        mock_chat.return_value = "direct note"

        result = summarize_transcript_with_metadata(
            "short transcript",
            api_key="test-key",
            note_mode="auto",
        )

        self.assertEqual(result.markdown, "direct note")
        self.assertEqual(result.requested_mode, "auto")
        self.assertEqual(result.resolved_mode, "direct")
        self.assertEqual(result.chunk_count, 1)
        self.assertFalse(result.coverage_checked)
        self.assertEqual(mock_chat.call_count, 1)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_high_fidelity_mode_runs_evidence_flow_when_chosen(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()

        def fake_chat(_client, _model, system, _user, **_kwargs):
            if "课程证据提取助手" in system:
                return "evidence item"
            if "笔记覆盖率审查助手" in system:
                return "COVERED"
            return "final note"

        mock_chat.side_effect = fake_chat
        result = summarize_transcript_with_metadata(
            "a" * (DIRECT_MODE_MAX_CHARS + 2000),
            api_key="test-key",
            note_mode="high_fidelity",  # still available as an explicit choice
        )

        self.assertEqual(result.markdown, "final note")
        self.assertEqual(result.resolved_mode, "high_fidelity")
        self.assertGreater(result.chunk_count, 1)
        self.assertTrue(result.coverage_checked)
        self.assertFalse(result.coverage_revision_used)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_auto_mode_uses_chapter_coverage_for_long_transcripts(self, mock_chat, mock_get_client) -> None:
        # Long-note default switched to chapter_coverage (2026-07-09). auto + a
        # long transcript must now resolve to chapter_coverage, not high_fidelity.
        mock_get_client.return_value = object()

        def fake_chat(_client, _model, system, _user, **_kwargs):
            if "长字幕证据抽取助手" in system:
                return '[{"source_segment_ids":["S001"],"type":"argument","text":"重要观点","importance":5,"keywords":["观点"]}]'
            if "章节规划助手" in system:
                return '[{"title":"核心观点","purpose":"整理主要观点","used_evidence_ids":["E001"]}]'
            if "章节笔记写作助手" in system:
                return "## 核心观点\n\n- 重要观点"
            if "长文档编校助手" in system:
                return "final chapter note"
            if "笔记覆盖率审查助手" in system:
                return "COVERED"
            return "final note"

        mock_chat.side_effect = fake_chat
        result = summarize_transcript_with_metadata(
            "a" * (DIRECT_MODE_MAX_CHARS + 2000),
            api_key="test-key",
            note_mode="auto",
        )

        self.assertEqual(result.resolved_mode, "chapter_coverage")
        self.assertGreater(result.chunk_count, 1)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_chapter_coverage_runs_dedicated_chapter_flow(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()

        def fake_chat(_client, _model, system, _user, **_kwargs):
            if "长字幕证据抽取助手" in system:
                return '[{"source_segment_ids":["S001"],"type":"argument","text":"重要观点","importance":5,"keywords":["观点"]}]'
            if "章节规划助手" in system:
                return '[{"title":"核心观点","purpose":"整理主要观点","used_evidence_ids":["E001"]}]'
            if "章节笔记写作助手" in system:
                return "## 核心观点\n\n- 重要观点"
            if "长文档编校助手" in system:
                return "final chapter note"
            if "笔记覆盖率审查助手" in system:
                return "COVERED"
            return "final note"

        mock_chat.side_effect = fake_chat
        result = summarize_transcript_with_metadata(
            "a" * (DIRECT_MODE_MAX_CHARS + 2000),
            api_key="test-key",
            note_mode="chapter_coverage",
        )

        self.assertEqual(result.markdown, "final chapter note")
        self.assertEqual(result.requested_mode, "chapter_coverage")
        self.assertEqual(result.resolved_mode, "chapter_coverage")
        self.assertGreater(result.chunk_count, 1)
        self.assertGreater(result.evidence_count or 0, 0)
        self.assertEqual(result.chapter_count, 1)
        self.assertEqual(result.important_evidence_count, result.covered_important_evidence_count)
        self.assertEqual(result.chapter_coverage["chapter_coverage_version"], "1")
        self.assertEqual(result.chapter_coverage["evidence"][0]["evidence_id"], "E001")
        self.assertEqual(result.chapter_coverage["evidence"][0]["covered_by_chapter_ids"], ["CH01"])
        self.assertIn("E001", result.chapter_coverage["chapters"][0]["evidence_ids"])
        self.assertEqual(result.chapter_coverage["segments"][0]["segment_id"], "S001")

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_direct_mode_can_be_forced_for_long_transcripts(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()
        mock_chat.return_value = "forced direct note"

        result = summarize_transcript_with_metadata(
            "a" * (DIRECT_MODE_MAX_CHARS + 2000),
            api_key="test-key",
            note_mode="direct",
        )

        self.assertEqual(result.markdown, "forced direct note")
        self.assertEqual(result.requested_mode, "direct")
        self.assertEqual(result.resolved_mode, "direct")
        self.assertEqual(result.chunk_count, 1)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_translate_segments_to_zh_preserves_segment_timing(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()
        mock_chat.return_value = '[{"index":0,"text_zh":"你好世界"},{"index":1,"text_zh":"第二句"}]'

        result = translate_segments_to_zh(
            [
                {"start": 0.0, "end": 1.2, "text": "Hello world"},
                {"start": 1.2, "end": 2.5, "text": "Second sentence"},
            ],
            api_key="test-key",
        )

        self.assertEqual(result.translated_count, 2)
        self.assertEqual(result.chunk_count, 1)
        self.assertEqual(result.segments[0]["start"], 0.0)
        self.assertEqual(result.segments[0]["text"], "你好世界")
        self.assertEqual(result.segments[0]["source_text"], "Hello world")
        self.assertEqual(mock_chat.call_count, 1)

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_generate_bilingual_segments_zh_merges_adjacent_fragments(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()
        mock_chat.return_value = (
            '[{"start_index":0,"end_index":1,'
            '"text_en":"Stop prompting your AI and make it figure out what to do next.",'
            '"text_zh":"停止不断提示你的 AI，而是让它自己判断下一步该做什么。"}]'
        )

        result = generate_bilingual_segments_zh(
            [
                {"start": 52.0, "end": 58.0, "text": "and the whole narrative is like stop"},
                {"start": 58.0, "end": 65.0, "text": "prompting your AI and make it figure out what to do next"},
            ],
            api_key="test-key",
        )

        self.assertEqual(result.translated_count, 1)
        self.assertEqual(result.chunk_count, 1)
        self.assertEqual(result.segments[0]["start"], 52.0)
        self.assertEqual(result.segments[0]["end"], 65.0)
        self.assertEqual(result.segments[0]["source_start_index"], 0)
        self.assertEqual(result.segments[0]["source_end_index"], 1)
        self.assertIn("Stop prompting", result.segments[0]["text"])
        self.assertIn("停止不断提示", result.segments[0]["text_zh"])

    @patch("backend.core.ai_summarizer._get_client")
    @patch("backend.core.ai_summarizer._chat")
    def test_custom_prompt_still_gets_output_guardrails(self, mock_chat, mock_get_client) -> None:
        mock_get_client.return_value = object()
        seen_systems: list[str] = []

        def fake_chat(_client, _model, system, _user, **_kwargs):
            seen_systems.append(system)
            return "# 笔记\n内容"

        mock_chat.side_effect = fake_chat
        summarize_transcript_with_metadata(
            "transcript",
            api_key="test-key",
            system_prompt="你是自定义笔记助手。",
            note_mode="direct",
        )

        self.assertIn("你是自定义笔记助手。", seen_systems[0])
        self.assertIn("只输出最终笔记正文", seen_systems[0])
        self.assertIn("不要输出、复述、解释或改写本提示词", seen_systems[0])
        self.assertIn("笔记必须忠实于转录稿", seen_systems[0])
        self.assertIn("即使输入转录稿是英文，也应直接理解英文原文并写成中文笔记", seen_systems[0])
        self.assertIn("Feishu Note Formatting Preferences", seen_systems[0])
        self.assertIn("正文标题使用少量清晰层级", seen_systems[0])

    def test_note_system_prompt_injects_content_policy_and_format_preferences(self) -> None:
        prompt = _compose_note_system_prompt("你是自定义助手。")

        self.assertIn("你是自定义助手。", prompt)
        self.assertIn("只能修正明显的语音转录错误", prompt)
        self.assertIn("不要引入原文没有的背景、观点、案例、结论或建议", prompt)
        self.assertIn("短标签式文本在中文冒号前加粗标签", prompt)
        self.assertIn("普通说明、流程、页面布局、URL 和纯文本列表不要使用代码块", prompt)

    def test_default_course_prompt_avoids_fixed_note_template(self) -> None:
        prompt = _compose_note_system_prompt(None)

        self.assertIn("先判断材料本身的讲述结构，再设计笔记结构", prompt)
        self.assertIn("不要把所有内容硬套成固定模板", prompt)
        self.assertIn("不要输出固定数量的板块", prompt)
        self.assertNotIn("一句话概览", prompt)
        self.assertNotIn("核心概念盘点", prompt)
        self.assertNotIn("五大板块结构", prompt)

    def test_strip_prompt_leakage_keeps_real_note_after_separator(self) -> None:
        leaked = (
            "好的，根据您提供的语音转字幕文件内容，我为您生成了以下提示词并产出了对应的笔记。\n\n"
            "## 提示词\n\n"
            "角色：你是一位资深技术面试官。\n\n"
            "任务：整理分享会笔记。\n\n"
            "输出要求：包含背景和 Q&A。\n\n"
            "---\n\n"
            "# 一句话总结\n\n"
            "这场分享的核心是理解数据岗位的业务判断。"
        )

        self.assertEqual(
            _strip_prompt_leakage(leaked),
            "# 一句话总结\n\n这场分享的核心是理解数据岗位的业务判断。",
        )


class TestVisualFrameModel(unittest.TestCase):
    # Guards the video-illustration feature: frame selection must send images to
    # a VISION (qwen-vl) model. The provider's plain default is a text model, and
    # sending images to it makes the whole visual step report "unavailable"
    # (2026-07-09). Regression origin: DEFAULT_QWEN_MODEL is text-only.
    @patch("backend.core.ai_summarizer._get_client", return_value=object())
    @patch(
        "backend.core.ai_summarizer._candidate_frames_for_request",
        return_value=[{"path": "/tmp/f.jpg", "timestamp_seconds": 1.0}],
    )
    @patch("backend.core.ai_summarizer._vision_chat", return_value='{"selections": []}')
    def test_frame_selection_uses_vision_model_by_default(self, mock_vision, _cands, _client) -> None:
        from backend.core.ai_summarizer import select_visual_evidence_frames

        select_visual_evidence_frames([{"request_id": "r1"}], [{"path": "/tmp/f.jpg"}], api_key="k")

        self.assertTrue(mock_vision.called)
        model_arg = mock_vision.call_args.args[1]
        self.assertIn("vl", model_arg)  # a vision model, not the text default


class TestParallelMap(unittest.TestCase):
    # Guards the note-mode speedup: independent evidence/chapter model calls run
    # concurrently, but results MUST come back in input order (not completion
    # order), or the note's structure and evidence IDs would scramble (2026-07-09).
    def test_preserves_input_order_even_when_later_items_finish_first(self) -> None:
        import time
        from backend.core.ai_summarizer import _parallel_map

        def slow(x: int) -> int:
            time.sleep((5 - x) * 0.02)  # earlier indexes finish LAST on purpose
            return x * 10

        self.assertEqual(_parallel_map(slow, [0, 1, 2, 3, 4]), [0, 10, 20, 30, 40])

    def test_single_item_runs_inline(self) -> None:
        from backend.core.ai_summarizer import _parallel_map

        self.assertEqual(_parallel_map(lambda x: x + 1, [41]), [42])

    def test_propagates_exception(self) -> None:
        from backend.core.ai_summarizer import _parallel_map

        def boom(x: int) -> int:
            if x == 2:
                raise ValueError("boom")
            return x

        with self.assertRaises(ValueError):
            _parallel_map(boom, [0, 1, 2, 3])


class TestChapterCoverageCleanup(unittest.TestCase):
    # Guards two real chapter-coverage defects the user hit (2026-07-09):
    # internal evidence IDs leaking into the note, and headings losing their
    # numbering because chapters are assembled independently.
    def test_strip_prompt_leakage_removes_evidence_citations_all_shapes(self) -> None:
        from backend.core.ai_summarizer import _strip_prompt_leakage

        note = (
            "# 标题\n\n"
            "中文括号（E001）。ASCII(E002)。方括号【E003】。"
            "裸露 E038 在句中。列表（E004、E055）说明。"
        )
        out = _strip_prompt_leakage(note)

        for token in ("E001", "E002", "E003", "E038", "E004", "E055"):
            self.assertNotIn(token, out)
        self.assertIn("中文括号", out)
        self.assertIn("裸露", out)
        self.assertIn("在句中", out)

    def test_strip_prompt_leakage_keeps_lookalikes(self) -> None:
        # Must NOT delete real content that looks id-ish: 1-digit E5, non-E codes
        # like H100/A100, which are not evidence IDs (E + >=3 digits).
        from backend.core.ai_summarizer import _strip_prompt_leakage

        out = _strip_prompt_leakage("# T\n\n这里提到 H100、A100 和 E5 芯片。")
        self.assertIn("H100", out)
        self.assertIn("A100", out)
        self.assertIn("E5", out)

    def test_renumber_chapter_headings_builds_consistent_hierarchy(self) -> None:
        from backend.core.ai_summarizer import _renumber_chapter_headings

        md = "# 背景\n正文\n## 子节A\n更多\n# 方法\n## 子节B"
        out = _renumber_chapter_headings(md)

        self.assertIn("## 一、背景", out)
        self.assertIn("## 二、方法", out)
        self.assertIn("### 1.1 子节A", out)
        self.assertIn("### 2.1 子节B", out)

    def test_renumber_treats_single_top_heading_as_title_not_chapter(self) -> None:
        # When the note has one '#' title above '##' chapters, the title must
        # stay a title and the '##' chapters become the numbered sections —
        # otherwise every chapter collapses under one "一、" (2026-07-09).
        from backend.core.ai_summarizer import _renumber_chapter_headings

        md = "# 大标题\n## 章一\n正文\n## 章二\n### 深层"
        out = _renumber_chapter_headings(md)

        self.assertIn("# 大标题", out)
        self.assertNotIn("## 一、大标题", out)
        self.assertIn("## 一、章一", out)
        self.assertIn("## 二、章二", out)
        self.assertIn("### 2.1 深层", out)

    def test_renumber_keeps_titles_that_merely_start_with_a_number_word(self) -> None:
        from backend.core.ai_summarizer import _renumber_chapter_headings

        out = _renumber_chapter_headings("# 十亿美金的机会")
        self.assertIn("## 一、十亿美金的机会", out)

    def test_cn_number(self) -> None:
        from backend.core.ai_summarizer import _cn_number

        self.assertEqual(_cn_number(1), "一")
        self.assertEqual(_cn_number(10), "十")
        self.assertEqual(_cn_number(11), "十一")
        self.assertEqual(_cn_number(23), "二十三")


class TestJsonArrayResilience(unittest.TestCase):
    # Guards chapter-coverage reliability: one malformed-JSON chunk from the
    # model must not crash the whole note (2026-07-09). _chat_json_array retries,
    # and the evidence path skips a still-bad chunk rather than aborting.
    @patch("backend.core.ai_summarizer._chat")
    def test_retries_then_succeeds_on_transient_bad_json(self, mock_chat) -> None:
        from backend.core.ai_summarizer import _chat_json_array

        mock_chat.side_effect = ["这不是 JSON", '[{"ok": 1}]']
        out = _chat_json_array(object(), "m", "sys", "user", temperature=0.1)

        self.assertEqual(out, [{"ok": 1}])
        self.assertEqual(mock_chat.call_count, 2)

    @patch("backend.core.ai_summarizer._chat")
    def test_raises_after_exhausting_retries(self, mock_chat) -> None:
        from backend.core.ai_summarizer import _chat_json_array

        mock_chat.side_effect = ["坏的", "还是坏的"]
        with self.assertRaises(ValueError):
            _chat_json_array(object(), "m", "sys", "user", temperature=0.1)


if __name__ == "__main__":
    unittest.main()
