"""Disabled-by-default server control plane for browser-to-OSS multipart uploads."""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

import backend.core.server_helpers as H
from backend.core.oss_config import OssDirectUploadConfig, oss_direct_upload_config
from backend.core.oss_multipart import build_oss_multipart_gateway
from backend.core.oss_upload_sessions import (
    OssUploadSessionCapacityError,
    abort_oss_upload_session as mark_oss_upload_session_aborted,
    activate_oss_upload_session,
    complete_oss_upload_session as mark_oss_upload_session_completed,
    fail_oss_upload_session,
    get_oss_upload_session,
    reserve_oss_upload_session,
)


router = APIRouter()
logger = logging.getLogger(__name__)
_MAX_PART_SIGNATURES_PER_REQUEST = 32
_MAX_ETAG_LENGTH = 512


def _ready_config() -> OssDirectUploadConfig:
    config = oss_direct_upload_config()
    if not config.enabled:
        raise HTTPException(status_code=404, detail="OSS direct upload is not enabled")
    if config.errors:
        raise HTTPException(status_code=503, detail="OSS direct upload configuration is incomplete")
    return config


def _account_owner_scope(request: Request) -> str:
    user = H._require_account_user(request)
    return f"user:{user['id']}"


def _source_metadata(payload: dict[str, Any], config: OssDirectUploadConfig) -> tuple[str, str | None, int, str, int]:
    filename = str(payload.get("filename") or "").strip()
    if not filename or len(filename) > 255 or "/" in filename or "\\" in filename or Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    suffix = Path(filename).suffix.lower()
    if suffix not in H.ALLOWED_SUFFIXES or suffix in H.TRANSCRIPT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix or 'unknown'}")
    raw_length = payload.get("content_length")
    if isinstance(raw_length, bool) or not isinstance(raw_length, int) or raw_length <= 0:
        raise HTTPException(status_code=400, detail="content_length must be a positive integer")
    max_bytes = int(H._max_upload_mb() * 1024 * 1024)
    if raw_length > max_bytes:
        raise HTTPException(status_code=413, detail=f"File is too large. Limit is {H._max_upload_mb():g} MB.")
    content_type = str(payload.get("content_type") or "").strip().lower() or None
    if content_type and (len(content_type) > 255 or not (content_type.startswith("audio/") or content_type.startswith("video/"))):
        raise HTTPException(status_code=400, detail="Invalid media content type")
    part_size_bytes = config.multipart_part_size_mb * 1024 * 1024
    expected_parts = math.ceil(raw_length / part_size_bytes)
    if expected_parts > 10_000:
        raise HTTPException(status_code=413, detail="File requires too many multipart upload parts")
    return filename, content_type, raw_length, suffix, expected_parts


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "filename": session["source_filename"],
        "content_length": session["content_length"],
        "part_size_bytes": session["part_size_bytes"],
        "expected_parts": math.ceil(session["content_length"] / session["part_size_bytes"]),
        "expires_at": session["expires_at"],
    }


def _active_session_or_error(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["status"] == "expired" or session["expired"]:
        raise HTTPException(status_code=410, detail="Upload session expired")
    if session["status"] != "initiated" or not session.get("upload_id"):
        raise HTTPException(status_code=409, detail=f"Upload session is {session['status']}")
    return session


def _part_numbers(payload: dict[str, Any], expected_parts: int) -> list[int]:
    values = payload.get("part_numbers")
    if not isinstance(values, list) or not values or len(values) > _MAX_PART_SIGNATURES_PER_REQUEST:
        raise HTTPException(status_code=400, detail="part_numbers must contain 1 to 32 parts")
    numbers: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > expected_parts:
            raise HTTPException(status_code=400, detail="Invalid multipart part number")
        numbers.append(value)
    if len(set(numbers)) != len(numbers):
        raise HTTPException(status_code=400, detail="Multipart part numbers must not repeat")
    return numbers


def _completed_parts(payload: dict[str, Any], expected_parts: int) -> list[tuple[int, str]]:
    values = payload.get("parts")
    if not isinstance(values, list) or len(values) != expected_parts:
        raise HTTPException(status_code=400, detail="Completion must include every multipart part exactly once")
    parts: list[tuple[int, str]] = []
    for value in values:
        if not isinstance(value, dict):
            raise HTTPException(status_code=400, detail="Invalid completed multipart part")
        number = value.get("part_number")
        etag = str(value.get("etag") or "").strip()
        if isinstance(number, bool) or not isinstance(number, int) or number < 1 or number > expected_parts:
            raise HTTPException(status_code=400, detail="Invalid completed multipart part number")
        if not etag or len(etag) > _MAX_ETAG_LENGTH:
            raise HTTPException(status_code=400, detail="Invalid completed multipart ETag")
        parts.append((number, etag))
    if {number for number, _etag in parts} != set(range(1, expected_parts + 1)):
        raise HTTPException(status_code=400, detail="Completion must include every multipart part exactly once")
    return sorted(parts)


def _oss_failure(action: str, session_id: str, exc: Exception) -> HTTPException:
    logger.warning("OSS multipart %s failed for session %s: %s", action, session_id, exc)
    return HTTPException(status_code=502, detail="OSS upload service is temporarily unavailable. Please retry.")


async def _fail_completed_upload(gateway: Any, session: dict[str, Any], *, reason: str) -> None:
    """Avoid retaining a completed-but-unverified source object after a control-plane error."""

    try:
        await asyncio.to_thread(gateway.delete, object_key=session["object_key"])
    except Exception as exc:  # pragma: no cover - cleanup is best effort after an upstream failure
        logger.warning("OSS multipart cleanup failed for session %s: %s", session["session_id"], exc)
    fail_oss_upload_session(session["session_id"], reason=reason)


@router.post("/oss-upload-sessions")
async def create_oss_upload_session(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a persisted multipart upload reservation without creating a task."""

    config = _ready_config()
    owner_scope = _account_owner_scope(request)
    filename, content_type, content_length, suffix, _expected_parts = _source_metadata(payload, config)
    H._enforce_submission_rate_limit(request, incoming=1)
    session_id = uuid.uuid4().hex
    object_key = f"{config.source_prefix}{session_id}/source{suffix}"
    try:
        session = reserve_oss_upload_session(
            session_id=session_id,
            owner_scope=owner_scope,
            object_key=object_key,
            source_filename=filename,
            content_type=content_type,
            content_length=content_length,
            part_size_bytes=config.multipart_part_size_mb * 1024 * 1024,
            expires_at=time.time() + config.upload_session_ttl_seconds,
            max_open_sessions=config.max_open_sessions_per_client,
        )
    except OssUploadSessionCapacityError as exc:
        raise HTTPException(status_code=429, detail="Too many unfinished uploads. Finish or cancel an existing upload first.") from exc

    try:
        gateway = await asyncio.to_thread(build_oss_multipart_gateway, config)
        upload_id = await asyncio.to_thread(gateway.initiate, object_key=object_key, content_type=content_type)
    except Exception as exc:
        fail_oss_upload_session(session_id, reason="oss_initiate_failed")
        raise _oss_failure("initiate", session_id, exc) from exc
    activated = activate_oss_upload_session(session_id, upload_id=upload_id)
    return {"ok": True, "session": _public_session(activated or session)}


@router.get("/oss-upload-sessions/{session_id}")
def get_oss_upload_session_status(request: Request, session_id: str) -> dict[str, Any]:
    _ready_config()
    session = get_oss_upload_session(session_id, owner_scope=_account_owner_scope(request))
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    return {"session": _public_session(session)}


@router.post("/oss-upload-sessions/{session_id}/parts")
async def sign_oss_upload_parts(
    request: Request,
    session_id: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    config = _ready_config()
    session = _active_session_or_error(get_oss_upload_session(session_id, owner_scope=_account_owner_scope(request)))
    expected_parts = math.ceil(session["content_length"] / session["part_size_bytes"])
    part_numbers = _part_numbers(payload, expected_parts)
    try:
        gateway = await asyncio.to_thread(build_oss_multipart_gateway, config)

        def sign_all():
            return [
                gateway.presign_part(
                    object_key=session["object_key"],
                    upload_id=session["upload_id"],
                    part_number=number,
                    expires_seconds=config.presign_ttl_seconds,
                )
                for number in part_numbers
            ]

        signatures = await asyncio.to_thread(sign_all)
    except Exception as exc:
        raise _oss_failure("presign", session_id, exc) from exc
    return {
        "session_id": session_id,
        "parts": [
            {"part_number": number, "method": signature.method, "url": signature.url, "headers": signature.headers}
            for number, signature in zip(part_numbers, signatures)
        ],
    }


@router.post("/oss-upload-sessions/{session_id}/complete")
async def complete_oss_upload_session(request: Request, session_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    config = _ready_config()
    session = _active_session_or_error(get_oss_upload_session(session_id, owner_scope=_account_owner_scope(request)))
    expected_parts = math.ceil(session["content_length"] / session["part_size_bytes"])
    parts = _completed_parts(payload, expected_parts)
    gateway: Any | None = None
    try:
        gateway = await asyncio.to_thread(build_oss_multipart_gateway, config)
        await asyncio.to_thread(
            gateway.complete,
            object_key=session["object_key"],
            upload_id=session["upload_id"],
            parts=parts,
        )
    except Exception as exc:
        if gateway is not None:
            await _fail_completed_upload(gateway, session, reason="oss_complete_failed")
        else:
            fail_oss_upload_session(session_id, reason="oss_complete_failed")
        raise _oss_failure("complete", session_id, exc) from exc
    try:
        actual_length = await asyncio.to_thread(gateway.head_size, object_key=session["object_key"])
    except Exception as exc:
        await _fail_completed_upload(gateway, session, reason="oss_completed_verification_failed")
        raise _oss_failure("verify", session_id, exc) from exc
    if actual_length != session["content_length"]:
        await _fail_completed_upload(gateway, session, reason="oss_completed_size_mismatch")
        raise HTTPException(status_code=422, detail="Uploaded object size could not be verified")
    completed = mark_oss_upload_session_completed(session_id)
    return {"ok": True, "session": _public_session(completed or session)}


@router.post("/oss-upload-sessions/{session_id}/abort")
async def abort_oss_upload_session_route(request: Request, session_id: str) -> dict[str, Any]:
    config = _ready_config()
    session = get_oss_upload_session(session_id, owner_scope=_account_owner_scope(request))
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session["status"] in {"aborted", "expired", "failed"}:
        return {"ok": True, "session": _public_session(session)}
    if session["status"] == "completed":
        raise HTTPException(status_code=409, detail="Completed uploads cannot be aborted")
    if session.get("upload_id"):
        try:
            gateway = await asyncio.to_thread(build_oss_multipart_gateway, config)
            await asyncio.to_thread(gateway.abort, object_key=session["object_key"], upload_id=session["upload_id"])
        except Exception as exc:
            raise _oss_failure("abort", session_id, exc) from exc
    aborted = mark_oss_upload_session_aborted(session_id)
    return {"ok": True, "session": _public_session(aborted or session)}
