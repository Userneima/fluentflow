from __future__ import annotations

from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app


def test_client_routes_fall_back_to_frontend_index() -> None:
    client = TestClient(app)

    response = client.get("/processing")

    assert response.status_code == 200
    assert "FluentFlow" in response.text
    assert 'type="module"' in response.text
    assert 'src="/assets/' in response.text


def test_api_like_unknown_routes_still_return_404() -> None:
    client = TestClient(app)

    assert client.get("/jobs/not-found/extra").status_code == 404
    assert client.get("/process").status_code == 404
    assert client.get("/missing.js").status_code == 404


def test_failed_job_can_be_deleted(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        main,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(main, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(main, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).delete("/jobs/task-failed", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_failed_job_can_be_deleted_via_post_fallback(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        main,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(main, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(main, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).post("/jobs/task-failed/delete", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_completed_job_delete_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "get_job",
        lambda task_id, client_id=None: {"task_id": task_id, "status": "completed", "client_id": client_id},
    )

    response = TestClient(app).delete("/jobs/task-done", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 409
