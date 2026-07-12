from __future__ import annotations

from fastapi import Request

import backend.core.server_helpers as H


def _local_request(path: str = "/queue/process", *, host: str = "127.0.0.1") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"x-fluentflow-execution-target", b"local")],
        "server": (host, 8000),
    })


def test_account_scope_survives_normalization_with_colon() -> None:
    # Regression origin (2026-07-09): an account owner tag is "user:<id>". An
    # earlier version ran it through the client-id sanitizer, which stripped the
    # colon (user:ID -> userID). That split ONE account's jobs across two owner
    # tags, so half the records became invisible in the account's list. The
    # colon must be preserved for any "user:" scope.
    assert H._normalize_client_scope("user:20d882b1") == "user:20d882b1"
    assert H._normalize_client_scope("  user:abc  ") == "user:abc"
    # Non-account client ids are still sanitized down to a safe token.
    assert H._normalize_client_scope("local user!@#") == "localuser"


def test_logged_in_localhost_scopes_to_account_not_local(monkeypatch) -> None:
    # Regression origin (2026-07-09): the same video submitted before login (as
    # the local-single-user bucket) and after login (as the account) produced
    # two owner tags on one machine, one of them hidden. Account identity must
    # win over the local-execution bucket so a logged-in user on localhost owns
    # their jobs under their account.
    monkeypatch.setattr(H, "_account_auth_enabled", lambda: True)
    monkeypatch.setattr(H, "_request_account_user", lambda request: {"id": "abc123"})

    assert H._request_client_scope(_local_request()) == "user:abc123"


def test_localhost_without_account_falls_back_to_local_bucket(monkeypatch) -> None:
    # Complement: when account auth is off (or nobody is logged in), a local
    # request still resolves to a stable single bucket rather than fragmenting.
    monkeypatch.setattr(H, "_account_auth_enabled", lambda: False)

    scope = H._request_client_scope(_local_request())
    assert scope  # a concrete, non-empty owner tag
    assert not scope.startswith("user:")  # not falsely attributed to an account
