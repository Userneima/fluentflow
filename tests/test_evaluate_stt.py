from __future__ import annotations

import unittest

from scripts.evaluate_stt import (
    evaluate_confusions,
    evaluate_glossary,
    evaluate_pair,
    normalize_text,
)


class TestEvaluateStt(unittest.TestCase):
    def test_normalize_text_removes_punctuation_and_spacing(self) -> None:
        self.assertEqual(normalize_text("岗位 JD / AB 实验。"), "岗位jdab实验")

    def test_evaluate_pair_reports_character_accuracy(self) -> None:
        result = evaluate_pair("业务方做 AB 实验", "业务房做 AV 实验", 1, 1)

        self.assertEqual(result.edit_distance, 2)
        self.assertAlmostEqual(result.char_accuracy, 1 - 2 / len("业务方做ab实验"))

    def test_glossary_recall_accepts_aliases(self) -> None:
        rows = evaluate_glossary(
            "岗位 JD 和 AB 实验",
            "岗位jd和a/b实验",
            [{"term": "JD"}, {"term": "AB 实验", "aliases": ["a/b实验"]}],
        )

        self.assertTrue(all(row["matched"] for row in rows))

    def test_confusion_hits_count_wrong_terms(self) -> None:
        rows = evaluate_confusions(
            "业务房做 AV 实验，业务房再看数据。",
            [{"wrong": "业务房", "correct": "业务方"}, {"wrong": "AV 实验", "correct": "AB 实验"}],
        )

        self.assertEqual(rows[0]["hit_count"], 2)
        self.assertEqual(rows[1]["hit_count"], 1)


if __name__ == "__main__":
    unittest.main()
