from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_compare_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "compare_stt_quality.py"
    spec = importlib.util.spec_from_file_location("compare_stt_quality", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_summary(path: Path, *, run: dict, metrics: dict) -> Path:
    payload = {
        "reference": "reference.srt",
        "hypothesis": f"{path.stem}.srt",
        "run": run,
        "metrics": metrics,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_compare_stt_quality_sorts_by_quality_then_speed(tmp_path: Path) -> None:
    compare = _load_compare_module()
    local = _write_summary(
        tmp_path / "local.json",
        run={
            "candidate_name": "local-medium",
            "provider": "local",
            "model": "medium",
            "source_duration_seconds": 100,
            "stt_elapsed_seconds": 50,
            "estimated_cost_usd": 0,
        },
        metrics={
            "char_accuracy": 0.96,
            "cer": 0.04,
            "segment_exact_rate": 0.7,
            "glossary_recall": 1.0,
            "active_confusion_count": 0,
        },
    )
    cloud = _write_summary(
        tmp_path / "elevenlabs.json",
        run={
            "candidate_name": "elevenlabs-scribe",
            "provider": "elevenlabs_scribe",
            "model": "scribe",
            "source_duration_seconds": 100,
            "stt_elapsed_seconds": 20,
            "estimated_cost_usd": 0.25,
        },
        metrics={
            "char_accuracy": 0.94,
            "cer": 0.06,
            "segment_exact_rate": 0.8,
            "glossary_recall": 0.9,
            "active_confusion_count": 1,
        },
    )

    summary = compare.summarize([cloud, local])

    assert summary["candidate_count"] == 2
    assert summary["candidates"][0]["label"] == "local-medium"
    assert summary["best_quality_label"] == "local-medium"
    assert summary["fastest_label"] == "elevenlabs-scribe"
    assert summary["cheapest_label"] == "local-medium"
    assert summary["candidates"][1]["realtime_speed"] == 5
    assert summary["candidates"][1]["cost_per_audio_hour_usd"] == 9


def test_compare_stt_quality_markdown_keeps_cost_and_provider(tmp_path: Path) -> None:
    compare = _load_compare_module()
    output = tmp_path / "report.md"
    summary_path = _write_summary(
        tmp_path / "whisperx.json",
        run={
            "candidate_name": "whisperx-large-v3",
            "provider": "whisperx",
            "model": "large-v3",
            "stt_elapsed_seconds": 12,
        },
        metrics={"char_accuracy": 0.98, "cer": 0.02, "segment_exact_rate": 0.75},
    )

    compare.write_markdown(compare.summarize([summary_path]), output)
    text = output.read_text(encoding="utf-8")

    assert "whisperx-large-v3" in text
    assert "whisperx" in text
    assert "n/a" in text
