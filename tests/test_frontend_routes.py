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
    assert response.headers["cache-control"] == "no-cache"
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


def test_video_link_pending_task_title_uses_platform_not_tracking_query() -> None:
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")

    assert "videoLinkDisplayTitle(input, lang)" in dashboard
    assert "display_title: job.metadata?.display_title || pendingTitle" in dashboard
    assert "Bilibili 视频" in fmt
    assert "spm_id_from" not in fmt
    assert "videoLinkDisplayTitle" in shared


def test_dashboard_cancel_task_uses_close_icon_not_disabled_icon() -> None:
    source = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")

    assert '<SvgIcon name="close" className="h-4 w-4"/>{t(\'dash.cancelTask\')}' in source
    assert '<SvgIcon name="cancel" className="h-4 w-4"/>{t(\'dash.cancel\')}' not in source


def test_media_text_entry_panel_uses_subtle_diffuse_color() -> None:
    source = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")

    assert "radial-gradient(circle_at_18%_14%,rgba(0,174,236,.14)" in source
    assert "radial-gradient(circle_at_82%_10%,rgba(255,0,51,.08)" in source
    assert "bg-white/72 dark:bg-[#1d1f22]/78" in source
    assert "dark:bg-white/[0.06]" not in source.split("onDrop={handleDrop}", 1)[0].split("<section", 1)[-1]


def test_processing_page_no_longer_exposes_settings_controls() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "set.sttLanguage" not in source
    assert "settings.sttLanguage||\"auto\"" not in source
    assert "<select" not in source
    assert "updateSettingNow" not in source


def test_frontend_cloud_stt_defaults_to_elevenlabs() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    settings_model = Path("frontend/src/lib/settingsModel.js").read_text(encoding="utf-8")
    settings = Path("frontend/src/routes/settings.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "export const DEFAULT_STT_PROVIDER = 'elevenlabs_scribe'" in settings_model
    assert "allowedSttProviders: ['elevenlabs_scribe', 'local']" in settings_model
    assert "const localAwareAllowed = publicMode || uniqueAllowed.includes('local')" in settings_model
    assert "from '../lib/settingsModel.js'" in shared
    assert "from '../lib/settingsModel.js'" in job_morph
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
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")

    assert "isCachedOnlyTask" in source
    assert "isCachedOnlyTask(job) && job.result" in source
    assert "err.status === 404 && job.result" in source
    assert "err.status = r.status" in shared
    assert "const {__cacheOnly, ...persistedJob} = job" in mapper


def test_tasks_strip_generated_video_prefix_from_video_source_title() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")

    assert "jobDisplayTitle" in source
    assert r"/^(?:[0-9]{10,24}|BV[a-zA-Z0-9]{8,})[-_]+/" in fmt
    assert "metadata.display_title" in mapper
    assert "videoSource.display_title" in mapper
    assert "result.display_title" in mapper
    assert "displayTitleForUser(" in mapper


def test_history_uses_backend_jobs_and_cache_as_source_of_truth() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    app_provider = Path("frontend/src/app/AppProvider.jsx").read_text(encoding="utf-8")
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    media_text = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "readBrowserHistoryEntries" not in shared
    assert "readBrowserHistoryEntries" not in app_provider
    assert "localStorage.setItem('fluentflow_history'" not in shared
    assert "localStorage.setItem('fluentflow_history'" not in app_provider
    assert "const [history, setHistory] = useState([])" in shared
    assert "const [history, setHistory] = useState([])" in app_provider
    assert "readCachedAccountJobs(accountCacheId)" in shared
    assert "writeCachedAccountJobs(accountCacheId, data.jobs)" in shared
    assert "rawFilename" in mapper
    assert "filename: h.rawFilename || h.name" in mapper
    assert "display_title: h.displayTitle || displayTitleForUser(h.name, h.rawFilename)" in mapper
    assert "setLastResult(historyEntryToResult(h)); navigate('/editor');" in dashboard
    assert "setLastResult(historyEntryToResult(item));" in media_text
    assert "historyEntryToResult(history.find" not in editor
    assert "historyEntryToResult(latestHistory)" not in processing
    assert "latestHistory" not in processing


def test_frontend_job_mapping_lives_in_dedicated_module() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")

    assert "from '../lib/jobMappers.js'" in shared
    assert "from '../lib/jobMappers.js'" in job_morph
    assert "export const resultToHistoryEntry" not in shared
    assert "export const resultToHistoryEntry" not in job_morph
    assert "export const resultToHistoryEntry" in mapper
    assert "normalizeResultPayload" in mapper


def test_frontend_settings_model_lives_in_dedicated_module() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    settings_model = Path("frontend/src/lib/settingsModel.js").read_text(encoding="utf-8")

    assert "from '../lib/settingsModel.js'" in shared
    assert "from '../lib/settingsModel.js'" in job_morph
    assert "export const sanitizeSettings" not in shared
    assert "export const sanitizeSettings" not in job_morph
    assert "export const sanitizeSettings" in settings_model
    assert "export const normalizeSttProvider" in settings_model


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
    settings_model = Path("frontend/src/lib/settingsModel.js").read_text(encoding="utf-8")
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
    assert "hotwordLibrary" in settings_model
    assert "reviewUseAi" in settings_model
    combined_routes = "\n".join([dashboard, editor, processing])
    assert "hotword" not in combined_routes.lower()
    assert "reviewMode" not in combined_routes


def test_frontend_no_longer_accepts_azure_fast_provider() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    local_execution = Path("frontend/src/lib/localExecution.js").read_text(encoding="utf-8")
    processing_plan = Path("backend/core/processing_plan.py").read_text(encoding="utf-8")

    assert "azure_fast" not in shared
    assert "azure_fast" not in job_morph
    assert "azure_fast" not in local_execution
    assert '"azure_fast"' not in processing_plan


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
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")
    download = Path("frontend/src/lib/download.js").read_text(encoding="utf-8")

    assert "中英对照" in source
    assert "原始字幕" in source
    assert "pickDisplayTranscriptSegments(result, segments)" in source
    assert "displaySegments: result.display_segments || []" in mapper
    assert "export const pickDisplayTranscriptSegments" in fmt
    assert "bilingualTranscriptSegments" in source
    assert "visibleTranscriptView === 'bilingual'" in source
    assert "segment?.text_zh" in download


def test_editor_routes_generation_explanation_to_agent_workflow() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    settings_model = Path("frontend/src/lib/settingsModel.js").read_text(encoding="utf-8")

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
    assert "noteModePlanReason" in mapper
    assert "chapter_coverage" in settings_model
    assert "完整覆盖笔记" in settings_model


def test_editor_visual_evidence_stays_inline_and_secondary() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    markdown = Path("frontend/src/lib/markdown.js").read_text(encoding="utf-8")
    icons = Path("frontend/src/components/SvgIcon.jsx").read_text(encoding="utf-8")
    plan = Path("docs/video_keyframe_notes_plan.md").read_text(encoding="utf-8")

    assert "const [visualEvidenceVisible, setVisualEvidenceVisible] = useState(true)" in source
    assert "inlineVisualEvidenceCount" in source
    assert "hasInlineVisualEvidence" in source
    assert "simpleMd(summary, {renderImages: !hasInlineVisualEvidence || visualEvidenceVisible})" in source
    assert "隐藏截图" in source
    assert "显示截图" in source
    assert "生成详情" not in source
    assert "const renderImages = options.renderImages !== false" in markdown
    assert "if(!renderImages)" in markdown
    assert "visibility_off: EyeOff" in icons
    assert "[x] Show screenshots inline in the note only when attached to a real section." in plan
    assert "[x] Keep screenshot controls secondary; do not add another large panel." in plan
    assert "[x] Add PDF/Word image export for selected visual evidence." in plan
    assert "[x] Add editor affordance to hide/show visual evidence if screenshots become distracting." in plan


def test_editor_uses_compact_review_workbench_layout() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "转录原文" in source
    assert "笔记正文" in source
    assert "inline-flex h-10 items-center" in source
    assert "max-w-[18em] truncate whitespace-nowrap font-headline" in source
    assert "{rawEditorTitle}" in source
    assert "title={rawEditorTitle}" in source
    assert "const editorTitle = compactDisplayFilename" not in source
    assert "formatElapsedMinuteSecond(sttElapsedSec)" in source
    assert "formatSttOriginalRatio(sttRealtimeFactor, lang)" in source
    assert "STT:" not in source
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
    assert "mt-1 flex flex-wrap items-center gap-1.5 pl-6" not in source
    assert "inline-flex h-5 items-center gap-1 rounded-[8px] px-1.5 text-[11px] font-bold leading-none" in source
    assert "标题旁状态标签" in design_system
    assert "必须小于标题字号" in design_system
    assert "editRecords.length > 0" in source
    assert "导出转录" not in source
    assert "lang === 'zh' ? '导出' : 'Export'" in source
    assert "const canDownloadSourceVideo = !!(" in source
    assert "const handleDownloadSourceVideo = async () =>" in source
    assert "fetchJobSourceFile(result.task_id" in source
    assert "label:t('dl.sourceVideo')" in source
    assert "source_video_downloaded" in source
    assert "inline-flex h-8 items-center justify-center gap-1.5 rounded-[13px] bg-[#111111] px-3" in source
    assert "inline-flex h-8 items-center justify-center gap-1.5 rounded-[13px] border border-[#e4e0e0] bg-white px-3" in source


def test_editor_video_review_keeps_current_subtitle_as_core_object() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "const [transcriptReviewMode, setTranscriptReviewMode] = useState('text')" in source
    assert "const canUseVideoReview = mediaKind === 'video' && !!mediaUrl && segments.length > 0" in source
    assert "文本校对" in source
    assert "视频复查" in source
    assert "grid min-h-[52px] grid-cols-[64px_minmax(0,1fr)] items-center gap-3" in source
    assert "grid min-h-[54px] grid-cols-[64px_minmax(0,1fr)] items-center gap-3" in source
    assert "flex h-full min-h-[38px] items-center justify-start font-mono text-xs tabular-nums" in source
    assert "min-h-[1.75rem] w-full resize-none overflow-hidden border-none bg-transparent p-0 text-sm font-medium leading-snug" in source
    assert "w-14 flex-shrink-0 pt-2 text-left font-mono" not in source
    assert "inline-flex h-9 items-center gap-1 rounded-[13px]" in source
    assert "inline-flex h-full items-center justify-center rounded-[10px]" in source
    assert "disabled:hover:bg-transparent" in source
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

    assert "API_BASE, apiFetch, noteModeLabel, useApp, useI18n" in source
    assert "apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}/detail`)" in source
    assert "apiFetch(`${API_BASE}/agent/v1/tasks/${encodeURIComponent(taskId)}/package`)" in source
    assert "visibleActions(pageData?.actions)" in source
    assert "runAction(action)" in source
    assert "setLastResult(job.result)" in source
    assert "setLastResult(data.result)" in source
    assert "request: apiRequest" not in source
    assert "apiRequest(" not in source


def test_agent_trace_respects_sidebar_offset_in_all_states() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert source.count("ml-[var(--sidebar-offset)]") >= 3
    assert source.count("transition-[margin] duration-200 ease-out") >= 3
    assert "ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 items-center justify-center" in source
    assert "ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 flex-col items-center justify-center" in source
    assert "ml-[var(--sidebar-offset)] min-h-dvh flex-1 overflow-y-auto" in source


def test_agent_trace_prioritizes_material_specific_judgment() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "decision_log" in source
    assert "decisionEntries" in source
    assert "fallbackDecisionEntries" in source
    assert "判断推进流" in source
    assert "关键判断、依据和影响" in source
    assert "真实记录" in source
    assert "兼容推导" in source
    assert "executionSteps" in source
    assert "timeline" in source
    assert "tool_trace" in source
    assert "THOUGHT_GENERATORS" not in source
    assert "inner monologue" not in source
    assert "内心独白" not in source


def test_agent_trace_surfaces_chapter_coverage_evidence_table() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "chapterCoverageData" in source
    assert "ChapterCoverageEvidence" in source
    assert "chapter_coverage" in source
    assert "Chapter Coverage 证据表" in source
    assert "这份笔记覆盖了哪些原文证据" in source
    assert "covered_by_chapter_ids" in source
    assert "start_seconds" in source
    assert "end_seconds" in source
    assert "formatSeconds" in source


def test_processing_page_is_agent_workflow_surface() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

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

    assert "<header" not in source
    assert "Agent 工作流" not in source
    assert "任务解释" not in source
    assert "展示本次任务的处理路线、判断依据和失败恢复建议。" not in source
    assert "{isZh ? '开始处理' : 'Start'}" not in source
    assert "{isZh ? '长期设置' : 'Settings'}" not in source
    assert "FLUENTFLOW AGENT" not in source
    assert "text-[34px]" not in source
    assert "lg:text-[44px]" not in source
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
    assert 'to="/settings"' not in source
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
    assert "下一步：删除这条取消记录。" not in tasks
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


def test_sidebar_collapse_keeps_navigation_vertical_rhythm() -> None:
    source = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")

    assert "const FluentFlowLogo = ({compact = false})" in source
    assert "compact ? 'size-6 rounded-[9px]' : 'size-10 rounded-[14px]'" in source
    assert "compact ? 'size-[18px]' : 'size-[30px]'" in source
    assert "flex h-16 items-center" in source
    assert "mb-3 flex-col justify-center gap-1" in source
    assert "'h-8 w-10 justify-center p-0'" in source
    assert "'h-5 w-10 rounded-[10px]'" in source
    assert "min-h-0 flex-1 space-y-1 overflow-y-auto overflow-x-hidden" in source
    assert "mx-auto h-10 w-12 justify-center rounded-[16px] p-0" in source
    assert '<Icon className="size-5 shrink-0" strokeWidth={2.15}/>' in source
    assert "mb-8 flex-col gap-4" not in source
    assert "size-[22px]" not in source


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


def test_about_terms_privacy_and_changelog_are_split_pages() -> None:
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    side_nav = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")
    about = Path("frontend/src/routes/about.jsx").read_text(encoding="utf-8")
    legal_submenu = side_nav.split("legalMenuOpen && (", 1)[1].split("{authMode === 'accounts' && user && (", 1)[0]

    assert '<Route path="/about/:page" element={<About/>}/>' in app_shell
    assert "to={`/about/${item.key}`}" in about
    assert "h-dvh overflow-y-auto" in about
    assert "服务条款" in about
    assert "隐私政策" in about
    assert "版本更新" in about
    assert "import('../../../docs/changelog.md?raw')" in about
    assert "docs/changelog.md" in about
    assert "isChangelogEntryTitle" in about
    assert "formatChangelogTitle" in about
    assert "待发布" in about
    assert "记录格式" not in about.split("const isChangelogEntryTitle", 1)[1]
    assert "if (items.length === 0) return null" in about
    assert "release.items.map" in about
    assert "暂时无法读取更新记录" in about
    assert "法律、医疗、投资、考试报名" in about
    assert "本地历史不会删除服务器任务" in about
    assert "const [legalMenuOpen, setLegalMenuOpen] = useState(false)" in side_nav
    assert "aria-expanded={legalMenuOpen}" in side_nav
    assert "onClick={() => setLegalMenuOpen((value) => !value)}" in side_nav
    assert "absolute left-full top-0" in side_nav
    assert "ChevronRight" in side_nav
    assert "{path: '/about/service'" in side_nav
    assert "{path: '/about/privacy'" in side_nav
    assert "{path: '/about/changelog'" in side_nav
    assert "ChevronRight" not in legal_submenu


def test_sidebar_agent_access_stays_in_low_frequency_menu() -> None:
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    side_nav = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")

    assert "const [agentAccessOpen, setAgentAccessOpen] = useState(false)" in side_nav
    assert "setMenuOpen(false); setAgentAccessOpen(true);" in side_nav
    assert "Agent 接入" in side_nav
    assert "role=\"dialog\"" in side_nav
    assert "aria-labelledby=\"agent-access-title\"" in side_nav
    assert "Agent API 数据链路" in side_nav
    assert "本地 stdio MCP Server" in side_nav
    assert "scripts/fluentflow_mcp_server.py" in side_nav
    assert "npm run mcp:check:e2e" in side_nav
    assert "MCP Server 还不是可配置成品" not in side_nav
    assert "/agent/v1/tasks/{task_id}/package" in side_nav
    assert "scripts/codex_transcribe_link.py" in side_nav
    assert "Claude Code、Codex" in side_nav
    assert 'path="/workspace/api"' not in app_shell
    assert "to=\"/workspace/api\"" not in side_nav


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


def test_tasks_route_diagnostics_to_agent_workflow() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "taskNextStepText" not in source
    assert "noteGenerationDiagnosis" not in source
    assert "hasFailedSummaryWithoutNote" not in source
    assert "liveStageDetail" in source
    assert "{isLiveJob(job) && (" in source
    assert "/tasks/${encodeURIComponent(job.task_id)}/agent" in source
    assert "下一步：" not in source
    assert "{nextStepText}" not in source


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


def test_job_detail_endpoint_returns_processing_timeline(monkeypatch) -> None:
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
            "metadata": {"queue_options": {"stt_provider": "local", "stt_model": "medium"}},
            "result": {},
        },
    )
    monkeypatch.setattr(
        _H,
        "list_job_steps",
        lambda task_id, limit=100: [{
            "task_id": task_id,
            "step_type": "transcription",
            "status": "running",
            "started_at": "2026-01-01T00:00:00+00:00",
        }],
    )

    response = TestClient(app).get("/jobs/task-running/detail", headers={"X-FluentFlow-Client-Id": "client-a"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["task_id"] == "task-running"
    assert any(step["id"] == "transcription" and step["status"] == "running" for step in payload["timeline"])
    assert payload["actions"][0]["id"] == "cancel"
    assert payload["data_quality"]["has_recorded_steps"] is True


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
