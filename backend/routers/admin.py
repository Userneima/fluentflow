from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import backend.core.server_helpers as H

router = APIRouter()


@router.get("/admin/users")
def admin_list_users(request: Request, limit: int = 100) -> dict[str, Any]:
    H._require_admin_user(request)
    users = []
    for user in H.list_users(limit=limit):
        public = H._public_account_payload(user)
        if public:
            users.append(public)
    return {"users": users}



@router.post("/admin/users/{user_id}/balance-adjustments")
def admin_adjust_user_balance(
    request: Request,
    user_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    admin = H._require_admin_user(request)
    target = H.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        units = int(payload.get("units") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="units must be an integer") from None
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    provider_reference = str(payload.get("provider_reference") or "").strip() or None
    try:
        tx = H.add_admin_adjustment(
            user_id,
            units=units,
            reason=reason,
            admin_account_id=str(admin["id"]),
            provider_reference=provider_reference,
            metadata={"route": "/admin/users/{user_id}/balance-adjustments"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "transaction": tx,
        "user": H._public_account_payload(target),
    }
