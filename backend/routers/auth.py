from __future__ import annotations

from typing import Any
import hmac
import os

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


def _feishu_redirect_uri(request: Request, explicit: str | None = None) -> str:
    configured = (explicit or os.environ.get("FEISHU_OAUTH_REDIRECT_URI") or "").strip()
    if configured:
        return configured
    return str(request.url_for("feishu_oauth_callback"))


@router.get("/account/feishu/connection")
def account_feishu_connection(request: Request) -> dict[str, Any]:
    user = H._require_account_user(request)
    return {
        "ok": True,
        "connection": H.feishu_connection_status(str(user["id"])),
    }


@router.post("/account/feishu/oauth/start")
def start_feishu_oauth(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    user = H._require_account_user(request)
    try:
        data = H.create_feishu_authorize_url(
            user_id=str(user["id"]),
            redirect_uri=_feishu_redirect_uri(request, str(payload.get("redirect_uri") or "")),
            next_url=str(payload.get("next_url") or "") or None,
        )
    except H.FeishuOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **data}


@router.get("/account/feishu/oauth/callback", name="feishu_oauth_callback")
def feishu_oauth_callback(request: Request, code: str = "", state: str = "") -> dict[str, Any]:
    user = H._require_account_user(request)
    if not code or not state:
        raise HTTPException(status_code=400, detail="Feishu OAuth callback is missing code or state.")
    try:
        return H.complete_feishu_oauth_callback(
            user_id=str(user["id"]),
            code=code,
            state=state,
        )
    except H.FeishuOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/account/feishu/disconnect")
def disconnect_account_feishu(request: Request) -> dict[str, Any]:
    user = H._require_account_user(request)
    return {
        "ok": True,
        "connection": H.disconnect_feishu_user(str(user["id"])),
    }


@router.delete("/account/feishu/connection")
def delete_account_feishu_connection(request: Request) -> dict[str, Any]:
    return disconnect_account_feishu(request)


def _api_key_owner_for_request(request: Request) -> tuple[str, str | None]:
    if H._account_auth_enabled():
        user = H.get_user_by_session_token(H._request_account_session_token(request))
        if not user:
            raise HTTPException(status_code=401, detail="FluentFlow account login is required.")
        return f"user:{user['id']}", str(user["id"])
    return H._request_client_scope(request), None


@router.get("/account/api-keys")
def account_api_keys(request: Request) -> dict[str, Any]:
    owner_scope, _user_id = _api_key_owner_for_request(request)
    return {"ok": True, "api_keys": H.list_api_keys(owner_scope)}


@router.post("/account/api-keys")
def create_account_api_key(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    owner_scope, user_id = _api_key_owner_for_request(request)
    name = str(payload.get("name") or "Agent API Key").strip()
    api_key = H.create_api_key(owner_scope=owner_scope, user_id=user_id, name=name)
    return {
        "ok": True,
        "api_key": api_key,
        "one_time_key": api_key.get("key"),
    }


@router.post("/account/api-keys/{key_id}/revoke")
def revoke_account_api_key(request: Request, key_id: str) -> dict[str, Any]:
    owner_scope, _user_id = _api_key_owner_for_request(request)
    api_key = H.revoke_api_key(key_id, owner_scope=owner_scope)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"ok": True, "api_key": api_key}


@router.delete("/account/api-keys/{key_id}")
def delete_account_api_key(request: Request, key_id: str) -> dict[str, Any]:
    return revoke_account_api_key(request, key_id)


@router.post("/account/import-history", include_in_schema=False)
def account_import_history_removed() -> None:
    raise HTTPException(status_code=410, detail="Local history import has been removed")
