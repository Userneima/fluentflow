from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import backend.main as main
from backend.core import job_store
from backend.core.server_helpers import (
    _attach_playback_audio_artifact,
    _attach_result_artifacts,
    _finalize_completed_result_storage,
)
import backend.core.server_helpers as _H


def test_attach_result_artifacts_writes_transcript_and_subtitle_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {
        "filename": "lesson.mp4",
        "transcript_text": "第一句\n第二句",
        "segments": [
            {"start": 0.0, "end": 1.25, "text": "第一句"},
            {"start": 1.25, "end": 3.5, "text": "第二句"},
        ],
        "summary_markdown": "# 摘要\n\n- 要点",
    }

    next_result = _attach_result_artifacts("task_artifact_test", result)

    artifacts = next_result["artifacts"]
    assert set(artifacts) == {"transcript_txt", "transcript_srt", "transcript_vtt", "summary_md"}
    for artifact in artifacts.values():
        assert artifact["url"].startswith("/jobs/task_artifact_test/artifacts/")
        assert (tmp_path / "task_artifact_test" / artifact["filename"]).is_file()

    srt = (tmp_path / "task_artifact_test" / artifacts["transcript_srt"]["filename"]).read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,250" in srt
    assert "第一句" in srt

    vtt = (tmp_path / "task_artifact_test" / artifacts["transcript_vtt"]["filename"]).read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.250 --> 00:00:03.500" in vtt

    summary = (tmp_path / "task_artifact_test" / artifacts["summary_md"]["filename"]).read_text(encoding="utf-8")
    assert summary.startswith("# 摘要")


def test_attach_result_artifacts_writes_bilingual_subtitles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {
        "filename": "english-lesson.mp4",
        "transcript_text": "Hello world\nSecond sentence",
        "segments": [
            {"start": 0.0, "end": 1.25, "text": "Hello world"},
            {"start": 1.25, "end": 3.5, "text": "Second sentence"},
        ],
        "translated_segments_zh": [
            {"start": 0.0, "end": 1.25, "text": "你好，世界"},
            {"start": 1.25, "end": 3.5, "text": "第二句"},
        ],
    }

    next_result = _attach_result_artifacts("task_bilingual_test", result)

    artifacts = next_result["artifacts"]
    assert "transcript_srt" in artifacts
    assert "transcript_bilingual_srt" in artifacts
    assert "transcript_bilingual_vtt" in artifacts
    bilingual_srt = (
        tmp_path / "task_bilingual_test" / artifacts["transcript_bilingual_srt"]["filename"]
    ).read_text(encoding="utf-8")
    assert "Hello world\n你好，世界" in bilingual_srt
    assert artifacts["transcript_bilingual_srt"]["filename"].endswith("_bilingual_zh.srt")
    assert next_result["result_schema_version"] == "2"
    assert next_result["raw_segments"][0]["text"] == "Hello world"
    assert next_result["display_segments"][0]["text_zh"] == "你好，世界"
    assert "segments" not in next_result
    assert "translated_segments_zh" not in next_result


def test_attach_result_artifacts_prefers_display_segments_for_bilingual_subtitles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {
        "filename": "english-lesson.mp4",
        "transcript_text": "Hello world",
        "raw_segments": [
            {"start": 0.0, "end": 1.25, "text": "Hello world"},
        ],
        "display_segments": [
            {"start": 0.0, "end": 1.25, "text": "Hello world.", "text_zh": "你好，世界。"},
        ],
        "translated_segments_zh": [
            {"start": 0.0, "end": 1.25, "text": "旧翻译"},
        ],
    }

    next_result = _attach_result_artifacts("task_display_segments_test", result)

    artifacts = next_result["artifacts"]
    bilingual_srt = (
        tmp_path / "task_display_segments_test" / artifacts["transcript_bilingual_srt"]["filename"]
    ).read_text(encoding="utf-8")
    source_srt = (
        tmp_path / "task_display_segments_test" / artifacts["transcript_srt"]["filename"]
    ).read_text(encoding="utf-8")
    assert "Hello world.\n你好，世界。" in bilingual_srt
    assert "旧翻译" not in bilingual_srt
    assert "Hello world" in source_srt
    assert "你好，世界。" not in source_srt


def test_attach_result_artifacts_adds_schema_version_when_nothing_to_write(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    result = {"filename": "empty.mp4"}

    next_result = _attach_result_artifacts("task_empty", result)

    assert next_result == {**result, "result_schema_version": "2"}
    assert not (tmp_path / "task_empty").exists()


def test_completed_result_retains_source_video_for_review(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "sources"
    task_source_dir = source_dir / "task_video"
    task_source_dir.mkdir(parents=True)
    source_file = task_source_dir / "source.mp4"
    source_file.write_bytes(b"video")
    temp_download = tmp_path / "download-cache.mp4"
    temp_download.write_bytes(b"duplicate")

    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(source_dir))
    monkeypatch.delenv("FLUENTFLOW_SOURCE_RETENTION_DAYS", raising=False)

    result = _finalize_completed_result_storage(
        "task_video",
        {"filename": "lesson.mp4", "source_file_available": True},
        {"video_source": {"file_path": str(temp_download)}},
    )

    assert result["source_file_available"] is True
    assert result["source_file_storage"] == "local"
    assert result["source_retention_status"] == "retained"
    assert result["source_retention_days"] == 7
    assert result["source_retention_expires_at"]
    assert source_file.is_file()
    assert not temp_download.exists()


def test_completed_result_can_delete_source_video_when_retention_disabled(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "sources"
    task_source_dir = source_dir / "task_delete_source"
    task_source_dir.mkdir(parents=True)
    source_file = task_source_dir / "source.mp4"
    source_file.write_bytes(b"video")

    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(source_dir))
    monkeypatch.setenv("FLUENTFLOW_SOURCE_RETENTION_DAYS", "0")

    result = _finalize_completed_result_storage(
        "task_delete_source",
        {"filename": "lesson.mp4", "source_file_available": True},
        {},
    )

    assert result["source_file_available"] is False
    assert result["source_retention_status"] == "deleted"
    assert not source_file.exists()


def test_history_retention_expires_only_source_video_not_result(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "sources"
    task_source_dir = source_dir / "task_expired_source"
    task_source_dir.mkdir(parents=True)
    source_file = task_source_dir / "source.mp4"
    source_file.write_bytes(b"video")
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    updates: list[dict] = []
    deleted: list[str] = []

    monkeypatch.setenv("FLUENTFLOW_SOURCE_DIR", str(source_dir))
    monkeypatch.setenv("FLUENTFLOW_HISTORY_RETENTION_PER_CLIENT", "100")
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_RETENTION_DAYS", "30")
    monkeypatch.setattr(
        _H,
        "list_jobs_for_retention",
        lambda client_id=None: [{
            "task_id": "task_expired_source",
            "client_id": client_id,
            "status": "completed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
            "result": {
                "task_id": "task_expired_source",
                "summary_markdown": "# Note",
                "source_file_available": True,
                "source_retention_expires_at": expired_at,
            },
        }],
    )
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.extend(task_ids))
    monkeypatch.setattr(_H, "update_job_result", lambda task_id, result, **kwargs: updates.append({"task_id": task_id, "result": result, **kwargs}))

    report = _H._enforce_history_retention("client-a")

    assert report["expired_source_count"] == 1
    assert report["pruned_count"] == 0
    assert deleted == []
    assert not source_file.exists()
    assert updates[0]["result"]["summary_markdown"] == "# Note"
    assert updates[0]["result"]["source_file_available"] is False
    assert updates[0]["result"]["source_retention_status"] == "expired"
    assert updates[0]["touch_updated_at"] is False


def test_playback_audio_artifact_survives_result_artifact_refresh(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    audio = tmp_path / "playback.mp3"
    audio.write_bytes(b"mp3")
    result = _attach_playback_audio_artifact(
        "task_audio",
        {"filename": "lesson.mp4", "transcript_text": "一句话"},
        audio,
    )

    next_result = _attach_result_artifacts("task_audio", result)

    artifacts = next_result["artifacts"]
    assert "playback_audio" in artifacts
    assert "transcript_txt" in artifacts
    assert (tmp_path / "task_audio" / artifacts["playback_audio"]["filename"]).read_bytes() == b"mp3"


def test_write_file_artifact_supports_nested_frame_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    source = tmp_path / "source.jpg"
    source.write_bytes(b"jpg")

    artifact = _H._write_file_artifact("task_frame", "frame", "frames/frame_001.jpg", source)

    assert artifact["kind"] == "frame"
    assert artifact["filename"] == "frames/frame_001.jpg"
    assert artifact["url"] == "/jobs/task_frame/artifacts/frame?file=frame_001.jpg"
    assert (tmp_path / "task_frame" / "frames" / "frame_001.jpg").read_bytes() == b"jpg"


def test_attach_result_artifacts_preserves_frame_download_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path))
    frame_dir = tmp_path / "input"
    frame_dir.mkdir()
    frame = frame_dir / "frame_001.jpg"
    frame.write_bytes(b"jpg")
    frame_artifact = _H._write_file_artifact("task_visual", "frame", "frames/frame_001.jpg", frame)

    result = _attach_result_artifacts(
        "task_visual",
        {
            "filename": "lesson.mp4",
            "transcript_text": "一句话",
            "frame_artifacts": [frame_artifact],
        },
    )

    artifacts = result["artifacts"]
    assert artifacts["frame_frame_001"]["url"] == "/jobs/task_visual/artifacts/frame?file=frame_001.jpg"
    assert artifacts["frame_frame_001"]["filename"] == "frames/frame_001.jpg"


def test_upload_job_playback_audio_persists_artifact_with_original_suffix(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobs.sqlite"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(artifact_dir))
    monkeypatch.delenv("FLUENTFLOW_ACCOUNT_AUTH", raising=False)
    monkeypatch.delenv("FLUENTFLOW_AUTH_MODE", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "get_job", lambda task_id, client_id=None: job_store.get_job(task_id, db_path=db_path, client_id=client_id))
    monkeypatch.setattr(_H, "update_job_result", lambda task_id, result, client_id=None: job_store.update_job_result(task_id, result, db_path=db_path, client_id=client_id))

    job_store.upsert_job(
        task_id="task_media",
        client_id="local-client",
        status="completed",
        stage="done",
        progress=100,
        source_type="audio",
        source_filename="lesson.m4a",
        result={"task_id": "task_media", "filename": "lesson.m4a", "transcript_text": "hello"},
        db_path=db_path,
    )

    with TestClient(main.app) as client:
        response = client.post(
            "/jobs/task_media/playback-audio",
            headers={"X-FluentFlow-Client-Id": "local-client"},
            files={"file": ("picked.m4a", b"audio-bytes", "audio/mp4")},
        )
        download = client.get(
            "/jobs/task_media/artifacts/playback_audio",
            headers={"X-FluentFlow-Client-Id": "local-client"},
        )

    assert response.status_code == 200
    artifact = response.json()["result"]["artifacts"]["playback_audio"]
    assert artifact["filename"].endswith(".m4a")
    assert response.json()["result"]["playback_audio_storage"] == "local"
    assert (artifact_dir / "task_media" / artifact["filename"]).read_bytes() == b"audio-bytes"
    assert download.status_code == 200
    assert download.content == b"audio-bytes"


def test_generate_job_zh_translations_persists_bilingual_artifacts(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobs.sqlite"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(artifact_dir))
    monkeypatch.delenv("FLUENTFLOW_ACCOUNT_AUTH", raising=False)
    monkeypatch.delenv("FLUENTFLOW_AUTH_MODE", raising=False)
    monkeypatch.setattr(_H, "_resume_queued_transcription_jobs", lambda *args, **kwargs: None)
    monkeypatch.setattr(_H, "get_job", lambda task_id, client_id=None: job_store.get_job(task_id, db_path=db_path, client_id=client_id))
    monkeypatch.setattr(_H, "update_job_result", lambda task_id, result, client_id=None: job_store.update_job_result(task_id, result, db_path=db_path, client_id=client_id))
    monkeypatch.setattr(
        _H,
        "generate_bilingual_segments_zh",
        lambda segments, **_kwargs: SimpleNamespace(
            segments=[
                {
                    "start": segments[0]["start"],
                    "end": segments[1]["end"],
                    "text": "Hello world. Second sentence.",
                    "text_zh": "你好，世界。第二句。",
                    "source_start_index": 0,
                    "source_end_index": 1,
                },
            ],
            translated_count=1,
            chunk_count=1,
        ),
    )

    job_store.upsert_job(
        task_id="task_translate",
        client_id="local-client",
        status="completed",
        stage="done",
        progress=100,
        source_type="video",
        source_filename="english.mp4",
        result={
            "task_id": "task_translate",
            "filename": "english.mp4",
            "transcript_text": "Hello world\nSecond sentence",
            "segments": [
                {"start": 0.0, "end": 1.25, "text": "Hello world"},
                {"start": 1.25, "end": 3.5, "text": "Second sentence"},
            ],
            "translation_status": "failed",
        },
        db_path=db_path,
    )

    response = TestClient(main.app).post(
        "/jobs/task_translate/translations/zh",
        headers={"X-FluentFlow-Client-Id": "local-client"},
        json={"aiProvider": "deepseek"},
    )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["translation_status"] == "completed"
    assert result["subtitle_mode"] == "bilingual_zh"
    assert result["result_schema_version"] == "2"
    assert result["raw_segments"][0]["text"] == "Hello world"
    assert result["display_segments"][0]["text_zh"] == "你好，世界。第二句。"
    assert "segments" not in result
    assert "bilingual_segments" not in result
    assert "translated_segments_zh" not in result
    artifacts = result["artifacts"]
    assert "transcript_bilingual_srt" in artifacts
    bilingual_srt = (
        artifact_dir / "task_translate" / artifacts["transcript_bilingual_srt"]["filename"]
    ).read_text(encoding="utf-8")
    assert "Hello world. Second sentence.\n你好，世界。第二句。" in bilingual_srt
