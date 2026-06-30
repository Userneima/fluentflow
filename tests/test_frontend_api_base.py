from __future__ import annotations

from pathlib import Path


def test_local_frontend_ports_route_api_to_backend() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    api_config = Path("frontend/src/app/apiConfig.js").read_text(encoding="utf-8")

    for source in (shared, api_config):
        assert 'hostname === "::1"' in source
        assert 'port && port !== "8000"' in source
        assert 'return "http://127.0.0.1:8000"' in source
        assert 'port === "5185"' not in source
