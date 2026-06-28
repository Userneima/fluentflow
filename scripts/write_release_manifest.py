#!/usr/bin/env python3
"""Write a release manifest for a FluentFlow build or deployment.

The manifest is an operational artifact, not source code. By default it is
written under `build/`, which is ignored by git. Deployment scripts can copy it
next to the running service so maintainers can later answer: which version,
which commit, which assets, and which schema versions were deployed?
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def git_value(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def git_dirty() -> bool | None:
    override = (os.environ.get("FLUENTFLOW_GIT_DIRTY") or "").strip().lower()
    if override in {"1", "true", "yes", "dirty"}:
        return True
    if override in {"0", "false", "no", "clean"}:
        return False
    status = git_value("status", "--porcelain")
    if status is None:
        return None
    return bool(status)


def frontend_assets() -> dict[str, list[str]]:
    assets_dir = ROOT / "frontend" / "dist" / "assets"
    if not assets_dir.exists():
        return {"js": [], "css": [], "other": []}
    grouped = {"js": [], "css": [], "other": []}
    for item in sorted(assets_dir.iterdir()):
        if not item.is_file():
            continue
        if item.suffix == ".js":
            grouped["js"].append(item.name)
        elif item.suffix == ".css":
            grouped["css"].append(item.name)
        else:
            grouped["other"].append(item.name)
    return grouped


def build_manifest(environment: str, backup_archive: str | None = None) -> dict[str, Any]:
    commit = (os.environ.get("FLUENTFLOW_GIT_COMMIT") or "").strip() or git_value("rev-parse", "HEAD")
    branch = (
        (os.environ.get("FLUENTFLOW_GIT_BRANCH") or "").strip()
        or git_value("rev-parse", "--abbrev-ref", "HEAD")
    )
    return {
        "app": "FluentFlow",
        "version": (os.environ.get("FLUENTFLOW_VERSION") or "").strip() or read_text(ROOT / "VERSION") or "0.0.0-dev",
        "commit": commit,
        "short_commit": commit[:7] if commit else None,
        "branch": branch,
        "dirty": git_dirty(),
        "environment": environment,
        "backup_archive": backup_archive,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schemas": {
            "result": "2",
            "event": "1.3",
            "agent_task_package": "1",
            "processing_plan": "1",
        },
        "frontend_assets": frontend_assets(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write FluentFlow release manifest")
    parser.add_argument("--environment", default=os.environ.get("FLUENTFLOW_ENV", "local"))
    parser.add_argument("--backup-archive")
    parser.add_argument("--output", default="build/release-manifest.json")
    args = parser.parse_args()

    manifest = build_manifest(args.environment, backup_archive=args.backup_archive)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
