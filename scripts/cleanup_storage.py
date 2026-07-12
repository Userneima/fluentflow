#!/usr/bin/env python3
"""Clean expired FluentFlow local storage artifacts.

Default mode is dry-run. Pass --apply to delete files/directories.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.runtime_paths import (  # noqa: E402
    default_artifact_dir,
    default_edited_transcript_dir,
    default_source_dir,
    default_transcript_edit_records_dir,
    default_video_source_dir,
)


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _newest_mtime(path: Path) -> float:
    if path.is_file():
        return path.stat().st_mtime
    newest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            newest = max(newest, child.stat().st_mtime)
        except OSError:
            continue
    return newest


def _collect_expired(root: Path, days: float) -> list[Path]:
    if days < 0 or not root.exists():
        return []
    cutoff = time.time() - days * 86400
    expired: list[Path] = []
    for child in root.iterdir():
        try:
            if _newest_mtime(child) < cutoff:
                expired.append(child)
        except OSError:
            continue
    return expired


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _clean_bucket(name: str, root: Path, days: float, apply: bool) -> dict[str, Any]:
    expired = _collect_expired(root, days)
    removed: list[str] = []
    errors: list[dict[str, str]] = []
    for path in expired:
        if apply:
            try:
                _remove(path)
                removed.append(str(path))
            except OSError as exc:
                errors.append({"path": str(path), "error": str(exc)})
        else:
            removed.append(str(path))
    return {
        "name": name,
        "root": str(root),
        "retention_days": days,
        "apply": apply,
        "count": len(removed),
        "paths": removed,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean expired FluentFlow local storage artifacts.")
    parser.add_argument("--apply", action="store_true", help="Delete expired paths. Omit for dry-run.")
    parser.add_argument("--sources-days", type=float, default=float(os.environ.get("FLUENTFLOW_SOURCE_RETENTION_DAYS", "1")))
    parser.add_argument("--artifacts-days", type=float, default=float(os.environ.get("FLUENTFLOW_ARTIFACT_RETENTION_DAYS", "30")))
    parser.add_argument("--edited-days", type=float, default=float(os.environ.get("FLUENTFLOW_EDITED_TRANSCRIPT_RETENTION_DAYS", "90")))
    parser.add_argument("--edit-records-days", type=float, default=float(os.environ.get("FLUENTFLOW_EDIT_RECORDS_RETENTION_DAYS", "90")))
    parser.add_argument("--video-sources-days", type=float, default=float(os.environ.get("FLUENTFLOW_VIDEO_SOURCE_RETENTION_DAYS", "7")))
    args = parser.parse_args()

    buckets = [
        ("sources", _path_from_env("FLUENTFLOW_SOURCE_DIR", default_source_dir()), args.sources_days),
        ("artifacts", _path_from_env("FLUENTFLOW_ARTIFACT_DIR", default_artifact_dir()), args.artifacts_days),
        ("edited_transcripts", _path_from_env("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", default_edited_transcript_dir()), args.edited_days),
        ("transcript_edit_records", _path_from_env("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", default_transcript_edit_records_dir()), args.edit_records_days),
        ("video_sources", _path_from_env("FLUENTFLOW_VIDEO_SOURCE_DIR", default_video_source_dir()), args.video_sources_days),
    ]
    report = [_clean_bucket(name, root, days, args.apply) for name, root, days in buckets]
    print(json.dumps({"apply": args.apply, "buckets": report}, ensure_ascii=False, indent=2))
    return 1 if any(bucket["errors"] for bucket in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
