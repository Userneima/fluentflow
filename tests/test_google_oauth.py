from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import google_oauth
from backend.core.account_store import get_oauth_identity
import backend.core.server_helpers as _H


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("FLUENTFLOW_ALLOW_SIGNUPS", "0")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _patch_google_user(monkeypatch, *, sub: str = "google-sub", email: str = "google@example.com") -> None:
    monkeypatch.setattr(
        google_oauth,
        "exchange_google_oauth_code",
        lambda *, code, redirect_uri, timeout=15: {"access_token": f"token-for-{code}"},
    )
    monkeypatch.setattr(
        google_oauth,
        "fetch_google_userinfo",
        lambda access_token, timeout=15: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": "Google User",
            "picture": "https://example.com/avatar.png",
        },
    )


def _start_state(client: TestClient, next_url: str = "/app") -> str:
    start = client.post("/auth/google/start", json={"next_url": next_url})
    assert start.status_code == 200
    parsed = urlparse(start.json()["authorize_url"])
    params = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert params["scope"] == ["openid email profile"]
    assert params["client_id"] == ["google-client"]
    assert params["redirect_uri"][0].endswith("/auth/google/callback")
    return params["state"][0]


def test_auth_status_exposes_google_oauth_when_configured(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        status = client.get("/auth/status")

    assert status.status_code == 200
    assert status.json()["google_oauth_enabled"] is True


def test_google_oauth_bootstraps_first_admin(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    _patch_google_user(monkeypatch, sub="admin-sub", email="owner@example.com")

    with TestClient(main.app) as client:
        state = _start_state(client, "/media-text")
        callback = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        status = client.get("/auth/status")

    assert callback.status_code == 303
    assert callback.headers["location"] == "/media-text"
    assert status.json()["authenticated"] is True
    assert status.json()["user"]["email"] == "owner@example.com"
    assert status.json()["user"]["role"] == "admin"
    assert status.json()["user"]["quota"]["balance_units"] == 100
    identity = get_oauth_identity("google", "admin-sub", db_path=tmp_path / "accounts.sqlite")
    assert identity and identity["email"] == "owner@example.com"


def test_google_oauth_links_existing_verified_email_when_signups_closed(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    _patch_google_user(monkeypatch, sub="existing-sub", email="owner@example.com")

    with TestClient(main.app) as client:
        created = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        state = _start_state(client)
        callback = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        status = client.get("/auth/status")

    assert created.status_code == 200
    assert callback.status_code == 303
    assert status.json()["authenticated"] is True
    assert status.json()["user"]["email"] == "owner@example.com"
    assert status.json()["user"]["id"] == created.json()["user"]["id"]


def test_google_oauth_rejects_new_account_when_signups_closed(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    _patch_google_user(monkeypatch, sub="new-sub", email="new@example.com")

    with TestClient(main.app) as client:
        client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        state = _start_state(client)
        callback = client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )
        status = client.get("/auth/status")

    assert callback.status_code == 303
    assert "auth_error=" in callback.headers["location"]
    assert status.json()["authenticated"] is False
    assert get_oauth_identity("google", "new-sub", db_path=tmp_path / "accounts.sqlite") is None
