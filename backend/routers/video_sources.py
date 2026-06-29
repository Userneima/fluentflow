from __future__ import annotations

from typing import Any, AsyncGenerator, Optional
import json
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.core.video_source import display_title_for_source_input
import backend.core.server_helpers as H

router = APIRouter()


@router.post("/video-sources/jobs")
async def create_video_source_job(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    input_text = str(payload.get("input") or "").strip()
    title = str(payload.get("title") or "").strip()
    client_id = H._request_client_scope(request)
    if not input_text:
        raise HTTPException(status_code=400, detail="缺少视频分享文本或视频链接")
    if len(input_text) > 4000:
        raise HTTPException(status_code=400, detail="分享文本过长")
    H._enforce_submission_rate_limit(request, incoming=1)
    H._enforce_active_job_limit(client_id, incoming=1)
    H._enforce_global_active_job_limit(incoming=1)
    H._enforce_daily_quota(client_id, incoming_jobs=1)
    H._enforce_global_daily_quota(client_id=client_id, incoming_jobs=1)

    options = H._queue_options_from_mapping(payload.get("options") if isinstance(payload.get("options"), dict) else {})
    task_id_value = H._new_task_id()
    raw_title = title or display_title_for_source_input(input_text, input_text[:80])
    display_name = H.display_title_for_user(raw_title, raw_title)
    metadata = H._metadata(
        route="/video-sources/jobs",
        queue_options=options,
        raw_title=raw_title,
        display_title=display_name,
        video_source_input_preview=input_text[:200],
    )
    H.log_event(
        task_id=task_id_value,
        event_name="video_source_submitted",
        source_type="video_link",
        source_filename=display_name,
        stage="queued",
        success=True,
        metadata=metadata,
    )
    H.upsert_job(
        task_id=task_id_value,
        status="queued",
        client_id=client_id,
        stage="queued",
        progress=0,
        source_type="video_link",
        source_filename=display_name,
        metadata=metadata,
    )
    H._start_video_source_job({
        "task_id": task_id_value,
        "input": input_text,
        "title": title or None,
        "options": options,
        "base_url": H._queue_base_url_from_request(request),
        "client_id": client_id,
    })
    return {
        "ok": True,
        "job": {
            "task_id": task_id_value,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "source_type": "video_link",
            "source_filename": display_name,
            "metadata": metadata,
        },
    }



@router.get("/video-sources/jobs")
def list_video_source_jobs(request: Request, limit: int = 50) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 50), 200))
    jobs = [
        job for job in H.list_jobs(limit=200, client_id=H._request_client_scope(request))
        if (job.get("metadata") or {}).get("route") == "/video-sources/jobs"
    ][:safe_limit]
    return {"jobs": jobs}
