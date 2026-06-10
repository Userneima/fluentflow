from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import backend.main as main


def test_auth_status_is_open_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {"access_required": False, "authenticated": True}


def test_auth_middleware_rejects_api_without_access_code(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        rejected = client.get("/jobs")
        allowed = client.get("/jobs", headers={"X-FluentFlow-Access-Token": "beta-code"})

    assert rejected.status_code == 401
    assert allowed.status_code == 200


def test_auth_login_sets_cookie(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCESS_TOKEN", "beta-code")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.post("/auth/login", json={"access_token": "beta-code"})
        jobs = client.get("/jobs")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert jobs.status_code == 200


def test_queue_file_limit_rejects_before_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_QUEUE_FILES", "1")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

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
    assert main._duration_limit_error(120, "demo.mp4") is not None

    monkeypatch.setenv("FLUENTFLOW_MAX_MEDIA_DURATION_SECONDS", "0")
    assert main._duration_limit_error(120, "demo.mp4") is None


def test_friendly_error_message_translates_common_azure_errors() -> None:
    message = (
        'Azure Batch transcription submit failed: HTTP 400 { "code": "InvalidRequest", '
        '"message": "Only \\"Standard\\" subscriptions for the region of the called service are valid." }'
    )

    assert "Standard 订阅" in main._friendly_error_message(message)


def test_friendly_error_message_keeps_video_link_failures_actionable() -> None:
    assert "直接上传视频文件" in main._friendly_error_message("暂时无法自动解析这个视频链接，请上传视频文件")


def test_public_mode_defaults_to_cloud_transcription(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", raising=False)

    assert main._allowed_stt_providers() == ("azure_batch",)
    assert main._normalize_stt_provider("local") == "azure_batch"


def test_explicit_provider_allowlist_preserves_local_dev(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_PUBLIC_MODE", raising=False)
    monkeypatch.setenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", "local,azure_batch")
    monkeypatch.setenv("FLUENTFLOW_DEFAULT_STT_PROVIDER", "local")

    assert main._allowed_stt_providers() == ("local", "azure_batch")
    assert main._normalize_stt_provider(None) == "local"


def test_active_job_limit_blocks_new_work_but_allows_same_task(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT", "1")
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "existing", "status": "running"},
            {"task_id": "done", "status": "completed"},
        ],
    )

    with pytest.raises(main.HTTPException):
        main._enforce_active_job_limit("client-a", incoming=1)

    main._enforce_active_job_limit("client-a", incoming=1, exclude_task_id="existing")


def test_daily_job_quota_blocks_excess_submissions(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    yesterday = (datetime.now(timezone.utc).astimezone() - timedelta(days=1)).isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "2")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "0")
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 10},
            {"task_id": "today-b", "created_at": now, "source_file_size_mb": 10},
            {"task_id": "old", "created_at": yesterday, "source_file_size_mb": 10},
        ],
    )

    with pytest.raises(main.HTTPException) as exc:
        main._enforce_daily_quota("client-a", incoming_jobs=1)

    assert exc.value.status_code == 429
    assert "每日上限" in exc.value.detail


def test_daily_upload_quota_blocks_excess_upload_mb(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", "0")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", "100")
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 80},
        ],
    )

    with pytest.raises(main.HTTPException) as exc:
        main._enforce_daily_quota("client-a", incoming_upload_mb=30)

    assert exc.value.status_code == 429
    assert "上传额度" in exc.value.detail


def test_global_active_job_limit_blocks_server_overload(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL", "2")
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "running-a", "status": "running"},
            {"task_id": "queued-b", "status": "queued"},
            {"task_id": "done", "status": "completed"},
        ],
    )

    with pytest.raises(main.HTTPException) as exc:
        main._enforce_global_active_job_limit(incoming=1)

    assert exc.value.status_code == 429
    assert "全站最多同时运行" in exc.value.detail


def test_global_daily_upload_quota_blocks_excess_usage(monkeypatch) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    monkeypatch.setenv("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL", "0")
    monkeypatch.setenv("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL", "100")
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda *args, **kwargs: [
            {"task_id": "today-a", "created_at": now, "source_file_size_mb": 90},
        ],
    )

    with pytest.raises(main.HTTPException) as exc:
        main._enforce_global_daily_quota(incoming_upload_mb=20)

    assert exc.value.status_code == 429
    assert "全站已使用" in exc.value.detail


def test_submission_rate_limit_blocks_repeated_requests(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP", "2")
    monkeypatch.setenv("FLUENTFLOW_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS", "60")
    main._SUBMISSION_RATE_EVENTS.clear()
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.10"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    main._enforce_submission_rate_limit(request, incoming=1)
    main._enforce_submission_rate_limit(request, incoming=1)

    with pytest.raises(main.HTTPException) as exc:
        main._enforce_submission_rate_limit(request, incoming=1)

    assert exc.value.status_code == 429
    assert "提交过于频繁" in exc.value.detail
    main._SUBMISSION_RATE_EVENTS.clear()


def test_runtime_config_exposes_public_mode_without_secrets(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_PUBLIC_MODE", "1")
    monkeypatch.delenv("FLUENTFLOW_ALLOWED_STT_PROVIDERS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)

    with TestClient(main.app) as client:
        response = client.get("/runtime-config")

    payload = response.json()
    assert response.status_code == 200
    assert payload["public_mode"] is True
    assert payload["allowed_stt_providers"] == ["azure_batch"]
    assert payload["show_maintainer_settings"] is False
    assert "key" not in str(payload).lower()
