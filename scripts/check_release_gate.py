#!/usr/bin/env python3
"""Release metadata gate for FluentFlow.

This is intentionally about release bookkeeping, not functional correctness.
It catches drift such as VERSION != package.json, malformed versions, or tags
that do not match the declared release version.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
    status = git_value("status", "--porcelain")
    if status is None:
        return None
    return bool(status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FluentFlow release metadata")
    parser.add_argument("--require-clean", action="store_true", help="fail if the git worktree is dirty")
    parser.add_argument("--require-tag", action="store_true", help="fail unless HEAD has tag v<VERSION>")
    parser.add_argument("--require-changelog-version", action="store_true", help="fail unless docs/changelog.md has v<VERSION>")
    args = parser.parse_args()

    failures: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = read_json(ROOT / "package.json")
    lock = read_json(ROOT / "package-lock.json")

    if not SEMVER_RE.match(version):
        failures.append(f"VERSION is not semver: {version!r}")
    if package.get("version") != version:
        failures.append(f"package.json version {package.get('version')!r} does not match VERSION {version!r}")
    if lock.get("version") != version:
        failures.append(f"package-lock.json version {lock.get('version')!r} does not match VERSION {version!r}")
    if lock.get("packages", {}).get("", {}).get("version") != version:
        failures.append("package-lock root package version does not match VERSION")

    expected_tag = f"v{version}"
    tags = set((git_value("tag", "--points-at", "HEAD") or "").splitlines())
    if args.require_tag and expected_tag not in tags:
        failures.append(f"HEAD is not tagged {expected_tag}")
    current_tag = git_value("describe", "--tags", "--exact-match")
    if current_tag and current_tag != expected_tag:
        failures.append(f"current tag {current_tag!r} does not match VERSION tag {expected_tag!r}")

    dirty = git_dirty()
    if args.require_clean and dirty:
        failures.append("git worktree is dirty")

    changelog = (ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")
    if "## Unreleased" not in changelog:
        failures.append("docs/changelog.md is missing ## Unreleased")
    if args.require_changelog_version and f"## v{version}" not in changelog:
        failures.append(f"docs/changelog.md has no ## v{version} section")

    if failures:
        print("Release gate failed:", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "ok",
        "version": version,
        "expected_tag": expected_tag,
        "dirty": dirty,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
