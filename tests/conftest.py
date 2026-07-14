from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_local_auth_env(monkeypatch):
    """Keep developer .env auth settings from changing default API tests."""
    monkeypatch.delenv("FLUENTFLOW_AUTH_MODE", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCOUNT_AUTH", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ALLOW_SIGNUPS", raising=False)
    # OAuth redirect/domain overrides must not leak from a developer .env into
    # tests that assert the default request-derived redirect_uri and base URL.
    monkeypatch.delenv("FEISHU_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("LARK_OPEN_BASE_URL", raising=False)
