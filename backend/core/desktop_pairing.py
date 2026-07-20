"""Local-only desktop pairing state for the explicit cloud sync flow."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform as system_platform
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from backend.core.desktop_device_store import DESKTOP_CREDENTIAL_PREFIX
from backend.core.local_config import config_path, load_config, load_project_env


PAIRING_TTL_MINUTES = 10
SYNC_CONFIG_KEY = "desktop_sync"
PAIRING_CALLBACK_PATH = "/desktop-sync/local/pairing/callback"


class DesktopPairingError(ValueError):
    """A client-safe desktop pairing error."""


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _write_config(data: dict[str, Any], path: Path | str | None = None) -> None:
    target = Path(path) if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    try:
        target.chmod(0o600)
    except OSError:
        pass


def _normalize_cloud_url(value: str) -> str:
    url = (value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise DesktopPairingError("cloud_url must be an absolute HTTP(S) URL")
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise DesktopPairingError("cloud_url must use HTTPS outside local development")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise DesktopPairingError("cloud_url must not include a path, query, or fragment")
    return url


def _validate_callback_url(value: str) -> str:
    callback = (value or "").strip()
    parsed = urlparse(callback)
    if (
        parsed.scheme != "http"
        or (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}
        or parsed.path != PAIRING_CALLBACK_PATH
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise DesktopPairingError("callback_url must be the local FluentFlow pairing callback")
    return callback


def _default_platform() -> str:
    return "windows" if system_platform.system().lower().startswith("win") else "macos"


def _default_display_name(platform_name: str) -> str:
    return "This Windows PC" if platform_name == "windows" else "This Mac"


def _sync_config(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get(SYNC_CONFIG_KEY)
    return dict(value) if isinstance(value, dict) else {}


def desktop_sync_status(path: Path | str | None = None) -> dict[str, Any]:
    sync = _sync_config(load_config(path))
    credential = str(sync.get("device_credential") or "").strip()
    pending = sync.get("pending_pairing") if isinstance(sync.get("pending_pairing"), dict) else None
    return {
        "connected": bool(credential and sync.get("cloud_url") and sync.get("device_id")),
        "cloud_url": sync.get("cloud_url") or None,
        "device_id": sync.get("device_id") or None,
        "display_name": sync.get("display_name") or None,
        "platform": sync.get("platform") or None,
        "connected_at": sync.get("connected_at") or None,
        "pairing_pending": bool(pending),
    }


def desktop_sync_default_cloud_url() -> str | None:
    """Return the launcher-provided cloud address without hard-coding a deployment."""
    load_project_env()
    configured = (os.environ.get("FLUENTFLOW_DESKTOP_SYNC_CLOUD_URL") or "").strip()
    if not configured:
        return None
    try:
        return _normalize_cloud_url(configured)
    except DesktopPairingError:
        return None


def start_desktop_pairing(
    *,
    cloud_url: str,
    callback_url: str,
    display_name: str = "",
    platform_name: str = "",
    path: Path | str | None = None,
) -> dict[str, Any]:
    cloud = _normalize_cloud_url(cloud_url)
    callback = _validate_callback_url(callback_url)
    platform_value = (platform_name or _default_platform()).strip().lower()
    if platform_value not in {"macos", "windows"}:
        raise DesktopPairingError("platform must be macos or windows")
    label = " ".join((display_name or _default_display_name(platform_value)).split())
    if not label or len(label) > 80 or any(char in label for char in ("/", "\\", "\r", "\n")):
        raise DesktopPairingError("display_name is invalid")

    credential = f"{DESKTOP_CREDENTIAL_PREFIX}{secrets.token_urlsafe(32)}"
    state = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(minutes=PAIRING_TTL_MINUTES)
    data = load_config(path)
    data[SYNC_CONFIG_KEY] = {
        **_sync_config(data),
        "pending_pairing": {
            "cloud_url": cloud,
            "callback_url": callback,
            "state": state,
            "device_credential": credential,
            "credential_hash": hashlib.sha256(credential.encode("utf-8")).hexdigest(),
            "credential_prefix": f"{credential[:11]}...",
            "display_name": label,
            "platform": platform_value,
            "expires_at": expires_at.isoformat(timespec="seconds"),
        },
    }
    _write_config(data, path)
    query = urlencode({
        "state": state,
        "callback_url": callback,
        "credential_hash": data[SYNC_CONFIG_KEY]["pending_pairing"]["credential_hash"],
        "credential_prefix": data[SYNC_CONFIG_KEY]["pending_pairing"]["credential_prefix"],
        "display_name": label,
        "platform": platform_value,
    })
    return {"pair_url": f"{cloud}/account/desktop-pair?{query}", **desktop_sync_status(path)}


def complete_desktop_pairing(
    *,
    state: str,
    device_id: str,
    path: Path | str | None = None,
) -> dict[str, Any]:
    data = load_config(path)
    sync = _sync_config(data)
    pending = sync.get("pending_pairing") if isinstance(sync.get("pending_pairing"), dict) else None
    if not pending:
        raise DesktopPairingError("No desktop pairing is waiting on this computer")
    expected_state = str(pending.get("state") or "")
    if not expected_state or not hmac.compare_digest(expected_state, str(state or "")):
        raise DesktopPairingError("Desktop pairing state does not match")
    try:
        expires_at = datetime.fromisoformat(str(pending.get("expires_at") or ""))
    except ValueError as exc:
        raise DesktopPairingError("Desktop pairing has expired") from exc
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now().astimezone(timezone.utc):
        raise DesktopPairingError("Desktop pairing has expired")
    normalized_device_id = str(device_id or "").strip()
    if not normalized_device_id or len(normalized_device_id) > 128:
        raise DesktopPairingError("Desktop pairing did not return a valid device")
    data[SYNC_CONFIG_KEY] = {
        "cloud_url": pending["cloud_url"],
        "device_id": normalized_device_id,
        "device_credential": pending["device_credential"],
        "display_name": pending["display_name"],
        "platform": pending["platform"],
        "connected_at": _now().isoformat(timespec="seconds"),
    }
    _write_config(data, path)
    return desktop_sync_status(path)
