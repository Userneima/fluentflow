from __future__ import annotations

from fastapi.testclient import TestClient

import backend.main as main


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


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
    assert after.json()["authenticated"] is True
    assert after.json()["user"]["email"] == "owner@example.com"


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
