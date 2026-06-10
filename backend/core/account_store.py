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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "fluentflow_accounts.sqlite"
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
