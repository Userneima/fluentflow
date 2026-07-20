from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import account_lifecycle, account_store, job_store
from backend.core import server_helpers as H


def _enable_account_auth(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def _patch_job_store(monkeypatch, db_path) -> None:
    monkeypatch.setattr(H, "get_job", lambda task_id, client_id=None: job_store.get_job(task_id, db_path=db_path, client_id=client_id))
    monkeypatch.setattr(H, "list_jobs_for_retention", lambda client_id=None: job_store.list_jobs_for_retention(db_path=db_path, client_id=client_id))
    monkeypatch.setattr(H, "upsert_job", lambda **kwargs: job_store.upsert_job(**kwargs, db_path=db_path))
    monkeypatch.setattr(H, "cancel_job_steps", lambda task_id: job_store.cancel_job_steps(task_id, db_path=db_path))


def test_account_deletion_freezes_access_and_google_recovery_can_cancel(monkeypatch, tmp_path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    job_db = tmp_path / "jobs.sqlite"
    _patch_job_store(monkeypatch, job_db)

    with TestClient(main.app) as client:
        created = client.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        user_id = created.json()["user"]["id"]
        job_store.upsert_job(
            task_id="deletion-job",
            status="queued",
            client_id=f"user:{user_id}",
            source_type="video",
            source_filename="recording.mp4",
            db_path=job_db,
        )

        requested = client.post("/account/deletion")
        assert requested.status_code == 200
        assert requested.json()["cancelled_tasks"] == 1
        assert requested.json()["deletion"]["purge_after_at"]
        assert client.get("/auth/status").json()["authenticated"] is False
        assert job_store.get_job("deletion-job", db_path=job_db)["status"] == "cancelled"

        recovery = account_store.create_session(
            user_id,
            purpose=account_store.SESSION_PURPOSE_DELETION_RECOVERY,
            db_path=tmp_path / "accounts.sqlite",
        )
        client.cookies.set(H.SESSION_COOKIE_NAME, recovery)
        pending = client.get("/auth/status").json()
        assert pending["account_deletion_recovery"] is True
        assert pending["authenticated"] is False

        cancelled = client.post("/account/deletion/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["deletion"]["cancelled_at"]
        assert client.get("/auth/status").json()["authenticated"] is True


def test_due_account_deletion_purges_tasks_and_identity(tmp_path) -> None:
    account_db = tmp_path / "accounts.sqlite"
    job_db = tmp_path / "jobs.sqlite"
    user = account_store.create_user("delete@example.com", "secure-pass", db_path=account_db)
    user_id = user["id"]
    job_store.upsert_job(
        task_id="purge-job",
        status="completed",
        client_id=f"user:{user_id}",
        source_type="audio",
        source_filename="note.mp3",
        db_path=job_db,
    )
    account_lifecycle.request_deletion(user_id, account_db_path=account_db)
    with sqlite3.connect(account_db) as conn:
        conn.execute(
            "UPDATE account_deletion_requests SET purge_after_at = '1970-01-01T00:00:00+00:00' WHERE user_id = ?",
            (user_id,),
        )

    cleaned = []
    purged = account_lifecycle.purge_due_deletions(
        cleanup_task_files=lambda task_id, _metadata: cleaned.append(task_id),
        account_db_path=account_db,
        job_db_path=job_db,
        event_db_path=tmp_path / "events.sqlite",
    )

    assert purged == [{"user_id": user_id, "task_count": 1, "quota_rows": 0, "api_keys": 0, "desktop_devices": 0}]
    assert cleaned == ["purge-job"]
    assert job_store.get_job("purge-job", db_path=job_db) is None
    assert account_store.get_user_by_id(user_id, db_path=account_db) is None
