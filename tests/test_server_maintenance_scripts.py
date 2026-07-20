from __future__ import annotations

import os
import sqlite3
import tarfile
from pathlib import Path

from scripts.backup_server_state import build_backup, prune_backups
from scripts.restore_server_state import restore_backup


def test_backup_and_restore_server_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "sources" / "task-1"
    source_dir.mkdir(parents=True)
    (source_dir / "source.mp4").write_bytes(b"video")
    jobs_db = tmp_path / "state" / "jobs.sqlite"
    jobs_db.parent.mkdir(parents=True)
    with sqlite3.connect(jobs_db) as conn:
        conn.execute("CREATE TABLE jobs (task_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO jobs VALUES ('task-1')")

    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "missing-artifacts"))
    monkeypatch.setenv("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", str(tmp_path / "missing-edited"))
    monkeypatch.setenv("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", str(tmp_path / "missing-edit-records"))
    monkeypatch.setenv("FLUENTFLOW_VIDEO_SOURCE_DIR", str(tmp_path / "missing-videos"))
    monkeypatch.setenv("FLUENTFLOW_JOB_DB_PATH", str(jobs_db))
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "missing-accounts.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_EVENT_DB_PATH", str(tmp_path / "missing-events.sqlite"))

    archive = build_backup(output_dir=tmp_path / "backups", env_file=None, include_env=False)

    with tarfile.open(archive, "r:gz") as handle:
        names = handle.getnames()
    assert "fluentflow-backup/storage/sources/task-1/source.mp4" in names
    assert "fluentflow-backup/databases/jobs.sqlite" in names

    restored_root = tmp_path / "restored"
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(restored_root / "sources"))
    monkeypatch.setenv("FLUENTFLOW_JOB_DB_PATH", str(restored_root / "jobs.sqlite"))
    report = restore_backup(archive_path=archive, env_file=None, apply=True)

    assert report["ok"] is True
    assert (restored_root / "sources" / "task-1" / "source.mp4").read_bytes() == b"video"
    with sqlite3.connect(restored_root / "jobs.sqlite") as conn:
        row = conn.execute("SELECT task_id FROM jobs").fetchone()
    assert row == ("task-1",)


def test_prune_backups_keeps_newest_archives(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    archives = []
    for index in range(3):
        archive = backup_dir / f"fluentflow-backup-20260720T1430{index}0Z.tar.gz"
        archive.write_bytes(b"backup")
        os.utime(archive, (1_700_000_000 + index, 1_700_000_000 + index))
        archives.append(archive)

    removed = prune_backups(output_dir=backup_dir, retain_count=2)

    assert removed == [archives[0]]
    assert not archives[0].exists()
    assert archives[1].exists()
    assert archives[2].exists()
