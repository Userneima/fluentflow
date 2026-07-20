"""Restricted API for desktop-local processing to synchronize safe results."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from backend.core.desktop_device_store import authenticate_desktop_credential
from backend.core.desktop_sync_store import (
    DesktopSyncConflictError,
    DesktopSyncError,
    DesktopSyncPermissionError,
    create_desktop_sync_task,
    sync_desktop_task_result,
    sync_desktop_task_status,
)


router = APIRouter(prefix="/desktop-sync/v1")
DEVICE_CREDENTIAL_HEADER = "x-fluentflow-desktop-credential"


def _desktop_auth(request: Request) -> dict[str, Any]:
    credential = (request.headers.get(DEVICE_CREDENTIAL_HEADER) or "").strip()
    auth = authenticate_desktop_credential(credential)
    if not auth or "sync" not in auth.get("scopes", []):
        raise HTTPException(status_code=401, detail="A valid desktop sync credential is required")
    return auth


def _sync_error(exc: DesktopSyncError) -> None:
    if isinstance(exc, DesktopSyncConflictError):
        raise HTTPException(status_code=409, detail={"message": str(exc), "latest": exc.task}) from exc
    if isinstance(exc, DesktopSyncPermissionError):
        raise HTTPException(status_code=404, detail="Desktop sync task not found") from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tasks")
def create_task(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    try:
        task, created = create_desktop_sync_task(
            device_auth=_desktop_auth(request),
            idempotency_key=payload.get("idempotency_key"),
            source=payload.get("source"),
        )
    except DesktopSyncError as exc:
        _sync_error(exc)
    return {"ok": True, "created": created, "task": task}


@router.patch("/tasks/{task_id}/status")
def sync_task_status(
    request: Request,
    task_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        response = sync_desktop_task_status(
            task_id=task_id,
            device_auth=_desktop_auth(request),
            operation_id=payload.get("operation_id"),
            base_revision=payload.get("base_revision"),
            status=payload.get("status"),
            stage=payload.get("stage"),
            progress=payload.get("progress"),
            error_code=payload.get("error_code"),
            error_reason=payload.get("error_reason"),
        )
    except DesktopSyncError as exc:
        _sync_error(exc)
    return {"ok": True, **response}


@router.put("/tasks/{task_id}/result")
def sync_task_result(
    request: Request,
    task_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        response = sync_desktop_task_result(
            task_id=task_id,
            device_auth=_desktop_auth(request),
            operation_id=payload.get("operation_id"),
            base_revision=payload.get("base_revision"),
            result=payload.get("result"),
        )
    except DesktopSyncError as exc:
        _sync_error(exc)
    return {"ok": True, **response}
