#!/usr/bin/env python3
"""Prepare FluentFlow release metadata.

This script handles the mechanical release preparation work:

- validate a semver release version
- keep VERSION, package.json, and package-lock.json in sync
- write a human checklist under build/

It intentionally does not decide which changelog entries are "done"; that is
product judgment, not a scripting task.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class ReleasePlan:
    version: str
    title: str
    release_date: str
    checklist_path: Path
    branch_name: str


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
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


def validate_version(version: str) -> None:
    if not SEMVER_RE.match(version):
        raise ValueError(f"release version must be semver, got {version!r}")


def current_version(root: Path) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def build_plan(root: Path, *, version: str, title: str, release_date: str | None = None) -> ReleasePlan:
    validate_version(version)
    stamp = release_date or date.today().isoformat()
    return ReleasePlan(
        version=version,
        title=title.strip() or "Release",
        release_date=stamp,
        checklist_path=root / "build" / f"release-checklist-v{version}.md",
        branch_name=f"release/v{version}",
    )


def sync_version_files(root: Path, version: str, *, apply: bool) -> list[str]:
    actions: list[str] = []
    version_file = root / "VERSION"
    package_file = root / "package.json"
    lock_file = root / "package-lock.json"

    if current_version(root) != version:
        actions.append(f"set VERSION to {version}")
        if apply:
            version_file.write_text(version + "\n", encoding="utf-8")

    package = read_json(package_file)
    if package.get("version") != version:
        actions.append(f"set package.json version to {version}")
        if apply:
            package["version"] = version
            write_json(package_file, package)

    lock = read_json(lock_file)
    lock_changed = False
    if lock.get("version") != version:
        actions.append(f"set package-lock.json version to {version}")
        lock["version"] = version
        lock_changed = True
    root_package = lock.setdefault("packages", {}).setdefault("", {})
    if root_package.get("version") != version:
        actions.append(f"set package-lock root package version to {version}")
        root_package["version"] = version
        lock_changed = True
    if apply and lock_changed:
        write_json(lock_file, lock)

    return actions


def checklist_body(root: Path, plan: ReleasePlan) -> str:
    commit = git_value(root, "rev-parse", "HEAD") or "unknown"
    branch = git_value(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    expected_tag = f"v{plan.version}"
    return f"""# FluentFlow Release Checklist {expected_tag}

Release title: {plan.title}
Release date: {plan.release_date}
Source branch: {branch}
Source commit: {commit}
Expected release branch: {plan.branch_name}
Expected tag: {expected_tag}

## Before Tagging

- [ ] Move shipped changelog entries from `## Unreleased` to `## {expected_tag}｜{plan.release_date}｜{plan.title}`.
- [ ] Leave unfinished work under `## Unreleased` or move it to planning docs.
- [ ] Confirm data/schema compatibility notes are explicit.
- [ ] Confirm rollback notes are explicit for any irreversible migration.

## Required Validation

```bash
python3 scripts/check_release_gate.py --require-changelog-version
npm run lint:frontend
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_versioning.py tests/test_frontend_routes.py::test_client_routes_fall_back_to_frontend_index -q
git diff --check
```

## Tagging

```bash
git switch -c {plan.branch_name}
git add VERSION package.json package-lock.json docs/changelog.md docs/release_process.md
git commit -m "Prepare release {expected_tag}"
git tag {expected_tag}
```

## Deployment

```bash
bash deploy/deploy_server.sh
```

After deployment, keep the generated release manifest from `/var/lib/fluentflow/releases/`.
"""


def write_checklist(root: Path, plan: ReleasePlan, *, apply: bool) -> str:
    action = f"write release checklist to {plan.checklist_path.relative_to(root)}"
    if apply:
        plan.checklist_path.parent.mkdir(parents=True, exist_ok=True)
        plan.checklist_path.write_text(checklist_body(root, plan), encoding="utf-8")
    return action


def create_release_branch(root: Path, plan: ReleasePlan, *, apply: bool) -> str:
    action = f"create local branch {plan.branch_name}"
    if apply:
        status = git_value(root, "status", "--porcelain")
        if status:
            raise RuntimeError("refusing to create release branch while git worktree is dirty")
        result = subprocess.run(["git", "switch", "-c", plan.branch_name], cwd=root, check=False, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"failed to create release branch {plan.branch_name}")
    return action


def run_release_gate(root: Path) -> None:
    result = subprocess.run([sys.executable, "scripts/check_release_gate.py"], cwd=root, check=False)
    if result.returncode != 0:
        raise RuntimeError("release gate failed after preparing release")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare FluentFlow release metadata")
    parser.add_argument("--version", help="release version, for example 0.2.0")
    parser.add_argument("--title", default="Release", help="short release title used in the checklist")
    parser.add_argument("--date", dest="release_date", help="release date in YYYY-MM-DD format")
    parser.add_argument("--apply", action="store_true", help="write files; default is dry-run")
    parser.add_argument("--create-branch", action="store_true", help="also create release/v<VERSION>; requires clean worktree")
    parser.add_argument("--skip-checklist", action="store_true", help="do not write build/release-checklist-v<VERSION>.md")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    root = args.root.resolve()
    version = (args.version or current_version(root)).strip()
    plan = build_plan(root, version=version, title=args.title, release_date=args.release_date)

    actions: list[str] = []
    if args.create_branch:
        actions.append(create_release_branch(root, plan, apply=args.apply))
    actions.extend(sync_version_files(root, version, apply=args.apply))
    if not args.skip_checklist:
        actions.append(write_checklist(root, plan, apply=args.apply))
    if args.apply:
        run_release_gate(root)

    print(json.dumps({
        "status": "applied" if args.apply else "dry-run",
        "version": plan.version,
        "release_branch": plan.branch_name,
        "checklist": str(plan.checklist_path),
        "actions": actions,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"prepare release failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
