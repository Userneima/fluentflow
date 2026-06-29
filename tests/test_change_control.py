from __future__ import annotations

from scripts.check_change_control import evaluate


def test_product_changes_require_changelog_bookkeeping() -> None:
    result = evaluate(["frontend/src/routes/dashboard.jsx"])

    assert result.product_files == ["frontend/src/routes/dashboard.jsx"]
    assert result.changelog_required is True
    assert result.scopes == ["frontend"]


def test_changelog_satisfies_product_change_bookkeeping() -> None:
    result = evaluate(["backend/routers/jobs.py", "docs/changelog.md"])

    assert result.product_files == ["backend/routers/jobs.py"]
    assert result.changelog_changed is True
    assert result.changelog_required is False


def test_tests_only_changes_do_not_require_changelog() -> None:
    result = evaluate(["tests/test_frontend_routes.py"])

    assert result.product_files == []
    assert result.changelog_required is False
    assert result.scopes == ["tests"]


def test_private_runtime_paths_are_flagged() -> None:
    result = evaluate(["data/fluentflow_jobs.sqlite", ".env"])

    assert result.privacy_risk_files == [".env", "data/fluentflow_jobs.sqlite"]
