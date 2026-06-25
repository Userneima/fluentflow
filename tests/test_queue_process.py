from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

import backend.main as main
import backend.core.server_helpers as _H
from backend.core.stt_process import start_transcription_process


def test_queue_process_persists_multiple_files_without_running_stt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)

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
                "stt_provider": "azure_batch",
                "stt_model": "medium",
                "skip_summary": "true",
                "export_to_lark": "true",
                "lark_export_route": "local_cli",
                "lark_via_cli": "true",
                "deepseek_api_key": "secret-deepseek",
                "azure_speech_key": "secret-azure",
                "azure_blob_container_sas_url": "https://example.blob.core.windows.net/fluentflow?sig=secret",
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
    assert jobs[0]["metadata"]["queue_options"]["stt_provider"] == "azure_batch"
    assert jobs[0]["metadata"]["queue_options"]["skip_summary"] == "true"
    assert jobs[0]["metadata"]["queue_options"]["export_to_lark"] == "true"
    assert jobs[0]["metadata"]["queue_options"]["lark_export_route"] == "local_cli"
    assert "deepseek_api_key" not in jobs[0]["metadata"]["queue_options"]
    assert "azure_speech_key" not in jobs[0]["metadata"]["queue_options"]
    assert "azure_blob_container_sas_url" not in jobs[0]["metadata"]["queue_options"]

    assert len(enqueued) == 2
    assert enqueued[0]["task_id"] == jobs[0]["task_id"]
    assert enqueued[1]["task_id"] == jobs[1]["task_id"]
    for item in enqueued:
        assert item["base_url"].startswith("http://testserver")
        assert (tmp_path / "sources" / item["task_id"]).is_dir()


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
        azure_speech_key=None,
        azure_speech_endpoint=None,
        azure_blob_container_sas_url=None,
        speaker_diarization=None,
        lark_app_id=None,
        lark_app_secret=None,
        system_prompt=None,
        prompt_preset=None,
        prompt_preset_label=None,
    )
