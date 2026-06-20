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


@router.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@router.get("/", include_in_schema=False)
def serve_frontend_index() -> FileResponse:
    if not H.FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index not found")
    return FileResponse(str(H.FRONTEND_INDEX))


@router.get("/{client_path:path}", include_in_schema=False)
def serve_frontend_route(client_path: str) -> FileResponse:
    first_segment = (client_path or "").split("/", 1)[0]
    if first_segment == "assets" or first_segment in H.API_ROUTE_PREFIXES or "." in first_segment:
        raise HTTPException(status_code=404, detail="Not Found")
    return serve_frontend_index()
