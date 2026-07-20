from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import backend.main as main
from backend.core.desktop_device_store import authenticate_desktop_credential
from backend.core.local_config import save_sensitive_settings
import backend.core.server_helpers as _H


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_CONFIG_PATH", str(tmp_path / "local-config.json"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _register(client: TestClient) -> dict:
    response = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
    assert response.status_code == 200
    return response.json()["user"]


def test_desktop_pairing_claims_only_a_hash_and_returns_to_local_callback(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app, base_url="http://127.0.0.1:8000") as client:
        user = _register(client)
        start = client.post(
            "/desktop-sync/local/pairing/start",
            json={"cloud_url": "https://cloud.example.com", "display_name": "Study Mac", "platform": "macos"},
        )
        pair_url = start.json()["pair_url"]
        pending = json.loads((tmp_path / "local-config.json").read_text(encoding="utf-8"))
        pending_credential = pending["desktop_sync"]["pending_pairing"]["device_credential"]
        query = parse_qs(urlparse(pair_url).query)
        claim = client.get(
            "/account/desktop-pair",
            params={key: values[0] for key, values in query.items()},
            follow_redirects=False,
        )
        callback = client.get(claim.headers["location"], follow_redirects=False)
        status = client.get("/desktop-sync/local/status")

    assert start.status_code == 200
    assert start.json()["connected"] is False
    assert pending_credential not in pair_url
    assert query["credential_prefix"][0].startswith("ffd_")
    assert "credential_hash" in query
    assert claim.status_code == 303
    assert claim.headers["location"].startswith("http://127.0.0.1:8000/desktop-sync/local/pairing/callback?")
    assert callback.status_code == 303
    assert callback.headers["location"] == "/settings?desktop_sync=connected"
    assert status.status_code == 200
    assert status.json()["sync"]["connected"] is True
    assert status.json()["sync"]["display_name"] == "Study Mac"
    config = json.loads((tmp_path / "local-config.json").read_text(encoding="utf-8"))
    credential = config["desktop_sync"]["device_credential"]
    assert credential.startswith("ffd_")
    auth = authenticate_desktop_credential(credential)
    assert auth and auth["user_id"] == user["id"]
    save_sensitive_settings({"deepseek_api_key": "example-key"})
    preserved = json.loads((tmp_path / "local-config.json").read_text(encoding="utf-8"))
    assert preserved["desktop_sync"]["device_id"] == status.json()["sync"]["device_id"]


def test_cloud_pairing_rejects_non_loopback_callback_before_creating_device(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        _register(client)
        rejected = client.get(
            "/account/desktop-pair",
            params={
                "state": "state",
                "callback_url": "https://attacker.example/callback",
                "credential_hash": "a" * 64,
                "credential_prefix": "ffd_demo...",
                "display_name": "Owner Mac",
                "platform": "macos",
            },
        )
        devices = client.get("/account/devices")

    assert rejected.status_code == 422
    assert devices.status_code == 200
    assert devices.json()["devices"] == []
