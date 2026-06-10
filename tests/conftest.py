from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_local_auth_env(monkeypatch):
    """Keep developer .env auth settings from changing default API tests."""
    monkeypatch.delenv("FLUENTFLOW_AUTH_MODE", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCOUNT_AUTH", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ALLOW_SIGNUPS", raising=False)
    monkeypatch.delenv("FLUENTFLOW_CLOUD_WORKSPACE_URL", raising=False)
