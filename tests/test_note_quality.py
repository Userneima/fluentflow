from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.core.note_quality import (
    NoteQualityInput,
    build_note_quality_collection,
    build_note_quality_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sample_result() -> dict:
    return {
        "result_schema_version": "2",
        "task_id": "sample-long-01",
        "display_title": "长视频课程样本",
        "transcript_text": "第一章介绍背景。第二章讲方法。第三章总结案例。",
        "raw_segments": [
            {"start": 0, "end": 10, "text": "第一章介绍背景。"},
            {"start": 10, "end": 20, "text": "第二章讲方法。"},
        ],
        "display_segments": [
            {"start": 0, "end": 10, "text": "第一章介绍背景。"},
            {"start": 10, "end": 20, "text": "第二章讲方法。"},
        ],
        "summary_markdown": "# 课程笔记\n\n- 背景\n- 方法",
        "summary_status": "completed",
        "requested_note_mode": "auto",
        "resolved_note_mode": "chapter_coverage",
        "prompt_preset": "course",
        "prompt_preset_label": "课程笔记",
        "note_mode_evidence_count": 6,
        "note_mode_chapter_count": 3,
        "note_mode_important_evidence_count": 4,
        "note_mode_covered_important_evidence_count": 3,
        "note_mode_coverage_missing_count": 1,
        "chapter_coverage": {
            "chapter_coverage_version": "1",
            "summary": {"evidence_count": 6, "chapter_count": 3},
        },
        "token_usage": {
            "input_tokens": 1200,
            "output_tokens": 360,
            "total_tokens": 1560,
        },
        "summary_elapsed_seconds": 42.5,
    }


def test_build_note_quality_report_records_metrics_without_fake_quality_score() -> None:
    report = build_note_quality_report(load_note_quality_input_from_result(_sample_result()))

    assert report["note_quality_report_version"] == "1"
    assert report["sample"]["sample_id"] == "sample-long-01"
    assert report["run"]["resolved_note_mode"] == "chapter_coverage"
    assert report["material_metrics"]["raw_segment_count"] == 2
    assert report["coverage_metadata"]["recorded_important_coverage_rate"] == 0.75
    assert report["coverage_metadata"]["chapter_coverage_version"] == "1"
    assert report["usage_metrics"]["total_tokens"] == 1560
    assert report["quality_review"]["status"] == "pending_review"
    assert all(value is None for value in report["quality_review"]["rubric"].values())


def test_build_note_quality_report_attaches_external_review() -> None:
    review = {
        "samples": {
            "sample-long-01": {
                "scores": {"coverage": 4.5, "faithfulness": 5, "structure": 4},
                "important_points": 5,
                "covered_important_points": 4,
                "missed_important_points": ["P009"],
                "hallucination_risk": "low",
                "reviewer": "model-review",
                "notes": "漏掉了一个案例。",
            }
        }
    }

    item = load_note_quality_input_from_result(_sample_result(), review=review)
    report = build_note_quality_report(item)

    assert report["quality_review"]["status"] == "reviewed"
    assert report["quality_review"]["rubric"]["coverage"] == 4.5
    assert report["quality_review"]["important_coverage_rate"] == 0.8
    assert report["quality_review"]["missed_important_points"] == ["P009"]


def test_build_note_quality_collection_groups_by_mode() -> None:
    direct = _sample_result() | {"task_id": "direct-01", "resolved_note_mode": "direct"}
    chapter = _sample_result() | {"task_id": "chapter-01", "resolved_note_mode": "chapter_coverage"}

    collection = build_note_quality_collection([
        load_note_quality_input_from_result(direct),
        load_note_quality_input_from_result(chapter),
    ])

    assert collection["run_count"] == 2
    assert collection["modes"]["direct"]["sample_ids"] == ["direct-01"]
    assert collection["modes"]["chapter_coverage"]["sample_ids"] == ["chapter-01"]


def test_evaluate_note_quality_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    input_path = tmp_path / "result.json"
    output_dir = tmp_path / "reports"
    input_path.write_text(json.dumps(_sample_result(), ensure_ascii=False), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_note_quality.py",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "sample-long-01" in (output_dir / "report.md").read_text(encoding="utf-8")
    payload = json.loads((output_dir / "runs.json").read_text(encoding="utf-8"))
    assert payload["run_count"] == 1
    assert payload["reports"][0]["quality_review"]["status"] == "pending_review"


def load_note_quality_input_from_result(result: dict, review: dict | None = None):
    return NoteQualityInput(
        sample_id=result["task_id"],
        result=result,
        job=None,
        source_path=None,
        review=review,
    )
