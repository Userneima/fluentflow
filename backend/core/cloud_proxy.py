"""Cloud workspace proxy helpers."""

from __future__ import annotations

import logging
from http.cookies import SimpleCookie
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException, Request, Response
from fastapi.responses import StreamingResponse


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


def should_stream_cloud_proxy_response(path: str, headers: httpx.Headers) -> bool:
    content_type = (headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type:
        return True
    if headers.get("content-disposition"):
        return True
    if path == "/process" or path.endswith("/events"):
        return True
    if path.endswith("/source") or "/artifacts/" in path:
        return True
    return False


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

    async def send_once() -> Response:
        client = httpx.AsyncClient(timeout=None, follow_redirects=False)
        content = None if request.method.upper() in {"GET", "HEAD"} else body_iter()
        stream = client.stream(request.method, target, headers=headers, content=content)
        try:
            remote = await stream.__aenter__()
        except Exception as exc:
            await client.aclose()
            active_logger.warning("Cloud workspace connection failed for %s: %s", target, exc)
            raise HTTPException(status_code=502, detail=f"Cloud workspace unavailable: {exc}") from exc

        async def response_iter() -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in remote.aiter_bytes():
                    if chunk:
                        yield chunk
            finally:
                await stream.__aexit__(None, None, None)
                await client.aclose()

        response_headers = proxy_response_headers(remote.headers)
        if should_stream_cloud_proxy_response(request.url.path, remote.headers):
            response = StreamingResponse(
                response_iter(),
                status_code=remote.status_code,
                headers=response_headers,
            )
        else:
            try:
                body = await remote.aread()
            finally:
                await stream.__aexit__(None, None, None)
                await client.aclose()
            response = Response(
                content=body,
                status_code=remote.status_code,
                headers=response_headers,
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
        return response

    try:
        return await send_once()
    except httpx.RemoteProtocolError:
        if request.method.upper() in {"GET", "HEAD"} and not should_stream_cloud_proxy_response(request.url.path, httpx.Headers()):
            try:
                return await send_once()
            except httpx.RemoteProtocolError as exc:
                raise HTTPException(status_code=502, detail=f"Cloud workspace response was incomplete: {exc}") from exc
        raise
