from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import job_store


def _patch_job_store(monkeypatch, db_path: Path) -> None:
    monkeypatch.setattr(
        main,
        "upsert_job",
        lambda **kwargs: job_store.upsert_job(**kwargs, db_path=db_path),
    )
    monkeypatch.setattr(
        main,
        "get_job",
        lambda task_id, client_id=None: job_store.get_job(task_id, db_path=db_path, client_id=client_id),
    )
    monkeypatch.setattr(
        main,
        "list_jobs",
        lambda limit=50, client_id=None: job_store.list_jobs(limit=limit, db_path=db_path, client_id=client_id),
    )


def _enable_account_auth(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_AUTH", "1")
    monkeypatch.setenv("FLUENTFLOW_ACCOUNT_DB_PATH", str(tmp_path / "accounts.sqlite"))
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FLUENTFLOW_ACCESS_TOKENS", raising=False)
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)


def test_guest_trial_status_bypasses_account_login_wall(monkeypatch, tmp_path: Path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_GUEST_TRIAL_ENABLED", "1")
    _patch_job_store(monkeypatch, tmp_path / "jobs.sqlite")

    with TestClient(main.app) as client:
        account_route = client.get("/jobs")
        guest_route = client.get("/guest-trial/status")

    assert account_route.status_code == 401
    assert guest_route.status_code == 200
    assert guest_route.json()["enabled"] is True


def test_guest_trial_process_creates_private_queued_job(monkeypatch, tmp_path: Path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_GUEST_TRIAL_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_GUEST_FILE_LIMIT_MB", "150")
    monkeypatch.setenv("FLUENTFLOW_GUEST_DURATION_LIMIT_SECONDS", "900")
    _patch_job_store(monkeypatch, tmp_path / "jobs.sqlite")
    monkeypatch.setattr(main, "log_event", lambda **kwargs: None)
    enqueued: list[dict[str, Any]] = []
    monkeypatch.setattr(main, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    with TestClient(main.app) as client:
        response = client.post(
            "/guest-trial/process",
            files={"file": ("demo.mp4", b"video-content", "video/mp4")},
            data={
                "stt_provider": "azure_batch",
                "system_prompt": "note prompt",
            },
        )
        payload = response.json()
        task_id = payload.get("task_id")
        token = payload.get("guest_token")
        private_job = client.get(f"/guest-trial/jobs/{task_id}", headers={main.GUEST_TRIAL_TOKEN_HEADER: token})
        blocked_job = client.get(f"/guest-trial/jobs/{task_id}")

    assert response.status_code == 200
    assert token
    assert task_id
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["client_id"] == f"guest_{token}"
    assert payload["job"]["metadata"]["guest_trial"]["token"] == token
    assert payload["job"]["metadata"]["guest_trial"]["duration_limit_seconds"] == 900
    assert float(payload["job"]["metadata"]["queue_options"]["duration_limit_seconds"]) == 900
    assert len(enqueued) == 1
    assert enqueued[0]["task_id"] == task_id
    assert enqueued[0]["client_id"] == f"guest_{token}"
    assert enqueued[0]["options"]["system_prompt"] == "note prompt"
    assert (tmp_path / "sources" / task_id / "source.mp4").is_file()
    assert private_job.status_code == 200
    assert blocked_job.status_code == 401


def test_guest_trial_queue_capacity_rejects_before_upload(monkeypatch, tmp_path: Path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_GUEST_TRIAL_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_GUEST_ACTIVE_PROCESSING_SLOTS", "1")
    monkeypatch.setenv("FLUENTFLOW_GUEST_WAITING_QUEUE_LIMIT", "1")
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    db_path = tmp_path / "jobs.sqlite"
    _patch_job_store(monkeypatch, db_path)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    for index in range(2):
        job_store.upsert_job(
            task_id=f"guest-{index}",
            status="queued",
            client_id=f"guest_token_{index}",
            stage="queued",
            metadata={"guest_trial": {"token": f"token_{index}", "ip_key": "203.0.113.1"}, "created_at": now},
            db_path=db_path,
        )
    enqueued: list[dict[str, Any]] = []
    monkeypatch.setattr(main, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    with TestClient(main.app) as client:
        response = client.post(
            "/guest-trial/process",
            files={"file": ("demo.mp4", b"video-content", "video/mp4")},
        )

    assert response.status_code == 429
    assert "队列" in response.json()["detail"]
    assert enqueued == []
    assert not (tmp_path / "sources").exists()


def test_guest_trial_daily_ip_limit_counts_only_today(monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_GUEST_DAILY_TRIALS_PER_IP", "1")
    monkeypatch.setattr(
        main,
        "_guest_trial_jobs",
        lambda *args, **kwargs: [
            {
                "task_id": "today",
                "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "metadata": {"guest_trial": {"ip_key": "203.0.113.9"}},
            }
        ],
    )
    request = type("Request", (), {"headers": {"x-forwarded-for": "203.0.113.9"}, "client": None})()

    try:
        main._enforce_guest_daily_ip_limit(request)
    except main.HTTPException as exc:
        assert exc.status_code == 429
        assert "每日上限" in exc.detail
    else:
        raise AssertionError("Expected guest daily IP limit to reject excess trials")


def test_guest_trial_artifact_download_requires_matching_token(monkeypatch, tmp_path: Path) -> None:
    _enable_account_auth(monkeypatch, tmp_path)
    monkeypatch.setenv("FLUENTFLOW_GUEST_TRIAL_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    db_path = tmp_path / "jobs.sqlite"
    _patch_job_store(monkeypatch, db_path)
    task_id = "guest-artifact"
    token = "token123"
    job_store.upsert_job(
        task_id=task_id,
        status="completed",
        client_id=f"guest_{token}",
        stage="done",
        result={"task_id": task_id, "artifacts": {"playback_audio": {"filename": "demo.mp3"}}},
        metadata={"guest_trial": {"token": token, "ip_key": "203.0.113.11"}},
        db_path=db_path,
    )
    artifact_dir = tmp_path / "artifacts" / task_id
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "demo_playback.mp3").write_bytes(b"audio")

    with TestClient(main.app) as client:
        allowed = client.get(
            f"/guest-trial/jobs/{task_id}/artifacts/playback_audio",
            headers={main.GUEST_TRIAL_TOKEN_HEADER: token},
        )
        blocked = client.get(
            f"/guest-trial/jobs/{task_id}/artifacts/playback_audio",
            headers={main.GUEST_TRIAL_TOKEN_HEADER: "wrong"},
        )

    assert allowed.status_code == 200
    assert allowed.content == b"audio"
    assert blocked.status_code == 404
