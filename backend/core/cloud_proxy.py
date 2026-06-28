"""Cloud workspace proxy helpers."""

from __future__ import annotations

import json
import logging
from http.cookies import SimpleCookie
from typing import Any, AsyncGenerator

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse


def proxy_response_headers(headers: httpx.Headers) -> dict[str, str]:
    blocked = {
        "connection",
        "content-encoding",
        "content-length",
        "set-cookie",
        "transfer-encoding",
        "www-authenticate",
    }
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def apply_remote_session_cookie(
    response: Response,
    request: Request,
    remote_headers: httpx.Headers,
    *,
    session_cookie_name: str,
    session_max_age_seconds: int,
    cookie_secure: bool,
) -> None:
    path = request.url.path
    if path == "/auth/logout":
        response.delete_cookie(session_cookie_name, samesite="lax")
        response.delete_cookie("fluentflow_access_token", samesite="lax")
        return
    if path not in {"/auth/login", "/auth/register"}:
        return
    for header in remote_headers.get_list("set-cookie"):
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except Exception:
            continue
        morsel = cookie.get(session_cookie_name)
        if not morsel:
            continue
        max_age_text = morsel.get("max-age")
        try:
            max_age = int(max_age_text) if max_age_text else session_max_age_seconds
        except ValueError:
            max_age = session_max_age_seconds
        response.set_cookie(
            key=session_cookie_name,
            value=morsel.value,
            max_age=max_age,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
        )
        break


def cloud_workspace_unavailable_payload(exc: Exception) -> dict[str, Any]:
    return {
        "detail": {
            "code": "cloud_workspace_unavailable",
            "message": "云端工作区暂时不可用，请稍后重试。",
            "detail": str(exc),
        }
    }


def cloud_workspace_unavailable_response(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content=cloud_workspace_unavailable_payload(exc),
    )


def proxy_should_stream_response(request: Request, remote: httpx.Response) -> bool:
    content_type = (remote.headers.get("content-type") or "").lower()
    path = request.url.path
    return (
        "text/event-stream" in content_type
        or path == "/process"
        or path.endswith("/events")
        or path.startswith("/guest-trial/")
    )


async def proxy_cloud_workspace_request(
    request: Request,
    *,
    base_url: str,
    session_token: str | None,
    session_cookie_name: str,
    session_max_age_seconds: int,
    cookie_secure: bool,
    logger: logging.Logger | None = None,
) -> Response:
    active_logger = logger or logging.getLogger(__name__)
    target = f"{base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    blocked_headers = {
        "connection",
        "content-length",
        "cookie",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    headers = {key: value for key, value in request.headers.items() if key.lower() not in blocked_headers}
    if session_token:
        headers["X-FluentFlow-Session"] = session_token

    async def body_iter() -> AsyncGenerator[bytes, None]:
        async for chunk in request.stream():
            if chunk:
                yield chunk

    client = httpx.AsyncClient(timeout=None, follow_redirects=False)
    stream = client.stream(request.method, target, headers=headers, content=body_iter())
    try:
        remote = await stream.__aenter__()
    except Exception as exc:
        await client.aclose()
        active_logger.warning("Cloud workspace connection failed for %s: %s", target, exc)
        return cloud_workspace_unavailable_response(exc)

    if not proxy_should_stream_response(request, remote):
        try:
            content = await remote.aread()
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.TransportError) as exc:
            active_logger.warning("Cloud workspace response failed for %s: %s", target, exc)
            await stream.__aexit__(type(exc), exc, exc.__traceback__)
            await client.aclose()
            return cloud_workspace_unavailable_response(exc)
        response = Response(
            content=content,
            status_code=remote.status_code,
            headers=proxy_response_headers(remote.headers),
            media_type=remote.headers.get("content-type"),
        )
        apply_remote_session_cookie(
            response,
            request,
            remote.headers,
            session_cookie_name=session_cookie_name,
            session_max_age_seconds=session_max_age_seconds,
            cookie_secure=cookie_secure,
        )
        await stream.__aexit__(None, None, None)
        await client.aclose()
        return response

    async def response_iter() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in remote.aiter_raw():
                if chunk:
                    yield chunk
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.TransportError) as exc:
            active_logger.warning("Cloud workspace stream interrupted for %s: %s", target, exc)
            payload = {
                "stage": "error",
                "code": "cloud_workspace_unavailable",
                "error": "云端工作区暂时不可用，请稍后重试。",
                "detail": str(exc),
            }
            yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        finally:
            await stream.__aexit__(None, None, None)
            await client.aclose()

    response = StreamingResponse(
        response_iter(),
        status_code=remote.status_code,
        headers=proxy_response_headers(remote.headers),
    )
    apply_remote_session_cookie(
        response,
        request,
        remote.headers,
        session_cookie_name=session_cookie_name,
        session_max_age_seconds=session_max_age_seconds,
        cookie_secure=cookie_secure,
    )
    return response
