"""Tests for local STT text normalization helpers."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from backend.core.local_stt import (
    TranscriptSegment,
    _MAX_HOTWORDS_CHARS,
    _MAX_INITIAL_PROMPT_CHARS,
    _build_transcribe_defaults,
    _filter_repeated_hallucination_segments,
    _looks_like_low_confidence_hallucination,
    _normalize_language,
    _resolve_model,
    _simplify_segments,
    _transcribe_profile_defaults,
    _to_simplified_chinese,
    _write_wav_chunks,
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

    def test_transcribe_prompt_and_hotwords_are_bounded(self) -> None:
        defaults = _build_transcribe_defaults(
            language="zh",
            speed_profile="balanced",
            hotwords=" ".join(f"热词{i}" for i in range(200)),
            initial_prompt="提示词" * 200,
        )

        self.assertLessEqual(len(defaults["initial_prompt"]), _MAX_INITIAL_PROMPT_CHARS)
        self.assertLessEqual(len(defaults["hotwords"]), _MAX_HOTWORDS_CHARS)
        self.assertIn("以下是普通话中文语音转录", defaults["initial_prompt"])

    def test_legacy_low_quality_models_resolve_to_medium(self) -> None:
        self.assertEqual(_resolve_model("tiny"), "medium")
        self.assertEqual(_resolve_model("base"), "medium")
        self.assertEqual(_resolve_model("small"), "medium")
        self.assertEqual(_resolve_model(""), "medium")

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

    def test_write_wav_chunks_preserves_offsets_and_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.wav"
            with wave.open(str(src), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(10)
                writer.writeframes(b"\x00\x00" * 25)

            chunks = _write_wav_chunks(src, Path(tmp) / "chunks", chunk_seconds=1.0)

            self.assertEqual(len(chunks), 3)
            self.assertEqual([round(chunk.start, 2) for chunk in chunks], [0.0, 1.0, 2.0])
            self.assertEqual([round(chunk.duration, 2) for chunk in chunks], [1.0, 1.0, 0.5])
            for chunk in chunks:
                self.assertTrue(chunk.path.is_file())


if __name__ == "__main__":
    unittest.main()
