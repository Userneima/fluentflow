from __future__ import annotations

from fastapi.testclient import TestClient

import backend.main as main


def test_queue_process_persists_multiple_files_without_running_stt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "log_event", lambda **kwargs: None)

    jobs: list[dict] = []
    enqueued: list[dict] = []
    monkeypatch.setattr(main, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(main, "_enqueue_transcription_job", lambda item: enqueued.append(item))

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
    assert "deepseek_api_key" not in jobs[0]["metadata"]["queue_options"]
    assert "azure_speech_key" not in jobs[0]["metadata"]["queue_options"]
    assert "azure_blob_container_sas_url" not in jobs[0]["metadata"]["queue_options"]

    assert len(enqueued) == 2
    assert enqueued[0]["task_id"] == jobs[0]["task_id"]
    assert enqueued[1]["task_id"] == jobs[1]["task_id"]
    for item in enqueued:
        assert item["base_url"].startswith("http://testserver")
        assert (tmp_path / "sources" / item["task_id"]).is_dir()
