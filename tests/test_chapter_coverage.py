from __future__ import annotations

from backend.core.chapter_coverage import bind_chapter_coverage_time_ranges


def test_bind_chapter_coverage_time_ranges_from_raw_segments() -> None:
    result = {
        "task_id": "task-coverage",
        "transcript_text": "第一段内容\n第二段重点\n第三段案例",
        "raw_segments": [
            {"start": 0.0, "end": 5.0, "text": "第一段内容"},
            {"start": 5.0, "end": 12.0, "text": "第二段重点"},
            {"start": 12.0, "end": 20.0, "text": "第三段案例"},
        ],
        "chapter_coverage": {
            "chapter_coverage_version": "1",
            "summary": {"evidence_count": 1, "chapter_count": 1},
            "segments": [
                {"segment_id": "S001", "char_start": 0, "char_end": 5},
                {"segment_id": "S002", "char_start": 6, "char_end": 11},
            ],
            "evidence": [
                {
                    "evidence_id": "E001",
                    "char_start": 6,
                    "char_end": 11,
                    "text": "第二段重点",
                    "source_segment_ids": ["S002"],
                }
            ],
            "chapters": [
                {
                    "chapter_id": "CH01",
                    "char_start": 0,
                    "char_end": 17,
                    "title": "核心内容",
                    "evidence_ids": ["E001"],
                }
            ],
        },
    }

    bound = bind_chapter_coverage_time_ranges(result)

    coverage = bound["chapter_coverage"]
    assert coverage["summary"]["time_bound"] is True
    assert coverage["summary"]["time_binding_source"] == "raw_segments"
    assert coverage["summary"]["time_bound_evidence_count"] == 1
    assert coverage["segments"][1]["start_seconds"] == 5.0
    assert coverage["segments"][1]["end_seconds"] == 12.0
    assert coverage["evidence"][0]["start_seconds"] == 5.0
    assert coverage["evidence"][0]["end_seconds"] == 12.0
    assert coverage["chapters"][0]["start_seconds"] == 0.0
    assert coverage["chapters"][0]["end_seconds"] == 20.0


def test_bind_chapter_coverage_keeps_result_when_timestamps_missing() -> None:
    result = {
        "transcript_text": "hello",
        "raw_segments": [{"text": "hello"}],
        "chapter_coverage": {
            "chapter_coverage_version": "1",
            "evidence": [{"evidence_id": "E001", "char_start": 0, "char_end": 5}],
        },
    }

    assert bind_chapter_coverage_time_ranges(result) == result


def test_bind_chapter_coverage_falls_back_to_display_segments() -> None:
    result = {
        "result_schema_version": "2",
        "transcript_text": "hello world",
        "raw_segments": [{"text": "hello world"}],
        "display_segments": [{"start": 3, "end": 6, "text": "hello world"}],
        "chapter_coverage": {
            "chapter_coverage_version": "1",
            "summary": {},
            "evidence": [{"evidence_id": "E001", "char_start": 0, "char_end": 11}],
        },
    }

    bound = bind_chapter_coverage_time_ranges(result)

    assert bound["chapter_coverage"]["summary"]["time_binding_source"] == "display_segments"
    assert bound["chapter_coverage"]["evidence"][0]["start_seconds"] == 3.0
    assert bound["chapter_coverage"]["evidence"][0]["end_seconds"] == 6.0
