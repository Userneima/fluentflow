from __future__ import annotations

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import desktop_device_store
import backend.core.server_helpers as _H


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _register(client: TestClient, email: str) -> dict:
    response = client.post("/auth/register", json={"email": email, "password": "secure-pass"})
    assert response.status_code == 200
    return response.json()["user"]


def test_account_can_register_list_and_revoke_its_desktop_device(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        user = _register(client, "owner@example.com")
        registered = client.post(
            "/account/devices",
            json={"platform": "macos", "display_name": "Owner Mac"},
        )
        listed = client.get("/account/devices")
        credential = registered.json()["one_time_credential"]
        auth = desktop_device_store.authenticate_desktop_credential(credential)
        client.post("/auth/logout")
        generic_api_attempt = client.get(
            "/agent/v1/tasks/missing/package",
            headers={"X-FluentFlow-Access-Token": credential},
        )
        client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        revoked = client.post(f"/account/devices/{registered.json()['device']['id']}/revoke")

    assert registered.status_code == 200
    assert credential.startswith("ffd_")
    assert "value" not in registered.json()["device"]["credential"]
    assert listed.status_code == 200
    assert listed.json()["devices"][0]["display_name"] == "Owner Mac"
    assert auth == {
        "credential_id": registered.json()["device"]["credential"]["id"],
        "device_id": registered.json()["device"]["id"],
        "user_id": user["id"],
        "owner_scope": f"user:{user['id']}",
        "display_name": "Owner Mac",
        "platform": "macos",
        "scopes": ["sync"],
    }
    assert generic_api_attempt.status_code == 401
    assert revoked.status_code == 200
    assert revoked.json()["device"]["revoked_at"]
    assert desktop_device_store.authenticate_desktop_credential(credential) is None


def test_desktop_device_isolated_to_its_account(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_ALLOW_SIGNUPS", "1")

    with TestClient(main.app) as client:
        _register(client, "owner@example.com")
        owner_device = client.post(
            "/account/devices",
            json={"platform": "windows", "display_name": "Owner PC"},
        ).json()["device"]
        client.post("/auth/logout")
        _register(client, "other@example.com")
        other_list = client.get("/account/devices")
        cross_account_revoke = client.post(f"/account/devices/{owner_device['id']}/revoke")
        client.post("/auth/logout")
        client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        owner_list = client.get("/account/devices")

    assert other_list.json()["devices"] == []
    assert cross_account_revoke.status_code == 404
    assert owner_list.json()["devices"][0]["id"] == owner_device["id"]
    assert owner_list.json()["devices"][0]["revoked_at"] is None


def test_desktop_device_registration_rejects_unsupported_platform_and_paths(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        _register(client, "owner@example.com")
        unsupported = client.post("/account/devices", json={"platform": "linux"})
        path_like_name = client.post(
            "/account/devices",
            json={"platform": "windows", "display_name": "C:\\Users\\owner"},
        )

    assert unsupported.status_code == 422
    assert "platform" in unsupported.json()["detail"]
    assert path_like_name.status_code == 422
    assert "file path" in path_like_name.json()["detail"]
