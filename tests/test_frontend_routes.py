from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app
import backend.core.server_helpers as _H


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


def test_frontend_asset_route_serves_javascript_not_spa_html() -> None:
    assets_dir = Path("frontend/dist/assets")
    asset = next(assets_dir.glob("index-*.js"))
    response = TestClient(app).get(f"/assets/{asset.name}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert not response.text.lstrip().startswith("<!DOCTYPE html>")


def test_processing_settings_no_longer_exposes_audio_language_control() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "set.sttLanguage" not in source
    assert "settings.sttLanguage||\"auto\"" not in source
    assert "音频语言" not in source
    assert "Audio Language" not in source


def test_failed_job_can_be_deleted(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).delete("/jobs/task-failed", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_failed_job_can_be_deleted_via_post_fallback(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).post("/jobs/task-failed/delete", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_completed_job_can_be_deleted(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "completed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).delete("/jobs/task-done", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-done"]
    assert deleted == [(["task-done"], "client-a")]


def test_running_job_delete_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {"task_id": task_id, "status": "running", "client_id": client_id},
    )

    response = TestClient(app).delete("/jobs/task-running", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 409


def test_running_job_can_be_cancelled(monkeypatch) -> None:
    cancelled: list[str] = []
    released: list[str] = []
    updated: list[dict] = []
    logged: list[str] = []
    published: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "running",
            "client_id": client_id,
            "stage": "stt",
            "progress": 42,
            "source_type": "video",
            "source_filename": "demo.mp4",
            "source_file_size_mb": 12,
            "summary_status": None,
            "metadata": {"source": "test"},
        },
    )

    async def fake_cancel(task_id: str) -> bool:
        cancelled.append(task_id)
        return True

    async def fake_publish(task_id: str, event: dict) -> None:
        published.append((task_id, event))

    monkeypatch.setattr(main.JOB_EVENTS, "cancel", fake_cancel)
    monkeypatch.setattr(main.JOB_EVENTS, "publish", fake_publish)
    monkeypatch.setattr(
        _H,
        "_release_task_quota",
        lambda client_id, task_id, reason, metadata=None: released.append(task_id),
    )
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: updated.append(kwargs))
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: logged.append(kwargs["event_name"]))

    response = TestClient(app).post("/jobs/task-running/cancel", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert cancelled == ["task-running"]
    assert released == ["task-running"]
    assert updated[0]["status"] == "cancelled"
    assert updated[0]["error_reason"] == "user_cancelled"
    assert published[0][1]["stage"] == "error"
    assert logged == ["task_cancelled"]


def test_manual_lark_export_does_not_require_stored_job(monkeypatch) -> None:
    exported: list[tuple[str, str]] = []
    logged: list[dict] = []

    monkeypatch.setattr(_H, "get_job", lambda task_id, client_id=None: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: logged.append(kwargs))

    def fake_export(title: str, markdown: str) -> dict:
        exported.append((title, markdown))
        return {"ok": True, "url": "https://example.feishu.cn/docx/demo"}

    monkeypatch.setattr(_H, "export_markdown_via_lark_cli", fake_export)

    response = TestClient(app).post(
        "/export-lark",
        headers={"X-FluentFlow-Client-Id": "client-a"},
        data={
            "task_id": "missing-local-history-task",
            "markdown": "# Demo\n\ncontent",
            "title": "Demo",
            "lark_via_cli": "true",
        },
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.feishu.cn/docx/demo"
    assert response.json()["task_id"] == "missing-local-history-task"
    assert exported == [("Demo", "# Demo\n\ncontent")]
    assert [item["event_name"] for item in logged] == ["lark_export_started", "lark_export_completed"]
