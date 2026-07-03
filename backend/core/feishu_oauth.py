"""Feishu user OAuth helpers for account-scoped export.

Refresh tokens are stored only in the server-side account database and are
never returned by API payloads. Production deployments should protect that
database with disk/database encryption or move token encryption to KMS-backed
secret storage.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

from backend.core.account_store import (
    consume_feishu_oauth_state,
    create_feishu_oauth_state,
    disconnect_feishu_connection,
    get_feishu_connection,
    get_feishu_connection_status,
    save_feishu_connection,
)
from backend.core.lark_exporter import DEFAULT_BASE_URL

DEFAULT_FEISHU_OAUTH_SCOPES = "offline_access"


class FeishuOAuthError(RuntimeError):
    """Raised when Feishu user OAuth cannot proceed."""


class FeishuConnectionRequired(FeishuOAuthError):
    """Raised when an export requires a connected user account."""


def _base_url() -> str:
    load_dotenv()
    return (os.environ.get("LARK_OPEN_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")


def _app_credentials() -> tuple[str, str]:
    load_dotenv()
    app_id = (os.environ.get("LARK_APP_ID") or "").strip()
    app_secret = (os.environ.get("LARK_APP_SECRET") or "").strip()
    if not app_id or not app_secret:
        raise FeishuOAuthError("Feishu OAuth requires LARK_APP_ID and LARK_APP_SECRET.")
    return app_id, app_secret


def _oauth_scopes() -> str:
    return (os.environ.get("FLUENTFLOW_FEISHU_OAUTH_SCOPES") or DEFAULT_FEISHU_OAUTH_SCOPES).strip()


def _post_json(url: str, body: dict[str, Any], *, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise FeishuOAuthError(f"Feishu OAuth HTTP {exc.code}: {raw[:800]}") from exc
    except urllib.error.URLError as exc:
        raise FeishuOAuthError(f"Feishu OAuth request failed: {exc}") from exc
    except ValueError as exc:
        raise FeishuOAuthError("Feishu OAuth returned invalid JSON.") from exc


def _token_payload(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("code") not in (None, 0):
        raise FeishuOAuthError(f"Feishu OAuth error: {data}")
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(payload, dict) or not (payload.get("access_token") or payload.get("user_access_token")):
        raise FeishuOAuthError(f"Feishu OAuth response missing access_token: {data}")
    return payload


def _expires_at(seconds: Any) -> str | None:
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return (datetime.now(timezone.utc).astimezone() + timedelta(seconds=value)).isoformat(timespec="seconds")


def create_feishu_authorize_url(
    *,
    user_id: str,
    redirect_uri: str,
    next_url: str | None = None,
) -> dict[str, Any]:
    app_id, _app_secret = _app_credentials()
    state_record = create_feishu_oauth_state(
        user_id,
        redirect_uri=redirect_uri,
        next_url=next_url,
    )
    params = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state_record["state"],
    }
    scopes = _oauth_scopes()
    if scopes:
        params["scope"] = scopes
    return {
        "authorize_url": f"{_base_url()}/open-apis/authen/v1/index?{urlencode(params)}",
        "state_expires_at": state_record["expires_at"],
        "scopes": scopes,
    }


def exchange_feishu_oauth_code(
    *,
    code: str,
    redirect_uri: str,
    timeout: int = 15,
) -> dict[str, Any]:
    app_id, app_secret = _app_credentials()
    data = _post_json(
        f"{_base_url()}/open-apis/authen/v2/oauth/token",
        {
            "grant_type": "authorization_code",
            "client_id": app_id,
            "client_secret": app_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=timeout,
    )
    return _token_payload(data)


def refresh_feishu_user_token(
    *,
    refresh_token: str,
    timeout: int = 15,
) -> dict[str, Any]:
    app_id, app_secret = _app_credentials()
    data = _post_json(
        f"{_base_url()}/open-apis/authen/v2/oauth/token",
        {
            "grant_type": "refresh_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "refresh_token": refresh_token,
        },
        timeout=timeout,
    )
    return _token_payload(data)


def complete_feishu_oauth_callback(
    *,
    user_id: str,
    state: str,
    code: str,
) -> dict[str, Any]:
    state_record = consume_feishu_oauth_state(state, user_id=user_id)
    if not state_record:
        raise FeishuOAuthError("Invalid or expired Feishu OAuth state.")
    token = exchange_feishu_oauth_code(code=code, redirect_uri=str(state_record["redirect_uri"]))
    access_token = str(token.get("access_token") or token.get("user_access_token") or "")
    status = save_feishu_connection(
        user_id,
        access_token=access_token,
        refresh_token=str(token.get("refresh_token") or "") or None,
        expires_in=int(token.get("expires_in") or 0) or None,
        refresh_expires_in=int(token.get("refresh_expires_in") or 0) or None,
        feishu_open_id=str(token.get("open_id") or "") or None,
        feishu_union_id=str(token.get("union_id") or "") or None,
        feishu_user_id=str(token.get("user_id") or "") or None,
        tenant_key=str(token.get("tenant_key") or "") or None,
        scopes=str(token.get("scope") or token.get("scopes") or _oauth_scopes()) or None,
        owner_scope=str(state_record.get("owner_scope") or f"user:{user_id}"),
    )
    return {
        "ok": True,
        "connection": status,
        "next_url": state_record.get("next_url"),
    }


def feishu_connection_status(user_id: str) -> dict[str, Any]:
    return get_feishu_connection_status(user_id)


def disconnect_feishu_user(user_id: str) -> dict[str, Any]:
    return disconnect_feishu_connection(user_id)


def get_valid_feishu_user_access_token(user_id: str) -> str:
    connection = get_feishu_connection(user_id)
    if not connection or connection.get("revoked_at"):
        raise FeishuConnectionRequired("需要先连接飞书账号，才能用用户身份导出。")
    token = str(connection.get("access_token") or "").strip()
    if not token:
        raise FeishuConnectionRequired("飞书连接已失效，请重新连接飞书账号。")
    expires_text = str(connection.get("access_token_expires_at") or "")
    expires_at: datetime | None = None
    if expires_text:
        try:
            expires_at = datetime.fromisoformat(expires_text)
        except ValueError:
            expires_at = None
    now = datetime.now(timezone.utc).astimezone()
    if expires_at is None or expires_at > now + timedelta(seconds=90):
        return token
    refresh_token = str(connection.get("refresh_token") or "").strip()
    if not refresh_token:
        raise FeishuConnectionRequired("飞书授权已过期，请重新连接飞书账号。")
    refreshed = refresh_feishu_user_token(refresh_token=refresh_token)
    refreshed_token = str(refreshed.get("access_token") or refreshed.get("user_access_token") or "")
    save_feishu_connection(
        user_id,
        access_token=refreshed_token,
        refresh_token=str(refreshed.get("refresh_token") or "") or refresh_token,
        expires_in=int(refreshed.get("expires_in") or 0) or None,
        refresh_expires_in=int(refreshed.get("refresh_expires_in") or 0) or None,
        feishu_open_id=str(connection.get("feishu_open_id") or "") or None,
        feishu_union_id=str(connection.get("feishu_union_id") or "") or None,
        feishu_user_id=str(connection.get("feishu_user_id") or "") or None,
        tenant_key=str(connection.get("tenant_key") or "") or None,
        scopes=str(refreshed.get("scope") or refreshed.get("scopes") or connection.get("scopes") or "") or None,
        owner_scope=str(connection.get("owner_scope") or f"user:{user_id}"),
    )
    return refreshed_token


__all__ = [
    "FeishuConnectionRequired",
    "FeishuOAuthError",
    "complete_feishu_oauth_callback",
    "create_feishu_authorize_url",
    "disconnect_feishu_user",
    "exchange_feishu_oauth_code",
    "feishu_connection_status",
    "get_valid_feishu_user_access_token",
    "refresh_feishu_user_token",
]
