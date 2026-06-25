from __future__ import annotations

from typing import Any
import hmac

from fastapi import APIRouter, Body, HTTPException, Request, Response

import backend.core.server_helpers as H

router = APIRouter()


@router.get("/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    if H._account_auth_enabled():
        user = H._request_account_user(request)
        return {
            "auth_mode": "accounts",
            "account_required": True,
            "authenticated": bool(user),
            "allow_signups": H._account_registration_allowed(),
            "bootstrap_required": H.count_users() == 0,
            "user": H._public_account_payload(user),
            "guest_trial": H._guest_trial_config(),
        }
    return {
        "access_required": H._access_control_enabled(),
        "authenticated": (not H._access_control_enabled()) or H._request_has_access(request),
        "guest_trial": H._guest_trial_config(),
    }



@router.post("/auth/login")
def auth_login(
    request: Request,
    response: Response,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    if H._account_auth_enabled():
        email = H._validate_account_email(str(payload.get("email") or ""))
        password = str(payload.get("password") or "")
        user = H.authenticate_user(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="邮箱或密码不正确")
        token = H.create_session(
            str(user["id"]),
            days=H._session_days(),
            user_agent=request.headers.get("user-agent"),
            ip_address=H._request_ip_key(request),
        )
        H._set_session_cookie(response, token)
        return {
            "ok": True,
            "auth_mode": "accounts",
            "account_required": True,
            "user": H._public_account_payload(user),
        }

    token = str(payload.get("access_token") or payload.get("token") or "").strip()
    if not H._access_control_enabled():
        return {"ok": True, "access_required": False}
    if not token or not any(hmac.compare_digest(token, configured) for configured in H._configured_access_tokens()):
        raise HTTPException(status_code=401, detail="Invalid access code")
    response.set_cookie(
        key="fluentflow_access_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=H._cookie_secure_enabled(),
        samesite="lax",
    )
    return {"ok": True, "access_required": True}



@router.post("/auth/register")
def auth_register(
    request: Request,
    response: Response,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    if not H._account_auth_enabled():
        raise HTTPException(status_code=404, detail="Account auth is not enabled")
    if not H._account_registration_allowed():
        raise HTTPException(status_code=403, detail="当前未开放注册，请联系产品维护者创建账号")
    email = H._validate_account_email(str(payload.get("email") or ""))
    password = H._validate_account_password(str(payload.get("password") or ""))
    first_user = H.count_users() == 0
    try:
        user = H.create_user(email, password, role="admin" if first_user else "user")
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="这个邮箱已经注册") from exc
        raise
    H._grant_starter_balance_if_needed(user)
    token = H.create_session(
        str(user["id"]),
        days=H._session_days(),
        user_agent=request.headers.get("user-agent"),
        ip_address=H._request_ip_key(request),
    )
    H._set_session_cookie(response, token)
    return {
        "ok": True,
        "auth_mode": "accounts",
        "account_required": True,
        "user": H._public_account_payload(user),
        "bootstrap_admin": first_user,
    }



@router.post("/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    if H._account_auth_enabled():
        H.revoke_session(H._request_account_session_token(request))
        response.delete_cookie(H.SESSION_COOKIE_NAME, samesite="lax")
    response.delete_cookie("fluentflow_access_token", samesite="lax")
    return {"ok": True}



@router.get("/account/quota")
def account_quota(request: Request) -> dict[str, Any]:
    user = H._require_account_user(request)
    return H._account_quota_payload(user)


@router.post("/account/import-history", include_in_schema=False)
def removed_account_import_history() -> None:
    raise HTTPException(status_code=404, detail="Local history import has been removed")
