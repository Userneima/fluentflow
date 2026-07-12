"""SQLite-backed API key persistence for Agent and MCP access."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from backend.core.account_store import _db_path, _now_iso, ensure_account_db


API_KEY_PREFIX = "ff_"


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _ensure_api_key_db(db_path: Path | str | None = None) -> None:
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_scope TEXT NOT NULL,
                user_id TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_api_keys_owner_scope ON api_keys(owner_scope);
            CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
            """
        )


def _row_to_public_key(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "key_prefix": row["key_prefix"],
        "owner_scope": row["owner_scope"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "revoked_at": row["revoked_at"],
    }


def create_api_key(
    *,
    owner_scope: str,
    name: str,
    user_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    scope = (owner_scope or "").strip()
    if not scope:
        raise ValueError("owner_scope is required")
    label = (name or "").strip()[:80] or "Agent API Key"
    _ensure_api_key_db(db_path)
    raw_key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    now = _now_iso()
    key_id = uuid.uuid4().hex
    public_prefix = f"{raw_key[:10]}..."
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO api_keys (id, key_hash, key_prefix, name, owner_scope, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (key_id, _hash_key(raw_key), public_prefix, label, scope, user_id, now),
        )
    created = get_api_key(key_id, owner_scope=scope, db_path=db_path)
    if not created:
        raise RuntimeError("created API key is missing")
    created["key"] = raw_key
    return created


def get_api_key(
    key_id: str,
    *,
    owner_scope: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    if not key_id:
        return None
    _ensure_api_key_db(db_path)
    params: list[Any] = [key_id]
    clause = "id = ?"
    if owner_scope:
        clause = f"{clause} AND owner_scope = ?"
        params.append(owner_scope)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT * FROM api_keys WHERE {clause}", params).fetchone()
    return _row_to_public_key(row)


def list_api_keys(owner_scope: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    scope = (owner_scope or "").strip()
    if not scope:
        return []
    _ensure_api_key_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM api_keys
            WHERE owner_scope = ?
            ORDER BY created_at DESC
            """,
            (scope,),
        ).fetchall()
    return [item for row in rows if (item := _row_to_public_key(row))]


def revoke_api_key(
    key_id: str,
    *,
    owner_scope: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    scope = (owner_scope or "").strip()
    if not key_id or not scope:
        return None
    _ensure_api_key_db(db_path)
    now = _now_iso()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            UPDATE api_keys
            SET revoked_at = COALESCE(revoked_at, ?)
            WHERE id = ? AND owner_scope = ?
            """,
            (now, key_id, scope),
        )
    return get_api_key(key_id, owner_scope=scope, db_path=db_path)


def authenticate_api_key(api_key: str | None, db_path: Path | str | None = None) -> dict[str, Any] | None:
    text = (api_key or "").strip()
    if not text.startswith(API_KEY_PREFIX):
        return None
    _ensure_api_key_db(db_path)
    key_hash = _hash_key(text)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM api_keys
            WHERE key_hash = ? AND revoked_at IS NULL
            """,
            (key_hash,),
        ).fetchone()
        if row is None or not hmac.compare_digest(row["key_hash"], key_hash):
            return None
        now = _now_iso()
        conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, row["id"]))
        public = _row_to_public_key(row)
    if not public:
        return None
    public["user_id"] = row["user_id"]
    public["last_used_at"] = now
    return public
