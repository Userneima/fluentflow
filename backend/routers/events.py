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


@router.post("/events")
async def record_client_event(request: Request, payload: dict[str, Any] = Body(...)):
    """Record explicit client-side button events without storing user content."""
    event_name = str(payload.get("event_name") or "")
    if event_name not in H.CLIENT_EVENT_NAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported event: {event_name}")
    task_id_value = str(payload.get("task_id") or "").strip() or H._new_task_id()
    client_id = H._request_client_scope(request)
    if event_name == "task_cancelled" and not H.get_job(task_id_value, client_id=client_id):
        raise HTTPException(status_code=404, detail="Job not found")
    raw_metadata = payload.get("metadata")
    allowed_client_metadata = (
        {k: raw_metadata.get(k) for k in ("format", "trigger") if k in raw_metadata}
        if isinstance(raw_metadata, dict)
        else {}
    )
    client_metadata = H._metadata(**allowed_client_metadata)
    H.log_event(
        task_id=task_id_value,
        event_name=event_name,
        source_type=payload.get("source_type"),
        source_filename=payload.get("source_filename"),
        source_duration_seconds=payload.get("source_duration_seconds"),
        source_file_size_mb=payload.get("source_file_size_mb"),
        transcript_length=payload.get("transcript_length"),
        summary_length=payload.get("summary_length"),
        stage=payload.get("stage"),
        duration_seconds=payload.get("duration_seconds"),
        success=payload.get("success"),
        error_reason=payload.get("error_reason"),
        export_target=payload.get("export_target"),
        feishu_doc_url=payload.get("feishu_doc_url"),
        metadata=client_metadata,
    )
    if event_name == "task_cancelled":
        await H.JOB_EVENTS.cancel(task_id_value)
        H.cancel_job_steps(task_id_value)
        H.log_event(
            task_id=task_id_value,
            event_name="task_completed",
            source_type=payload.get("source_type"),
            source_filename=payload.get("source_filename"),
            source_duration_seconds=payload.get("source_duration_seconds"),
            source_file_size_mb=payload.get("source_file_size_mb"),
            transcript_length=payload.get("transcript_length"),
            summary_length=payload.get("summary_length"),
            stage="cancelled",
            duration_seconds=payload.get("duration_seconds"),
            success=False,
            metadata=H._metadata(
                **H._runtime_context_metadata(),
                final_status="cancelled",
                total_duration_seconds=payload.get("duration_seconds"),
                summary_status=payload.get("summary_status"),
                lark_requested=payload.get("lark_requested"),
                lark_success=payload.get("lark_success"),
                source_type=payload.get("source_type"),
                pipeline_mode=H._pipeline_mode(payload.get("source_type")),
                completion_reason="user_cancelled",
            ),
        )
    return {"ok": True, "task_id": task_id_value}
