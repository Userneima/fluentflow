from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import backend.main as main
from backend.core.video_source import SavedVideoSource
import backend.core.server_helpers as _H


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
        raw_title="测试视频",
        display_title="测试视频",
        title="测试视频",
        filename="demo123-测试视频.mp4",
        file_path=str(source_file),
        file_url="/video-sources/files/demo123.mp4",
        metadata_path=str(tmp_path / "downloaded.source.json"),
        size_bytes=source_file.stat().st_size,
        downloaded_at="2026-06-06T00:00:00+08:00",
    )
    monkeypatch.setattr(_H, "download_video_source", lambda *args, **kwargs: saved)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    enqueued: list[dict] = []
    jobs: list[dict] = []
    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: enqueued.append(item))
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(_H, "_publish_job_event_from_thread", lambda task_id, event: published.append((task_id, event)))

    _H._run_video_source_job({
        "task_id": "task-link",
        "input": "https://v.douyin.com/demo/",
        "options": {"stt_provider": "azure_batch", "skip_summary": "true"},
        "base_url": "http://testserver",
    })

    assert enqueued == [{
        "task_id": "task-link",
        "source_path": str(tmp_path / "sources" / "task-link" / "source.mp4"),
        "filename": "demo123-测试视频.mp4",
        "raw_title": "测试视频",
        "display_title": "测试视频",
        "options": {"stt_provider": "azure_batch", "skip_summary": "true"},
        "base_url": "http://testserver",
    }]
    final_job = jobs[-1]
    assert final_job["status"] == "queued"
    assert final_job["stage"] == "queued"
    assert final_job["source_type"] == "video"
    assert final_job["metadata"]["video_source"]["provider"] == "direct"
    assert final_job["metadata"]["video_source"]["asset_strategy"] is None
    assert final_job["metadata"]["display_title"] == "测试视频"
    assert final_job["metadata"]["video_source"]["raw_title"] == "测试视频"
    assert final_job["metadata"]["video_source"]["display_title"] == "测试视频"
    assert Path(final_job["metadata"]["source_path"]).read_bytes() == b"downloaded video"
    assert published[-1] == ("task-link", {"stage": "queued", "progress": 0})


def test_video_source_job_submits_youtube_captions_to_transcript_route(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    source_file = tmp_path / "downloaded.srt"
    source_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    saved = SavedVideoSource(
        ok=True,
        provider="yt-dlp",
        source_url="https://www.youtube.com/watch?v=demo123",
        download_url="https://www.youtube.com/watch?v=demo123",
        video_id="demo123",
        raw_title="YouTube Demo",
        display_title="YouTube Demo",
        title="YouTube Demo",
        filename="demo123-YouTube Demo.srt",
        file_path=str(source_file),
        file_url="/video-sources/files/demo123-YouTube%20Demo.srt",
        metadata_path=str(tmp_path / "downloaded.source.json"),
        size_bytes=source_file.stat().st_size,
        downloaded_at="2026-06-06T00:00:00+08:00",
        media_type="transcript",
        asset_strategy={
            "transcript_asset": {"status": "completed"},
            "playback_asset": {"playback_mode": "external_url"},
            "visual_asset": {"status": "unavailable"},
            "download_status": "skipped",
            "failure_reason": None,
        },
    )
    submitted: list[dict] = []
    jobs: list[dict] = []
    monkeypatch.setattr(_H, "download_video_source", lambda *args, **kwargs: saved)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: (_ for _ in ()).throw(AssertionError("transcript source should not enqueue media transcription")))
    monkeypatch.setattr(_H, "_submit_transcript_source_file", lambda **kwargs: submitted.append(kwargs))
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    monkeypatch.setattr(_H, "_publish_job_event_from_thread", lambda *args, **kwargs: None)

    _H._run_video_source_job({
        "task_id": "task-link",
        "input": "https://youtu.be/demo123",
        "options": {"note_mode": "auto"},
        "base_url": "http://testserver",
    })

    assert submitted == [{
        "task_id": "task-link",
        "source_path": tmp_path / "sources" / "task-link" / "source.srt",
        "filename": "demo123-YouTube Demo.srt",
        "options": {"note_mode": "auto"},
        "base_url": "http://testserver",
        "client_id": None,
    }]
    final_job = jobs[-1]
    assert final_job["source_type"] == "transcript_file"
    assert final_job["metadata"]["video_source"]["media_type"] == "transcript"
    assert final_job["metadata"]["asset_strategy"]["transcript_asset"]["status"] == "completed"
    assert final_job["metadata"]["asset_strategy"]["playback_asset"]["playback_mode"] == "external_url"
    assert Path(final_job["metadata"]["source_path"]).suffix == ".srt"
    assert Path(final_job["metadata"]["source_path"]).read_text(encoding="utf-8").startswith("1\n")


def test_create_video_source_job_filters_sensitive_options(monkeypatch) -> None:
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    jobs: list[dict] = []
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: jobs.append(kwargs))
    started: list[dict] = []
    monkeypatch.setattr(_H, "_start_video_source_job", lambda item: started.append(item))

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
    payload = response.json()
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["stage"] == "queued"
    assert payload["job"]["progress"] == 0
    assert jobs[0]["status"] == "queued"
    assert jobs[0]["stage"] == "queued"
    assert jobs[0]["progress"] == 0
    assert started
    assert started[0]["options"] == {"stt_provider": "azure_batch"}


def test_video_source_job_publishes_resolving_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(tmp_path / "sources"))
    source_file = tmp_path / "downloaded.mp4"
    source_file.write_bytes(b"downloaded video")
    saved = SavedVideoSource(
        ok=True,
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=demo123",
        download_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        video_id="demo123",
        raw_title="测试视频",
        display_title="测试视频",
        title="测试视频",
        filename="demo123-测试视频.mp4",
        file_path=str(source_file),
        file_url="/video-sources/files/demo123.mp4",
        metadata_path=str(tmp_path / "downloaded.source.json"),
        size_bytes=source_file.stat().st_size,
        downloaded_at="2026-06-06T00:00:00+08:00",
    )

    def fake_download(*args, **kwargs):
        kwargs["on_progress"](_H.VideoSourceProgress(stage="resolving", message="正在解析分享链接", percent=8))
        return saved

    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(_H, "download_video_source", fake_download)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(_H, "_enqueue_transcription_job", lambda item: None)
    monkeypatch.setattr(_H, "_publish_job_event_from_thread", lambda task_id, event: published.append((task_id, event)))

    _H._run_video_source_job({
        "task_id": "task-link",
        "input": "https://v.douyin.com/demo/",
        "options": {"stt_provider": "azure_batch"},
        "base_url": "http://testserver",
    })

    assert ("task-link", {
        "stage": "resolving",
        "progress": 8.0,
        "message": "正在解析分享链接",
        "loaded_bytes": None,
        "total_bytes": None,
    }) in published


def test_start_video_source_job_writes_persistent_step(monkeypatch) -> None:
    steps: list[dict] = []
    signals: list[dict] = []

    monkeypatch.setattr(_H, "enqueue_job_step", lambda **kwargs: steps.append(kwargs) or {"id": 1})
    monkeypatch.setattr(_H, "_ensure_queue_worker_started_locked", lambda: None)
    monkeypatch.setattr(_H._TRANSCRIPTION_QUEUE, "put", lambda item: signals.append(item))

    _H._start_video_source_job({
        "task_id": "task-link",
        "input": "https://v.douyin.com/demo/",
        "options": {"stt_provider": "azure_batch"},
    })

    assert steps[0]["task_id"] == "task-link"
    assert steps[0]["step_type"] == "video_source"
    assert steps[0]["step_key"] == "task-link:video_source"
    assert signals == [{"wake": "video_source", "task_id": "task-link"}]


def test_local_queued_transcription_keeps_process_request_local(tmp_path, monkeypatch) -> None:
    source_file = tmp_path / "source.mp4"
    source_file.write_bytes(b"video")
    captured: list[dict] = []

    class DummyResponse:
        is_error = False

    class DummyClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            captured.append({"url": url, **kwargs})
            return DummyResponse()

    monkeypatch.setattr(_H, "get_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H.httpx, "Client", lambda **kwargs: DummyClient())

    _H._run_queued_transcription({
        "task_id": "task-local",
        "source_path": str(source_file),
        "filename": source_file.name,
        "options": {"stt_provider": "local"},
        "base_url": "http://127.0.0.1:8000",
    })

    assert captured
    assert captured[0]["headers"]["X-FluentFlow-Execution-Target"] == "local"


def test_local_transcript_source_submission_keeps_request_local(tmp_path, monkeypatch) -> None:
    source_file = tmp_path / "source.srt"
    source_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    captured: list[dict] = []

    class DummyResponse:
        is_error = False

    class DummyClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, **kwargs):
            captured.append({"url": url, **kwargs})
            return DummyResponse()

    monkeypatch.setattr(_H.httpx, "Client", lambda **kwargs: DummyClient())

    _H._submit_transcript_source_file(
        task_id="task-local-transcript",
        source_path=source_file,
        filename=source_file.name,
        options={"stt_provider": "local"},
        base_url="http://127.0.0.1:8000",
        client_id="local-single-user",
    )

    assert captured
    assert captured[0]["url"] == "http://127.0.0.1:8000/summarize-transcript-file"
    assert captured[0]["headers"]["X-FluentFlow-Execution-Target"] == "local"


def test_transcript_summary_queue_401_is_user_readable() -> None:
    raw = (
        'Queued transcript summary request failed: HTTP 401 '
        '{"detail":"FluentFlow account login is required.","auth_mode":"accounts","account_required":true}'
    )

    message = _H._friendly_error_message(raw)

    assert "账号未登录或登录态已失效" in message
    assert "HTTP 401" not in message
