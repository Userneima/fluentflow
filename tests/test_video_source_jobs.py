from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.core.video_source import SavedVideoSource


def test_video_source_job_downloads_then_enqueues_transcription(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    source_file = tmp_path / "downloaded.mp4"
    source_file.write_bytes(b"downloaded video")
    saved = SavedVideoSource(
        ok=True,
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=demo123",
        download_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        video_id="demo123",
        title="测试视频",
        filename="demo123-测试视频.mp4",
        file_path=str(source_file),
        file_url="/video-sources/files/demo123.mp4",
        metadata_path=str(tmp_path / "downloaded.source.json"),
        size_bytes=source_file.stat().st_size,
        downloaded_at="2026-06-06T00:00:00+08:00",
    )
    monkeypatch.setattr(main, "download_video_source", lambda *args, **kwargs: saved)
    monkeypatch.setattr(main, "log_event", lambda **kwargs: None)
    enqueued: list[dict] = []
    jobs: list[dict] = []
    monkeypatch.setattr(main, "_enqueue_transcription_job", lambda item: enqueued.append(item))
    monkeypatch.setattr(main, "upsert_job", lambda **kwargs: jobs.append(kwargs))

    main._run_video_source_job({
        "task_id": "task-link",
        "input": "https://v.douyin.com/demo/",
        "options": {"stt_provider": "azure_batch", "skip_summary": "true"},
        "base_url": "http://testserver",
    })

    assert enqueued == [{
        "task_id": "task-link",
        "source_path": str(tmp_path / "sources" / "task-link" / "source.mp4"),
        "filename": "demo123-测试视频.mp4",
        "options": {"stt_provider": "azure_batch", "skip_summary": "true"},
        "base_url": "http://testserver",
    }]
    final_job = jobs[-1]
    assert final_job["status"] == "queued"
    assert final_job["stage"] == "queued"
    assert final_job["source_type"] == "video"
    assert final_job["metadata"]["video_source"]["provider"] == "direct"
    assert Path(final_job["metadata"]["source_path"]).read_bytes() == b"downloaded video"


def test_create_video_source_job_filters_sensitive_options(monkeypatch) -> None:
    monkeypatch.setattr(main, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(main, "upsert_job", lambda **kwargs: None)
    started: list[dict] = []
    monkeypatch.setattr(main, "_start_video_source_job", lambda item: started.append(item))

    with TestClient(main.app) as client:
        response = client.post(
            "/video-sources/jobs",
            json={
                "input": "3.21 复制打开抖音 https://v.douyin.com/demo/",
                "options": {
                    "stt_provider": "azure_batch",
                    "deepseek_api_key": "secret",
                    "azure_blob_container_sas_url": "https://example.com?sig=secret",
                },
            },
        )

    assert response.status_code == 200
    assert started
    assert started[0]["options"] == {"stt_provider": "azure_batch"}
