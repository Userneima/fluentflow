from __future__ import annotations

from pathlib import Path

from backend.core import runtime_paths


def test_default_runtime_paths_use_system_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FLUENTFLOW_DATA_DIR", raising=False)
    monkeypatch.delenv("FLUENTFLOW_JOB_DB_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(runtime_paths.platform, "system", lambda: "Darwin")

    root = tmp_path / "Library" / "Application Support" / "FluentFlow"

    assert runtime_paths.app_data_root() == root
    assert runtime_paths.default_job_db_path() == root / "fluentflow_jobs.sqlite"
    assert runtime_paths.default_oss_upload_session_db_path() == root / "fluentflow_oss_upload_sessions.sqlite"
    assert runtime_paths.default_artifact_dir() == root / "artifacts"


def test_runtime_paths_use_data_dir_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_DATA_DIR", str(tmp_path / "fluentflow-data"))
    monkeypatch.delenv("FLUENTFLOW_SOURCE_DIR", raising=False)
    monkeypatch.delenv("FLUENTFLOW_JOB_DB_PATH", raising=False)

    assert runtime_paths.app_data_root() == tmp_path / "fluentflow-data"
    assert runtime_paths.default_source_dir() == tmp_path / "fluentflow-data" / "sources"
    assert runtime_paths.default_job_db_path() == tmp_path / "fluentflow-data" / "fluentflow_jobs.sqlite"
    assert runtime_paths.default_oss_upload_session_db_path() == tmp_path / "fluentflow-data" / "fluentflow_oss_upload_sessions.sqlite"


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


def test_migration_apply_preserves_existing_target_conflicts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_DATA_DIR", str(tmp_path / "target"))
    from scripts import migrate_runtime_storage

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "same.txt").write_text("same", encoding="utf-8")
    (legacy / "conflict.txt").write_text("legacy", encoding="utf-8")
    (legacy / "new.txt").write_text("new", encoding="utf-8")

    target_bucket = tmp_path / "target" / "bucket"
    target_bucket.mkdir(parents=True)
    (target_bucket / "same.txt").write_text("same", encoding="utf-8")
    (target_bucket / "conflict.txt").write_text("target", encoding="utf-8")

    monkeypatch.setattr(
        migrate_runtime_storage,
        "build_migration_plan",
        lambda: [("bucket", legacy, target_bucket)],
    )

    report = migrate_runtime_storage.migrate_runtime_storage(apply=True)

    assert report["apply"] is True
    assert report["legacy_retention_days"] == 14
    assert (tmp_path / "target" / "legacy_runtime_migration_manifest.json").is_file()
    assert (target_bucket / "same.txt").read_text(encoding="utf-8") == "same"
    assert (target_bucket / "conflict.txt").read_text(encoding="utf-8") == "target"
    assert (target_bucket / "new.txt").read_text(encoding="utf-8") == "new"
    conflict_root = Path(report["conflict_root"])
    assert (conflict_root / "bucket" / "conflict.txt").read_text(encoding="utf-8") == "legacy"
    item = report["items"][0]
    assert item["copied"] == 1
    assert item["skipped_same"] == 1
    assert item["conflicts_preserved"] == 1
