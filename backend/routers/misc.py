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
from backend.core.task_detail import build_task_snapshot

router = APIRouter()


@router.get("/jobs")
def get_jobs(request: Request, limit: int = 50, include_result: bool = False) -> dict[str, Any]:
    client_id = H._request_client_scope(request)
    jobs = (
        H.list_jobs(limit=limit, client_id=client_id)
        if include_result
        else H.list_job_summaries(limit=limit, client_id=client_id)
    )
    return {"jobs": [{**job, "task_snapshot": build_task_snapshot(job)} for job in jobs]}
