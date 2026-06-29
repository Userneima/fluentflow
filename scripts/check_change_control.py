#!/usr/bin/env python3
"""Daily change-control checks for FluentFlow.

This script is intentionally different from the release gate:

- change-control checks help agents keep normal commits reviewable;
- release checks prove that a clean commit/tag is ready to ship.

The script should stay conservative. It can identify risky paths and missing
bookkeeping, but it should not pretend to understand product intent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = "docs/changelog.md"

PRIVATE_PATH_PREFIXES = (
    ".env",
    "backend/data/",
    "data/",
    "docs/private/",
    "exports/",
    "logs/",
    "reports/",
)

GENERATED_PATH_PREFIXES = (
    "frontend/dist/",
    "build/",
    "node_modules/",
    "venv/",
)

PRODUCT_CODE_PREFIXES = (
    "backend/",
    "frontend/src/",
    "frontend/public/",
    "deploy/",
    "launchers/",
    "scripts/",
)

PRODUCT_DOCS = {
    "AGENTS.md",
    "VERSION",
    "package.json",
    "package-lock.json",
    "docs/release_process.md",
    "docs/versioning_strategy.md",
    "docs/result_schema.md",
    "docs/event_logging.md",
    "docs/operations_runbook.md",
}

NON_PRODUCT_PREFIXES = (
    "tests/",
    "docs/private/",
)


@dataclass(frozen=True)
class ChangeControlResult:
    changed_files: list[str]
    privacy_risk_files: list[str]
    generated_files: list[str]
    product_files: list[str]
    changelog_changed: bool
    changelog_required: bool
    version_files_changed: list[str]
    scopes: list[str]


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "git command failed").strip())
    return result.stdout.strip()


def changed_files(*, staged: bool = False, base: str | None = None) -> list[str]:
    if base:
        output = run_git(["diff", "--name-only", f"{base}...HEAD"])
    elif staged:
        output = run_git(["diff", "--cached", "--name-only"])
    else:
        output = run_git(["status", "--porcelain"])
        files: list[str] = []
        for line in output.splitlines():
            if not line:
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            files.append(path)
        return sorted(set(files))
    return sorted({line.strip() for line in output.splitlines() if line.strip()})


def has_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def is_product_file(path: str) -> bool:
    if path == CHANGELOG:
        return False
    if has_prefix(path, NON_PRODUCT_PREFIXES):
        return False
    if path.startswith("tests/"):
        return False
    return has_prefix(path, PRODUCT_CODE_PREFIXES) or path in PRODUCT_DOCS


def scope_for(path: str) -> str:
    if path.startswith("backend/"):
        return "backend"
    if path.startswith("frontend/"):
        return "frontend"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("docs/") or path == "AGENTS.md":
        return "docs"
    if path.startswith("deploy/") or path.startswith("launchers/"):
        return "ops"
    if path.startswith("scripts/") or path in {"package.json", "package-lock.json", "VERSION"}:
        return "tooling"
    return "other"


def evaluate(paths: list[str]) -> ChangeControlResult:
    privacy_risk_files = sorted(path for path in paths if has_prefix(path, PRIVATE_PATH_PREFIXES))
    generated_files = sorted(path for path in paths if has_prefix(path, GENERATED_PATH_PREFIXES))
    product_files = sorted(path for path in paths if is_product_file(path))
    changelog_changed = CHANGELOG in paths
    version_files_changed = [path for path in paths if path in {"VERSION", "package.json", "package-lock.json"}]
    return ChangeControlResult(
        changed_files=paths,
        privacy_risk_files=privacy_risk_files,
        generated_files=generated_files,
        product_files=product_files,
        changelog_changed=changelog_changed,
        changelog_required=bool(product_files) and not changelog_changed,
        version_files_changed=version_files_changed,
        scopes=sorted({scope_for(path) for path in paths}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FluentFlow daily change-control hygiene")
    parser.add_argument("--staged", action="store_true", help="check staged files instead of the full worktree")
    parser.add_argument("--base", help="check committed branch changes against a base ref, for example origin/main")
    parser.add_argument("--require-changelog", action="store_true", help="fail when product files changed but changelog did not")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    try:
        result = evaluate(changed_files(staged=args.staged, base=args.base))
    except Exception as exc:
        print(f"change-control check failed: {exc}", file=sys.stderr)
        return 1

    failures: list[str] = []
    warnings: list[str] = []
    if result.privacy_risk_files:
        failures.append("private/runtime paths are included: " + ", ".join(result.privacy_risk_files))
    if result.generated_files:
        warnings.append("generated/dependency paths changed: " + ", ".join(result.generated_files))
    if result.changelog_required:
        message = f"product-impacting files changed without {CHANGELOG}"
        if args.require_changelog:
            failures.append(message)
        else:
            warnings.append(message)
    if "VERSION" in result.version_files_changed and len(set(result.version_files_changed)) != 3:
        warnings.append("version files changed partially; VERSION, package.json, and package-lock.json should move together")

    payload = {
        "status": "failed" if failures else "ok",
        "changed_file_count": len(result.changed_files),
        "scopes": result.scopes,
        "product_file_count": len(result.product_files),
        "changelog_changed": result.changelog_changed,
        "changelog_required": result.changelog_required,
        "privacy_risk_files": result.privacy_risk_files,
        "generated_files": result.generated_files,
        "version_files_changed": result.version_files_changed,
        "warnings": warnings,
        "failures": failures,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Change-control status: {payload['status']}")
        print(f"- changed files: {payload['changed_file_count']}")
        print(f"- scopes: {', '.join(result.scopes) if result.scopes else 'none'}")
        print(f"- product files: {payload['product_file_count']}")
        print(f"- changelog changed: {payload['changelog_changed']}")
        for item in warnings:
            print(f"warning: {item}", file=sys.stderr)
        for item in failures:
            print(f"failure: {item}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
