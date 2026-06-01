import unittest

from backend.core.transcript_parser import parse_transcript_file


class TranscriptParserTest(unittest.TestCase):
    def test_parse_srt_segments(self) -> None:
        raw = (
            "1\n"
            "00:00:01,000 --> 00:00:03,500\n"
            "大家好\n\n"
            "2\n"
            "00:00:04,000 --> 00:00:05,250\n"
            "今天讲产品分析\n"
        ).encode("utf-8")
        parsed = parse_transcript_file(raw, "demo.srt")

        self.assertEqual(parsed.text, "大家好\n今天讲产品分析")
        self.assertEqual(len(parsed.segments), 2)
        self.assertEqual(parsed.segments[0]["start"], 1.0)
        self.assertEqual(parsed.segments[1]["end"], 5.25)
        self.assertEqual(parsed.duration, 5.25)

    def test_parse_vtt_without_sequence_numbers(self) -> None:
        raw = (
            "WEBVTT\n\n"
            "00:00.000 --> 00:02.000\n"
            "<v Speaker>hello world</v>\n"
        ).encode("utf-8")
        parsed = parse_transcript_file(raw, "demo.vtt")

        self.assertEqual(parsed.text, "hello world")
        self.assertEqual(parsed.segments[0]["end"], 2.0)

    def test_parse_plain_text(self) -> None:
        parsed = parse_transcript_file("第一段\n\n第二段".encode("utf-8"), "demo.txt")

        self.assertEqual(parsed.text, "第一段\n第二段")
        self.assertEqual(parsed.segments, ())
        self.assertEqual(parsed.duration, 0.0)


if __name__ == "__main__":
    unittest.main()
