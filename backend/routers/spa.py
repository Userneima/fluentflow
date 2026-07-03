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


@router.get("/favicon.svg")
def favicon_svg() -> Response:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="16" fill="#111111"/>'
        '<path d="M16 39c9-15 23-15 32 0" fill="none" stroke="#8de7d2" stroke-width="6" stroke-linecap="round"/>'
        '<path d="M20 25h24" fill="none" stroke="#f4d77a" stroke-width="6" stroke-linecap="round"/>'
        '</svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/", include_in_schema=False)
def serve_frontend_index() -> FileResponse:
    if not H.FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend index not found")
    return FileResponse(str(H.FRONTEND_INDEX), headers={"Cache-Control": "no-cache"})


@router.get("/{client_path:path}", include_in_schema=False)
def serve_frontend_route(client_path: str) -> FileResponse:
    first_segment = (client_path or "").split("/", 1)[0]
    request_path = f"/{client_path or ''}"
    if first_segment == "assets" or "." in first_segment:
        raise HTTPException(status_code=404, detail="Not Found")
    if H._is_api_route_path(request_path):
        raise HTTPException(status_code=404, detail="Not Found")
    return serve_frontend_index()
