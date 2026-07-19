from __future__ import annotations

import time

from fastapi.testclient import TestClient

import backend.main as main
import backend.core.server_helpers as helpers
import backend.routers.oss_uploads as oss_uploads
from backend.core.oss_multipart import OssPartSignature
from backend.core.oss_upload_sessions import (
    OssUploadSessionCapacityError,
    get_oss_upload_session,
    reserve_oss_upload_session,
)


class FakeOssGateway:
    def __init__(self, *, object_size: int, fail_head: bool = False):
        self.object_size = object_size
        self.fail_head = fail_head
        self.initiated: list[tuple[str, str | None]] = []
        self.signed: list[int] = []
        self.completed: list[list[tuple[int, str]]] = []
        self.aborted: list[str] = []
        self.deleted: list[str] = []

    def initiate(self, *, object_key: str, content_type: str | None) -> str:
        self.initiated.append((object_key, content_type))
        return "upload-id-1"

    def presign_part(self, *, object_key: str, upload_id: str, part_number: int, expires_seconds: int) -> OssPartSignature:
        self.signed.append(part_number)
        return OssPartSignature("PUT", f"https://oss.example/{part_number}", {"x-oss-test": "yes"})

    def complete(self, *, object_key: str, upload_id: str, parts: list[tuple[int, str]]) -> None:
        self.completed.append(parts)

    def head_size(self, *, object_key: str) -> int:
        if self.fail_head:
            raise RuntimeError("simulated head failure")
        return self.object_size

    def abort(self, *, object_key: str, upload_id: str) -> None:
        self.aborted.append(upload_id)

    def delete(self, *, object_key: str) -> None:
        self.deleted.append(object_key)

    def download_to_file(self, *, object_key, target_path) -> int:
        target_path.write_bytes(b"x" * self.object_size)
        return self.object_size


def _enable_direct_upload(monkeypatch, tmp_path, gateway: FakeOssGateway) -> None:
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_PUBLIC_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_INTERNAL_ENDPOINT", "oss-cn-hongkong-internal.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")
    monkeypatch.setenv("FLUENTFLOW_OSS_MAX_SOURCE_MB", "4096")
    monkeypatch.setenv("FLUENTFLOW_OSS_UPLOAD_SESSION_DB_PATH", str(tmp_path / "oss-sessions.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_JOB_DB_PATH", str(tmp_path / "jobs.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_EVENT_DB_PATH", str(tmp_path / "events.sqlite"))
    monkeypatch.setenv("FLUENTFLOW_MAX_UPLOAD_MB", "128")
    monkeypatch.setattr(helpers, "_require_account_user", lambda request: {"id": "account-a"})
    monkeypatch.setattr(oss_uploads, "build_oss_multipart_gateway", lambda config: gateway)
    monkeypatch.setattr(helpers, "_enqueue_oss_source_download", lambda item: None)
    monkeypatch.setattr(helpers, "_enforce_active_job_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "_enforce_global_active_job_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "_enforce_daily_quota", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "_enforce_global_daily_quota", lambda *args, **kwargs: None)
    helpers._SUBMISSION_RATE_EVENTS.clear()


def test_session_reservation_is_owner_scoped_and_releases_expired_capacity(tmp_path) -> None:
    db_path = tmp_path / "sessions.sqlite"
    reserved = reserve_oss_upload_session(
        session_id="one",
        owner_scope="user:a",
        object_key="uploads/source/one/source.mp4",
        source_filename="lesson.mp4",
        content_type="video/mp4",
        content_length=10,
        part_size_bytes=5,
        expires_at=time.time() + 60,
        max_open_sessions=1,
        db_path=db_path,
    )
    assert reserved["status"] == "creating"
    assert get_oss_upload_session("one", owner_scope="user:b", db_path=db_path) is None
    try:
        reserve_oss_upload_session(
            session_id="two",
            owner_scope="user:a",
            object_key="uploads/source/two/source.mp4",
            source_filename="lesson.mp4",
            content_type="video/mp4",
            content_length=10,
            part_size_bytes=5,
            expires_at=time.time() + 60,
            max_open_sessions=1,
            db_path=db_path,
        )
    except OssUploadSessionCapacityError:
        pass
    else:
        raise AssertionError("expected owner session capacity to be enforced")
    expired = reserve_oss_upload_session(
        session_id="expired",
        owner_scope="user:b",
        object_key="uploads/source/expired/source.mp4",
        source_filename="lesson.mp4",
        content_type="video/mp4",
        content_length=10,
        part_size_bytes=5,
        expires_at=time.time() - 1,
        max_open_sessions=1,
        db_path=db_path,
    )
    assert expired["status"] == "creating"
    replacement = reserve_oss_upload_session(
        session_id="replacement",
        owner_scope="user:b",
        object_key="uploads/source/replacement/source.mp4",
        source_filename="lesson.mp4",
        content_type="video/mp4",
        content_length=10,
        part_size_bytes=5,
        expires_at=time.time() + 60,
        max_open_sessions=1,
        db_path=db_path,
    )
    assert replacement["status"] == "creating"


def test_disabled_direct_upload_does_not_expose_session_api(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", raising=False)
    with TestClient(main.app) as client:
        response = client.post("/oss-upload-sessions", json={})
    assert response.status_code == 404


def test_direct_upload_rejects_over_quota_before_creating_an_oss_session(tmp_path, monkeypatch) -> None:
    gateway = FakeOssGateway(object_size=32 * 1024 * 1024)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)

    def reject(*args, **kwargs):
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail="daily upload limit reached")

    monkeypatch.setattr(helpers, "_enforce_daily_quota", reject)
    with TestClient(main.app) as client:
        response = client.post(
            "/oss-upload-sessions",
            json={"filename": "recording.mp4", "content_length": 32 * 1024 * 1024, "content_type": "video/mp4"},
        )

    assert response.status_code == 429
    assert gateway.initiated == []


def test_direct_upload_uses_its_own_four_gigabyte_limit(tmp_path, monkeypatch) -> None:
    file_size = 4 * 1024 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    with TestClient(main.app) as client:
        response = client.post(
            "/oss-upload-sessions",
            json={"filename": "recording.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )

    assert response.status_code == 200
    assert response.json()["session"]["expected_parts"] == 128


def test_direct_upload_rejects_files_above_its_own_four_gigabyte_limit(tmp_path, monkeypatch) -> None:
    gateway = FakeOssGateway(object_size=1)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    with TestClient(main.app) as client:
        response = client.post(
            "/oss-upload-sessions",
            json={
                "filename": "recording.mp4",
                "content_length": 4 * 1024 * 1024 * 1024 + 1,
                "content_type": "video/mp4",
            },
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "File is too large. Limit is 4096 MB."


def test_multipart_session_signs_parts_and_verifies_completed_object(tmp_path, monkeypatch) -> None:
    file_size = 40 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    with TestClient(main.app) as client:
        created = client.post(
            "/oss-upload-sessions",
            json={"filename": "lesson.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )
        assert created.status_code == 200
        session = created.json()["session"]
        assert session["expected_parts"] == 2
        assert "upload_id" not in session
        assert "object_key" not in session

        signed = client.post(f"/oss-upload-sessions/{session['session_id']}/parts", json={"part_numbers": [2, 1]})
        assert signed.status_code == 200
        assert [part["part_number"] for part in signed.json()["parts"]] == [2, 1]

        completed = client.post(
            f"/oss-upload-sessions/{session['session_id']}/complete",
            json={"parts": [{"part_number": 2, "etag": "etag-two"}, {"part_number": 1, "etag": "etag-one"}]},
        )

    assert completed.status_code == 200
    assert completed.json()["session"]["status"] == "completed"
    assert completed.json()["session"]["task_id"]
    assert gateway.signed == [2, 1]
    assert gateway.completed == [[(1, "etag-one"), (2, "etag-two")]]


def test_completed_upload_creates_an_account_scoped_download_job(tmp_path, monkeypatch) -> None:
    file_size = 32 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    jobs: list[dict] = []
    events: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(helpers, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(helpers, "log_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(helpers, "_enqueue_oss_source_download", lambda item: enqueued.append(item))

    with TestClient(main.app) as client:
        created = client.post(
            "/oss-upload-sessions",
            json={"filename": "lesson.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )
        session_id = created.json()["session"]["session_id"]
        completed = client.post(
            f"/oss-upload-sessions/{session_id}/complete",
            json={
                "parts": [{"part_number": 1, "etag": "etag-one"}],
                "options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true"},
            },
        )
        stored = client.get(f"/oss-upload-sessions/{session_id}")

    assert completed.status_code == 200
    task_id = completed.json()["session"]["task_id"]
    assert task_id
    assert stored.json()["session"]["task_id"] == task_id
    queued_job = next(job for job in jobs if job["task_id"] == task_id)
    assert queued_job == {
        "task_id": task_id,
        "status": "queued",
        "client_id": "user:account-a",
        "stage": "source_download",
        "progress": 0,
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "source_file_size_mb": 32.0,
        "metadata": {
            "event_schema_version": helpers.EVENT_SCHEMA_VERSION,
            "app_version": helpers.APP_VERSION,
            "route": "/oss-upload-sessions",
            "source_storage": "oss",
            "oss_upload_session_id": session_id,
            "queue_options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true"},
        },
    }
    assert any(event["event_name"] == "source_uploaded" and event["task_id"] == task_id for event in events)
    assert enqueued == [
        {
            "task_id": task_id,
            "object_key": gateway.initiated[0][0],
            "expected_size_bytes": file_size,
            "filename": "lesson.mp4",
            "options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true"},
            "base_url": "http://testserver",
            "client_id": "user:account-a",
            "oss_upload_session_id": session_id,
            "route": "/oss-upload-sessions",
        }
    ]


def test_post_upload_admission_rejection_cleans_up_completed_object(tmp_path, monkeypatch) -> None:
    file_size = 32 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)

    def reject(*args, **kwargs):
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail="queue full")

    with TestClient(main.app) as client:
        created = client.post(
            "/oss-upload-sessions",
            json={"filename": "lesson.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )
        session_id = created.json()["session"]["session_id"]
        monkeypatch.setattr(helpers, "_enforce_active_job_limit", reject)
        response = client.post(
            f"/oss-upload-sessions/{session_id}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag-one"}]},
        )
        stored = client.get(f"/oss-upload-sessions/{session_id}")

    assert response.status_code == 429
    assert gateway.deleted
    assert stored.json()["session"]["status"] == "failed"


def test_completed_size_mismatch_deletes_object_and_marks_session_failed(tmp_path, monkeypatch) -> None:
    file_size = 32 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size - 1)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    with TestClient(main.app) as client:
        created = client.post(
            "/oss-upload-sessions",
            json={"filename": "lesson.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )
        session_id = created.json()["session"]["session_id"]
        response = client.post(
            f"/oss-upload-sessions/{session_id}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag-one"}]},
        )
        status = client.get(f"/oss-upload-sessions/{session_id}")

    assert response.status_code == 422
    assert gateway.deleted
    assert status.json()["session"]["status"] == "failed"


def test_completion_verification_failure_cleans_up_and_marks_session_failed(tmp_path, monkeypatch) -> None:
    file_size = 32 * 1024 * 1024
    gateway = FakeOssGateway(object_size=file_size, fail_head=True)
    _enable_direct_upload(monkeypatch, tmp_path, gateway)
    with TestClient(main.app) as client:
        created = client.post(
            "/oss-upload-sessions",
            json={"filename": "lesson.mp4", "content_length": file_size, "content_type": "video/mp4"},
        )
        session_id = created.json()["session"]["session_id"]
        response = client.post(
            f"/oss-upload-sessions/{session_id}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag-one"}]},
        )
        status = client.get(f"/oss-upload-sessions/{session_id}")

    assert response.status_code == 502
    assert gateway.deleted
    assert status.json()["session"]["status"] == "failed"
