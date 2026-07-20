"""Account-bound credentials for FluentFlow desktop sync clients.

Desktop credentials deliberately do not share the Agent API key store.  They
are restricted to the future desktop-sync API surface and are stored hashed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from backend.core.account_store import _db_path, _now, _now_iso, ensure_account_db


DESKTOP_CREDENTIAL_PREFIX = "ffd_"
DESKTOP_CREDENTIAL_DAYS = 180
SUPPORTED_PLATFORMS = frozenset({"macos", "windows"})


def _hash_credential(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def _ensure_desktop_device_db(db_path: Path | str | None = None) -> None:
    ensure_account_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS desktop_devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_desktop_devices_user_id ON desktop_devices(user_id);
            CREATE INDEX IF NOT EXISTS idx_desktop_devices_revoked_at ON desktop_devices(revoked_at);

            CREATE TABLE IF NOT EXISTS desktop_device_credentials (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                credential_hash TEXT NOT NULL UNIQUE,
                credential_prefix TEXT NOT NULL,
                scopes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(device_id) REFERENCES desktop_devices(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_desktop_device_credentials_device_id
                ON desktop_device_credentials(device_id);
            CREATE INDEX IF NOT EXISTS idx_desktop_device_credentials_expires_at
                ON desktop_device_credentials(expires_at);
            """
        )


def _normalize_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized not in SUPPORTED_PLATFORMS:
        raise ValueError("platform must be macos or windows")
    return normalized


def _normalize_display_name(display_name: str, platform: str) -> str:
    label = " ".join((display_name or "").split())
    if not label:
        return "Mac" if platform == "macos" else "Windows PC"
    if len(label) > 80:
        raise ValueError("display_name must be 80 characters or fewer")
    if any(char in label for char in ("/", "\\", "\r", "\n")):
        raise ValueError("display_name must not contain a file path")
    return label


def _row_to_public_device(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "platform": row["platform"],
        "created_at": row["created_at"],
        "last_seen_at": row["last_seen_at"],
        "revoked_at": row["revoked_at"],
        "credential": {
            "id": row["credential_id"],
            "prefix": row["credential_prefix"],
            "scopes": (row["credential_scopes"] or "sync").split(),
            "created_at": row["credential_created_at"],
            "expires_at": row["credential_expires_at"],
            "last_used_at": row["credential_last_used_at"],
            "revoked_at": row["credential_revoked_at"],
        }
        if row["credential_id"]
        else None,
    }


def _select_device_sql() -> str:
    return """
        SELECT
            d.id, d.user_id, d.display_name, d.platform, d.created_at, d.last_seen_at, d.revoked_at,
            c.id AS credential_id, c.credential_prefix, c.scopes AS credential_scopes,
            c.created_at AS credential_created_at, c.expires_at AS credential_expires_at,
            c.last_used_at AS credential_last_used_at, c.revoked_at AS credential_revoked_at
        FROM desktop_devices d
        LEFT JOIN desktop_device_credentials c ON c.device_id = d.id
        WHERE d.id = ?
        ORDER BY c.created_at DESC
        LIMIT 1
    """


def register_desktop_device(
    *,
    user_id: str,
    platform: str,
    display_name: str = "",
    credential_days: int = DESKTOP_CREDENTIAL_DAYS,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    account_id = (user_id or "").strip()
    if not account_id:
        raise ValueError("user_id is required")
    if credential_days < 1:
        raise ValueError("credential_days must be at least one day")
    normalized_platform = _normalize_platform(platform)
    label = _normalize_display_name(display_name, normalized_platform)
    _ensure_desktop_device_db(db_path)

    device_id = uuid.uuid4().hex
    credential_id = uuid.uuid4().hex
    raw_credential = f"{DESKTOP_CREDENTIAL_PREFIX}{secrets.token_urlsafe(32)}"
    now = _now()
    now_text = now.isoformat(timespec="seconds")
    expires_at = (now + timedelta(days=credential_days)).isoformat(timespec="seconds")
    public_prefix = f"{raw_credential[:11]}..."

    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT id FROM users WHERE id = ? AND status = 'active'", (account_id,)).fetchone()
        if user is None:
            raise ValueError("active account is required")
        conn.execute(
            """
            INSERT INTO desktop_devices (id, user_id, display_name, platform, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, account_id, label, normalized_platform, now_text),
        )
        conn.execute(
            """
            INSERT INTO desktop_device_credentials
                (id, device_id, credential_hash, credential_prefix, scopes, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (credential_id, device_id, _hash_credential(raw_credential), public_prefix, "sync", now_text, expires_at),
        )
        row = conn.execute(_select_device_sql(), (device_id,)).fetchone()

    device = _row_to_public_device(row)
    if not device:
        raise RuntimeError("created desktop device is missing")
    device["credential"]["value"] = raw_credential
    return device


def claim_desktop_device_credential_hash(
    *,
    user_id: str,
    platform: str,
    display_name: str,
    credential_hash: str,
    credential_prefix: str,
    credential_days: int = DESKTOP_CREDENTIAL_DAYS,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Bind a locally generated credential hash to the signed-in account.

    The desktop keeps the raw credential. The browser pairing URL carries only
    this hash, so the cloud never needs to return a usable credential.
    """
    account_id = (user_id or "").strip()
    digest = (credential_hash or "").strip().lower()
    prefix = (credential_prefix or "").strip()
    if not account_id:
        raise ValueError("user_id is required")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("credential_hash must be a SHA-256 hex digest")
    if not prefix.startswith(DESKTOP_CREDENTIAL_PREFIX) or len(prefix) > 24:
        raise ValueError("credential_prefix is invalid")
    if credential_days < 1:
        raise ValueError("credential_days must be at least one day")
    normalized_platform = _normalize_platform(platform)
    label = _normalize_display_name(display_name, normalized_platform)
    _ensure_desktop_device_db(db_path)

    now = _now()
    now_text = now.isoformat(timespec="seconds")
    expires_at = (now + timedelta(days=credential_days)).isoformat(timespec="seconds")
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT id FROM users WHERE id = ? AND status = 'active'", (account_id,)).fetchone()
        if user is None:
            raise ValueError("active account is required")
        existing = conn.execute(
            """
            SELECT d.*,
                c.id AS credential_id, c.credential_prefix, c.scopes AS credential_scopes,
                c.created_at AS credential_created_at, c.expires_at AS credential_expires_at,
                c.last_used_at AS credential_last_used_at, c.revoked_at AS credential_revoked_at
            FROM desktop_device_credentials c
            JOIN desktop_devices d ON d.id = c.device_id
            WHERE c.credential_hash = ?
            """,
            (digest,),
        ).fetchone()
        if existing is not None:
            if existing["user_id"] != account_id:
                raise ValueError("desktop credential has already been claimed")
            device = _row_to_public_device(existing)
            if not device or device.get("revoked_at") or (device.get("credential") or {}).get("revoked_at"):
                raise ValueError("desktop credential is no longer active")
            return device

        device_id = uuid.uuid4().hex
        credential_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO desktop_devices (id, user_id, display_name, platform, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (device_id, account_id, label, normalized_platform, now_text),
        )
        conn.execute(
            """
            INSERT INTO desktop_device_credentials
                (id, device_id, credential_hash, credential_prefix, scopes, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (credential_id, device_id, digest, prefix, "sync", now_text, expires_at),
        )
        row = conn.execute(_select_device_sql(), (device_id,)).fetchone()
    device = _row_to_public_device(row)
    if not device:
        raise RuntimeError("claimed desktop device is missing")
    return device


def list_desktop_devices(user_id: str, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    account_id = (user_id or "").strip()
    if not account_id:
        return []
    _ensure_desktop_device_db(db_path)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                d.id, d.user_id, d.display_name, d.platform, d.created_at, d.last_seen_at, d.revoked_at,
                c.id AS credential_id, c.credential_prefix, c.scopes AS credential_scopes,
                c.created_at AS credential_created_at, c.expires_at AS credential_expires_at,
                c.last_used_at AS credential_last_used_at, c.revoked_at AS credential_revoked_at
            FROM desktop_devices d
            LEFT JOIN desktop_device_credentials c ON c.device_id = d.id
            WHERE d.user_id = ?
            ORDER BY d.created_at DESC, c.created_at DESC
            """,
            (account_id,),
        ).fetchall()

    devices: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        device_id = str(row["id"])
        if device_id in seen_ids:
            continue
        device = _row_to_public_device(row)
        if device:
            devices.append(device)
            seen_ids.add(device_id)
    return devices


def revoke_desktop_device(
    device_id: str,
    *,
    user_id: str,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    target_id = (device_id or "").strip()
    account_id = (user_id or "").strip()
    if not target_id or not account_id:
        return None
    _ensure_desktop_device_db(db_path)
    now = _now_iso()
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        updated = conn.execute(
            """
            UPDATE desktop_devices
            SET revoked_at = COALESCE(revoked_at, ?)
            WHERE id = ? AND user_id = ?
            """,
            (now, target_id, account_id),
        )
        if updated.rowcount == 0:
            return None
        conn.execute(
            """
            UPDATE desktop_device_credentials
            SET revoked_at = COALESCE(revoked_at, ?)
            WHERE device_id = ?
            """,
            (now, target_id),
        )
        row = conn.execute(_select_device_sql(), (target_id,)).fetchone()
    return _row_to_public_device(row)


def authenticate_desktop_credential(
    credential: str | None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    value = (credential or "").strip()
    if not value.startswith(DESKTOP_CREDENTIAL_PREFIX):
        return None
    _ensure_desktop_device_db(db_path)
    credential_hash = _hash_credential(value)
    now = _now().astimezone(timezone.utc)
    with sqlite3.connect(_db_path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                c.id AS credential_id, c.credential_hash, c.scopes, c.expires_at,
                d.id AS device_id, d.user_id, d.display_name, d.platform,
                u.status AS user_status
            FROM desktop_device_credentials c
            JOIN desktop_devices d ON d.id = c.device_id
            JOIN users u ON u.id = d.user_id
            WHERE c.credential_hash = ?
              AND c.revoked_at IS NULL
              AND d.revoked_at IS NULL
            """,
            (credential_hash,),
        ).fetchone()
        if row is None or not hmac.compare_digest(row["credential_hash"], credential_hash):
            return None
        try:
            expires_at = _parse_utc(str(row["expires_at"]))
        except ValueError:
            return None
        if row["user_status"] != "active" or expires_at <= now:
            return None
        used_at = _now_iso()
        conn.execute(
            "UPDATE desktop_device_credentials SET last_used_at = ? WHERE id = ?",
            (used_at, row["credential_id"]),
        )
        conn.execute("UPDATE desktop_devices SET last_seen_at = ? WHERE id = ?", (used_at, row["device_id"]))

    return {
        "credential_id": row["credential_id"],
        "device_id": row["device_id"],
        "user_id": row["user_id"],
        "owner_scope": f"user:{row['user_id']}",
        "display_name": row["display_name"],
        "platform": row["platform"],
        "scopes": str(row["scopes"] or "sync").split(),
    }


def _parse_utc(value: str):
    from datetime import datetime

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
