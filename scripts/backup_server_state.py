#!/usr/bin/env python3
"""Create a FluentFlow server-state backup archive.

The backup is intentionally data-first: databases and generated user artifacts
are included by default, while secret env files are excluded unless explicitly
requested.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _path_from_env(name: str, default: Path) -> Path:
    value = (os.environ.get(name) or "").strip()
    return Path(value).expanduser() if value else default


def _copy_sqlite(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(src) as source, sqlite3.connect(dst) as target:
        source.backup(target)
    return True


def _copy_tree(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return True


def _default_output_dir() -> Path:
    return _path_from_env("FLUENTFLOW_BACKUP_DIR", Path("/var/backups/fluentflow"))


def build_backup(*, output_dir: Path, env_file: Path | None, include_env: bool) -> Path:
    if env_file:
        _load_env_file(env_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"fluentflow-backup-{stamp}.tar.gz"

    paths = {
        "sources": _path_from_env("FLUENTFLOW_SOURCE_DIR", PROJECT_ROOT / "data" / "sources"),
        "artifacts": _path_from_env("FLUENTFLOW_ARTIFACT_DIR", PROJECT_ROOT / "data" / "artifacts"),
        "edited_transcripts": _path_from_env("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", PROJECT_ROOT / "data" / "edited_transcripts"),
        "transcript_edit_records": _path_from_env("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", PROJECT_ROOT / "data" / "transcript_edit_records"),
        "video_sources": _path_from_env("FLUENTFLOW_VIDEO_SOURCE_DIR", PROJECT_ROOT / "视频文件"),
    }
    db_paths = {
        "jobs.sqlite": _path_from_env("FLUENTFLOW_JOB_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_jobs.sqlite"),
        "accounts.sqlite": _path_from_env("FLUENTFLOW_ACCOUNT_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_accounts.sqlite"),
        "events.sqlite": _path_from_env("FLUENTFLOW_EVENT_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_events.sqlite"),
    }

    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "include_env": include_env,
        "paths": {name: str(path) for name, path in paths.items()},
        "databases": {name: str(path) for name, path in db_paths.items()},
        "included": [],
        "missing": [],
    }

    with tempfile.TemporaryDirectory(prefix="fluentflow_backup_") as tmp:
        staging = Path(tmp) / "fluentflow-backup"
        staging.mkdir()
        for name, path in paths.items():
            target = staging / "storage" / name
            if _copy_tree(path, target):
                manifest["included"].append({"kind": "storage", "name": name, "source": str(path)})
            else:
                manifest["missing"].append({"kind": "storage", "name": name, "source": str(path)})
        for name, path in db_paths.items():
            target = staging / "databases" / name
            if _copy_sqlite(path, target):
                manifest["included"].append({"kind": "database", "name": name, "source": str(path)})
            else:
                manifest["missing"].append({"kind": "database", "name": name, "source": str(path)})
        if include_env and env_file and env_file.is_file():
            env_target = staging / "config" / env_file.name
            env_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(env_file, env_target)
            manifest["included"].append({"kind": "config", "name": env_file.name, "source": str(env_file)})
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(staging, arcname="fluentflow-backup")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a FluentFlow data backup archive.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=Path("/etc/fluentflow/fluentflow.env"))
    parser.add_argument("--include-env", action="store_true", help="Include the env file with secrets. Off by default.")
    args = parser.parse_args()

    if args.env_file:
        _load_env_file(args.env_file)
    output_dir = args.output_dir or _default_output_dir()
    archive = build_backup(output_dir=output_dir, env_file=args.env_file, include_env=args.include_env)
    print(json.dumps({"ok": True, "archive": str(archive)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
