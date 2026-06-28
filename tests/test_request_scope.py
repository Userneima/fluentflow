from __future__ import annotations

from fastapi import Request

from backend.core import request_scope


def _request(path: str, *, host: str = "127.0.0.1", local: bool = True) -> Request:
    headers = [(b"x-fluentflow-execution-target", b"local")] if local else []
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "server": (host, 8000),
    })


def test_request_scope_requires_localhost_header_and_allowed_route() -> None:
    assert request_scope.request_is_local_execution(_request("/agent/v1/tasks/task/package")) is True
    assert request_scope.request_is_local_execution(_request("/jobs/task")) is True
    assert request_scope.request_is_local_execution(_request("/process")) is True
    assert request_scope.request_is_local_execution(_request("/runtime-config")) is False
    assert request_scope.request_is_local_execution(_request("/jobs/task", local=False)) is False
    assert request_scope.request_is_local_execution(_request("/jobs/task", host="cloud.example.com")) is False


def test_request_execution_scope_names_local_and_cloud() -> None:
    assert request_scope.request_execution_scope(_request("/jobs/task")) == "local"
    assert request_scope.request_execution_scope(_request("/jobs/task", local=False)) == "cloud"


def test_request_client_id_is_sanitized() -> None:
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/jobs",
        "headers": [(b"x-fluentflow-client-id", b" local user!@# ")],
        "server": ("127.0.0.1", 8000),
    })

    assert request_scope.request_client_id(request) == "localuser"
