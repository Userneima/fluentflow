from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import job_store


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _patch_job_store(monkeypatch, db_path: Path) -> None:
    monkeypatch.setattr(
        main,
        "upsert_job",
        lambda **kwargs: job_store.upsert_job(**kwargs, db_path=db_path),
    )
    monkeypatch.setattr(
        main,
        "get_job",
        lambda task_id, client_id=None: job_store.get_job(task_id, db_path=db_path, client_id=client_id),
    )
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda limit=50, client_id=None: job_store.list_jobs(limit=limit, db_path=db_path, client_id=client_id),
    )
    monkeypatch.setattr(
        main,
        "list_jobs_for_retention",
        lambda client_id=None: job_store.list_jobs_for_retention(db_path=db_path, client_id=client_id),
    )


def test_account_status_bootstraps_first_admin(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        status = client.get("/auth/status")
        register = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        after = client.get("/auth/status")

    assert status.status_code == 200
    assert status.json()["auth_mode"] == "accounts"
    assert status.json()["account_required"] is True
    assert status.json()["bootstrap_required"] is True
    assert register.status_code == 200
    assert register.json()["user"]["role"] == "admin"
    assert register.json()["user"]["quota"]["balance_units"] == 100
    assert after.json()["authenticated"] is True
    assert after.json()["user"]["email"] == "owner@example.com"
    assert after.json()["user"]["quota"]["balance_units"] == 100


def test_account_middleware_rejects_api_without_session(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        response = client.get("/jobs")

    assert response.status_code == 401
    assert response.json()["account_required"] is True


def test_account_login_sets_session_cookie(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        rejected = client.get("/jobs")
        login = client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        allowed = client.get("/jobs")

    assert rejected.status_code == 401
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "owner@example.com"
    assert login.json()["user"]["quota"]["balance_units"] == 100
    assert allowed.status_code == 200


def test_account_registration_requires_signup_flag_after_bootstrap(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        first = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        blocked = client.post("/auth/register", json={"email": "user@example.com", "password": "secure-pass"})

    assert first.status_code == 200
    assert blocked.status_code == 403


def test_account_scope_replaces_device_scope(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    captured = {}

    def fake_list_jobs(*args, **kwargs):
        captured["client_id"] = kwargs.get("client_id")
        return []

    monkeypatch.setattr(main, "list_jobs", fake_list_jobs)

    with TestClient(main.app) as client:
        register = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        response = client.get("/jobs", headers={"X-FluentFlow-Client-Id": "browser-device"})

    assert register.status_code == 200
    assert response.status_code == 200
    assert captured["client_id"] == f"user:{register.json()['user']['id']}"


def test_cloud_workspace_proxy_bypasses_local_account_gate(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", "http://cloud.example")

    async def fake_proxy(request):
        return main.JSONResponse({"proxied": request.url.path})

    monkeypatch.setattr(main, "_proxy_cloud_workspace_request", fake_proxy)

    with TestClient(main.app) as client:
        response = client.get("/jobs")

    assert response.status_code == 200
    assert response.json() == {"proxied": "/jobs"}


def test_account_quota_endpoint_and_admin_adjustment(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_ALLOW_SIGNUPS", "1")

    with TestClient(main.app) as client:
        admin = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        user = client.post("/auth/register", json={"email": "user@example.com", "password": "secure-pass"})
        user_id = user.json()["user"]["id"]
        user_quota = client.get("/account/quota")
        forbidden = client.get("/admin/users")
        client.post("/auth/logout")
        client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        users = client.get("/admin/users")
        adjustment = client.post(
            f"/admin/users/{user_id}/balance-adjustments",
            json={"units": 25, "reason": "manual beta recharge", "provider_reference": "test-ref"},
        )

    assert admin.status_code == 200
    assert user_quota.status_code == 200
    assert user_quota.json()["balance_units"] == 100
    assert forbidden.status_code == 403
    assert users.status_code == 200
    assert any(item["email"] == "user@example.com" for item in users.json()["users"])
    assert adjustment.status_code == 200
    assert adjustment.json()["user"]["quota"]["balance_units"] == 125
    assert adjustment.json()["transaction"]["provider_reference"] == "test-ref"


def test_account_user_without_balance_cannot_start_processing(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_ALLOW_SIGNUPS", "1")
    monkeypatch.setenv("FLUENTFLOW_STARTER_BALANCE_UNITS", "0")
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(main, "_media_duration_seconds", lambda *_args, **_kwargs: 600.0)

    with TestClient(main.app) as client:
        client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        user = client.post("/auth/register", json={"email": "user@example.com", "password": "secure-pass"})
        response = client.post(
            "/process",
            files={"file": ("sample.mp3", b"not-real-audio", "audio/mpeg")},
        )

    assert user.status_code == 200
    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["required_units"] > detail["balance_units"]


def test_account_import_history_creates_account_job_and_dedupes(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    _patch_job_store(monkeypatch, tmp_path / "jobs.sqlite")
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    entry = {
        "taskId": "local-task-1",
        "name": "Local lesson.mp4",
        "timestamp": 1_718_000_000_000,
        "source": "local_desktop",
        "sourceFingerprint": "fingerprint-1",
        "transcriptText": "hello from local history",
        "segments": [{"start": 0, "end": 1.2, "text": "hello from local history"}],
        "summary": "## Summary\nLocal note",
        "audioDurationSec": 72,
        "sttElapsedSec": 8,
        "sttProvider": "azure_batch",
    }

    with TestClient(main.app) as client:
        unauthenticated = client.post("/account/import-history", json={"entries": [entry]})
        register = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        first = client.post("/account/import-history", json={"entries": [entry]})
        second = client.post("/account/import-history", json={"entries": [entry]})
        jobs = client.get("/jobs")

    assert unauthenticated.status_code == 401
    assert register.status_code == 200
    assert first.status_code == 200
    assert first.json()["imported_count"] == 1
    assert first.json()["imported"][0]["client_id"] == f"user:{register.json()['user']['id']}"
    assert first.json()["imported"][0]["result"]["transcript_text"] == "hello from local history"
    assert second.status_code == 200
    assert second.json()["imported_count"] == 0
    assert second.json()["skipped"][0]["reason"] == "duplicate"
    assert jobs.status_code == 200
    assert len(jobs.json()["jobs"]) == 1
