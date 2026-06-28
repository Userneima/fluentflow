from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from backend.core.event_logger import log_event


def _load_report_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "report_stt_performance.py"
    spec = importlib.util.spec_from_file_location("report_stt_performance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_report_groups_stt_events_by_provider(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"

    log_event(
        task_id="local-task",
        event_name="stt_completed",
        source_duration_seconds=100,
        duration_seconds=50,
        success=True,
        metadata={
            "runtime_os": "Darwin",
            "runtime_machine": "arm64",
            "stt_model": "medium",
            "stt_speed": "balanced",
            "stt_language": "zh",
            "detected_language": "zh-CN",
            "stt_realtime_factor": 0.5,
        },
        db_path=db_path,
    )
    log_event(
        task_id="elevenlabs-task",
        event_name="stt_completed",
        source_duration_seconds=100,
        duration_seconds=20,
        success=True,
        metadata={
            "runtime_os": "Darwin",
            "runtime_machine": "arm64",
            "stt_provider": "elevenlabs_scribe",
            "stt_model": "elevenlabs-scribe",
            "stt_speed": "balanced",
            "stt_language": "auto",
            "detected_language": "en-US",
            "stt_realtime_factor": 0.2,
            "elevenlabs_audio_size_mb": 3.5,
            "elevenlabs_duration_seconds": 100.0,
        },
        db_path=db_path,
    )

    summary = report.summarize(report.load_stt_events(db_path))
    providers = {row["stt_provider"]: row for row in summary["providers"]}

    assert summary["event_count"] == 2
    assert providers["local"]["sample_count"] == 1
    assert providers["local"]["inferred_provider_count"] == 1
    assert providers["local"]["weighted_realtime_factor"] == 0.5
    assert providers["elevenlabs_scribe"]["sample_count"] == 1
    assert providers["elevenlabs_scribe"]["inferred_provider_count"] == 0
    assert providers["elevenlabs_scribe"]["weighted_realtime_factor"] == 0.2
    assert providers["elevenlabs_scribe"]["detected_languages"] == {"en-US": 1}
    assert providers["elevenlabs_scribe"]["avg_cloud_upload_audio_size_mb"] == 3.5
    assert providers["elevenlabs_scribe"]["avg_cloud_upload_duration_seconds"] == 100.0


def test_report_summarizes_cloud_upload_metrics(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"
    log_event(
        task_id="elevenlabs-task",
        event_name="stt_completed",
        source_duration_seconds=120,
        duration_seconds=24,
        success=True,
        metadata={
            "stt_provider": "elevenlabs_scribe",
            "stt_model": "elevenlabs-scribe",
            "detected_language": "zh-CN",
            "elevenlabs_audio_size_mb": 4.25,
            "elevenlabs_duration_seconds": 120.0,
        },
        db_path=db_path,
    )

    summary = report.summarize(report.load_stt_events(db_path))
    providers = {row["stt_provider"]: row for row in summary["providers"]}

    assert providers["elevenlabs_scribe"]["avg_cloud_upload_audio_size_mb"] == 4.25
    assert providers["elevenlabs_scribe"]["avg_cloud_upload_duration_seconds"] == 120.0


def test_report_json_summary_is_serializable(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"
    log_event(
        task_id="task",
        event_name="stt_completed",
        source_duration_seconds=30,
        duration_seconds=15,
        success=True,
        metadata={"stt_provider": "local", "stt_model": "medium"},
        db_path=db_path,
    )

    json.dumps(report.summarize(report.load_stt_events(db_path)), ensure_ascii=False)


def test_report_markdown_includes_cloud_upload_and_detected_language(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"
    output = tmp_path / "report.md"
    log_event(
        task_id="elevenlabs-task",
        event_name="stt_completed",
        source_duration_seconds=60,
        duration_seconds=12,
        success=True,
        metadata={
            "stt_provider": "elevenlabs_scribe",
            "stt_model": "elevenlabs-scribe",
            "stt_speed": "balanced",
            "stt_language": "auto",
            "detected_language": "en-US",
            "elevenlabs_audio_size_mb": 2.25,
            "elevenlabs_duration_seconds": 60.0,
        },
        db_path=db_path,
    )

    summary = report.summarize(report.load_stt_events(db_path))
    report.write_markdown(summary, output)
    text = output.read_text(encoding="utf-8")

    assert "Detected languages" in text
    assert "Avg cloud upload MB" in text
    assert "en-US:1" in text
    assert "2.25" in text


def test_report_same_source_cross_provider_comparison(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"
    fingerprint = {"sha256": "abc123"}
    log_event(
        task_id="local-task",
        event_name="stt_completed",
        source_filename="sample.m4a",
        source_duration_seconds=100,
        duration_seconds=50,
        success=True,
        metadata={
            "source_fingerprint": fingerprint,
            "stt_provider": "local",
            "stt_model": "medium",
            "stt_realtime_factor": 0.5,
        },
        db_path=db_path,
    )
    log_event(
        task_id="azure-task",
        event_name="stt_completed",
        source_filename="sample.m4a",
        source_duration_seconds=100,
        duration_seconds=20,
        success=True,
        metadata={
            "source_fingerprint": fingerprint,
            "stt_provider": "azure_batch",
            "stt_model": "azure-batch-transcription",
            "stt_realtime_factor": 0.2,
        },
        db_path=db_path,
    )

    summary = report.summarize(report.load_stt_events(db_path))
    comparison = summary["same_source_comparisons"][0]

    assert summary["same_source_comparison_count"] == 1
    assert comparison["source_filename"] == "sample.m4a"
    assert comparison["fastest_provider"] == "azure_batch"
    assert comparison["slowest_provider"] == "local"
    assert comparison["fastest_vs_slowest_speedup"] == 2.5


def test_report_markdown_includes_same_source_comparison(tmp_path: Path) -> None:
    report = _load_report_module()
    db_path = tmp_path / "events.sqlite"
    output = tmp_path / "report.md"
    fingerprint = {"sha256": "same-source"}
    for provider, elapsed in (("local", 40), ("azure_batch", 10)):
        log_event(
            task_id=f"{provider}-task",
            event_name="stt_completed",
            source_filename="same.m4a",
            source_duration_seconds=80,
            duration_seconds=elapsed,
            success=True,
            metadata={
                "source_fingerprint": fingerprint,
                "stt_provider": provider,
                "stt_realtime_factor": elapsed / 80,
            },
            db_path=db_path,
        )

    report.write_markdown(report.summarize(report.load_stt_events(db_path)), output)
    text = output.read_text(encoding="utf-8")

    assert "Same-Source Comparisons" in text
    assert "same.m4a" in text
    assert "azure_batch" in text
    assert "4.0" in text
