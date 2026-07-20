from __future__ import annotations

from pathlib import Path
import uuid

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import job_store
import backend.core.server_helpers as _H


def _enable_account_auth(monkeypatch, tmp_path) -> Path:
    jobs_db = tmp_path / "jobs.sqlite"
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_JOB_DB_PATH", str(jobs_db))
    monkeypatch.setenv("FLUENTFLOW_ALLOW_SIGNUPS", "1")
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: job_store.get_job(task_id, db_path=jobs_db, client_id=client_id),
    )
    monkeypatch.setattr(
        _H,
        "list_job_steps",
        lambda task_id=None, limit=100: job_store.list_job_steps(task_id=task_id, db_path=jobs_db, limit=limit),
    )
    return jobs_db


def _register(client: TestClient, email: str) -> dict:
    response = client.post("/auth/register", json={"email": email, "password": "secure-pass"})
    assert response.status_code == 200
    return response.json()["user"]


def _register_device(client: TestClient, name: str = "Owner Mac") -> str:
    response = client.post("/account/devices", json={"platform": "macos", "display_name": name})
    assert response.status_code == 200
    return response.json()["one_time_credential"]


def _sync_headers(credential: str) -> dict[str, str]:
    return {"X-FluentFlow-Desktop-Credential": credential}


def test_desktop_sync_is_idempotent_conflict_safe_and_visible_to_its_account(monkeypatch, tmp_path) -> None:
    jobs_db = _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        owner = _register(client, "owner@example.com")
        credential = _register_device(client)
        client.post("/auth/logout")

        supplied_task_id = uuid.uuid4().hex
        create_payload = {
            "task_id": supplied_task_id,
            "idempotency_key": "desktop-run-001",
            "source": {
                "type": "video",
                "filename": "lecture.mp4",
                "file_size_bytes": 1024 * 1024 * 20,
                "duration_seconds": 1800,
            },
        }
        created = client.post("/desktop-sync/v1/tasks", headers=_sync_headers(credential), json=create_payload)
        duplicate = client.post("/desktop-sync/v1/tasks", headers=_sync_headers(credential), json=create_payload)
        task_id = created.json()["task"]["task_id"]
        initial_read = client.get(f"/desktop-sync/v1/tasks/{task_id}", headers=_sync_headers(credential))

        generic_api_attempt = client.get(f"/jobs/{task_id}", headers=_sync_headers(credential))
        running = client.patch(
            f"/desktop-sync/v1/tasks/{task_id}/status",
            headers=_sync_headers(credential),
            json={"operation_id": "status-001", "base_revision": 0, "status": "running", "stage": "stt", "progress": 35},
        )
        replay = client.patch(
            f"/desktop-sync/v1/tasks/{task_id}/status",
            headers=_sync_headers(credential),
            json={"operation_id": "status-001", "base_revision": 0, "status": "running", "stage": "stt", "progress": 35},
        )
        stale = client.patch(
            f"/desktop-sync/v1/tasks/{task_id}/status",
            headers=_sync_headers(credential),
            json={"operation_id": "status-002", "base_revision": 0, "status": "running", "stage": "summary", "progress": 70},
        )
        forbidden_result = client.put(
            f"/desktop-sync/v1/tasks/{task_id}/result",
            headers=_sync_headers(credential),
            json={
                "operation_id": "result-forbidden",
                "base_revision": 1,
                "result": {"transcript_text": "hello", "source_path": "/Users/owner/lecture.mp4"},
            },
        )
        completed = client.put(
            f"/desktop-sync/v1/tasks/{task_id}/result",
            headers=_sync_headers(credential),
            json={
                "operation_id": "result-001",
                "base_revision": 1,
                "result": {
                    "transcript_text": "A complete transcript.",
                    "raw_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
                    "display_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
                    "summary_markdown": "# Lecture note",
                    "summary_status": "completed",
                },
            },
        )
        result_replay = client.put(
            f"/desktop-sync/v1/tasks/{task_id}/result",
            headers=_sync_headers(credential),
            json={
                "operation_id": "result-001",
                "base_revision": 1,
                "result": {"transcript_text": "ignored duplicate"},
            },
        )

        client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        job = client.get(f"/jobs/{task_id}")
        package = client.get(f"/agent/v1/tasks/{task_id}/package")

    assert created.status_code == 200
    assert created.json()["created"] is True
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["task"]["task_id"] == task_id
    assert task_id == supplied_task_id
    assert initial_read.status_code == 200
    assert initial_read.json()["task"]["result_revision"] == 0
    assert generic_api_attempt.status_code == 401
    assert job_store.list_job_steps(task_id=task_id, db_path=jobs_db) == []
    assert running.status_code == 200
    assert running.json()["result_revision"] == 1
    assert replay.json() == running.json()
    assert stale.status_code == 409
    assert stale.json()["detail"]["latest"]["result_revision"] == 1
    assert forbidden_result.status_code == 422
    assert "source_path" in forbidden_result.json()["detail"]
    assert completed.status_code == 200
    assert completed.json()["result_revision"] == 2
    assert completed.json()["result_expires_at"]
    assert result_replay.json() == completed.json()
    assert job.status_code == 200
    assert job.json()["client_id"] == f"user:{owner['id']}"
    assert job.json()["result"]["summary_markdown"] == "# Lecture note"
    assert job.json()["result"]["source_file_available"] is False
    assert job.json()["metadata"]["desktop_sync"]["execution_location"] == "local_desktop"
    assert job.json()["metadata"]["desktop_sync"]["source_availability"] == "local_only"
    assert package.status_code == 200
    assert package.json()["execution"]["location"] == "local_desktop"
    assert package.json()["execution"]["source_availability"] == "local_only"


def test_only_originating_device_and_owner_can_sync_a_desktop_task(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)

    with TestClient(main.app) as client:
        _register(client, "owner@example.com")
        owner_credential = _register_device(client, "Owner Mac")
        second_credential = _register_device(client, "Owner Windows")
        client.post("/auth/logout")
        task = client.post(
            "/desktop-sync/v1/tasks",
            headers=_sync_headers(owner_credential),
            json={"idempotency_key": "owner-task", "source": {"type": "audio", "filename": "lesson.m4a"}},
        ).json()["task"]
        other_device = client.patch(
            f"/desktop-sync/v1/tasks/{task['task_id']}/status",
            headers=_sync_headers(second_credential),
            json={"operation_id": "other-device", "base_revision": 0, "status": "running"},
        )
        other_device_read = client.get(
            f"/desktop-sync/v1/tasks/{task['task_id']}",
            headers=_sync_headers(second_credential),
        )
        client.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        client.post("/auth/logout")
        _register(client, "other@example.com")
        other_account_credential = _register_device(client, "Other Mac")
        client.post("/auth/logout")
        other_account = client.patch(
            f"/desktop-sync/v1/tasks/{task['task_id']}/status",
            headers=_sync_headers(other_account_credential),
            json={"operation_id": "other-account", "base_revision": 0, "status": "running"},
        )

    assert other_device.status_code == 404
    assert other_device_read.status_code == 404
    assert other_account.status_code == 404
