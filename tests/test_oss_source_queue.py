from __future__ import annotations

from pathlib import Path

import pytest

import backend.core.server_helpers as helpers
from backend.core.media_preflight import MediaPreflightError, MediaPreflightResult


class FakeDownloadGateway:
    def download_to_file(self, *, object_key: str, target_path: Path) -> int:
        payload = b"streamed media bytes"
        target_path.write_bytes(payload)
        return len(payload)


def _passing_media_preflight() -> MediaPreflightResult:
    return MediaPreflightResult(
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
        audio_stream_count=1,
        duration_seconds=120.0,
        enabled_guards=("empty_file", "container", "audio_stream", "audio_decode"),
    )


def test_oss_source_download_uses_task_source_then_existing_transcription_queue(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")
    monkeypatch.setattr(helpers, "build_oss_multipart_gateway", lambda config: FakeDownloadGateway())
    monkeypatch.setattr(helpers, "preflight_media_file", lambda path: _passing_media_preflight())
    monkeypatch.setattr(helpers, "get_job", lambda task_id: None)
    monkeypatch.setattr(helpers, "_reserve_task_quota", lambda **kwargs: {"reserved_units": 2})
    monkeypatch.setattr(helpers, "_job_metadata_for_update", lambda task_id, client_id, **kwargs: kwargs)
    upserts: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(helpers, "upsert_job", lambda **kwargs: upserts.append(kwargs))
    monkeypatch.setattr(helpers, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(helpers, "_publish_job_event_from_thread", lambda task_id, event: None)
    monkeypatch.setattr(helpers, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    helpers._run_oss_source_download(
        {
            "task_id": "task-oss-1",
            "object_key": "uploads/source/private/source.mp4",
            "expected_size_bytes": len(b"streamed media bytes"),
            "filename": "lesson.mp4",
            "options": {"stt_provider": "elevenlabs_scribe"},
            "client_id": "user:account-a",
            "oss_upload_session_id": "session-1",
        }
    )

    source_path = tmp_path / "sources" / "task-oss-1" / "source.mp4"
    assert source_path.read_bytes() == b"streamed media bytes"
    assert [entry["status"] for entry in upserts] == ["running", "queued"]
    assert enqueued == [
        {
            "task_id": "task-oss-1",
            "source_path": str(source_path),
            "filename": "lesson.mp4",
            "options": {"stt_provider": "elevenlabs_scribe"},
            "base_url": "http://127.0.0.1:8000",
            "client_id": "user:account-a",
            "route": "/oss-upload-sessions",
        }
    ]


def test_oss_source_download_removes_local_copy_when_preflight_rejects(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setenv("FLUENTFLOW_OSS_DIRECT_UPLOAD_ENABLED", "1")
    monkeypatch.setenv("FLUENTFLOW_OSS_REGION", "cn-hongkong")
    monkeypatch.setenv("FLUENTFLOW_OSS_ENDPOINT", "oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setenv("FLUENTFLOW_OSS_BUCKET", "fluentflow-media-test")
    monkeypatch.setenv("FLUENTFLOW_OSS_ECS_RAM_ROLE", "FluentFlowOssUploadRole")
    monkeypatch.setattr(helpers, "build_oss_multipart_gateway", lambda config: FakeDownloadGateway())
    monkeypatch.setattr(
        helpers,
        "preflight_media_file",
        lambda path: (_ for _ in ()).throw(MediaPreflightError("media_audio_stream_missing", "no audio")),
    )
    monkeypatch.setattr(helpers, "get_job", lambda task_id: None)
    monkeypatch.setattr(helpers, "upsert_job", lambda **kwargs: None)
    monkeypatch.setattr(helpers, "_publish_job_event_from_thread", lambda task_id, event: None)

    with pytest.raises(MediaPreflightError, match="no audio"):
        helpers._run_oss_source_download(
            {
                "task_id": "task-oss-rejected",
                "object_key": "uploads/source/private/source.mp4",
                "expected_size_bytes": len(b"streamed media bytes"),
                "filename": "lesson.mp4",
                "client_id": "user:account-a",
            }
        )

    assert not (tmp_path / "sources" / "task-oss-rejected").exists()


def test_oss_download_step_failure_releases_any_reserved_quota(monkeypatch) -> None:
    releases: list[dict] = []
    updates: list[dict] = []
    monkeypatch.setattr(helpers, "_release_task_quota", lambda **kwargs: releases.append(kwargs))
    monkeypatch.setattr(helpers, "upsert_job", lambda **kwargs: updates.append(kwargs))
    monkeypatch.setattr(helpers, "_publish_job_event_from_thread", lambda task_id, event: None)

    helpers._handle_step_failure(
        {
            "task_id": "task-oss-release",
            "step_type": "oss_source_download",
            "input": {"client_id": "user:account-a", "route": "/oss-upload-sessions"},
        },
        RuntimeError("download failed"),
    )

    assert releases and releases[0]["task_id"] == "task-oss-release"
    assert releases[0]["metadata"]["route"] == "/oss-upload-sessions"
    assert updates and updates[0]["status"] == "failed"
