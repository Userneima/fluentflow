from __future__ import annotations

from fastapi.testclient import TestClient

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
