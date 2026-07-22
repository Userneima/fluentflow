from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import backend.core.server_helpers as H
import backend.routers.agent as agent_router
from backend.main import app


def test_agent_task_package_returns_stable_agent_contract(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_get_job(task_id: str, client_id: str | None = None):
        captured["task_id"] = task_id
        captured["client_id"] = client_id
        return {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "source_type": "video_link",
            "source_filename": "demo.mp4",
            "summary_status": "completed",
            "metadata": {
                "raw_title": "1234567890123-Demo title",
                "display_title": "Demo title",
                "stt_provider": "elevenlabs_scribe",
                "video_source": {
                    "provider": "youtube-yt-dlp",
                    "url": "https://example.com/video",
                    "media_type": "video",
                    "file_ext": ".mp4",
                    "resolution_trace": [{"provider": "yt-dlp", "status": "selected"}],
                },
            },
            "result": {
                "filename": "demo.mp4",
                "display_title": "Demo title",
                "source_language": "en",
                "subtitle_mode": "bilingual_zh",
                "translation_status": "completed",
                "transcript_text": "Hello world",
                "corrected_transcript_text": "Hello World",
                "corrected_segments": [{"start": 0, "end": 1, "text": "Hello World"}],
                "transcript_correction_status": "completed",
                "transcript_correction": {
                    "transcript_correction_version": "1",
                    "status": "completed",
                    "applied_count": 1,
                    "note_input_applied": True,
                },
                "transcript_corrections": [
                    {
                        "segment_index": 0,
                        "start": 0,
                        "end": 1,
                        "original_text": "Hello world",
                        "corrected_text": "Hello World",
                        "reason": "Terminology capitalization.",
                        "confidence": 0.9,
                    }
                ],
                "note_generation_transcript_source": "corrected_transcript",
                "segments": [{"start": 0, "end": 1, "text": "Hello world"}],
                "translated_segments_zh": [{"start": 0, "end": 1, "text": "你好世界"}],
                "summary_markdown": "# Summary",
                "summary_status": "completed",
                "stt_provider": "elevenlabs_scribe",
                "cloud_transcription": {
                    "provider": "elevenlabs_scribe",
                    "elevenlabs_request_id": "req-demo",
                    "elevenlabs_http_status": 200,
                    "elevenlabs_outcome": "completed",
                },
                "chapter_coverage": {
                    "chapter_coverage_version": "1",
                    "summary": {"evidence_count": 1, "chapter_count": 1},
                    "evidence": [{"evidence_id": "E001", "text": "Important point", "covered": True}],
                    "chapters": [{"chapter_id": "CH01", "title": "Core", "evidence_ids": ["E001"]}],
                },
                "artifacts": {"summary_md": {"filename": "demo.md", "url": "/jobs/task-agent/artifacts/summary_md"}},
                "visual_requests": [
                    {
                        "id": "vr_001",
                        "note_section": "核心概念",
                        "start_seconds": 10,
                        "end_seconds": 20,
                        "reason": "这里需要展示核心示意图。",
                        "query": "选择清晰的核心示意图",
                        "priority": "high",
                        "max_images": 1,
                    }
                ],
                "visual_frame_selections": [
                    {
                        "request_id": "vr_001",
                        "note_section": "核心概念",
                        "filename": "visual_001.jpg",
                        "caption": "核心示意图",
                        "reason": "这张图最清晰。",
                        "confidence": "high",
                        "purpose": "inline_evidence",
                        "timestamp_seconds": 12.5,
                    }
                ],
                "visual_key_moments": [
                    {
                        "id": "key_visual_001",
                        "request_id": "vr_002",
                        "timestamp_seconds": 42.0,
                        "caption": "代码演示画面",
                        "reason": "适合复查代码示例，但不插入正文。",
                        "note_section": "代码演示",
                        "confidence": "medium",
                        "purpose": "key_moment",
                        "source": "visual_frame_selection",
                        "provider": "local_ffmpeg",
                        "artifact_url": "/jobs/task-agent/artifacts/frame?file=code_001.jpg",
                        "filename": "frames/code_001.jpg",
                    }
                ],
                "visual_key_moments_status": "completed",
                "visual_key_moments_reason": "视觉模型选择了适合复查但未插入正文的关键画面。",
                "visual_evidence_pipeline": "text_plan_qwen_local_window",
                "visual_evidence": [
                    {
                        "id": "visual_001",
                        "timestamp_seconds": 12.5,
                        "reason": "这一帧展示了课程中的核心示意图。",
                        "note_section": "核心概念",
                        "source": "agent_transcript",
                        "confidence": "high",
                        "provider": "local_ffmpeg",
                        "artifact_kind": "visual_001",
                    }
                ],
                "visual_artifacts": {
                    "visual_001": {
                        "filename": "visual/visual_001.jpg",
                        "url": "/jobs/task-agent/artifacts/frame?file=visual_001.jpg",
                        "content_type": "image/jpeg",
                        "timestamp_seconds": 12.5,
                        "provider": "local_ffmpeg",
                    }
                },
                "frame_artifacts": [
                    {"kind": "frame", "filename": "frames/frame_001.jpg", "url": "/jobs/task-agent/artifacts/frame?file=frame_001.jpg"}
                ],
            },
        }

    monkeypatch.setattr(H, "get_job", fake_get_job)

    response = TestClient(app).get(
        "/agent/v1/tasks/task-agent/package",
        headers={"X-FluentFlow-Client-Id": "client-a"},
    )

    assert response.status_code == 200
    package = response.json()
    assert captured == {"task_id": "task-agent", "client_id": "client-a"}
    assert package["agent_task_package_version"] == "1"
    assert package["task"]["task_id"] == "task-agent"
    assert package["title"] == "Demo title"
    assert package["source"]["type"] == "video_link"
    assert package["source"]["video_source"]["provider"] == "youtube-yt-dlp"
    assert package["source"]["video_source"]["media_type"] == "video"
    assert package["source"]["video_source"]["resolution_trace"] == [{"provider": "yt-dlp", "status": "selected"}]
    assert package["transcript"]["text"] == "Hello world"
    assert package["transcript"]["raw_segments"][0]["text"] == "Hello world"
    assert package["transcript"]["display_segments"][0]["text_zh"] == "你好世界"
    assert package["transcript"]["corrected_text"] == "Hello World"
    assert package["transcript"]["corrected_segments"][0]["text"] == "Hello World"
    assert package["transcript"]["corrections"][0]["confidence"] == 0.9
    assert package["transcript"]["correction"]["status"] == "completed"
    assert package["transcript"]["note_input_source"] == "corrected_transcript"
    assert package["note"]["status"] == "completed"
    assert package["note"]["markdown"] == "# Summary"
    assert package["note"]["diagnosis"]["code"] == "note_completed"
    assert package["note"]["chapter_coverage"]["evidence"][0]["evidence_id"] == "E001"
    assert package["usage"]["cloud_transcription"]["elevenlabs_request_id"] == "req-demo"
    assert package["usage"]["cloud_transcription"]["elevenlabs_outcome"] == "completed"
    assert package["processing_plan"]["processing_plan_version"] == "1"
    assert package["processing_plan"]["material"]["source_type"] == "video_link"
    assert package["decision_log"]["decision_log_version"] == "1"
    assert any(entry["id"] == "note_generation_outcome" for entry in package["decision_log"]["entries"])
    assert package["artifacts"]["summary_md"]["url"] == "/jobs/task-agent/artifacts/summary_md"
    assert package["visual"]["available"] is True
    assert package["visual"]["key_moments_available"] is True
    assert package["visual"]["candidate_frame_count"] == 1
    assert package["visual"]["evidence"][0]["artifact_url"] == "/jobs/task-agent/artifacts/frame?file=visual_001.jpg"
    assert package["visual"]["evidence"][0]["reason"] == "这一帧展示了课程中的核心示意图。"
    assert package["visual"]["artifacts"]["visual_001"]["filename"] == "visual/visual_001.jpg"
    assert package["visual"]["pipeline"] == "text_plan_qwen_local_window"
    assert package["visual"]["requests"][0]["id"] == "vr_001"
    assert package["visual"]["frame_selections"][0]["request_id"] == "vr_001"
    assert package["visual"]["frame_selections"][0]["purpose"] == "inline_evidence"
    assert package["visual"]["key_moments"][0]["purpose"] == "key_moment"
    assert package["visual"]["key_moments"][0]["artifact_url"].endswith("code_001.jpg")
    assert package["visual"]["key_moments_status"] == "completed"
    assert package["next_actions"] == []


def test_agent_task_package_explains_missing_note(monkeypatch) -> None:
    monkeypatch.setattr(
        H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "source_type": "video",
            "source_filename": "demo.mp4",
            "summary_status": "skipped",
            "result": {
                "filename": "demo.mp4",
                "transcript_text": "Transcript is available",
                "summary_skipped": True,
                "summary_status": "skipped",
            },
        },
    )

    response = TestClient(app).get("/agent/v1/tasks/task-skipped/package")

    assert response.status_code == 200
    package = response.json()
    assert package["note"]["status"] == "skipped"
    assert package["note"]["diagnosis"]["code"] == "transcript_only_mode"
    assert package["note"]["diagnosis"]["retryable"] is True
    assert package["next_actions"][0]["action"] == "regenerate_note"


def test_agent_task_package_exposes_retry_for_failed_oss_source(monkeypatch) -> None:
    monkeypatch.setattr(
        H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "stage": "oss_source_download",
            "progress": 0,
            "source_type": "video",
            "source_filename": "lesson.mp4",
            "error_reason": "云端文件下载失败。",
            "metadata": {"source_storage": "oss", "oss_upload_session_id": "session-1"},
            "result": {},
        },
    )

    response = TestClient(app).get("/agent/v1/tasks/task-oss/package")

    assert response.status_code == 200
    assert response.json()["next_actions"][0] == {
        "action": "retry_task",
        "method": "POST",
        "path": "/agent/v1/tasks/task-oss/retry",
        "reason": "已上传的云端文件可直接重新进入处理队列，无需再次上传。",
    }


def test_agent_task_retry_reuses_existing_retry_contract(monkeypatch) -> None:
    retried_job = {
        "task_id": "retried-task",
        "status": "queued",
        "stage": "source_download",
        "source_type": "video",
        "source_filename": "lesson.mp4",
        "metadata": {"source_storage": "oss"},
    }
    monkeypatch.setattr(
        agent_router,
        "retry_job_from_stored_source",
        lambda request, task_id: {"ok": True, "source_task_id": task_id, "task_id": "retried-task", "job": retried_job},
    )

    response = TestClient(app).post("/agent/v1/tasks/old-task/retry")

    assert response.status_code == 200
    assert response.json()["task_id"] == "retried-task"
    assert response.json()["package_url"] == "/agent/v1/tasks/retried-task/package"


def test_agent_task_package_returns_404_for_missing_job(monkeypatch) -> None:
    monkeypatch.setattr(H, "get_job", lambda task_id, client_id=None: None)

    response = TestClient(app).get("/agent/v1/tasks/missing/package")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_agent_create_video_link_task_starts_existing_video_source_flow(monkeypatch) -> None:
    calls: dict[str, object] = {}

    for name in [
        "_enforce_submission_rate_limit",
        "_enforce_active_job_limit",
        "_enforce_global_active_job_limit",
        "_enforce_daily_quota",
        "_enforce_global_daily_quota",
    ]:
        monkeypatch.setattr(H, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(H, "_new_task_id", lambda: "agent-link-task")
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(H, "upsert_job", lambda **kwargs: calls.setdefault("upsert", kwargs))
    monkeypatch.setattr(H, "_start_video_source_job", lambda payload: calls.setdefault("started", payload))
    monkeypatch.setattr(
        H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "running",
            "stage": "resolving",
            "progress": 2,
            "client_id": client_id,
        },
    )

    response = TestClient(app).post(
        "/agent/v1/tasks",
        headers={"X-FluentFlow-Client-Id": "client-a"},
        json={"input": "https://v.douyin.com/demo/", "options": {"stt_provider": "local", "skip_summary": False}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "agent-link-task"
    assert data["package_url"] == "/agent/v1/tasks/agent-link-task/package"
    assert calls["started"]["task_id"] == "agent-link-task"
    assert calls["started"]["options"]["stt_provider"] == "local"
    assert calls["upsert"]["client_id"] == "client-a"


def test_agent_wait_returns_package_for_terminal_task(monkeypatch) -> None:
    monkeypatch.setattr(
        H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "result": {"transcript_text": "Done", "summary_markdown": "# Done"},
        },
    )

    response = TestClient(app).post("/agent/v1/tasks/task-done/wait", json={"timeout_seconds": 0})

    assert response.status_code == 200
    data = response.json()
    assert data["done"] is True
    assert data["package"]["task"]["status"] == "completed"
    assert data["package"]["note"]["diagnosis"]["code"] == "note_completed"


def test_agent_regenerate_note_uses_stored_transcript_and_updates_package(monkeypatch) -> None:
    stored: dict[str, object] = {}
    captured: dict[str, str] = {}

    def fake_get_job(task_id: str, client_id: str | None = None):
        if stored.get("updated"):
            return stored["updated"]
        return {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "source_type": "video",
            "source_filename": "demo.mp4",
            "result": {
                "task_id": task_id,
                "filename": "demo.mp4",
                "transcript_text": "Hello",
                "corrected_transcript_text": "Hello corrected",
                "note_generation_transcript_source": "corrected_transcript",
            },
        }

    def fake_upsert_job(**kwargs):
        stored["updated"] = {
            "task_id": kwargs["task_id"],
            "status": kwargs["status"],
            "stage": kwargs["stage"],
            "summary_status": kwargs["summary_status"],
            "source_type": kwargs["source_type"],
            "source_filename": kwargs["source_filename"],
            "result": kwargs["result"],
        }

    monkeypatch.setattr(H, "get_job", fake_get_job)
    monkeypatch.setattr(H, "upsert_job", fake_upsert_job)
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(H, "_attach_result_artifacts", lambda task_id, result: result)
    monkeypatch.setattr(H, "_plan_note_mode_for_summary", lambda kwargs, transcript, **meta: (kwargs, {"requested_note_mode": "auto"}))

    def fake_summarize(transcript, **kwargs):
        captured["transcript"] = transcript
        return SimpleNamespace(
            markdown="# New note",
            requested_mode="auto",
            resolved_mode="direct",
            chunk_count=1,
            segment_count=None,
            evidence_count=None,
            chapter_count=None,
            important_evidence_count=None,
            covered_important_evidence_count=None,
            coverage_missing_count=None,
        )

    monkeypatch.setattr(
        H,
        "summarize_transcript_with_metadata",
        fake_summarize,
    )

    response = TestClient(app).post("/agent/v1/tasks/task-note/note/regenerate", json={"note_mode": "auto"})

    assert response.status_code == 200
    package = response.json()["package"]
    assert package["note"]["markdown"] == "# New note"
    assert package["note"]["diagnosis"]["code"] == "note_completed"
    assert captured["transcript"] == "Hello corrected"
    assert stored["updated"]["summary_status"] == "completed"


def test_agent_export_uses_stored_note_markdown(monkeypatch) -> None:
    stored: dict[str, object] = {}

    def fake_get_job(task_id: str, client_id: str | None = None):
        if stored.get("updated"):
            return stored["updated"]
        return {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "source_type": "video",
            "source_filename": "demo.mp4",
            "summary_status": "completed",
            "result": {"task_id": task_id, "filename": "demo.mp4", "summary_markdown": "# Note", "transcript_text": "Hello"},
        }

    def fake_upsert_job(**kwargs):
        stored["updated"] = {
            "task_id": kwargs["task_id"],
            "status": kwargs["status"],
            "stage": kwargs["stage"],
            "progress": kwargs["progress"],
            "summary_status": kwargs["summary_status"],
            "source_type": kwargs["source_type"],
            "source_filename": kwargs["source_filename"],
            "result": kwargs["result"],
        }

    monkeypatch.setattr(H, "get_job", fake_get_job)
    monkeypatch.setattr(H, "upsert_job", fake_upsert_job)
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(H, "export_markdown_to_lark", lambda title, markdown, **kwargs: {"ok": True, "url": "https://feishu.cn/docx/demo"})

    response = TestClient(app).post("/agent/v1/tasks/task-export/exports", json={"target": "lark", "title": "Demo"})

    assert response.status_code == 200
    data = response.json()
    assert data["export"]["url"] == "https://feishu.cn/docx/demo"
    assert data["package"]["note"]["markdown"] == "# Note"
    assert stored["updated"]["result"]["exports"][0]["url"] == "https://feishu.cn/docx/demo"


def test_agent_export_can_use_feishu_user_oauth_route(monkeypatch) -> None:
    stored: dict[str, object] = {}
    captured: dict[str, object] = {}

    def fake_get_job(task_id: str, client_id: str | None = None):
        if stored.get("updated"):
            return stored["updated"]
        return {
            "task_id": task_id,
            "status": "completed",
            "stage": "done",
            "progress": 100,
            "source_type": "video",
            "source_filename": "demo.mp4",
            "summary_status": "completed",
            "result": {"task_id": task_id, "filename": "demo.mp4", "summary_markdown": "# Note", "transcript_text": "Hello"},
        }

    def fake_upsert_job(**kwargs):
        stored["updated"] = {
            "task_id": kwargs["task_id"],
            "status": kwargs["status"],
            "stage": kwargs["stage"],
            "progress": kwargs["progress"],
            "summary_status": kwargs["summary_status"],
            "source_type": kwargs["source_type"],
            "source_filename": kwargs["source_filename"],
            "result": kwargs["result"],
        }

    def fake_export(title, markdown, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "url": "https://feishu.cn/docx/user", "auth_mode": "user_oauth"}

    monkeypatch.setattr(H, "_request_client_scope", lambda request: "user:account-1")
    monkeypatch.setattr(H, "get_valid_feishu_user_access_token", lambda user_id: f"user-token-for-{user_id}")
    monkeypatch.setattr(H, "get_job", fake_get_job)
    monkeypatch.setattr(H, "upsert_job", fake_upsert_job)
    monkeypatch.setattr(H, "log_event", lambda **kwargs: None)
    monkeypatch.setattr(H, "export_markdown_to_lark", fake_export)

    response = TestClient(app).post(
        "/agent/v1/tasks/task-export/exports",
        json={"target": "lark", "title": "Demo", "lark_export_route": "user_oauth"},
    )

    assert response.status_code == 200
    assert response.json()["export"]["route"] == "feishu_user_oauth"
    assert captured["user_access_token"] == "user-token-for-account-1"
