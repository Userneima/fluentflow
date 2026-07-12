"""Google OAuth login helpers for FluentFlow accounts.

This module only implements the basic sign-in surface with Google OpenID
Connect scopes. It does not request Google Drive, Gmail, or other product-data
permissions.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

from backend.core.account_store import (
    consume_oauth_login_state,
    count_users,
    create_oauth_login_state,
    create_oauth_user,
    get_oauth_identity,
    get_user_by_email,
    get_user_by_id,
    save_oauth_identity,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DEFAULT_GOOGLE_OAUTH_SCOPES = "openid email profile"


class GoogleOAuthError(RuntimeError):
    """Raised when Google OAuth login cannot proceed."""


def _credentials() -> tuple[str, str]:
    load_dotenv()
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise GoogleOAuthError("Google login requires GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")
    return client_id, client_secret


def google_oauth_enabled() -> bool:
    try:
        _credentials()
    except GoogleOAuthError:
        return False
    return True


def _scopes() -> str:
    return (os.environ.get("FLUENTFLOW_GOOGLE_OAUTH_SCOPES") or DEFAULT_GOOGLE_OAUTH_SCOPES).strip()


def create_google_authorize_url(
    *,
    redirect_uri: str,
    next_url: str | None = None,
) -> dict[str, Any]:
    client_id, _client_secret = _credentials()
    state_record = create_oauth_login_state(
        "google",
        redirect_uri=redirect_uri,
        next_url=next_url,
    )
    scopes = _scopes()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state_record["state"],
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return {
        "authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
        "state_expires_at": state_record["expires_at"],
        "scopes": scopes,
    }


def _post_form(url: str, form: dict[str, Any], *, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=urlencode(form).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise GoogleOAuthError(f"Google OAuth HTTP {exc.code}: {raw[:800]}") from exc
    except urllib.error.URLError as exc:
        raise GoogleOAuthError(f"Google OAuth request failed: {exc}") from exc
    except ValueError as exc:
        raise GoogleOAuthError("Google OAuth returned invalid JSON.") from exc


def _get_json(url: str, *, access_token: str, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise GoogleOAuthError(f"Google userinfo HTTP {exc.code}: {raw[:800]}") from exc
    except urllib.error.URLError as exc:
        raise GoogleOAuthError(f"Google userinfo request failed: {exc}") from exc
    except ValueError as exc:
        raise GoogleOAuthError("Google userinfo returned invalid JSON.") from exc


def exchange_google_oauth_code(
    *,
    code: str,
    redirect_uri: str,
    timeout: int = 15,
) -> dict[str, Any]:
    client_id, client_secret = _credentials()
    data = _post_form(
        GOOGLE_TOKEN_URL,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=timeout,
    )
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise GoogleOAuthError(f"Google OAuth response missing access_token: {data}")
    return data


def fetch_google_userinfo(access_token: str, *, timeout: int = 15) -> dict[str, Any]:
    token = (access_token or "").strip()
    if not token:
        raise GoogleOAuthError("Google access_token is required.")
    data = _get_json(GOOGLE_USERINFO_URL, access_token=token, timeout=timeout)
    subject = str(data.get("sub") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    if not subject:
        raise GoogleOAuthError("Google userinfo response missing subject.")
    if not email:
        raise GoogleOAuthError("Google userinfo response missing email.")
    return data


def complete_google_oauth_callback(
    *,
    state: str,
    code: str,
    allow_create_user: bool,
) -> dict[str, Any]:
    state_record = consume_oauth_login_state("google", state)
    if not state_record:
        raise GoogleOAuthError("Invalid or expired Google OAuth state.")
    token = exchange_google_oauth_code(code=code, redirect_uri=str(state_record["redirect_uri"]))
    userinfo = fetch_google_userinfo(str(token.get("access_token") or ""))
    subject = str(userinfo.get("sub") or "").strip()
    email = str(userinfo.get("email") or "").strip().lower()
    email_verified = bool(userinfo.get("email_verified"))

    identity = get_oauth_identity("google", subject)
    user = get_user_by_id(str(identity["user_id"])) if identity else None
    created = False
    linked_existing = False
    if not user:
        user = get_user_by_email(email) if email_verified else None
        linked_existing = bool(user)
    if not user:
        if not allow_create_user:
            raise GoogleOAuthError("当前未开放新账号注册。请先使用已注册邮箱登录，或联系产品维护者。")
        first_user = count_users() == 0
        user = create_oauth_user(email, role="admin" if first_user else "user")
        created = True

    save_oauth_identity(
        "google",
        subject,
        user_id=str(user["id"]),
        email=email,
        email_verified=email_verified,
        profile={
            "email": email,
            "email_verified": email_verified,
            "name": userinfo.get("name"),
            "picture": userinfo.get("picture"),
            "locale": userinfo.get("locale"),
        },
    )
    refreshed = get_user_by_id(str(user["id"])) or user
    return {
        "ok": True,
        "user": refreshed,
        "created": created,
        "linked_existing": linked_existing,
        "next_url": state_record.get("next_url"),
    }


__all__ = [
    "GoogleOAuthError",
    "complete_google_oauth_callback",
    "create_google_authorize_url",
    "exchange_google_oauth_code",
    "fetch_google_userinfo",
    "google_oauth_enabled",
]
