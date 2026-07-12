"""Account session/quota helpers, extracted from server_helpers.py.
account_quota_summary is imported lazily to avoid a circular import.
Re-imported by server_helpers so H._* / SESSION_COOKIE_NAME keep working."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Request


SESSION_COOKIE_NAME = "fluentflow_session"


def _session_days() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_SESSION_DAYS", "30")), 1)
    except ValueError:
        return 30


def _request_account_session_token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    header_token = (request.headers.get("x-fluentflow-session") or "").strip()
    if header_token:
        return header_token
    return (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()


def _public_account_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "role": user.get("role"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }


def _account_quota_payload(user: dict[str, Any] | None) -> dict[str, Any]:
    if not user or not user.get("id"):
        return {"balance_units": 0, "recent_transactions": [], "unlimited": False, "quota_exempt": False}
    from backend.core.quota_store import account_quota_summary
    summary = account_quota_summary(str(user["id"]))
    is_admin = user.get("role") == "admin"
    summary["unlimited"] = bool(is_admin)
    summary["quota_exempt"] = bool(is_admin)
    return summary


def _starter_balance_units() -> int:
    try:
        return max(int(os.environ.get("FLUENTFLOW_STARTER_BALANCE_UNITS", "100")), 0)
    except ValueError:
        return 100
