from __future__ import annotations

import json
from pathlib import Path

from scripts import codex_transcribe_link as script


def test_resolve_stt_provider_prefers_local_when_available() -> None:
    config = {"allowed_stt_providers": ["azure_batch", "local"], "default_stt_provider": "azure_batch"}

    assert script.resolve_stt_provider("auto", config) == "local"


def test_resolve_stt_provider_falls_back_to_runtime_default() -> None:
    config = {"allowed_stt_providers": ["azure_batch"], "default_stt_provider": "azure_batch"}

    assert script.resolve_stt_provider("auto", config) == "azure_batch"
    assert script.resolve_stt_provider("local", config) == "azure_batch"


def test_build_codex_result_keeps_transcript_summary_and_artifact_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUENTFLOW_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    job = {
        "task_id": "task-1",
        "status": "completed",
        "stage": "done",
        "source_filename": "demo.mp4",
        "source_type": "video",
        "metadata": {"video_source": {"title": "Demo title"}},
        "result": {
            "filename": "demo.mp4",
            "stt_provider": "local",
            "source_language": "en",
            "subtitle_mode": "bilingual_en_zh",
            "transcript_text": "Hello world",
            "segments": [{"start": 0, "end": 1, "text": "Hello world"}],
            "translated_segments_zh": [{"start": 0, "end": 1, "text": "你好世界"}],
            "summary_markdown": "# Summary",
            "artifacts": {
                "transcript_bilingual_srt": {
                    "filename": "demo_bilingual_zh.srt",
                    "url": "/jobs/task-1/artifacts/transcript_bilingual_srt",
                }
            },
        },
    }

    payload = script.build_codex_result(
        job,
        api_base="http://127.0.0.1:8000/",
        client_id="local-yuchao",
        stt_provider="local",
    )

    assert payload["title"] == "Demo title"
    assert payload["transcript_text"] == "Hello world"
    assert payload["summary_markdown"] == "# Summary"
    assert payload["translated_segments_zh"][0]["text"] == "你好世界"
    assert payload["artifact_paths"]["transcript_bilingual_srt"].endswith("task-1/demo_bilingual_zh.srt")


def test_build_codex_result_strips_generated_video_prefix_from_title() -> None:
    job = {
        "task_id": "task-title",
        "status": "completed",
        "metadata": {"video_source": {"title": "7653403556564700443-超级周期已经开始 富人投资5类资产"}},
        "result": {"filename": "7653403556564700443-超级周期已经开始 富人投资5类资产.mp4"},
    }

    payload = script.build_codex_result(
        job,
        api_base="http://127.0.0.1:8000",
        client_id="local-yuchao",
        stt_provider="local",
    )

    assert payload["title"] == "超级周期已经开始 富人投资5类资产"


def test_write_result_accepts_directory_output(tmp_path: Path) -> None:
    payload = {"task_id": "task-2", "transcript_text": "text"}

    output = script.write_result(payload, str(tmp_path))

    assert output == tmp_path / "task-2.json"
    assert json.loads(output.read_text(encoding="utf-8"))["transcript_text"] == "text"


def test_create_video_job_marks_local_execution_header(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_api_request(method: str, api_base: str, path: str, **kwargs):
        captured.update({"method": method, "api_base": api_base, "path": path, **kwargs})
        return {"job": {"task_id": "task-local"}}

    monkeypatch.setattr(script, "api_request", fake_api_request)

    job = script.create_video_job(
        "https://v.douyin.com/demo/",
        api_base="http://127.0.0.1:8000",
        client_id="local-yuchao",
        access_token=None,
        stt_provider="local",
        skip_summary=False,
        stt_model="medium",
        stt_speed="balanced",
        note_mode=None,
        prompt_preset=None,
    )

    assert job["task_id"] == "task-local"
    assert captured["path"] == "/video-sources/jobs"
    assert captured["local_execution"] is True
    assert captured["payload"]["options"]["stt_provider"] == "local"
    assert captured["payload"]["options"]["skip_summary"] == "false"
