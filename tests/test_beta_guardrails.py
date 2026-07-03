from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

import backend.main as main
import backend.core.server_helpers as _H


def test_auth_status_is_open_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.get("/auth/status")

    assert response.status_code == 200
    request = Request({"type": "http", "method": "GET", "path": "/jobs", "headers": [], "server": ("testclient", 80)})
    assert _H._request_client_scope(request) == "anonymous"
    payload = response.json()
    assert payload["access_required"] is False
    assert payload["authenticated"] is True


def test_auth_middleware_rejects_api_without_access_code(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        rejected = client.get("/jobs")
        allowed = client.get("/jobs", headers={"X-FluentFlow-Access-Token": "beta-code"})

    assert rejected.status_code == 401
    assert allowed.status_code == 200


def test_auth_login_sets_cookie(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.post("/auth/login", json={"access_token": "beta-code"})
        jobs = client.get("/jobs")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert jobs.status_code == 200


def test_local_vite_origin_can_preflight_login_with_credentials(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_AUTH_MODE", "accounts")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-fluentflow-client-id",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_external_origin_does_not_receive_wildcard_login_cors(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_AUTH_MODE", "accounts")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.options(
            "/auth/login",
            headers={
                "Origin": "https://example.invalid",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-fluentflow-client-id",
            },
        )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") != "*"


def test_queue_file_limit_rejects_before_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_QUEUE_FILES", "1")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.post(
            "/queue/process",
            files=[
                ("files", ("one.mp4", b"one", "video/mp4")),
                ("files", ("two.mp4", b"two", "video/mp4")),
            ],
        )

    assert response.status_code == 413
    assert "Too many files" in response.json()["detail"]


def test_duration_limit_error_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS", "60")
    assert _H._duration_limit_error(120, "demo.mp4") is not None

    monkeypatch.setenv("FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS", "0")
    assert _H._duration_limit_error(120, "demo.mp4") is None


def test_friendly_error_message_translates_common_azure_errors() -> None:
    message = (
        'Azure Batch transcription submit failed: HTTP 400 { "code": "InvalidRequest", '
        '"message": "Only \\"Standard\\" subscriptions for the region of the called service are valid." }'
    )

    assert "Standard 订阅" in _H._friendly_error_message(message)


def test_friendly_error_message_keeps_video_link_failures_actionable() -> None:
    assert "直接上传视频文件" in _H._friendly_error_message("暂时无法自动解析这个视频链接，请上传视频文件")


def test_public_mode_defaults_to_cloud_transcription(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", raising=False)

    assert _H._allowed_stt_providers() == ("elevenlabs_scribe",)
    assert _H._normalize_stt_provider("local") == "elevenlabs_scribe"


def test_cloud_alias_resolves_to_elevenlabs(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_PUBLIC_MODE", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", raising=False)

    assert _H._normalize_stt_provider("cloud") == "elevenlabs_scribe"
    assert _H._normalize_stt_provider("cloud_stt") == "elevenlabs_scribe"


def test_public_mode_keeps_cloud_admin_on_cloud_transcription(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", raising=False)
    monkeypatch.setattr(_H, "_request_account_user", lambda request: {"id": "admin", "role": "admin"})
    request = Request({"type": "http", "method": "GET", "path": "/runtime-config", "headers": [], "server": ("cloud.example.com", 443)})

    assert _H._allowed_stt_providers(request) == ("elevenlabs_scribe",)
    assert _H._normalize_stt_provider("local", request) == "elevenlabs_scribe"


def test_public_mode_allows_localhost_to_choose_local_transcription(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", raising=False)
    request = Request({"type": "http", "method": "GET", "path": "/runtime-config", "headers": [], "server": ("127.0.0.1", 8000)})

    assert _H._allowed_stt_providers(request) == ("elevenlabs_scribe", "local")
    assert _H._normalize_stt_provider("local", request) == "local"


def test_cloud_workspace_keeps_local_capability_routes_on_localhost(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", "https://cloud.example.com")

    runtime_request = Request({
        "type": "http",
        "method": "GET",
        "path": "/runtime-config",
        "headers": [],
        "server": ("127.0.0.1", 8000),
    })
    local_process_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/process",
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": ("127.0.0.1", 8000),
    })
    cloud_process_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/process",
        "headers": [],
        "server": ("127.0.0.1", 8000),
    })
    local_video_source_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/video-sources/jobs",
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": ("127.0.0.1", 8000),
    })
    local_job_events_request = Request({
        "type": "http",
        "method": "GET",
        "path": "/jobs/task-local/events",
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": ("127.0.0.1", 8000),
    })
    local_jobs_request = Request({
        "type": "http",
        "method": "GET",
        "path": "/jobs",
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": ("127.0.0.1", 8000),
    })
    remote_local_process_request = Request({
        "type": "http",
        "method": "POST",
        "path": "/process",
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": ("cloud.example.com", 443),
    })

    assert _H._should_proxy_cloud_workspace(runtime_request) is False
    assert _H._should_proxy_cloud_workspace(local_process_request) is False
    assert _H._should_proxy_cloud_workspace(local_video_source_request) is False
    assert _H._should_proxy_cloud_workspace(local_job_events_request) is False
    assert _H._should_proxy_cloud_workspace(cloud_process_request) is True
    assert _H._request_is_local_execution(local_process_request) is True
    assert _H._request_is_local_execution(local_jobs_request) is True
    assert _H._request_is_local_execution(remote_local_process_request) is False


def test_cloud_workspace_buffers_json_api_but_streams_long_running_routes() -> None:
    json_headers = _H.httpx.Headers({"content-type": "application/json"})
    event_headers = _H.httpx.Headers({"content-type": "text/event-stream"})
    download_headers = _H.httpx.Headers({"content-disposition": 'attachment; filename="source.mp4"'})

    assert _H._should_stream_cloud_proxy_response("/jobs", json_headers) is False
    assert _H._should_stream_cloud_proxy_response("/auth/status", json_headers) is False
    assert _H._should_stream_cloud_proxy_response("/process", event_headers) is True
    assert _H._should_stream_cloud_proxy_response("/jobs/task-1/events", json_headers) is True
    assert _H._should_stream_cloud_proxy_response("/jobs/task-1/source", download_headers) is True


def test_cloud_workspace_retries_incomplete_buffered_get(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", "https://cloud.example.com")

    class DummyRemote:
        status_code = 200
        headers = _H.httpx.Headers({"content-type": "application/json"})

        def __init__(self, fail: bool):
            self.fail = fail

        async def aread(self):
            if self.fail:
                raise _H.httpx.RemoteProtocolError("peer closed connection without sending complete message body")
            return b'{"jobs":[]}'

        async def aiter_bytes(self):
            yield b'{"jobs":[]}'

    class DummyStream:
        def __init__(self, remote):
            self.remote = remote

        async def __aenter__(self):
            return self.remote

        async def __aexit__(self, *_args):
            return None

    class DummyAsyncClient:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        def stream(self, *_args, **_kwargs):
            type(self).calls += 1
            return DummyStream(DummyRemote(fail=type(self).calls == 1))

        async def aclose(self):
            return None

    monkeypatch.setattr(_H.httpx, "AsyncClient", DummyAsyncClient)
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/jobs",
        "query_string": b"limit=100",
        "headers": [],
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
    })

    response = asyncio.run(_H._proxy_cloud_workspace_request(request))

    assert response.status_code == 200
    assert response.body == b'{"jobs":[]}'
    assert DummyAsyncClient.calls == 2


def test_local_status_routes_are_public_only_on_localhost() -> None:
    local_request = Request({
        "type": "http",
        "method": "GET",
        "path": "/credentials/status",
        "headers": [],
        "server": ("127.0.0.1", 8000),
    })
    public_request = Request({
        "type": "http",
        "method": "GET",
        "path": "/credentials/status",
        "headers": [],
        "server": ("cloud.example.com", 443),
    })

    assert _H._is_public_request(local_request) is True
    assert _H._is_public_request(public_request) is False


def test_local_execution_bypasses_account_middleware_on_localhost(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.delenv("FLUENTFLOW_AUTH_MODE", raising=False)
    monkeypatch.delenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", raising=False)
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/process",
        "headers": [(b"x-fluentflow-execution-target", b"local"), (b"x-fluentflow-client-id", b"local-client")],
        "server": ("127.0.0.1", 8000),
    })

    async def call_next(_request):
        return JSONResponse({"ok": True})

    response = asyncio.run(_H.beta_access_middleware(request, call_next))

    assert response.status_code == 200
    assert _H._request_client_scope(request) == "local-client"


def test_local_history_candidates_endpoint_is_removed(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", "https://cloud.example.com")

    with TestClient(main.app) as client:
        response = client.get("/local-history/candidates?limit=20")

    assert response.status_code == 410


def test_public_cloud_filters_explicit_local_provider(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "local,elevenlabs_scribe")
    request = Request({"type": "http", "method": "GET", "path": "/runtime-config", "headers": [], "server": ("cloud.example.com", 443)})

    assert _H._allowed_stt_providers(request) == ("elevenlabs_scribe",)


def test_explicit_provider_allowlist_preserves_local_dev(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_PUBLIC_MODE", raising=False)
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "local,elevenlabs_scribe")
    monkeypatch.setenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", "local")

    assert _H._allowed_stt_providers() == ("local", "elevenlabs_scribe")
    assert _H._normalize_stt_provider(None) == "local"


def test_active_job_limit_blocks_new_work_but_allows_same_task(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT", "1")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "existing", "status": "running"},
            {"task_id": "done", "status": "completed"},
        ],
    )

    with pytest.raises(HTTPException):
        _H._enforce_active_job_limit("client-a", incoming=1)

    _H._enforce_active_job_limit("client-a", incoming=1, exclude_task_id="existing")


def test_daily_job_quota_blocks_excess_submissions(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    yesterday = (datetime.now(timezone.utc).astimezone() - timedelta(days=1)).isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "2")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "0")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 10},
            {"task_id": "today-b", "created_at": now, "source_file_size_mb": 10},
            {"task_id": "old", "created_at": yesterday, "source_file_size_mb": 10},
        ],
    )

    with pytest.raises(HTTPException) as exc:
        _H._enforce_daily_quota("client-a", incoming_jobs=1)

    assert exc.value.status_code == 429
    assert "每日上限" in exc.value.detail


def test_daily_job_quota_ignores_imported_history(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "2")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "0")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {
                "task_id": "imported-a",
                "created_at": now,
                "source_type": "imported_local_history",
                "source_file_size_mb": 10,
                "metadata": {"imported_by_account_id": "account-1"},
                "result": {"imported_from_local_history": True},
            },
            {
                "task_id": "imported-b",
                "created_at": now,
                "source_type": "imported_local_history",
                "source_file_size_mb": 10,
                "metadata": {"imported_by_account_id": "account-1"},
            },
        ],
    )

    _H._enforce_daily_quota("user:account-1", incoming_jobs=1)


def test_daily_quota_skips_admin_client_scope(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "1")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL", "1")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "0")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL", "0")
    monkeypatch.setattr(
        _H,
        "get_user_by_id",
        lambda account_id: {"id": account_id, "role": "admin"},
    )
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 10},
            {"task_id": "today-b", "created_at": now, "source_file_size_mb": 10},
        ],
    )

    _H._enforce_daily_quota("user:admin-1", incoming_jobs=1)
    _H._enforce_global_daily_quota(client_id="user:admin-1", incoming_jobs=1)


def test_daily_upload_quota_blocks_excess_upload_mb(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "0")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "100")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 80},
        ],
    )

    with pytest.raises(HTTPException) as exc:
        _H._enforce_daily_quota("client-a", incoming_upload_mb=30)

    assert exc.value.status_code == 429
    assert "上传额度" in exc.value.detail


def test_global_active_job_limit_blocks_server_overload(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL", "2")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "running-a", "status": "running"},
            {"task_id": "queued-b", "status": "queued"},
            {"task_id": "done", "status": "completed"},
        ],
    )

    with pytest.raises(HTTPException) as exc:
        _H._enforce_global_active_job_limit(incoming=1)

    assert exc.value.status_code == 429
    assert "全站最多同时运行" in exc.value.detail


def test_global_daily_upload_quota_blocks_excess_usage(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL", "0")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL", "100")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 90},
        ],
    )

    with pytest.raises(HTTPException) as exc:
        _H._enforce_global_daily_quota(incoming_upload_mb=20)

    assert exc.value.status_code == 429
    assert "全站已使用" in exc.value.detail


def test_submission_rate_limit_blocks_repeated_requests(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP", "2")
    monkeypatch.setenv("FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS", "60")
    _H._SUBMISSION_RATE_EVENTS.clear()
    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="203.0.113.10"),
    )

    _H._enforce_submission_rate_limit(request, incoming=1)
    _H._enforce_submission_rate_limit(request, incoming=1)

    with pytest.raises(HTTPException) as exc:
        _H._enforce_submission_rate_limit(request, incoming=1)

    assert exc.value.status_code == 429
    assert "提交过于频繁" in exc.value.detail
    _H._SUBMISSION_RATE_EVENTS.clear()


def test_history_retention_prunes_oldest_completed_task_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", str(tmp_path / "edited"))
    monkeypatch.setenv("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", str(tmp_path / "edit-records"))
    monkeypatch.setenv("FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT", "1")
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_RETENTION_DAYS", "0")
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    jobs = [
        {"task_id": "keep", "status": "completed", "updated_at": now, "metadata": {}},
        {"task_id": "prune", "status": "completed", "updated_at": now, "metadata": {}},
    ]
    for task_id in ("keep", "prune"):
        (tmp_path / "sources" / task_id).mkdir(parents=True)
        (tmp_path / "sources" / task_id / "source.mp4").write_bytes(b"video")
        (tmp_path / "artifacts" / task_id).mkdir(parents=True)
        (tmp_path / "artifacts" / task_id / "audio.mp3").write_bytes(b"audio")
    deleted: list[str] = []
    monkeypatch.setattr(_H, "list_jobs_for_retention", lambda client_id=None: jobs)
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.extend(task_ids) or len(task_ids))

    result = _H._enforce_history_retention("client-a")

    assert result["task_ids"] == ["prune"]
    assert deleted == ["prune"]
    assert (tmp_path / "sources" / "keep").is_dir()
    assert not (tmp_path / "sources" / "prune").exists()
    assert not (tmp_path / "artifacts" / "prune").exists()


def test_runtime_config_exposes_public_mode_without_secrets(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.get("/runtime-config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["public_mode"] is True
    assert payload["allowed_stt_providers"] == ["elevenlabs_scribe"]
    assert payload["show_maintainer_settings"] is False
    assert payload["features"]["job_retry_from_stored_source"] is True
    assert "key" not in str(payload).lower()


def test_startup_recovery_requeues_restorable_jobs_and_fails_missing_sources(tmp_path, monkeypatch) -> None:
    source_path = tmp_path / "sources" / "task-ok" / "source.mp4"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"video")
    jobs = [
        {
            "task_id": "task-ok",
            "status": "running",
            "client_id": "client-a",
            "source_filename": "ok.mp4",
            "metadata": {"queue_options": {"stt_provider": "azure_batch"}, "source_path": str(source_path)},
        },
        {
            "task_id": "task-missing",
            "status": "queued",
            "client_id": "client-a",
            "source_filename": "missing.mp4",
            "metadata": {"queue_options": {"stt_provider": "azure_batch"}, "source_path": str(tmp_path / "missing.mp4")},
        },
    ]
    updates: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(_H, "list_jobs", lambda *args, **kwargs: jobs)
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: updates.append(kwargs))
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    _H._resume_queued_transcription_jobs(base_url="http://127.0.0.1:8000")

    assert [item["task_id"] for item in enqueued] == ["task-ok"]
    assert any(item["task_id"] == "task-ok" and item["status"] == "queued" for item in updates)
    assert any(item["task_id"] == "task-missing" and item["status"] == "failed" for item in updates)


def test_job_metadata_update_preserves_queue_recovery_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "client_id": client_id,
            "metadata": {
                "route": "/queue/process",
                "queue_options": {"stt_provider": "azure_batch"},
                "source_path": "/var/lib/fluentflow/sources/task/source.mp4",
            },
        },
    )

    metadata = _H._job_metadata_for_update(
        "task",
        "client-a",
        route="/process",
        source_fingerprint={"sha256": "abc"},
    )

    assert metadata["route"] == "/process"
    assert metadata["queue_options"] == {"stt_provider": "azure_batch"}
    assert metadata["source_path"] == "/var/lib/fluentflow/sources/task/source.mp4"
    assert metadata["source_fingerprint"] == {"sha256": "abc"}


def test_ops_status_reports_stale_jobs_without_secret_values(tmp_path, monkeypatch) -> None:
    old_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_STALE_JOB_SECONDS", "60")
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", str(tmp_path / "edited"))
    monkeypatch.setenv("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", str(tmp_path / "edit-records"))
    monkeypatch.setenv("FLUENTFLOW_VIDEO_SOURCE_DIR", str(tmp_path / "videos"))
    monkeypatch.setenv("AZURE_SPEECH_KEY", "super-secret-value")
    monkeypatch.setattr(
        _H,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "stale", "status": "running", "stage": "stt", "updated_at": old_time, "source_filename": "demo.mp4"},
            {"task_id": "done", "status": "completed", "stage": "done", "updated_at": old_time},
        ],
    )

    payload = _H._ops_status_payload()

    assert payload["status"] == "warn"
    assert payload["jobs"]["stale_count"] == 1
    assert "super-secret-value" not in str(payload)
