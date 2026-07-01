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
    result = evaluate(["data/fluentflow_jobs.sqlite", ".env", ".env.local"])

    assert result.privacy_risk_files == [".env", ".env.local", "data/fluentflow_jobs.sqlite"]


def test_env_example_is_allowed_as_public_template() -> None:
    result = evaluate([".env.example"])

    assert result.privacy_risk_files == []


def test_frontend_route_change_prompts_long_term_doc_review() -> None:
    result = evaluate(["frontend/src/routes/editor.jsx", "docs/changelog.md"])

    assert any("docs/ui_design_system.md" in item for item in result.doc_governance_warnings)
    assert any("docs/workflow_design_system.md" in item for item in result.doc_governance_warnings)


def test_large_work_unit_prompts_staged_plan_warning() -> None:
    result = evaluate(
        [
            "backend/main.py",
            "backend/routers/jobs.py",
            "backend/core/job_store.py",
            "frontend/src/routes/editor.jsx",
            "frontend/src/routes/history.jsx",
            "frontend/src/app/App.jsx",
            "docs/changelog.md",
            "docs/agent_task_brief.md",
            "tests/test_change_control.py",
        ]
    )

    assert any("large work unit" in item for item in result.work_unit_warnings)


def test_cross_scope_work_unit_prompts_split_review() -> None:
    result = evaluate(
        [
            "backend/routers/jobs.py",
            "frontend/src/routes/editor.jsx",
            "docs/changelog.md",
            "tests/test_change_control.py",
        ]
    )

    assert any("work unit spans" in item for item in result.work_unit_warnings)
    assert any("backend, frontend, docs, and tests" in item for item in result.work_unit_warnings)
