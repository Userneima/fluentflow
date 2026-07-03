from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import backend.main as main
import backend.core.server_helpers as H
from backend.core import feishu_oauth


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.setenv("LARK_APP_ID", "cli_test")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _register(client: TestClient) -> str:
    response = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
    assert response.status_code == 200
    return response.json()["user"]["id"]


def test_feishu_connection_status_and_disconnect_never_return_tokens(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        user_id = _register(client)
        initial = client.get("/account/feishu/connection")
        H.save_feishu_connection(
            user_id,
            access_token="user-access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            refresh_expires_in=86400,
            feishu_open_id="ou_demo",
            feishu_union_id="on_demo",
            tenant_key="tenant_demo",
        )
        connected = client.get("/account/feishu/connection")
        disconnected = client.post("/account/feishu/disconnect")

    assert initial.json()["connection"]["connected"] is False
    assert connected.json()["connection"]["connected"] is True
    assert connected.json()["connection"]["feishu_open_id"] == "ou_demo"
    assert "user-access-token" not in str(connected.json())
    assert "refresh-token" not in str(connected.json())
    assert disconnected.json()["connection"]["connected"] is False
    assert "refresh-token" not in str(disconnected.json())


def test_feishu_oauth_start_and_callback_store_connection(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    def fake_exchange(*, code: str, redirect_uri: str, timeout: int = 15) -> dict:
        assert code == "auth-code"
        assert redirect_uri.startswith("http://testserver/account/feishu/oauth/callback")
        return {
            "access_token": "user-access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "refresh_expires_in": 86400,
            "open_id": "ou_demo",
            "union_id": "on_demo",
            "user_id": "feishu_user",
            "tenant_key": "tenant_demo",
        }

    monkeypatch.setattr(feishu_oauth, "exchange_feishu_oauth_code", fake_exchange)

    with TestClient(main.app) as client:
        _register(client)
        start = client.post("/account/feishu/oauth/start", json={"next_url": "/settings"})
        parsed = urlparse(start.json()["authorize_url"])
        params = parse_qs(parsed.query)
        callback = client.get(
            "/account/feishu/oauth/callback",
            params={"code": "auth-code", "state": params["state"][0]},
        )
        status = client.get("/account/feishu/connection")

    assert start.status_code == 200
    assert "/open-apis/authen/v1/index" in start.json()["authorize_url"]
    assert params["app_id"] == ["cli_test"]
    assert params["scope"] == ["offline_access"]
    assert callback.status_code == 200
    assert callback.json()["connection"]["connected"] is True
    assert callback.json()["connection"]["tenant_key"] == "tenant_demo"
    assert "refresh-token" not in str(callback.json())
    assert status.json()["connection"]["feishu_union_id"] == "on_demo"


def test_feishu_oauth_callback_rejects_invalid_state(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        _register(client)
        response = client.get(
            "/account/feishu/oauth/callback",
            params={"code": "auth-code", "state": "wrong-state"},
        )

    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_export_lark_user_oauth_requires_connection(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setattr(H, "get_job", lambda task_id, client_id=None: None)
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)

    with TestClient(main.app) as client:
        _register(client)
        response = client.post(
            "/export-lark",
            data={
                "markdown": "# Demo",
                "title": "Demo",
                "lark_export_route": "user_oauth",
            },
        )

    assert response.status_code == 409
    assert "连接飞书" in response.json()["detail"]


def test_export_lark_user_oauth_uses_account_connection(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    captured: dict[str, object] = {}
    monkeypatch.setattr(H, "get_job", lambda task_id, client_id=None: None)
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)

    def fake_export(title: str, markdown: str, **kwargs) -> dict:
        captured.update(kwargs)
        return {"ok": True, "url": "https://feishu.cn/docx/user-doc", "auth_mode": "user_oauth"}

    monkeypatch.setattr(H, "export_markdown_to_lark", fake_export)

    with TestClient(main.app) as client:
        user_id = _register(client)
        H.save_feishu_connection(
            user_id,
            access_token="user-access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            refresh_expires_in=86400,
        )
        response = client.post(
            "/export-lark",
            data={
                "markdown": "# Demo",
                "title": "Demo",
                "lark_export_route": "user_oauth",
            },
        )

    assert response.status_code == 200
    assert response.json()["auth_mode"] == "user_oauth"
    assert captured["user_access_token"] == "user-access-token"
    assert "user-access-token" not in str(response.json())
