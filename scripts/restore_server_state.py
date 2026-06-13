#!/usr/bin/env python3
"""Restore a FluentFlow server-state backup archive.

This script is deliberately explicit: dry-run is the default, and --apply is
required before any existing server data is overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
import tempfile
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


def _copy_path(src: Path, dst: Path, *, apply: bool) -> dict[str, Any]:
    report = {"source": str(src), "target": str(dst), "applied": apply, "exists": src.exists()}
    if not src.exists() or not apply:
        return report
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return report


def _safe_extract(archive: tarfile.TarFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.getmembers():
        member_path = (target_dir / member.name).resolve()
        if target_root not in (member_path, *member_path.parents):
            raise RuntimeError(f"Unsafe backup archive member: {member.name}")
    archive.extractall(target_dir)


def restore_backup(*, archive_path: Path, env_file: Path | None, apply: bool) -> dict[str, Any]:
    if env_file:
        _load_env_file(env_file)
    targets = {
        "storage": {
            "sources": _path_from_env("FLUENTFLOW_SOURCE_DIR", PROJECT_ROOT / "data" / "sources"),
            "artifacts": _path_from_env("FLUENTFLOW_ARTIFACT_DIR", PROJECT_ROOT / "data" / "artifacts"),
            "edited_transcripts": _path_from_env("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", PROJECT_ROOT / "data" / "edited_transcripts"),
            "transcript_edit_records": _path_from_env("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", PROJECT_ROOT / "data" / "transcript_edit_records"),
            "video_sources": _path_from_env("FLUENTFLOW_VIDEO_SOURCE_DIR", PROJECT_ROOT / "视频文件"),
        },
        "databases": {
            "jobs.sqlite": _path_from_env("FLUENTFLOW_JOB_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_jobs.sqlite"),
            "accounts.sqlite": _path_from_env("FLUENTFLOW_ACCOUNT_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_accounts.sqlite"),
            "events.sqlite": _path_from_env("FLUENTFLOW_EVENT_DB_PATH", PROJECT_ROOT / "data" / "fluentflow_events.sqlite"),
        },
    }
    with tempfile.TemporaryDirectory(prefix="fluentflow_restore_") as tmp:
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract(archive, Path(tmp))
        root = Path(tmp) / "fluentflow-backup"
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        restored: list[dict[str, Any]] = []
        for name, target in targets["storage"].items():
            restored.append(_copy_path(root / "storage" / name, target, apply=apply))
        for name, target in targets["databases"].items():
            restored.append(_copy_path(root / "databases" / name, target, apply=apply))
    return {"ok": True, "apply": apply, "manifest": manifest, "restored": restored}


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a FluentFlow data backup archive.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path("/etc/fluentflow/fluentflow.env"))
    parser.add_argument("--apply", action="store_true", help="Actually overwrite target paths. Omit for dry-run.")
    args = parser.parse_args()
    if not args.archive.is_file():
        raise SystemExit(f"Backup archive not found: {args.archive}")
    report = restore_backup(archive_path=args.archive, env_file=args.env_file, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
