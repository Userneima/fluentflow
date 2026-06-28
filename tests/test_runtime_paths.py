from __future__ import annotations

from pathlib import Path

from backend.core import runtime_paths


def test_runtime_paths_use_data_dir_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_DATA_DIR", str(tmp_path / "fluentflow-data"))
    monkeypatch.delenv("FLUENTFLOW_SOURCE_DIR", raising=False)
    monkeypatch.delenv("FLUENTFLOW_JOB_DB_PATH", raising=False)

    assert runtime_paths.app_data_root() == tmp_path / "fluentflow-data"
    assert runtime_paths.default_source_dir() == tmp_path / "fluentflow-data" / "sources"
    assert runtime_paths.default_job_db_path() == tmp_path / "fluentflow-data" / "fluentflow_jobs.sqlite"


def test_specific_runtime_path_env_override_wins(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_DATA_DIR", str(tmp_path / "root"))
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "custom-artifacts"))

    assert runtime_paths.default_artifact_dir() == tmp_path / "custom-artifacts"
    assert runtime_paths.default_source_dir() == tmp_path / "root" / "sources"


def test_migration_script_dry_run_reports_legacy_locations(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_DATA_DIR", str(tmp_path / "target"))
    from scripts.migrate_runtime_storage import migrate_runtime_storage

    report = migrate_runtime_storage(apply=False)

    assert report["apply"] is False
    assert report["target_root"] == str(tmp_path / "target")
    names = {item["name"] for item in report["items"]}
    assert {"repo_data_fluentflow_jobs.sqlite", "repo_data_artifacts", "backend_video_sources"} <= names
