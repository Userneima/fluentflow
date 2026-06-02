from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_client_routes_fall_back_to_frontend_index() -> None:
    client = TestClient(app)

    response = client.get("/processing")

    assert response.status_code == 200
    assert "FluentFlow" in response.text
    assert 'src="/assets/app.js"' in response.text


def test_api_like_unknown_routes_still_return_404() -> None:
    client = TestClient(app)

    assert client.get("/jobs/not-found/extra").status_code == 404
    assert client.get("/process").status_code == 404
    assert client.get("/missing.js").status_code == 404
