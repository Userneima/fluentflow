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


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "app_version": H.APP_VERSION,
        "event_schema_version": H.EVENT_SCHEMA_VERSION,
        "runtime": H._runtime_context_metadata(),
        "limits": H._runtime_limits_for_request(request),
    }



@router.get("/ops/status")
def ops_status() -> dict[str, Any]:
    return H._ops_status_payload()
