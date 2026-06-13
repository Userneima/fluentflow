"""SQLite-backed quota balance ledger for FluentFlow accounts."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "fluentflow_accounts.sqlite"
CURRENT_RATE_CARD_VERSION = "quota-v0"


class InsufficientBalanceError(ValueError):
    """Raised when an account cannot reserve the requested processing units."""

    def __init__(self, *, balance_units: int, required_units: int) -> None:
        self.balance_units = int(balance_units)
        self.required_units = int(required_units)
        super().__init__(
            f"Insufficient balance: required {self.required_units}, available {self.balance_units}"
        )


def _db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    override = (os.environ.get("FLUENTFLOW_ACCOUNT_DB_PATH") or "").strip()
    return Path(override).expanduser() if override else DEFAULT_DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _clean_units(value: Any) -> int:
    try:
        return max(0, int(round(float(value or 0))))
    except (TypeError, ValueError):
        return 0


def ensure_quota_db(db_path: Path | str | None = None) -> None:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS balance_transactions (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                task_id TEXT,
                purchase_order_id TEXT,
                transaction_type TEXT NOT NULL,
                unit_delta INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                rate_card_version TEXT NOT NULL,
                reason TEXT,
                provider_reference TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_balance_transactions_account_created
                ON balance_transactions(account_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_balance_transactions_task
                ON balance_transactions(task_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_balance_starter_once
                ON balance_transactions(account_id, transaction_type)
                WHERE transaction_type = 'starter_grant';
            """
        )


def _balance_for_account(conn: sqlite3.Connection, account_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(unit_delta), 0) FROM balance_transactions WHERE account_id = ?",
        (account_id,),
    ).fetchone()
    return int(row[0] if row else 0)


def _task_has_final_charge(conn: sqlite3.Connection, account_id: str, task_id: str) -> bool:
    row = conn.execute(
        """
        SELECT id FROM balance_transactions
        WHERE account_id = ? AND task_id = ? AND transaction_type = 'finalize_charge'
        LIMIT 1
        """,
        (account_id, task_id),
    ).fetchone()
    return row is not None


def _task_reserved_units(conn: sqlite3.Connection, account_id: str, task_id: str) -> int:
    if _task_has_final_charge(conn, account_id, task_id):
        return 0
    row = conn.execute(
        """
        SELECT COALESCE(SUM(unit_delta), 0) FROM balance_transactions
        WHERE account_id = ? AND task_id = ?
          AND transaction_type IN ('reserve', 'release_reservation')
        """,
        (account_id, task_id),
    ).fetchone()
    return max(0, -int(row[0] if row else 0))


def get_balance(account_id: str, db_path: Path | str | None = None) -> int:
    if not account_id:
        return 0
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        return _balance_for_account(conn, account_id)


def _insert_transaction(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    transaction_type: str,
    unit_delta: int,
    balance_after: int,
    task_id: str | None = None,
    purchase_order_id: str | None = None,
    reason: str | None = None,
    provider_reference: str | None = None,
    metadata: dict[str, Any] | None = None,
    rate_card_version: str = CURRENT_RATE_CARD_VERSION,
) -> dict[str, Any]:
    tx_id = uuid.uuid4().hex
    created_at = _now_iso()
    conn.execute(
        """
        INSERT INTO balance_transactions (
            id, account_id, task_id, purchase_order_id, transaction_type,
            unit_delta, balance_after, rate_card_version, reason,
            provider_reference, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id,
            account_id,
            task_id,
            purchase_order_id,
            transaction_type,
            int(unit_delta),
            int(balance_after),
            rate_card_version,
            reason,
            provider_reference,
            _json_dumps(metadata),
            created_at,
        ),
    )
    return {
        "id": tx_id,
        "account_id": account_id,
        "task_id": task_id,
        "purchase_order_id": purchase_order_id,
        "transaction_type": transaction_type,
        "unit_delta": int(unit_delta),
        "balance_after": int(balance_after),
        "rate_card_version": rate_card_version,
        "reason": reason,
        "provider_reference": provider_reference,
        "metadata": metadata,
        "created_at": created_at,
    }


def grant_starter_balance(
    account_id: str,
    *,
    units: int,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    units = _clean_units(units)
    if not account_id or units <= 0:
        return None
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT id FROM balance_transactions
            WHERE account_id = ? AND transaction_type = 'starter_grant'
            """,
            (account_id,),
        ).fetchone()
        if existing:
            return None
        balance_after = _balance_for_account(conn, account_id) + units
        return _insert_transaction(
            conn,
            account_id=account_id,
            transaction_type="starter_grant",
            unit_delta=units,
            balance_after=balance_after,
            reason="New account starter balance",
        )


def add_admin_adjustment(
    account_id: str,
    *,
    units: int,
    reason: str,
    admin_account_id: str | None = None,
    provider_reference: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    units = int(round(float(units or 0)))
    if not account_id:
        raise ValueError("account_id is required")
    if units == 0:
        raise ValueError("units must be non-zero")
    reason_text = (reason or "").strip()
    if not reason_text:
        raise ValueError("reason is required")
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        balance_after = _balance_for_account(conn, account_id) + units
        merged_metadata = {
            **(metadata or {}),
            "admin_account_id": admin_account_id,
        }
        return _insert_transaction(
            conn,
            account_id=account_id,
            transaction_type="admin_adjustment",
            unit_delta=units,
            balance_after=balance_after,
            reason=reason_text,
            provider_reference=provider_reference,
            metadata=merged_metadata,
        )


def reserve_units(
    account_id: str,
    *,
    task_id: str,
    units: int,
    reason: str = "Task processing reservation",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    units = _clean_units(units)
    if not account_id:
        raise ValueError("account_id is required")
    if not task_id:
        raise ValueError("task_id is required")
    if units <= 0:
        raise ValueError("units must be positive")
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        already = conn.execute(
            """
            SELECT id FROM balance_transactions
            WHERE account_id = ? AND task_id = ? AND transaction_type = 'reserve'
            """,
            (account_id, task_id),
        ).fetchone()
        if already:
            return {
                "account_id": account_id,
                "task_id": task_id,
                "outstanding_reserved_units": _task_reserved_units(conn, account_id, task_id),
                "balance_units": _balance_for_account(conn, account_id),
            }
        balance = _balance_for_account(conn, account_id)
        if balance < units:
            raise InsufficientBalanceError(balance_units=balance, required_units=units)
        balance_after = balance - units
        return _insert_transaction(
            conn,
            account_id=account_id,
            task_id=task_id,
            transaction_type="reserve",
            unit_delta=-units,
            balance_after=balance_after,
            reason=reason,
            metadata=metadata,
        )


def task_reserved_units(
    account_id: str,
    task_id: str,
    db_path: Path | str | None = None,
) -> int:
    if not account_id or not task_id:
        return 0
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        return _task_reserved_units(conn, account_id, task_id)


def release_reservation(
    account_id: str,
    *,
    task_id: str,
    units: int | None = None,
    reason: str = "Release task reservation",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    if not account_id or not task_id:
        return None
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        reserved = _task_reserved_units(conn, account_id, task_id)
        release_units = reserved if units is None else min(_clean_units(units), reserved)
        if release_units <= 0:
            return None
        balance_after = _balance_for_account(conn, account_id) + release_units
        return _insert_transaction(
            conn,
            account_id=account_id,
            task_id=task_id,
            transaction_type="release_reservation",
            unit_delta=release_units,
            balance_after=balance_after,
            reason=reason,
            metadata=metadata,
        )


def finalize_task_charge(
    account_id: str,
    *,
    task_id: str,
    final_units: int,
    reason: str = "Finalize task charge",
    metadata: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    final_units = _clean_units(final_units)
    if not account_id:
        raise ValueError("account_id is required")
    if not task_id:
        raise ValueError("task_id is required")
    ensure_quota_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            """
            SELECT id FROM balance_transactions
            WHERE account_id = ? AND task_id = ? AND transaction_type = 'finalize_charge'
            """,
            (account_id, task_id),
        ).fetchone()
        if existing:
            return {
                "account_id": account_id,
                "task_id": task_id,
                "outstanding_reserved_units": _task_reserved_units(conn, account_id, task_id),
                "balance_units": _balance_for_account(conn, account_id),
            }
        reserved = _task_reserved_units(conn, account_id, task_id)
        release_units = max(reserved - final_units, 0)
        balance = _balance_for_account(conn, account_id)
        if release_units > 0:
            balance += release_units
            _insert_transaction(
                conn,
                account_id=account_id,
                task_id=task_id,
                transaction_type="release_reservation",
                unit_delta=release_units,
                balance_after=balance,
                reason="Release unused task reservation",
                metadata=metadata,
            )
        finalize_metadata = {
            **(metadata or {}),
            "reserved_units": reserved,
            "final_units": final_units,
            "capped_loss_units": max(final_units - reserved, 0),
        }
        return _insert_transaction(
            conn,
            account_id=account_id,
            task_id=task_id,
            transaction_type="finalize_charge",
            unit_delta=0,
            balance_after=balance,
            reason=reason,
            metadata=finalize_metadata,
        )


def get_task_quota_summary(
    account_id: str,
    task_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    transactions = list_transactions(account_id, task_id=task_id, db_path=db_path)
    reserved = 0
    final_units = None
    for tx in transactions:
        if tx["transaction_type"] == "reserve":
            reserved += abs(int(tx["unit_delta"]))
        elif tx["transaction_type"] == "finalize_charge":
            metadata = tx.get("metadata") or {}
            final_units = metadata.get("final_units")
    return {
        "account_id": account_id,
        "task_id": task_id,
        "reserved_units": reserved,
        "outstanding_reserved_units": task_reserved_units(account_id, task_id, db_path=db_path),
        "final_units": final_units,
        "transactions": transactions,
    }


def list_transactions(
    account_id: str,
    *,
    task_id: str | None = None,
    limit: int = 100,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    if not account_id:
        return []
    ensure_quota_db(db_path)
    safe_limit = max(1, min(int(limit or 100), 500))
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if task_id:
            rows = conn.execute(
                """
                SELECT * FROM balance_transactions
                WHERE account_id = ? AND task_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (account_id, task_id, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM balance_transactions
                WHERE account_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (account_id, safe_limit),
            ).fetchall()
    return [_row_to_transaction(row) for row in rows]


def account_quota_summary(account_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    return {
        "balance_units": get_balance(account_id, db_path=db_path),
        "rate_card_version": CURRENT_RATE_CARD_VERSION,
        "recent_transactions": list_transactions(account_id, limit=20, db_path=db_path),
    }


def _row_to_transaction(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "task_id": row["task_id"],
        "purchase_order_id": row["purchase_order_id"],
        "transaction_type": row["transaction_type"],
        "unit_delta": int(row["unit_delta"]),
        "balance_after": int(row["balance_after"]),
        "rate_card_version": row["rate_card_version"],
        "reason": row["reason"],
        "provider_reference": row["provider_reference"],
        "metadata": _json_loads(row["metadata_json"]) or {},
        "created_at": row["created_at"],
    }
