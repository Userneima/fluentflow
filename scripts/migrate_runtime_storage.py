#!/usr/bin/env python3
"""Copy legacy repo-local FluentFlow runtime data to the app data directory.

Dry-run is the default. Pass --apply to copy files. The script never deletes
legacy data; cleanup can happen manually after verification.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
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


def _copy_path(src: Path, dst: Path, *, apply: bool) -> dict[str, Any]:
    files = _iter_files(src)
    report = {
        "source": str(src),
        "target": str(dst),
        "exists": src.exists(),
        "file_count": len(files),
        "size_bytes": _path_size(src),
        "applied": apply,
        "copied": False,
    }
    if not src.exists() or not apply:
        return report
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name in SKIP_NAMES:
                continue
            target = dst / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_NAMES))
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    report["copied"] = True
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
    items = []
    for name, src, dst in build_migration_plan():
        report = _copy_path(src, dst, apply=apply)
        report["name"] = name
        items.append(report)
    return {
        "ok": True,
        "apply": apply,
        "target_root": str(app_data_root()),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate repo-local FluentFlow runtime data to the app data directory.")
    parser.add_argument("--apply", action="store_true", help="Copy files. Omit for dry-run.")
    args = parser.parse_args()
    print(json.dumps(migrate_runtime_storage(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
