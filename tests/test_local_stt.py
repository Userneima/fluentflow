"""Tests for local STT text normalization helpers."""

from __future__ import annotations

import unittest

from backend.core.local_stt import (
    TranscriptSegment,
    _filter_repeated_hallucination_segments,
    _looks_like_low_confidence_hallucination,
    _normalize_language,
    _simplify_segments,
    _transcribe_profile_defaults,
    _to_simplified_chinese,
)


class TestLocalStt(unittest.TestCase):
    def test_to_simplified_chinese(self) -> None:
        self.assertEqual(
            _to_simplified_chinese("現在我們會篩選創造營同學的作業"),
            "现在我们会筛选创造营同学的作业",
        )

    def test_simplify_segments(self) -> None:
        segments = (
            TranscriptSegment(start=0, end=1, text="現在"),
            TranscriptSegment(start=1, end=2, text="創造營"),
        )
        simplified = _simplify_segments(segments)
        self.assertEqual([s.text for s in simplified], ["现在", "创造营"])

    def test_fast_profile_uses_greedy_decode(self) -> None:
        defaults = _transcribe_profile_defaults("fast")
        self.assertEqual(defaults["beam_size"], 1)
        self.assertEqual(defaults["best_of"], 1)

    def test_unknown_profile_falls_back_to_balanced(self) -> None:
        defaults = _transcribe_profile_defaults("unknown")
        self.assertEqual(defaults["beam_size"], 3)
        self.assertEqual(defaults["best_of"], 3)

    def test_language_defaults_to_auto_detection(self) -> None:
        self.assertIsNone(_normalize_language(None))
        self.assertIsNone(_normalize_language("auto"))
        self.assertEqual(_normalize_language("zh-CN"), "zh")
        self.assertEqual(_normalize_language("English"), "en")

    def test_filter_repeated_short_hallucination_run(self) -> None:
        segments = (
            TranscriptSegment(start=0, end=2, text="真实内容"),
            TranscriptSegment(start=10, end=12, text="大学生 课题"),
            TranscriptSegment(start=12, end=14, text="大学生 课题"),
            TranscriptSegment(start=14, end=16, text="大学生 课题"),
            TranscriptSegment(start=16, end=18, text="大学生 课题"),
            TranscriptSegment(start=20, end=22, text="后续内容"),
        )
        filtered = _filter_repeated_hallucination_segments(segments)

        self.assertEqual([s.text for s in filtered], ["真实内容", "后续内容"])

    def test_keep_short_phrase_when_not_repeated_enough(self) -> None:
        segments = (
            TranscriptSegment(start=0, end=1, text="好"),
            TranscriptSegment(start=1, end=2, text="好"),
            TranscriptSegment(start=2, end=3, text="继续"),
        )
        filtered = _filter_repeated_hallucination_segments(segments)

        self.assertEqual([s.text for s in filtered], ["好", "好", "继续"])

    def test_low_confidence_segment_detection(self) -> None:
        class Segment:
            no_speech_prob = 0.9
            avg_logprob = -0.8
            compression_ratio = 1.0

        self.assertTrue(_looks_like_low_confidence_hallucination(Segment()))


if __name__ == "__main__":
    unittest.main()
