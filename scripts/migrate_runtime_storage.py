#!/usr/bin/env python3
"""Copy legacy repo-local FluentFlow runtime data to the app data directory.

Dry-run is the default. Pass --apply to copy files. The script never deletes
legacy data; cleanup can happen manually after verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.runtime_paths import (  # noqa: E402
    app_data_root,
    default_video_source_dir,
    legacy_backend_data_root,
    legacy_backend_video_source_dir,
    legacy_repo_data_root,
)


SKIP_NAMES = {".DS_Store", ".gitkeep"}
LEGACY_DATA_RETENTION_DAYS = 14
MIGRATION_MANIFEST_NAME = "legacy_runtime_migration_manifest.json"
LEGACY_REPO_DATA_ITEMS = [
    "fluentflow_config.json",
    "fluentflow_jobs.sqlite",
    "fluentflow_accounts.sqlite",
    "fluentflow_accounts.local.sqlite",
    "fluentflow_events.sqlite",
    "sources",
    "artifacts",
    "edited_transcripts",
    "transcript_edit_records",
    "codex_exports",
    "backups",
    "stt_eval",
]


def _iter_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    if path.is_file():
        return [path]
    return [item for item in path.rglob("*") if item.is_file() and item.name not in SKIP_NAMES]


def _path_size(path: Path) -> int:
    return sum(item.stat().st_size for item in _iter_files(path))


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same_file(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        return _file_digest(left) == _file_digest(right)
    except OSError:
        return False


def _copy_file_non_destructive(src: Path, dst: Path, *, conflict_dst: Path, apply: bool) -> str:
    if not dst.exists():
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return "copied"
    if dst.is_file() and _same_file(src, dst):
        return "skipped_same"
    if apply:
        conflict_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, conflict_dst)
    return "conflict_preserved"


def _copy_path(src: Path, dst: Path, *, conflict_root: Path, apply: bool) -> dict[str, Any]:
    files = _iter_files(src)
    report = {
        "source": str(src),
        "target": str(dst),
        "exists": src.exists(),
        "file_count": len(files),
        "size_bytes": _path_size(src),
        "applied": apply,
        "copied": 0,
        "skipped_same": 0,
        "conflicts_preserved": 0,
        "conflict_target": str(conflict_root),
    }
    if not src.exists() or not apply:
        if src.exists():
            for item in files:
                rel = item.relative_to(src) if src.is_dir() else Path(item.name)
                target = dst / rel if src.is_dir() else dst
                if not target.exists():
                    report["copied"] += 1
                elif target.is_file() and _same_file(item, target):
                    report["skipped_same"] += 1
                else:
                    report["conflicts_preserved"] += 1
        return report
    if src.is_file():
        status = _copy_file_non_destructive(src, dst, conflict_dst=conflict_root / dst.name, apply=apply)
        report["copied"] += int(status == "copied")
        report["skipped_same"] += int(status == "skipped_same")
        report["conflicts_preserved"] += int(status == "conflict_preserved")
    else:
        dst.mkdir(parents=True, exist_ok=True)
        for item in files:
            rel = item.relative_to(src)
            status = _copy_file_non_destructive(
                item,
                dst / rel,
                conflict_dst=conflict_root / rel,
                apply=apply,
            )
            report["copied"] += int(status == "copied")
            report["skipped_same"] += int(status == "skipped_same")
            report["conflicts_preserved"] += int(status == "conflict_preserved")
    return report


def build_migration_plan() -> list[tuple[str, Path, Path]]:
    target_root = app_data_root()
    repo_data_root = legacy_repo_data_root()
    plan = [
        (f"repo_data_{item}", repo_data_root / item, target_root / item)
        for item in LEGACY_REPO_DATA_ITEMS
    ]
    plan.extend(
        [
            ("backend_artifacts", legacy_backend_data_root() / "artifacts", target_root / "artifacts"),
            ("backend_edited_transcripts", legacy_backend_data_root() / "edited_transcripts", target_root / "edited_transcripts"),
            (
                "backend_transcript_edit_records",
                legacy_backend_data_root() / "transcript_edit_records",
                target_root / "transcript_edit_records",
            ),
            ("backend_sources", legacy_backend_data_root() / "sources", target_root / "sources"),
            ("backend_video_sources", legacy_backend_video_source_dir(), default_video_source_dir()),
        ]
    )
    return plan


def migrate_runtime_storage(*, apply: bool) -> dict[str, Any]:
    applied_at = datetime.now(timezone.utc).astimezone()
    cleanup_after = applied_at + timedelta(days=LEGACY_DATA_RETENTION_DAYS)
    stamp = applied_at.strftime("%Y%m%d-%H%M%S")
    conflict_base = app_data_root() / "legacy_migration" / stamp
    items = []
    for name, src, dst in build_migration_plan():
        report = _copy_path(src, dst, conflict_root=conflict_base / name, apply=apply)
        report["name"] = name
        items.append(report)
    result = {
        "ok": True,
        "apply": apply,
        "target_root": str(app_data_root()),
        "conflict_root": str(conflict_base),
        "legacy_cleanup_after": cleanup_after.date().isoformat(),
        "legacy_retention_days": LEGACY_DATA_RETENTION_DAYS,
        "manifest": str(app_data_root() / MIGRATION_MANIFEST_NAME),
        "items": items,
    }
    if apply:
        app_data_root().mkdir(parents=True, exist_ok=True)
        (app_data_root() / MIGRATION_MANIFEST_NAME).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate repo-local FluentFlow runtime data to the app data directory.")
    parser.add_argument("--apply", action="store_true", help="Copy files. Omit for dry-run.")
    args = parser.parse_args()
    print(json.dumps(migrate_runtime_storage(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
