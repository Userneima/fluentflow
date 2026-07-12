"""Request scope and execution-target helpers."""

from __future__ import annotations

from typing import Optional

from fastapi import Request


EXECUTION_TARGET_HEADER = "x-fluentflow-execution-target"
EXECUTION_TARGET_LOCAL = "local"
EXECUTION_SCOPE_LOCAL = "local"
EXECUTION_SCOPE_CLOUD = "cloud"

LOCAL_REQUEST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}

LOCAL_EXECUTION_EXACT_PATHS = {
    "/process",
    "/queue/process",
    "/summarize-transcript-file",
    "/regenerate-summary",
    "/export-lark",
    "/video-sources/jobs",
    "/jobs",
}
LOCAL_EXECUTION_PATH_PREFIXES = (
    "/jobs/",
    "/agent/",
)


def normalize_client_id(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    safe = "".join(ch for ch in text if ch.isalnum() or ch in {"-", "_"})
    return safe[:96] or None


def request_client_id(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return normalize_client_id(
        request.headers.get("x-fluentflow-client-id")
        or request.cookies.get("fluentflow_client_id")
    )


def request_is_localhost(request: Request) -> bool:
    client_host = ((request.client.host if request.client else "") or "").strip().lower()
    url_host = (request.url.hostname or "").strip().lower()
    return client_host in LOCAL_REQUEST_HOSTS or url_host in LOCAL_REQUEST_HOSTS


def request_prefers_local_execution(request: Request) -> bool:
    return (request.headers.get(EXECUTION_TARGET_HEADER) or "").strip().lower() == EXECUTION_TARGET_LOCAL


def route_allows_local_execution(path: str) -> bool:
    return path in LOCAL_EXECUTION_EXACT_PATHS or any(
        path.startswith(prefix) for prefix in LOCAL_EXECUTION_PATH_PREFIXES
    )


def request_is_local_execution(request: Request) -> bool:
    return (
        request_prefers_local_execution(request)
        and request_is_localhost(request)
        and route_allows_local_execution(request.url.path)
    )


def request_execution_scope(request: Request) -> str:
    return EXECUTION_SCOPE_LOCAL if request_is_local_execution(request) else EXECUTION_SCOPE_CLOUD
