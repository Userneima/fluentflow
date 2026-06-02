#!/usr/bin/env python3
"""Evaluate an STT subtitle against a human-corrected reference."""

from __future__ import annotations

import argparse
import csv
import json
import string
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.transcript_parser import parse_transcript_file  # noqa: E402


@dataclass(frozen=True)
class EvaluationResult:
    segment_count: int
    changed_segment_count: int
    reference_chars: int
    hypothesis_chars: int
    edit_distance: int
    cer: float

    @property
    def char_accuracy(self) -> float:
        return 1.0 - self.cer

    @property
    def segment_exact_rate(self) -> float:
        if self.segment_count <= 0:
            return 0.0
        return 1.0 - self.changed_segment_count / self.segment_count


def normalize_text(value: str) -> str:
    """Normalize text for Mandarin-heavy STT evaluation."""
    normalized = unicodedata.normalize("NFKC", value or "").lower()
    return "".join(
        char
        for char in normalized
        if not char.isspace()
        and not unicodedata.category(char).startswith("P")
        and char not in string.punctuation
    )


def levenshtein_distance(reference: str, hypothesis: str) -> int:
    """Return character edit distance between reference and hypothesis."""
    if reference == hypothesis:
        return 0
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)

    previous = list(range(len(hypothesis) + 1))
    for i, reference_char in enumerate(reference, start=1):
        current = [i]
        for j, hypothesis_char in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (reference_char != hypothesis_char),
                )
            )
        previous = current
    return previous[-1]


def load_subtitle(path: Path) -> tuple[str, tuple[dict[str, float | str], ...]]:
    parsed = parse_transcript_file(path.read_bytes(), path.name)
    if parsed.segments:
        return parsed.text, parsed.segments
    return parsed.text, tuple(
        {"start": 0.0, "end": 0.0, "text": line}
        for line in parsed.text.splitlines()
        if line.strip()
    )


def evaluate_pair(reference_text: str, hypothesis_text: str, segment_count: int, changed_segments: int) -> EvaluationResult:
    reference_norm = normalize_text(reference_text)
    hypothesis_norm = normalize_text(hypothesis_text)
    distance = levenshtein_distance(reference_norm, hypothesis_norm)
    cer = distance / len(reference_norm) if reference_norm else 0.0
    return EvaluationResult(
        segment_count=segment_count,
        changed_segment_count=changed_segments,
        reference_chars=len(reference_norm),
        hypothesis_chars=len(hypothesis_norm),
        edit_distance=distance,
        cer=cer,
    )


def load_json_list(path: Path | None, key: str) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [item for item in payload[key] if isinstance(item, dict)]
    raise ValueError(f"{path} must be a JSON list or contain a {key!r} list")


def evaluate_glossary(reference_text: str, hypothesis_text: str, glossary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_norm = normalize_text(reference_text)
    hypothesis_norm = normalize_text(hypothesis_text)
    rows: list[dict[str, Any]] = []
    for item in glossary:
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        aliases = [str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()]
        variants = [term, *aliases]
        in_reference = any(normalize_text(variant) in reference_norm for variant in variants)
        in_hypothesis = any(normalize_text(variant) in hypothesis_norm for variant in variants)
        rows.append(
            {
                "term": term,
                "category": item.get("category") or "",
                "in_reference": in_reference,
                "in_hypothesis": in_hypothesis,
                "matched": (not in_reference) or in_hypothesis,
            }
        )
    return rows


def evaluate_confusions(hypothesis_text: str, confusions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hypothesis_norm = normalize_text(hypothesis_text)
    rows: list[dict[str, Any]] = []
    for item in confusions:
        wrong = str(item.get("wrong") or "").strip()
        correct = str(item.get("correct") or "").strip()
        if not wrong or not correct:
            continue
        count = hypothesis_norm.count(normalize_text(wrong))
        rows.append(
            {
                "wrong": wrong,
                "correct": correct,
                "category": item.get("category") or "",
                "hit_count": count,
                "active": count > 0,
                "note": item.get("note") or "",
            }
        )
    return rows


def changed_segment_rows(
    reference_segments: tuple[dict[str, float | str], ...],
    hypothesis_segments: tuple[dict[str, float | str], ...],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (reference, hypothesis) in enumerate(zip(reference_segments, hypothesis_segments), start=1):
        reference_text = str(reference.get("text") or "")
        hypothesis_text = str(hypothesis.get("text") or "")
        if reference_text == hypothesis_text:
            continue
        distance = levenshtein_distance(normalize_text(reference_text), normalize_text(hypothesis_text))
        rows.append(
            {
                "index": index,
                "start": reference.get("start"),
                "end": reference.get("end"),
                "edit_distance": distance,
                "reference": reference_text,
                "hypothesis": hypothesis_text,
            }
        )
    return rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path, help="Human-corrected SRT/VTT/TXT")
    parser.add_argument("--hypothesis", required=True, type=Path, help="Model-generated SRT/VTT/TXT")
    parser.add_argument("--glossary", type=Path, default=None, help="Optional JSON glossary")
    parser.add_argument("--confusions", type=Path, default=None, help="Optional JSON confusion pairs")
    parser.add_argument("--output-dir", type=Path, default=None, help="Write summary and TSV reports")
    args = parser.parse_args()

    reference_text, reference_segments = load_subtitle(args.reference.expanduser().resolve())
    hypothesis_text, hypothesis_segments = load_subtitle(args.hypothesis.expanduser().resolve())
    changed_rows = changed_segment_rows(reference_segments, hypothesis_segments)
    result = evaluate_pair(
        reference_text,
        hypothesis_text,
        max(len(reference_segments), len(hypothesis_segments)),
        len(changed_rows),
    )
    glossary_rows = evaluate_glossary(reference_text, hypothesis_text, load_json_list(args.glossary, "terms"))
    confusion_rows = evaluate_confusions(hypothesis_text, load_json_list(args.confusions, "pairs"))

    glossary_reference_rows = [row for row in glossary_rows if row["in_reference"]]
    glossary_matched_rows = [row for row in glossary_reference_rows if row["in_hypothesis"]]
    summary: dict[str, Any] = {
        "reference": str(args.reference),
        "hypothesis": str(args.hypothesis),
        "metrics": {
            "segment_count": result.segment_count,
            "changed_segment_count": result.changed_segment_count,
            "segment_exact_rate": round(result.segment_exact_rate, 6),
            "reference_chars": result.reference_chars,
            "hypothesis_chars": result.hypothesis_chars,
            "edit_distance": result.edit_distance,
            "cer": round(result.cer, 6),
            "char_accuracy": round(result.char_accuracy, 6),
            "glossary_reference_count": len(glossary_reference_rows),
            "glossary_matched_count": len(glossary_matched_rows),
            "glossary_recall": round(len(glossary_matched_rows) / len(glossary_reference_rows), 6)
            if glossary_reference_rows
            else None,
            "active_confusion_count": sum(1 for row in confusion_rows if row["active"]),
        },
    }

    if args.output_dir:
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_tsv(output_dir / "changed_segments.tsv", changed_rows)
        write_tsv(output_dir / "glossary_recall.tsv", glossary_rows)
        write_tsv(output_dir / "confusion_hits.tsv", confusion_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
