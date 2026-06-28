from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.core.versioning import get_app_version, get_version_info


def test_app_version_comes_from_version_file() -> None:
    expected = Path("VERSION").read_text(encoding="utf-8").strip()

    assert get_app_version() == expected
    assert get_version_info()["version"] == expected


def test_version_endpoint_exposes_release_metadata() -> None:
    response = TestClient(main.app).get("/version")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "FluentFlow"
    assert payload["component"] == "backend"
    assert payload["version"] == Path("VERSION").read_text(encoding="utf-8").strip()
    assert "commit" in payload
    assert payload["schemas"]["result"] == "2"


def test_health_uses_same_app_version() -> None:
    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["app_version"] == get_app_version()
