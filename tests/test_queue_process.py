from __future__ import annotations

import inspect
from pathlib import Path
import threading

import pytest
from fastapi.testclient import TestClient

import backend.main as main
import backend.core.server_helpers as _H
import backend.routers.jobs as jobs_router
import backend.routers.processing as processing_router
from backend.core.media_preflight import MediaPreflightError, MediaPreflightResult
from backend.core.stt_process import start_transcription_process


def _passing_media_preflight() -> MediaPreflightResult:
    return MediaPreflightResult(
        format_name="mov,mp4,m4a,3gp,3g2,mj2",
        audio_stream_count=1,
        duration_seconds=120.0,
        enabled_guards=("empty_file", "container", "audio_stream", "audio_decode"),
    )


def test_queue_process_persists_multiple_files_without_running_stt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(processing_router, "preflight_media_file", lambda path: _passing_media_preflight())

    jobs: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    with TestClient(main.app) as client:
        response = client.post(
            "/queue/process",
            files=[
                ("files", ("lesson-one.mp4", b"video-one", "video/mp4")),
                ("files", ("lesson-two.m4a", b"audio-two", "audio/mp4")),
            ],
            data={
                "stt_provider": "elevenlabs_scribe",
                "stt_model": "medium",
                "skip_summary": "true",
                "export_to_lark": "true",
                "lark_export_route": "local_cli",
                "lark_via_cli": "true",
                "deepseek_api_key": "secret-deepseek",
                "elevenlabs_api_key": "secret-elevenlabs",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert [item["status"] for item in payload["queued"]] == ["queued", "queued"]

    assert len(jobs) == 2
    assert [job["status"] for job in jobs] == ["queued", "queued"]
    assert [job["stage"] for job in jobs] == ["queued", "queued"]
    assert [job["source_type"] for job in jobs] == ["video", "audio"]
    assert jobs[0]["metadata"]["queue_position"] == 1
    assert jobs[1]["metadata"]["queue_position"] == 2
    assert jobs[0]["metadata"]["queue_total"] == 2
    assert jobs[0]["metadata"]["queue_options"]["stt_provider"] == "elevenlabs_scribe"
    assert jobs[0]["metadata"]["queue_options"]["skip_summary"] == "true"
    assert jobs[0]["metadata"]["queue_options"]["export_to_lark"] == "true"
    assert jobs[0]["metadata"]["queue_options"]["lark_export_route"] == "local_cli"
    assert "deepseek_api_key" not in jobs[0]["metadata"]["queue_options"]
    assert "elevenlabs_api_key" not in jobs[0]["metadata"]["queue_options"]

    assert len(enqueued) == 2
    assert enqueued[0]["task_id"] == jobs[0]["task_id"]
    assert enqueued[1]["task_id"] == jobs[1]["task_id"]
    for item in enqueued:
        assert item["base_url"].startswith("http://testserver")
        assert (tmp_path / "sources" / item["task_id"]).is_dir()


def test_queue_process_rejects_invalid_media_before_creating_jobs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    events: list[dict] = []
    jobs: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: enqueued.append(item))

    def reject(path):
        raise MediaPreflightError("media_audio_stream_missing", "媒体中没有可转录的音轨，请上传包含系统声音或麦克风声音的音视频文件。")

    monkeypatch.setattr(processing_router, "preflight_media_file", reject)

    with TestClient(main.app) as client:
        response = client.post(
            "/queue/process",
            files={"files": ("screen-recording.mp4", b"video-only", "video/mp4")},
        )

    assert response.status_code == 422
    assert "没有可转录的音轨" in response.json()["detail"]
    assert jobs == []
    assert enqueued == []
    assert events[0]["event_name"] == "media_preflight_rejected"
    assert not list((tmp_path / "sources").rglob("source.*"))


def test_direct_process_rejects_invalid_media_before_creating_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    events: list[dict] = []
    jobs: list[dict] = []
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: events.append(kwargs))
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))

    def reject(path):
        raise MediaPreflightError("media_container_unreadable", "媒体文件无法读取，可能已损坏或文件内容与扩展名不匹配。")

    monkeypatch.setattr(processing_router, "preflight_media_file", reject)

    with TestClient(main.app) as client:
        response = client.post(
            "/process",
            files={"file": ("broken.mp4", b"not-media", "video/mp4")},
            data={"stt_provider": "elevenlabs_scribe"},
        )

    assert response.status_code == 422
    assert jobs == []
    assert events[0]["event_name"] == "media_preflight_rejected"
    assert not list((tmp_path / "sources").rglob("source.*"))


def test_queue_runner_rechecks_media_before_starting_pipeline(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"not-media")

    def reject(path):
        raise MediaPreflightError("media_container_unreadable", "媒体文件无法读取，可能已损坏或文件内容与扩展名不匹配。")

    monkeypatch.setattr(_H, "preflight_media_file", reject)

    with pytest.raises(MediaPreflightError, match="媒体文件无法读取"):
        _H._run_queued_transcription({
            "task_id": "legacy-task",
            "source_path": str(source),
            "filename": "source.mp4",
        })


def test_enqueue_transcription_job_writes_persistent_step(monkeypatch) -> None:
    steps: list[dict] = []
    signals: list[dict] = []

    monkeypatch.setattr(_H, "enqueue_job_step", lambda **kwargs: steps.append(kwargs) or {"id": 1})
    monkeypatch.setattr(_H, "_ensure_queue_worker_started_locked", lambda: None)
    monkeypatch.setattr(_H._TRANSCRIPTION_QUEUE, "put", lambda item: signals.append(item))

    _H._enqueue_transcription_job({
        "task_id": "task-persistent",
        "source_path": "/tmp/source.mp4",
        "filename": "source.mp4",
    })

    assert steps[0]["task_id"] == "task-persistent"
    assert steps[0]["step_type"] == "transcription"
    assert steps[0]["step_key"] == "task-persistent:transcription"
    assert signals == [{"wake": "transcription", "task_id": "task-persistent"}]


def test_claimed_queue_step_finishes_with_its_lease_owner(monkeypatch) -> None:
    completed: list[dict] = []
    monkeypatch.setattr(_H, "_run_job_step", lambda step: None)
    monkeypatch.setattr(_H, "_start_job_step_heartbeat", lambda step: (threading.Event(), None))
    monkeypatch.setattr(
        _H,
        "complete_job_step",
        lambda step_id, *, lock_id: completed.append({"step_id": step_id, "lock_id": lock_id}) or {"id": step_id},
    )

    _H._run_claimed_job_step({"id": 9, "task_id": "task-owned", "lock_id": "lease-owner", "step_type": "transcription"})

    assert completed == [{"step_id": 9, "lock_id": "lease-owner"}]


def test_retry_job_from_stored_source_requeues_without_browser_upload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(_H, "list_jobs", lambda *args, **kwargs: [])
    monkeypatch.setattr(_H, "_media_duration_seconds", lambda path: 2106.0)

    old_source = tmp_path / "sources" / "old-task" / "source.mp4"
    old_source.parent.mkdir(parents=True)
    old_source.write_bytes(b"stored video")
    old_job = {
        "task_id": "old-task",
        "status": "cancelled",
        "client_id": "anonymous",
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "source_file_size_mb": 97.3,
        "metadata": {"queue_options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true"}},
    }
    jobs: dict[str, dict] = {}
    enqueued: list[dict] = []

    def fake_get_job(task_id, client_id=None):
        if task_id == "old-task":
            return old_job
        return jobs.get(task_id)

    def fake_upsert_job(**kwargs):
        jobs[kwargs["task_id"]] = kwargs

    monkeypatch.setattr(_H, "get_job", fake_get_job)
    monkeypatch.setattr(_H, "upsert_job", fake_upsert_job)
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: enqueued.append(item))
    monkeypatch.setattr(jobs_router, "preflight_media_file", lambda path: _passing_media_preflight())

    with TestClient(main.app) as client:
        response = client.post("/jobs/old-task/retry")

    assert response.status_code == 200
    payload = response.json()
    new_task_id = payload["task_id"]
    assert new_task_id != "old-task"
    assert payload["job"]["status"] == "queued"
    assert jobs[new_task_id]["metadata"]["retry_source_task_id"] == "old-task"
    assert jobs[new_task_id]["metadata"]["queue_options"]["stt_provider"] == "elevenlabs_scribe"
    assert jobs[new_task_id]["metadata"]["queue_options"]["skip_summary"] == "true"
    assert enqueued == [{
        "task_id": new_task_id,
        "source_path": str(Path(enqueued[0]["source_path"])),
        "filename": "lesson.mp4",
        "options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true", "title": "lesson"},
        "base_url": "http://testserver",
        "client_id": "anonymous",
    }]
    assert Path(enqueued[0]["source_path"]).read_bytes() == b"stored video"
    assert Path(enqueued[0]["source_path"]).parent.name == new_task_id


def test_retry_job_requeues_completed_oss_source_without_browser_upload(monkeypatch) -> None:
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(_H, "list_jobs", lambda *args, **kwargs: [])
    monkeypatch.setattr(_H, "_find_source_file", lambda task_id: None)
    for name in [
        "_enforce_submission_rate_limit",
        "_enforce_active_job_limit",
        "_enforce_global_active_job_limit",
        "_enforce_daily_quota",
        "_enforce_global_daily_quota",
    ]:
        monkeypatch.setattr(_H, name, lambda *args, **kwargs: None)

    old_job = {
        "task_id": "old-oss-task",
        "status": "failed",
        "client_id": "anonymous",
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "source_file_size_mb": 97.3,
        "metadata": {
            "source_storage": "oss",
            "oss_upload_session_id": "session-1",
            "queue_options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true"},
        },
    }
    jobs: dict[str, dict] = {}
    enqueued: list[dict] = []
    session_scopes: list[str] = []

    def fake_get_job(task_id, client_id=None):
        if task_id == "old-oss-task":
            return old_job if client_id == "anonymous" else None
        return jobs.get(task_id)

    def fake_session(session_id, *, owner_scope):
        session_scopes.append(owner_scope)
        assert session_id == "session-1"
        return {
            "session_id": session_id,
            "status": "completed",
            "object_key": "uploads/source/user-a/lesson.mp4",
            "source_filename": "lesson.mp4",
            "content_length": 97 * 1024 * 1024,
        }

    def fake_upsert_job(**kwargs):
        jobs[kwargs["task_id"]] = kwargs

    monkeypatch.setattr(_H, "get_job", fake_get_job)
    monkeypatch.setattr(_H, "upsert_job", fake_upsert_job)
    monkeypatch.setattr(_H, "_enqueue_oss_source_download", lambda item: enqueued.append(item))
    monkeypatch.setattr(jobs_router, "get_oss_upload_session", fake_session)

    with TestClient(main.app) as client:
        response = client.post("/jobs/old-oss-task/retry")

    assert response.status_code == 200
    payload = response.json()
    new_task_id = payload["task_id"]
    assert new_task_id != "old-oss-task"
    assert session_scopes == ["anonymous"]
    assert payload["job"]["stage"] == "source_download"
    assert jobs[new_task_id]["metadata"]["retry_source_task_id"] == "old-oss-task"
    assert jobs[new_task_id]["metadata"]["source_storage"] == "oss"
    assert enqueued == [{
        "task_id": new_task_id,
        "object_key": "uploads/source/user-a/lesson.mp4",
        "expected_size_bytes": 97 * 1024 * 1024,
        "filename": "lesson.mp4",
        "options": {"stt_provider": "elevenlabs_scribe", "skip_summary": "true", "title": "lesson"},
        "base_url": "http://testserver",
        "client_id": "anonymous",
        "oss_upload_session_id": "session-1",
        "route": "/jobs/{task_id}/retry",
    }]


def test_main_processing_route_does_not_accept_or_forward_hotwords() -> None:
    assert "hotwords" not in inspect.signature(start_transcription_process).parameters
    assert "hotwords" not in _H._queue_options_from_mapping({"hotwords": "legacy term"})
    assert "hotwords" not in _H._queue_options_from_form(
        export_to_lark=None,
        lark_export_route=None,
        lark_via_cli=None,
        title=None,
        folder_token=None,
        deepseek_api_key=None,
        openai_api_key=None,
        ai_provider=None,
        ai_model=None,
        note_mode=None,
        skip_summary=None,
        stt_model=None,
        stt_speed=None,
        stt_language=None,
        stt_provider=None,
        elevenlabs_api_key=None,
        speaker_diarization=None,
        lark_app_id=None,
        lark_app_secret=None,
        system_prompt=None,
        prompt_preset=None,
        prompt_preset_label=None,
    )
