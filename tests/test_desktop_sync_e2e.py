from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
import uuid

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import desktop_sync_client as sync_client
from backend.core import job_store
import backend.core.server_helpers as _H


def _enable_account_auth(monkeypatch, tmp_path) -> Path:
    jobs_db = tmp_path / "cloud-jobs.sqlite"
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
    return jobs_db


def _write_paired_config(path: Path, credential: str, device_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "desktop_sync": {
                    "cloud_url": "https://cloud.example.test",
                    "device_id": device_id,
                    "device_credential": credential,
                    "display_name": "Test Mac",
                    "platform": "macos",
                }
            }
        ),
        encoding="utf-8",
    )


class _CloudApiBridge:
    """Route the local outbox HTTP client to the real in-process cloud API."""

    def __init__(self, cloud: TestClient) -> None:
        self.cloud = cloud
        self.payloads: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    @staticmethod
    def _path(url: str) -> str:
        return urlparse(url).path

    def post(self, url: str, *, headers: dict, json: dict):
        self.payloads.append(json)
        return self.cloud.post(self._path(url), headers=headers, json=json)

    def patch(self, url: str, *, headers: dict, json: dict):
        self.payloads.append(json)
        return self.cloud.patch(self._path(url), headers=headers, json=json)

    def put(self, url: str, *, headers: dict, json: dict):
        self.payloads.append(json)
        return self.cloud.put(self._path(url), headers=headers, json=json)

    def get(self, url: str, *, headers: dict):
        return self.cloud.get(self._path(url), headers=headers)


def test_paired_desktop_outbox_reaches_real_cloud_task_api(monkeypatch, tmp_path) -> None:
    jobs_db = _enable_account_auth(monkeypatch, tmp_path)
    config_path = tmp_path / "desktop-config.json"
    outbox_path = tmp_path / "desktop-outbox.sqlite"
    task_id = uuid.uuid4().hex

    with TestClient(main.app) as cloud:
        register = cloud.post("/auth/register", json={"email": "owner@example.com", "password": "secure-pass"})
        assert register.status_code == 200
        device = cloud.post("/account/devices", json={"platform": "macos", "display_name": "Test Mac"})
        assert device.status_code == 200
        credential = device.json()["one_time_credential"]
        _write_paired_config(config_path, credential, device.json()["device"]["id"])
        cloud.post("/auth/logout")

        bridge = _CloudApiBridge(cloud)
        monkeypatch.setattr(sync_client.httpx, "Client", lambda **_kwargs: bridge)
        assert sync_client.queue_desktop_task(
            task_id=task_id,
            source={"type": "video", "filename": "lecture.mp4", "file_size_bytes": 2048, "duration_seconds": 90},
            config_path=config_path,
            outbox_path=outbox_path,
        )
        assert sync_client.queue_desktop_status(
            task_id=task_id,
            status="running",
            stage="stt",
            progress=35,
            outbox_path=outbox_path,
        )
        assert sync_client.queue_desktop_result(
            task_id=task_id,
            result={
                "transcript_text": "A complete transcript.",
                "raw_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
                "display_segments": [{"start": 0, "end": 2, "text": "A complete transcript."}],
                "summary_markdown": "# Note\n![Local frame](/jobs/task/artifacts/frame.png)",
                "source_path": "/Users/example/lecture.mp4",
            },
            outbox_path=outbox_path,
        )

        outcome = sync_client.flush_desktop_sync_outbox(config_path=config_path, outbox_path=outbox_path)
        assert outcome == {"sent": 4, "pending": 0, "skipped": 0}

        login = cloud.post("/auth/login", json={"email": "owner@example.com", "password": "secure-pass"})
        assert login.status_code == 200
        job_response = cloud.get(f"/jobs/{task_id}")

    assert job_response.status_code == 200
    job = job_response.json()
    assert job["result"]["summary_markdown"] == "# Note\n"
    assert job["metadata"]["desktop_sync"]["execution_location"] == "local_desktop"
    assert job["metadata"]["desktop_sync"]["source_availability"] == "local_only"
    assert job["metadata"]["desktop_sync"]["result_expires_at"]
    assert job_store.get_job(task_id, db_path=jobs_db)["result"]["source_file_available"] is False
    assert "/Users/example" not in json.dumps(bridge.payloads)
