"""Tests for backend.core.tool_trace — deterministic trace builder."""

from backend.core.tool_trace import build_tool_trace


def _job(overrides=None):
    return dict({
        "task_id": "test-1",
        "status": "completed",
        "source_type": "video",
        "source_filename": "lecture.mp4",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:05:00",
    }, **(overrides or {}))


def _result(overrides=None):
    return dict({
        "task_id": "test-1",
        "source": "video",
        "filename": "lecture.mp4",
        "stt_provider": "local",
        "stt_model": "medium",
        "stt_elapsed_seconds": 45.2,
        "stt_realtime_factor": 2.1,
        "detected_language": "zh",
        "transcript_text": "这节课讲的是 Agent 设计模式。",
        "raw_segments": [
            {"start": 0.0, "end": 2.0, "text": "这节课讲的是 Agent 设计模式。"},
        ],
        "transcript_cleanup": {
            "applied_count": 1,
            "removed_segment_count": 0,
            "issues": [{"type": "repeat", "count": 1}],
        },
        "summary_markdown": "# Agent 设计模式\n\n核心概念...",
        "summary_status": "completed",
        "resolved_note_mode": "direct",
        "ai_provider": "deepseek",
        "ai_model": "deepseek-reasoner",
        "audio_duration_seconds": 120.0,
        "artifacts": {
            "summary_md": {"filename": "note.md"},
            "transcript_srt": {"filename": "transcript.srt"},
        },
    }, **(overrides or {}))


class TestBuildToolTrace:
    def test_local_video_full_pipeline(self):
        trace = build_tool_trace(_result(), job=_job())
        assert trace["status"] == "completed"
        assert trace["step_count"] >= 6
        ids = [s["id"] for s in trace["steps"]]
        assert "save_source" in ids
        assert "extract_audio" in ids
        assert "local_stt" in ids
        assert "cleanup_transcript" in ids
        assert "generate_note" in ids
        assert "save_artifacts" in ids

    def test_local_stt_step_metadata(self):
        trace = build_tool_trace(_result(), job=_job())
        stt = next(s for s in trace["steps"] if s["id"] == "local_stt")
        assert stt["status"] == "completed"
        assert stt["vendor"] == "faster-whisper"
        assert stt["metadata"]["model"] == "medium"
        assert stt["metadata"]["language"] == "zh"
        assert stt["duration_seconds"] == 45.2

    def test_note_step_metadata(self):
        trace = build_tool_trace(_result(), job=_job())
        note = next(s for s in trace["steps"] if s["id"] == "generate_note")
        assert note["status"] == "completed"
        assert note["metadata"]["note_mode"] == "direct"
        assert note["metadata"]["provider"] == "deepseek"

    def test_summary_skipped_omits_note_step(self):
        result = _result({"summary_markdown": "", "summary_skipped": True, "summary_status": "skipped"})
        trace = build_tool_trace(result, job=_job())
        ids = [s["id"] for s in trace["steps"]]
        assert "generate_note" not in ids

    def test_summary_failed_reports_error(self):
        result = _result({"summary_markdown": "", "summary_error": "AI 返回空笔记"})
        trace = build_tool_trace(result, job=_job())
        note = next(s for s in trace["steps"] if s["id"] == "generate_note")
        assert note["status"] == "failed"
        assert "空笔记" in note["error_reason"]
        assert "generate_note" in trace["failed_step_ids"]

    def test_transcript_file_skips_audio_steps(self):
        result = _result({
            "source": "transcript_file",
            "stt_provider": "",
            "transcript_text": "字幕导入内容...",
            "raw_segments": [],
            "transcript_cleanup": None,
            "audio_duration_seconds": None,
        })
        job = _job({"source_type": "transcript_file"})
        trace = build_tool_trace(result, job=job)
        ids = [s["id"] for s in trace["steps"]]
        assert "extract_audio" not in ids
        assert "local_stt" not in ids
        assert "cloud_stt" not in ids
        assert "parse_subtitles" in ids

    def test_video_link_pipeline(self):
        result = _result({"source": "video_link"})
        job = _job({"source_type": "video_link"})
        trace = build_tool_trace(result, job=job)
        ids = [s["id"] for s in trace["steps"]]
        assert "resolve_link" in ids
        assert "download_video" in ids

    def test_lark_export_success(self):
        result = _result({"lark_response": {"url": "https://feishu.cn/doc/123"}})
        trace = build_tool_trace(result, job=_job())
        lark = next(s for s in trace["steps"] if s["id"] == "export_lark")
        assert lark["status"] == "completed"
        assert lark["metadata"]["doc_url"] == "https://feishu.cn/doc/123"

    def test_lark_export_failure(self):
        result = _result({"lark_response": None, "lark_error": "Permission denied"})
        trace = build_tool_trace(result, job=_job())
        lark = next(s for s in trace["steps"] if s["id"] == "export_lark")
        assert lark["status"] == "failed"
        assert "export_lark" in trace["failed_step_ids"]

    def test_cloud_stt(self):
        result = _result({"stt_provider": "elevenlabs_scribe", "stt_model": "scribe_v2", "stt_elapsed_seconds": 300})
        trace = build_tool_trace(result, job=_job())
        stt = next(s for s in trace["steps"] if s["id"] == "cloud_stt")
        assert stt["vendor"] == "elevenlabs"
        assert stt["metadata"]["provider"] == "elevenlabs_scribe"

    def test_pending_job_returns_pending_status(self):
        job = _job({"status": "queued"})
        trace = build_tool_trace({}, job=job)
        assert trace["status"] == "pending"

    def test_diarization_requested_applied(self):
        result = _result({
            "speaker_diarization": {
                "requested": True,
                "applied": True,
                "speaker_count": 2,
            },
        })
        trace = build_tool_trace(result, job=_job())
        dia = next(s for s in trace["steps"] if s["id"] == "diarize_speakers")
        assert dia["status"] == "completed"
        assert dia["vendor"] == "pyannote"

    def test_diarization_requested_failed(self):
        result = _result({
            "speaker_diarization": {
                "requested": True,
                "applied": False,
                "error_reason": "pyannote token missing",
            },
        })
        trace = build_tool_trace(result, job=_job())
        dia = next(s for s in trace["steps"] if s["id"] == "diarize_speakers")
        assert dia["status"] == "failed"
        assert "diarize_speakers" in trace["failed_step_ids"]
