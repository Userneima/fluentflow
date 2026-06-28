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
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    settings = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "export const DEFAULT_STT_PROVIDER = 'elevenlabs_scribe'" in shared
    assert "allowedSttProviders: ['elevenlabs_scribe', 'local']" in shared
    assert "const localAwareAllowed = publicMode || uniqueAllowed.includes('local')" in shared
    assert "const localAwareAllowed = publicMode || uniqueAllowed.includes('local')" in job_morph
    assert "sttProvider: 'elevenlabs_scribe'" in settings
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


def test_dashboard_homepage_copy_matches_recording_product_positioning() -> None:
    source = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")

    assert "今天想记录些什么呢？" in source
    assert "What do you want to record today?" in source
    assert "今天想创作些什么呢？" not in source
    assert "What do you want to create today?" not in source


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


def test_editor_routes_generation_explanation_to_agent_workflow() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "summaryFailureNextStep" in source
    assert "agentWorkflowHref" in source
    assert "Agent 工作流" in source
    assert "生成详情" not in source
    assert "summaryCompactMeta" not in source
    assert "summaryGenerationMeta" not in source
    assert "summaryReasonItems" not in source
    assert "prompt.activeHint" not in source
    assert "noteModeText" not in source
    assert "fixed bottom-16 right-8" not in source
    assert "planNoteStrategy.reason" in processing
    assert "noteModePlanReason" in shared
    assert "chapter_coverage" in shared
    assert "完整覆盖笔记" in shared


def test_editor_uses_compact_review_workbench_layout() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "转录原文" in source
    assert "笔记正文" in source
    assert "inline-flex h-10 items-center" in source
    assert "h-[82px]" not in source
    assert "w-[360px]" not in source
    assert "当前结果没有时间戳分段，只能按纯文本编辑" not in source
    assert "No timestamped segments. Retranscribe the source audio" in source
    assert "flex justify-end border-t" in source
    assert "生成详情" not in source
    assert "生成中英对照" not in source
    assert "Add Bilingual" not in source
    assert "handleTranslateTranscript" not in source
    assert "translatingTranscript" not in source
    assert "translateJobSegments" not in source
    assert "纯文本模式" not in source
    assert "Plain text" not in source
    assert "转录已保存" in source
    assert "editRecords.length > 0" in source
    assert "导出转录" in source


def test_editor_video_review_keeps_current_subtitle_as_core_object() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "const [transcriptReviewMode, setTranscriptReviewMode] = useState('text')" in source
    assert "const canUseVideoReview = mediaKind === 'video' && !!mediaUrl && segments.length > 0" in source
    assert "文本校对" in source
    assert "视频复查" in source
    assert "currentVideoSegment" in source
    assert "当前字幕" in source
    assert "handleVideoSegmentStep" in source
    assert "fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)" in source
    assert "max-h-[min(42vh,360px)]" in source
    assert "视频复查模式不是视频播放器页面" in design_system
    assert "没有原视频、没有时间戳或只有音频时" in design_system


def test_editor_destructive_top_actions_require_confirmation() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    legacy_i18n = Path("frontend/src/app/i18n.jsx").read_text(encoding="utf-8")
    format_helpers = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")
    tasks = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "const [regenerateConfirmOpen, setRegenerateConfirmOpen] = useState(false)" in source
    assert "onClick={()=>setRegenerateConfirmOpen(true)}" in source
    assert "edit.regenerateConfirmTitle" in source
    assert "edit.regenerateConfirmDesc" in source
    assert "edit.regenerateConfirmAction" in source
    assert "onClick={handleRegenerate}" in source
    assert "setRetranscribeConfirmOpen(true)" in source
    assert "onClick={handleRetranscribe}" in source
    assert "'edit.regenerate':'重生笔记'" in shared
    assert "'edit.regenerateConfirmAction':'确认重生笔记'" in shared
    assert "点击“重生笔记”" in source
    assert "点击重新生成" not in shared
    assert "export {I18nProvider, msgs, useI18n} from './shared.jsx';" in legacy_i18n
    assert "点击“重新生成”" not in format_helpers
    assert "重新生成摘要" not in tasks
    assert "重新生成笔记" not in agent_trace


def test_editor_agent_workflow_link_requires_real_task_id() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "const activeTaskId = result?.task_id || fallbackTaskIdRef.current" in source
    assert "const agentWorkflowHref = result?.task_id ? `/tasks/${encodeURIComponent(result.task_id)}/agent` : '/processing';" in source
    assert "encodeURIComponent(activeTaskId)}/agent" not in source


def test_agent_trace_uses_existing_api_fetch_helper() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "API_BASE, apiFetch, noteModeLabel, useI18n" in source
    assert "apiFetch(`${API_BASE}/agent/v1/tasks/${encodeURIComponent(taskId)}/package`)" in source
    assert "request: apiRequest" not in source
    assert "apiRequest(" not in source


def test_agent_trace_prioritizes_material_specific_judgment() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "buildJudgmentCards" in source
    assert "材料判断" in source
    assert "笔记策略" in source
    assert "复查点" in source
    assert "转录信号" in source
    assert "对结果的影响" in source
    assert "executionSteps" in source
    assert "tool_trace" in source
    assert "THOUGHT_GENERATORS" not in source
    assert "inner monologue" not in source
    assert "内心独白" not in source


def test_processing_page_is_agent_workflow_surface() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "Agent 工作流" in source
    assert "执行路线" in source
    assert "Agent 判断" in source
    assert "使用依据" in source
    assert "processing_plan" in source
    assert "note_strategy" in source
    assert "planSteps" in source
    assert "planEvidence" in source
    assert "计划依据" in source
    assert "高级详情" in source
    assert "editorActionLabel" in source
    assert "h-dvh overflow-y-auto" in source


def test_processing_page_uses_timeline_not_card_stack() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "const Card" not in source
    assert "<Card" not in source
    assert "xl:border-l" in source
    assert "grid-cols-[44px_minmax(0,1fr)]" in source
    assert "rounded-[14px] bg-[#f4f3f3] px-4 py-3" not in source


def test_processing_page_uses_compact_tool_header() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "FLUENTFLOW AGENT" not in source
    assert "text-[34px]" not in source
    assert "lg:text-[44px]" not in source
    assert "任务解释" in source
    assert "Page Header Density" in design_system
    assert "不要在应用内页面顶部放大面积品牌标题" in design_system


def test_processing_page_constrains_long_task_titles() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert 'className="grid min-w-0 gap-7' in source
    assert 'className="min-w-0 space-y-7"' in source
    assert "min-w-0 max-w-full flex-1 overflow-hidden" in source
    assert "max-w-full truncate font-headline" in source
    assert "只给文本节点加 `truncate` 不够" in design_system
    assert "minmax(0, 1fr)" in design_system
    assert "打开编辑器重生笔记" in source
    assert 'to="/settings"' in source
    assert "ml-[var(--sidebar-offset)]" in source
    assert "saveCredentials" not in source
    assert "getCredentialsStatus" not in source
    assert "secretDraft" not in source
    assert "<select" not in source
    assert "updateSettingNow" not in source


def test_workflow_next_step_copy_is_action_oriented() -> None:
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    tasks = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "复查结果" in processing
    assert "查看运行状态" in processing
    assert "重生笔记" in processing
    assert "开始处理任务" in processing
    assert "结果可以复查" not in processing
    assert "任务正在运行" not in processing
    assert "还没有可解释的任务" not in processing
    assert "下一步：删除这条取消记录。" in tasks
    assert "下一步：可以删除" not in tasks
    assert "复查结果" in agent_trace
    assert "打开编辑器复查正文" in agent_trace
    assert "可以随时下载或导出" not in agent_trace
    assert "Action-Oriented Copy" in design_system
    assert "避免把行动标题写成状态判断句" in design_system


def test_ui_copy_does_not_leak_internal_product_principles() -> None:
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "按执行顺序展示本次任务经过的处理步骤。" in processing
    assert "这不是多 Agent 表演" not in processing
    assert "decorative multi-agent theater" not in processing
    assert "证据摘要" in agent_trace
    assert "可复查的判断结论、依据和影响" in agent_trace
    assert "不适合直接喂给模型" not in agent_trace
    assert "而不是按时间戳" not in agent_trace
    assert "内心独白" not in agent_trace
    assert "内部产品原则不能原样进入 UI" in design_system
    assert "避免防御性文案和自证清白式表达" in design_system


def test_sidebar_keeps_visible_login_entry_for_accounts_mode() -> None:
    source = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")

    assert "showAccountLoginEntry = (authMode === 'accounts' || guestMode) && !user" in source
    assert "sidebarLoginActionTitle" in source
    assert "sidebarLoginActionSubtitle" in source
    assert "anonymousEntryTitle" in source
    assert "登录账号" in source
    assert "同步任务和额度" in source
    assert "AnonymousEntryIcon" in source
    assert "onClick={() => openAuth('login')}" in source
    assert "{showAccountLoginEntry && (" in source
    assert "min-h-0 flex-1" in source
    assert "overflow-y-auto" in source


def test_auth_status_failure_keeps_login_path_visible() -> None:
    source = Path("frontend/src/app/AccessGate.jsx").read_text(encoding="utf-8")

    assert "} catch(_) {" in source
    assert "setAuthMode('accounts');" in source
    assert "setRequired(true);" in source
    assert "setAuthenticated(false);" in source
    assert "setGuestMode(false);" in source


def test_secondary_surfaces_use_current_ui_language() -> None:
    access_gate = Path("frontend/src/app/AccessGate.jsx").read_text(encoding="utf-8")
    about = Path("frontend/src/routes/about.jsx").read_text(encoding="utf-8")
    prompt_dialog = Path("frontend/src/components/PromptTemplateDialog.jsx").read_text(encoding="utf-8")
    settings = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")

    for source in (access_gate, about, prompt_dialog):
        assert "rounded-sm" not in source
        assert "text-purple" not in source
        assert "bg-purple" not in source
        assert "border-slate" not in source
        assert "text-slate" not in source

    assert "min-h-dvh" in access_gate
    assert "bg-[#f8f7fb]" in access_gate
    assert "关于与协议" in about
    assert "grid gap-3 px-5 py-5 md:grid-cols-[180px_minmax(0,1fr)]" in about
    assert "presetChipClass" in prompt_dialog
    assert "textAreaClass" in prompt_dialog
    assert "dark:hover:bg-white/[0.88]" in prompt_dialog
    assert "rounded-sm" not in settings
    assert "hover:bg-blue" not in settings
    assert "单次任务判断放在 Agent 工作流里解释" in settings


def test_settings_page_stays_focused_on_real_settings() -> None:
    source = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")

    assert "处理偏好" in source
    assert "导出与集成" in source
    assert "数据与隐私" in source
    assert "系统维护" in source
    assert "账号与额度" not in source
    assert "笔记模板" not in source
    assert "外观" not in source
    assert "lg:grid-cols-[210px_minmax(0,1fr)]" not in source
    assert "长期偏好、凭证和模板维护" not in source
    assert "清除当前浏览器保存的本地历史记录，不会删除服务器任务" in source
    assert "当前是线上云端环境，本地转录不可用" in source
    assert "本机打开时可以选择本地或云端" in source
    assert "Agent 会根据内容自动选用最匹配的" not in source
    assert "Agent auto-selects the best match" not in source


def test_settings_clear_history_requires_confirmation_dialog() -> None:
    source = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")

    assert "clearConfirmOpen" in source
    assert "confirmClearHistory" in source
    assert 'role="dialog"' in source
    assert "确认清除本地历史？" in source
    assert "setClearArmed" not in source
    assert "edit.clearConfirmAgain" not in source


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
