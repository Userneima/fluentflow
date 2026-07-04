"""SQLite-backed account and session persistence for FluentFlow."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.core.runtime_paths import default_account_db_path

DEFAULT_DB_PATH = default_account_db_path()
PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000


def _db_path(db_path: Path | str | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    override = (os.environ.get("FLUENTFLOW_ACCOUNT_DB_PATH") or "").strip()
    return Path(override).expanduser() if override else DEFAULT_DB_PATH


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def ensure_account_db(db_path: Path | str | None = None) -> None:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

            CREATE TABLE IF NOT EXISTS feishu_connections (
                user_id TEXT PRIMARY KEY,
                owner_scope TEXT NOT NULL,
                feishu_open_id TEXT,
                feishu_union_id TEXT,
                feishu_user_id TEXT,
                tenant_key TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                access_token_expires_at TEXT,
                refresh_token_expires_at TEXT,
                scopes TEXT,
                connected_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_feishu_connections_owner_scope ON feishu_connections(owner_scope);
            CREATE INDEX IF NOT EXISTS idx_feishu_connections_open_id ON feishu_connections(feishu_open_id);

            CREATE TABLE IF NOT EXISTS feishu_oauth_states (
                state_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                owner_scope TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                next_url TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_feishu_oauth_states_user_id ON feishu_oauth_states(user_id);
            CREATE INDEX IF NOT EXISTS idx_feishu_oauth_states_expires_at ON feishu_oauth_states(expires_at);
            """
        )


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"{PASSWORD_ALGORITHM}${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    if algorithm != PASSWORD_ALGORITHM or iterations <= 0:
        return False
    try:
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            iterations,
        ).hex()
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


def _row_to_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def _row_to_auth_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    user = _row_to_user(row)
    if user is not None and row is not None:
        user["password_hash"] = row["password_hash"]
    return user


def count_users(db_path: Path | str | None = None) -> int:
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return int(row[0] if row else 0)


def get_user_by_email(email: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE email = ?", (normalize_email(email),)).fetchone()
    return _row_to_auth_user(row)


def get_user_by_id(user_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    if not user_id:
        return None
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    user = _row_to_auth_user(row)
    if user:
        user.pop("password_hash", None)
    return user


def list_users(limit: int = 100, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    ensure_account_db(db_path)
    safe_limit = max(1, min(int(limit or 100), 500))
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    result = []
    for row in rows:
        user = _row_to_user(row)
        if user:
            result.append(user)
    return result


def create_user(
    email: str,
    password: str,
    *,
    role: str = "user",
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    normalized = normalize_email(email)
    if not normalized:
        raise ValueError("email is required")
    if not password:
        raise ValueError("password is required")
    ensure_account_db(db_path)
    user_id = uuid.uuid4().hex
    now = _now_iso()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, password_hash, role, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
            """,
            (user_id, normalized, hash_password(password), role or "user", now, now),
        )
    user = get_user_by_email(normalized, db_path=db_path)
    if not user:
        raise RuntimeError("created user is missing")
    user.pop("password_hash", None)
    return user


def authenticate_user(email: str, password: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    user = get_user_by_email(email, db_path=db_path)
    if not user or user.get("status") != "active":
        return None
    if not verify_password(password, str(user.get("password_hash") or "")):
        return None
    now = _now_iso()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now, now, user["id"]))
    user.pop("password_hash", None)
    user["last_login_at"] = now
    user["updated_at"] = now
    return user


def _session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    user_id: str,
    *,
    days: int = 30,
    user_agent: str | None = None,
    ip_address: str | None = None,
    db_path: Path | str | None = None,
) -> str:
    ensure_account_db(db_path)
    token = secrets.token_urlsafe(48)
    now = _now()
    expires = now + timedelta(days=max(int(days or 30), 1))
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO sessions (token_hash, user_id, created_at, expires_at, user_agent, ip_address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _session_token_hash(token),
                user_id,
                now.isoformat(timespec="seconds"),
                expires.isoformat(timespec="seconds"),
                (user_agent or "")[:240],
                (ip_address or "")[:128],
            ),
        )
    return token


def get_user_by_session_token(token: str | None, db_path: Path | str | None = None) -> dict[str, Any] | None:
    token_text = (token or "").strip()
    if not token_text:
        return None
    ensure_account_db(db_path)
    token_hash = _session_token_hash(token_text)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        session = conn.execute("SELECT expires_at FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
        if session is not None:
            expires = _parse_iso(session["expires_at"])
            if expires is None or expires < _now():
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                return None
    user = _row_to_user(row)
    if user and user.get("status") != "active":
        return None
    return user


def revoke_session(token: str | None, db_path: Path | str | None = None) -> None:
    token_text = (token or "").strip()
    if not token_text:
        return
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_session_token_hash(token_text),))


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def create_feishu_oauth_state(
    user_id: str,
    *,
    redirect_uri: str,
    owner_scope: str | None = None,
    next_url: str | None = None,
    ttl_seconds: int = 600,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    if not redirect_uri:
        raise ValueError("redirect_uri is required")
    ensure_account_db(db_path)
    state = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(seconds=max(int(ttl_seconds or 600), 60))
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO feishu_oauth_states
                (state_hash, user_id, owner_scope, redirect_uri, next_url, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _state_hash(state),
                user_id,
                owner_scope or f"user:{user_id}",
                redirect_uri,
                (next_url or "")[:500] or None,
                now.isoformat(timespec="seconds"),
                expires.isoformat(timespec="seconds"),
            ),
        )
    return {
        "state": state,
        "user_id": user_id,
        "owner_scope": owner_scope or f"user:{user_id}",
        "redirect_uri": redirect_uri,
        "next_url": next_url,
        "expires_at": expires.isoformat(timespec="seconds"),
    }


def consume_feishu_oauth_state(
    state: str,
    *,
    user_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    if not state or not user_id:
        return None
    ensure_account_db(db_path)
    state_digest = _state_hash(state)
    now = _now()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM feishu_oauth_states WHERE state_hash = ?",
            (state_digest,),
        ).fetchone()
        if row is None:
            return None
        expires = _parse_iso(row["expires_at"])
        if row["user_id"] != user_id or row["consumed_at"] or expires is None or expires < now:
            return None
        consumed_at = now.isoformat(timespec="seconds")
        conn.execute(
            "UPDATE feishu_oauth_states SET consumed_at = ? WHERE state_hash = ?",
            (consumed_at, state_digest),
        )
    return {
        "user_id": row["user_id"],
        "owner_scope": row["owner_scope"],
        "redirect_uri": row["redirect_uri"],
        "next_url": row["next_url"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "consumed_at": consumed_at,
    }


def _connection_public_payload(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "connected": False,
            "provider": "feishu",
        }
    revoked_at = row["revoked_at"] if isinstance(row, sqlite3.Row) else row.get("revoked_at")
    connected = not bool(revoked_at)
    return {
        "connected": connected,
        "provider": "feishu",
        "owner_scope": row["owner_scope"] if isinstance(row, sqlite3.Row) else row.get("owner_scope"),
        "feishu_open_id": row["feishu_open_id"] if isinstance(row, sqlite3.Row) else row.get("feishu_open_id"),
        "feishu_union_id": row["feishu_union_id"] if isinstance(row, sqlite3.Row) else row.get("feishu_union_id"),
        "feishu_user_id": row["feishu_user_id"] if isinstance(row, sqlite3.Row) else row.get("feishu_user_id"),
        "tenant_key": row["tenant_key"] if isinstance(row, sqlite3.Row) else row.get("tenant_key"),
        "access_token_expires_at": row["access_token_expires_at"] if isinstance(row, sqlite3.Row) else row.get("access_token_expires_at"),
        "refresh_token_expires_at": row["refresh_token_expires_at"] if isinstance(row, sqlite3.Row) else row.get("refresh_token_expires_at"),
        "scopes": row["scopes"] if isinstance(row, sqlite3.Row) else row.get("scopes"),
        "connected_at": row["connected_at"] if isinstance(row, sqlite3.Row) else row.get("connected_at"),
        "updated_at": row["updated_at"] if isinstance(row, sqlite3.Row) else row.get("updated_at"),
        "revoked_at": revoked_at,
    }


def save_feishu_connection(
    user_id: str,
    *,
    access_token: str,
    refresh_token: str | None = None,
    expires_in: int | None = None,
    refresh_expires_in: int | None = None,
    feishu_open_id: str | None = None,
    feishu_union_id: str | None = None,
    feishu_user_id: str | None = None,
    tenant_key: str | None = None,
    scopes: str | None = None,
    owner_scope: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    token = (access_token or "").strip()
    if not token:
        raise ValueError("access_token is required")
    ensure_account_db(db_path)
    now = _now()
    now_text = now.isoformat(timespec="seconds")
    access_expires_at = (
        now + timedelta(seconds=max(int(expires_in or 0), 0))
    ).isoformat(timespec="seconds") if expires_in else None
    refresh_expires_at = (
        now + timedelta(seconds=max(int(refresh_expires_in or 0), 0))
    ).isoformat(timespec="seconds") if refresh_expires_in else None
    with sqlite3.connect(_db_path(db_path)) as conn:
        existing = conn.execute(
            "SELECT connected_at FROM feishu_connections WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        connected_at = existing[0] if existing else now_text
        conn.execute(
            """
            INSERT INTO feishu_connections (
                user_id, owner_scope, feishu_open_id, feishu_union_id, feishu_user_id,
                tenant_key, access_token, refresh_token, access_token_expires_at,
                refresh_token_expires_at, scopes, connected_at, updated_at, revoked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                owner_scope = excluded.owner_scope,
                feishu_open_id = excluded.feishu_open_id,
                feishu_union_id = excluded.feishu_union_id,
                feishu_user_id = excluded.feishu_user_id,
                tenant_key = excluded.tenant_key,
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, feishu_connections.refresh_token),
                access_token_expires_at = excluded.access_token_expires_at,
                refresh_token_expires_at = COALESCE(excluded.refresh_token_expires_at, feishu_connections.refresh_token_expires_at),
                scopes = excluded.scopes,
                updated_at = excluded.updated_at,
                revoked_at = NULL
            """,
            (
                user_id,
                owner_scope or f"user:{user_id}",
                (feishu_open_id or "").strip() or None,
                (feishu_union_id or "").strip() or None,
                (feishu_user_id or "").strip() or None,
                (tenant_key or "").strip() or None,
                token,
                (refresh_token or "").strip() or None,
                access_expires_at,
                refresh_expires_at,
                (scopes or "").strip() or None,
                connected_at,
                now_text,
            ),
        )
    return get_feishu_connection_status(user_id, db_path=db_path)


def get_feishu_connection(user_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    if not user_id:
        return None
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM feishu_connections WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_feishu_connection_status(user_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    connection = get_feishu_connection(user_id, db_path=db_path)
    return _connection_public_payload(connection)


def disconnect_feishu_connection(user_id: str, db_path: Path | str | None = None) -> dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    ensure_account_db(db_path)
    now = _now_iso()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.execute(
            """
            UPDATE feishu_connections
            SET access_token = '', refresh_token = '', revoked_at = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (now, now, user_id),
        )
    return get_feishu_connection_status(user_id, db_path=db_path)
