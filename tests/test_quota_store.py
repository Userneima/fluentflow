from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.quota_store import (
    InsufficientBalanceError,
    account_quota_summary,
    add_admin_adjustment,
    finalize_task_charge,
    get_balance,
    grant_starter_balance,
    list_transactions,
    release_reservation,
    reserve_units,
    task_reserved_units,
)


def test_starter_balance_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "accounts.sqlite"

    first = grant_starter_balance("user-1", units=100, db_path=db)
    second = grant_starter_balance("user-1", units=100, db_path=db)

    assert first is not None
    assert second is None
    assert get_balance("user-1", db_path=db) == 100
    assert [tx["transaction_type"] for tx in list_transactions("user-1", db_path=db)] == ["starter_grant"]


def test_reserve_blocks_when_balance_is_insufficient(tmp_path: Path) -> None:
    db = tmp_path / "accounts.sqlite"
    grant_starter_balance("user-1", units=10, db_path=db)

    with pytest.raises(InsufficientBalanceError) as exc:
        reserve_units("user-1", task_id="task-1", units=12, db_path=db)

    assert exc.value.balance_units == 10
    assert exc.value.required_units == 12
    assert get_balance("user-1", db_path=db) == 10


def test_finalize_releases_unused_reservation(tmp_path: Path) -> None:
    db = tmp_path / "accounts.sqlite"
    grant_starter_balance("user-1", units=100, db_path=db)
    reserve_units("user-1", task_id="task-1", units=30, db_path=db)

    final = finalize_task_charge("user-1", task_id="task-1", final_units=18, db_path=db)

    assert final["transaction_type"] == "finalize_charge"
    assert get_balance("user-1", db_path=db) == 82
    assert task_reserved_units("user-1", "task-1", db_path=db) == 0
    types = [tx["transaction_type"] for tx in list_transactions("user-1", task_id="task-1", db_path=db)]
    assert sorted(types) == ["finalize_charge", "release_reservation", "reserve"]


def test_release_refunds_failed_task_reservation(tmp_path: Path) -> None:
    db = tmp_path / "accounts.sqlite"
    grant_starter_balance("user-1", units=50, db_path=db)
    reserve_units("user-1", task_id="task-1", units=20, db_path=db)

    release = release_reservation("user-1", task_id="task-1", reason="failed", db_path=db)

    assert release is not None
    assert get_balance("user-1", db_path=db) == 50
    assert task_reserved_units("user-1", "task-1", db_path=db) == 0


def test_admin_adjustment_records_reason_and_reference(tmp_path: Path) -> None:
    db = tmp_path / "accounts.sqlite"

    tx = add_admin_adjustment(
        "user-1",
        units=25,
        reason="manual beta recharge",
        admin_account_id="admin-1",
        provider_reference="wx-test",
        db_path=db,
    )

    assert tx["balance_after"] == 25
    summary = account_quota_summary("user-1", db_path=db)
    assert summary["balance_units"] == 25
    assert summary["recent_transactions"][0]["provider_reference"] == "wx-test"
