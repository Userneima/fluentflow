"""Cloud account claim and loopback callback for desktop sync pairing."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import RedirectResponse

import backend.core.server_helpers as H
from backend.core.desktop_device_store import claim_desktop_device_credential_hash
from backend.core.desktop_pairing import (
    PAIRING_CALLBACK_PATH,
    DesktopPairingError,
    _validate_callback_url,
    complete_desktop_pairing,
    desktop_sync_default_cloud_url,
    desktop_sync_status,
    start_desktop_pairing,
)
from backend.core.desktop_sync_client import desktop_sync_outbox_status, flush_desktop_sync_outbox


cloud_router = APIRouter()
local_router = APIRouter(prefix="/desktop-sync/local")


def _require_loopback(request: Request) -> None:
    if not H._request_is_localhost(request):
        raise HTTPException(status_code=404, detail="Not found")


@cloud_router.get("/account/desktop-pair")
def claim_desktop_pair(
    request: Request,
    state: str = "",
    callback_url: str = "",
    credential_hash: str = "",
    credential_prefix: str = "",
    display_name: str = "",
    platform: str = "",
) -> RedirectResponse:
    user = H._require_account_user(request)
    try:
        callback = _validate_callback_url(callback_url)
        device = claim_desktop_device_credential_hash(
            user_id=str(user["id"]),
            platform=platform,
            display_name=display_name,
            credential_hash=credential_hash,
            credential_prefix=credential_prefix,
        )
    except (DesktopPairingError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    query = urlencode({"state": state, "device_id": device["id"]})
    return RedirectResponse(f"{callback}?{query}", status_code=303)


@local_router.get("/status")
def local_pairing_status(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    return {
        "ok": True,
        "sync": desktop_sync_status(),
        "outbox": desktop_sync_outbox_status(),
        "default_cloud_url": desktop_sync_default_cloud_url(),
    }


@local_router.post("/pairing/start")
def start_local_pairing(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    _require_loopback(request)
    callback_url = str(request.base_url).rstrip("/") + PAIRING_CALLBACK_PATH
    try:
        result = start_desktop_pairing(
            cloud_url=str(payload.get("cloud_url") or ""),
            callback_url=callback_url,
            display_name=str(payload.get("display_name") or ""),
            platform_name=str(payload.get("platform") or ""),
        )
    except DesktopPairingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, **result}


@local_router.post("/flush")
def flush_local_desktop_sync(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    last_flush = flush_desktop_sync_outbox()
    return {
        "ok": True,
        "sync": desktop_sync_status(),
        "outbox": {**desktop_sync_outbox_status(), "last_flush": last_flush},
    }


@local_router.get("/pairing/callback")
def complete_local_pairing(request: Request, state: str = "", device_id: str = "") -> RedirectResponse:
    _require_loopback(request)
    try:
        complete_desktop_pairing(state=state, device_id=device_id)
    except DesktopPairingError as exc:
        return RedirectResponse(f"/settings?desktop_sync_error={str(exc)}", status_code=303)
    return RedirectResponse("/settings?desktop_sync=connected", status_code=303)
