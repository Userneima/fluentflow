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
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = "docs/changelog.md"
AGENTS = "AGENTS.md"
AGENTS_MAX_LINES = 90

PRIVATE_PATH_PREFIXES = (
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
    "docs/ui_design_system.md",
    "docs/workflow_design_system.md",
}

NON_PRODUCT_PREFIXES = (
    "tests/",
    "docs/private/",
)

UI_REVIEW_PREFIXES = (
    "frontend/src/",
)

WORKFLOW_REVIEW_PATHS = (
    "frontend/src/routes/",
    "frontend/src/app/",
    "frontend/src/components/",
    "backend/routers/jobs.py",
    "backend/core/error_diagnostics.py",
    "backend/core/job_store.py",
    "backend/core/server_helpers.py",
)

WORK_UNIT_FILE_WARNING_THRESHOLD = 8
WORK_UNIT_SCOPE_WARNING_THRESHOLD = 3


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
    work_unit_warnings: list[str]
    doc_governance_warnings: list[str]
    doc_governance_failures: list[str]


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


def is_private_runtime_path(path: str) -> bool:
    if path.startswith(".env") and path != ".env.example":
        return True
    return has_prefix(path, PRIVATE_PATH_PREFIXES)


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


def agent_doc_references() -> list[str]:
    target = ROOT / AGENTS
    if not target.exists():
        return []
    text = target.read_text(encoding="utf-8")
    refs: list[str] = []
    for ref in re.findall(r"`([^`]+)`", text):
        if ref.endswith("/"):
            continue
        if ref.startswith(("docs/", "deploy/")) or ref in {".env.example"}:
            refs.append(ref)
    return sorted(set(refs))


def evaluate_doc_governance(paths: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    failures: list[str] = []

    agents_path = ROOT / AGENTS
    if agents_path.exists():
        line_count = len(agents_path.read_text(encoding="utf-8").splitlines())
        if line_count > AGENTS_MAX_LINES:
            failures.append(f"{AGENTS} has {line_count} lines; keep it at or below {AGENTS_MAX_LINES} or move details into focused docs")

    missing_refs = [ref for ref in agent_doc_references() if not (ROOT / ref).exists()]
    if missing_refs:
        failures.append(f"{AGENTS} references missing files: {', '.join(missing_refs)}")

    if any(has_prefix(path, UI_REVIEW_PREFIXES) for path in paths) and "docs/ui_design_system.md" not in paths:
        warnings.append("frontend UI files changed; review docs/ui_design_system.md and update it only if a reusable UI rule changed")

    if any(path == item or path.startswith(item) for path in paths for item in WORKFLOW_REVIEW_PATHS) and "docs/workflow_design_system.md" not in paths:
        warnings.append("workflow-facing files changed; review docs/workflow_design_system.md and update it only if task/page responsibility rules changed")

    return warnings, failures


def evaluate_work_unit_size(paths: list[str], scopes: list[str]) -> list[str]:
    warnings: list[str] = []
    if len(paths) > WORK_UNIT_FILE_WARNING_THRESHOLD:
        warnings.append(
            f"large work unit touches {len(paths)} files; confirm it is one coherent stage or split it before continuing"
        )

    if len(scopes) > WORK_UNIT_SCOPE_WARNING_THRESHOLD:
        warnings.append(
            f"work unit spans {len(scopes)} scopes ({', '.join(scopes)}); use docs/agent_task_brief.md to stage the work if these changes do not share one outcome"
        )

    scope_set = set(scopes)
    if {"backend", "frontend", "docs", "tests"}.issubset(scope_set):
        warnings.append(
            "backend, frontend, docs, and tests changed together; verify this is one workflow-sized stage with one validation path"
        )

    return warnings


def evaluate(paths: list[str]) -> ChangeControlResult:
    privacy_risk_files = sorted(path for path in paths if is_private_runtime_path(path))
    generated_files = sorted(path for path in paths if has_prefix(path, GENERATED_PATH_PREFIXES))
    product_files = sorted(path for path in paths if is_product_file(path))
    changelog_changed = CHANGELOG in paths
    version_files_changed = [path for path in paths if path in {"VERSION", "package.json", "package-lock.json"}]
    doc_warnings, doc_failures = evaluate_doc_governance(paths)
    scopes = sorted({scope_for(path) for path in paths})
    work_unit_warnings = evaluate_work_unit_size(paths, scopes)
    return ChangeControlResult(
        changed_files=paths,
        privacy_risk_files=privacy_risk_files,
        generated_files=generated_files,
        product_files=product_files,
        changelog_changed=changelog_changed,
        changelog_required=bool(product_files) and not changelog_changed,
        version_files_changed=version_files_changed,
        scopes=scopes,
        work_unit_warnings=work_unit_warnings,
        doc_governance_warnings=doc_warnings,
        doc_governance_failures=doc_failures,
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
    warnings.extend(result.work_unit_warnings)
    warnings.extend(result.doc_governance_warnings)
    failures.extend(result.doc_governance_failures)

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
        "work_unit_warnings": result.work_unit_warnings,
        "doc_governance_warnings": result.doc_governance_warnings,
        "doc_governance_failures": result.doc_governance_failures,
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
