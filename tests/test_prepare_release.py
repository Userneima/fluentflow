from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.prepare_release import build_plan, sync_version_files, validate_version, write_checklist


def _write_minimal_release_root(root: Path) -> None:
    (root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"version": "0.1.0", "scripts": {}}) + "\n", encoding="utf-8")
    (root / "package-lock.json").write_text(
        json.dumps({"version": "0.1.0", "packages": {"": {"version": "0.1.0"}}}) + "\n",
        encoding="utf-8",
    )


def test_prepare_release_syncs_version_files(tmp_path: Path) -> None:
    _write_minimal_release_root(tmp_path)

    actions = sync_version_files(tmp_path, "0.2.0", apply=True)

    assert "set VERSION to 0.2.0" in actions
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == "0.2.0\n"
    assert json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))["version"] == "0.2.0"
    lock = json.loads((tmp_path / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == "0.2.0"
    assert lock["packages"][""]["version"] == "0.2.0"


def test_prepare_release_dry_run_does_not_write_files(tmp_path: Path) -> None:
    _write_minimal_release_root(tmp_path)

    actions = sync_version_files(tmp_path, "0.2.0", apply=False)

    assert actions
    assert (tmp_path / "VERSION").read_text(encoding="utf-8") == "0.1.0\n"


def test_prepare_release_writes_checklist(tmp_path: Path) -> None:
    _write_minimal_release_root(tmp_path)
    plan = build_plan(tmp_path, version="0.2.0", title="Beta release", release_date="2026-06-28")

    write_checklist(tmp_path, plan, apply=True)

    body = plan.checklist_path.read_text(encoding="utf-8")
    assert "FluentFlow Release Checklist v0.2.0" in body
    assert "## Before Tagging" in body
    assert "check_release_gate.py --require-changelog-version" in body


def test_prepare_release_rejects_non_semver() -> None:
    with pytest.raises(ValueError):
        validate_version("next")
