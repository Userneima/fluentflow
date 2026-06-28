from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import backend.main as main
from backend.main import app
import backend.core.server_helpers as _H


def test_client_routes_fall_back_to_frontend_index() -> None:
    client = TestClient(app)

    response = client.get("/processing")

    assert response.status_code == 200
    assert "FluentFlow" in response.text
    assert 'type="module"' in response.text
    assert 'src="/assets/' in response.text


def test_api_like_unknown_routes_still_return_404() -> None:
    client = TestClient(app)

    assert client.get("/jobs/not-found/extra").status_code == 404
    assert client.get("/process").status_code == 404
    assert client.get("/missing.js").status_code == 404


def test_frontend_asset_route_serves_javascript_not_spa_html() -> None:
    assets_dir = Path("frontend/dist/assets")
    asset = next(assets_dir.glob("index-*.js"))
    response = TestClient(app).get(f"/assets/{asset.name}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert not response.text.lstrip().startswith("<!DOCTYPE html>")


def test_processing_page_no_longer_exposes_settings_controls() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "set.sttLanguage" not in source
    assert "settings.sttLanguage||\"auto\"" not in source
    assert "<select" not in source
    assert "updateSettingNow" not in source


def test_frontend_cloud_stt_defaults_to_elevenlabs() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    settings = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "export const DEFAULT_STT_PROVIDER = 'elevenlabs_scribe'" in shared
    assert "allowedSttProviders: ['elevenlabs_scribe', 'local']" in shared
    assert 'value="elevenlabs_scribe"' in settings
    assert "ElevenLabs 云端转录" in processing
    assert "isCloudSttConfigured(sttProvider, status)" in editor
    assert "isAzureCloudProvider(sttProvider)" not in editor


def test_dashboard_stops_polling_stale_missing_job() -> None:
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "err?.status === 404" in dashboard
    assert "prev?.taskId === currentJob.taskId ? null : prev" in dashboard
    assert "const cachedRunning = cachedJobs.find" not in shared
    assert "err.status = r.status" in shared
    assert "subscribeJobEvents" in shared


def test_tasks_open_cached_result_without_backend_detail_request() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "isCachedOnlyTask" in source
    assert "isCachedOnlyTask(job) && job.result" in source
    assert "err.status === 404 && job.result" in source
    assert "err.status = r.status" in shared
    assert "const {__cacheOnly, ...persistedJob} = job" in shared


def test_tasks_strip_generated_video_prefix_from_video_source_title() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")

    assert "jobDisplayTitle" in source
    assert r"/^[0-9]{10,24}[-_]+/" in fmt
    assert "metadata.display_title" in shared
    assert "videoSource.display_title" in shared
    assert "result.display_title" in shared
    assert "displayTitleForUser(" in shared


def test_history_entries_preserve_raw_filename_and_display_title() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "normalizeHistoryEntryTitles" in shared
    assert "readBrowserHistoryEntries()" in shared
    assert "displayTitle: displayTitle || rawTitle" in shared
    assert "rawFilename" in shared
    assert "filename: h.rawFilename || h.name" in shared
    assert "display_title: h.displayTitle || displayTitleForUser(h.name, h.rawFilename)" in shared


def test_frontend_no_longer_prompts_for_local_history_import() -> None:
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "发现本机历史" not in dashboard
    assert "Local history found" not in dashboard
    assert "导入当前账号" not in dashboard
    assert "localHistoryImport" not in dashboard
    assert "importLocalHistory" not in dashboard
    assert "/local-history/candidates" not in shared
    assert "/account/import-history" not in shared
    assert "fluentflow_processed_import_keys" not in shared


def test_frontend_no_longer_exposes_hotword_review_ui_or_payload() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "work.hotword" not in shared
    assert "work.reviewMode" not in shared
    assert "work.reviewUseAi" not in shared
    assert "edit.reviewButton" not in shared
    assert "edit.reviewTitle" not in shared
    assert "热词库" not in shared
    assert "字幕审阅" not in shared
    assert "Hotword library" not in shared
    assert "Subtitle review" not in shared
    assert "LEGACY_REMOVED_SETTING_KEYS" in shared
    assert "hotwordLibrary" in shared
    assert "reviewUseAi" in shared
    combined_routes = "\n".join([dashboard, editor, processing])
    assert "hotword" not in combined_routes.lower()
    assert "reviewMode" not in combined_routes


def test_tasks_route_does_not_use_source_filename_as_display_title() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "const displayTitle = jobDisplayTitle(job, lang)" in source
    assert "title={displayTitle}" in source
    assert "{displayTitle}</h2>" in source
    assert "const displayTitle = job?.source_filename" not in source
    assert "<h2 className=\"text-sm font-headline font-extrabold text-on-surface truncate\" title={job.source_filename}" not in source


def test_editor_lark_export_uses_local_execution_header_on_localhost() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "shouldUseLocalSingleUserClientId()" in source
    assert "localExecutionHeaders({localExecution: true, larkExportRoute})" in source
    assert "fd.append('lark_export_route', larkExportRoute)" in source
    assert "isLocalLarkExportRoute(larkExportRoute)" in source
    assert "options.localExecution" in shared
    assert "isLocalLarkExportRoute(options.larkExportRoute)" in shared


def test_settings_page_uses_explicit_lark_export_routes() -> None:
    settings = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "larkExportRouteFromSettings(settings)" in settings
    assert "LARK_EXPORT_ROUTE_OPENAPI" in settings
    assert "LARK_EXPORT_ROUTE_LOCAL_CLI" in settings
    assert "larkExportRouteFromSettings(settings)" not in processing
    assert "set.larkExportRoute" in shared
    assert "fd.append(\"lark_export_route\", larkRoute)" in shared
    assert "payloadOptions.lark_export_route = larkRoute" in shared
    assert "id=\"workLarkViaCli\"" not in processing


def test_editor_uses_local_channel_for_local_job_result_requests() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "const jobOptionsForResult = (result)" in source
    assert "if (isLocalHistoryResult(result)) return;" in source
    assert "getJob(result.task_id, resultJobOptions)" in source
    assert "fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)" in source
    assert "saveTranscriptEdit(result.task_id, {" in source
    assert "}, resultJobOptions)" in source
    assert "const fetchJobSourceFile = async (taskId, filename='source', options={})" in shared
    assert "const saveTranscriptEdit = async (taskId, payload={}, options={})" in shared


def test_subtitle_import_is_a_note_generation_action() -> None:
    source = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "导入字幕生成笔记" in shared
    assert "skipSummary: false" in source
    assert "summarizeTranscriptFile(file, {taskId, ...buildAiOptions(settings), skipSummary: false}" in source
    assert "\.(srt|vtt|txt|md)$" in source


def test_editor_bilingual_view_keeps_original_subtitle_mode() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")
    download = Path("frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert "中英对照" in source
    assert "原始字幕" in source
    assert "pickDisplayTranscriptSegments(result, segments)" in source
    assert "displaySegments: pickDisplayTranscriptSegments(result" in shared
    assert "export const pickDisplayTranscriptSegments" in fmt
    assert "bilingualTranscriptSegments" in source
    assert "visibleTranscriptView === 'bilingual'" in source
    assert "segment?.text_zh" in download


def test_editor_explains_generation_reasons() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "noteModeReasonText" in source
    assert "note_mode_plan_reason" in source
    assert "chapter_coverage" in source
    assert "note_mode_chapter_count" in source
    assert "note_mode_evidence_count" in source
    assert "note_mode_covered_important_evidence_count" in source
    assert "promptPresetReasonText" in source
    assert "subtitleReasonText" in source
    assert "summaryFailureNextStep" in source
    assert "summaryReasonItems.map" in source
    assert "noteModePlanReason" in shared
    assert "chapter_coverage" in shared
    assert "完整覆盖笔记" in shared


def test_processing_page_is_agent_workflow_surface() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "Agent 工作流" in source
    assert "执行路线" in source
    assert "Agent 判断" in source
    assert "使用依据" in source
    assert "高级详情" in source
    assert 'to="/settings"' in source
    assert "ml-[var(--sidebar-offset)]" in source
    assert "saveCredentials" not in source
    assert "getCredentialsStatus" not in source
    assert "secretDraft" not in source
    assert "<select" not in source
    assert "updateSettingNow" not in source


def test_tasks_show_actionable_next_step_for_failures() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "taskNextStepText" in source
    assert "Unsupported note generation mode" in source or "unsupported note generation mode" in source
    assert "下一步：" in source
    assert "旧模式残留" not in source
    assert "当前版本已不支持的笔记模式" in source
    assert "{nextStepText}" in source


def test_failed_job_can_be_deleted(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).delete("/jobs/task-failed", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_failed_job_can_be_deleted_via_post_fallback(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "failed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).post("/jobs/task-failed/delete", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-failed"]
    assert deleted == [(["task-failed"], "client-a")]


def test_completed_job_can_be_deleted(monkeypatch) -> None:
    deleted: list[tuple[list[str], str | None]] = []
    cleaned: list[str] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "completed",
            "client_id": client_id,
            "metadata": {"source": "test"},
        },
    )
    monkeypatch.setattr(_H, "_cleanup_task_all_files", lambda task_id, metadata=None: cleaned.append(task_id) or {})
    monkeypatch.setattr(_H, "delete_jobs", lambda task_ids, client_id=None: deleted.append((list(task_ids), client_id)) or 1)

    response = TestClient(app).delete("/jobs/task-done", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert cleaned == ["task-done"]
    assert deleted == [(["task-done"], "client-a")]


def test_running_job_delete_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {"task_id": task_id, "status": "running", "client_id": client_id},
    )

    response = TestClient(app).delete("/jobs/task-running", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 409


def test_running_job_can_be_cancelled(monkeypatch) -> None:
    cancelled: list[str] = []
    released: list[str] = []
    updated: list[dict] = []
    logged: list[str] = []
    published: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        _H,
        "get_job",
        lambda task_id, client_id=None: {
            "task_id": task_id,
            "status": "running",
            "client_id": client_id,
            "stage": "stt",
            "progress": 42,
            "source_type": "video",
            "source_filename": "demo.mp4",
            "source_file_size_mb": 12,
            "summary_status": None,
            "metadata": {"source": "test"},
        },
    )

    async def fake_cancel(task_id: str) -> bool:
        cancelled.append(task_id)
        return True

    async def fake_publish(task_id: str, event: dict) -> None:
        published.append((task_id, event))

    monkeypatch.setattr(_H.JOB_EVENTS, "cancel", fake_cancel)
    monkeypatch.setattr(_H.JOB_EVENTS, "publish", fake_publish)
    monkeypatch.setattr(
        _H,
        "_release_task_quota",
        lambda client_id, task_id, reason, metadata=None: released.append(task_id),
    )
    monkeypatch.setattr(_H, "upsert_job", lambda **kwargs: updated.append(kwargs))
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: logged.append(kwargs["event_name"]))

    response = TestClient(app).post("/jobs/task-running/cancel", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert cancelled == ["task-running"]
    assert released == ["task-running"]
    assert updated[0]["status"] == "cancelled"
    assert updated[0]["error_reason"] == "user_cancelled"
    assert published[0][1]["stage"] == "error"
    assert logged == ["task_cancelled"]


def test_manual_lark_export_does_not_require_stored_job(monkeypatch) -> None:
    exported: list[tuple[str, str]] = []
    logged: list[dict] = []

    monkeypatch.setattr(_H, "get_job", lambda task_id, client_id=None: None)
    monkeypatch.setattr(_H, "log_event", lambda **kwargs: logged.append(kwargs))

    def fake_export(title: str, markdown: str) -> dict:
        exported.append((title, markdown))
        return {"ok": True, "url": "https://example.feishu.cn/docx/demo"}

    monkeypatch.setattr(_H, "export_markdown_via_lark_cli", fake_export)

    response = TestClient(app).post(
        "/export-lark",
        headers={"X-FluentFlow-Client-Id": "client-a"},
        data={
            "task_id": "missing-local-history-task",
            "markdown": "# Demo\n\ncontent",
            "title": "Demo",
            "lark_export_route": "local_cli",
        },
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.feishu.cn/docx/demo"
    assert response.json()["task_id"] == "missing-local-history-task"
    assert exported == [("Demo", "# Demo\n\ncontent")]
    assert [item["event_name"] for item in logged] == ["lark_export_started", "lark_export_completed"]
    assert [item["export_target"] for item in logged] == ["lark_cli", "lark_cli"]
