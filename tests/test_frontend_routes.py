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


def test_media_text_top_actions_stay_on_one_row_when_narrow() -> None:
    source = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")

    assert 'className="mb-7 flex items-center justify-between gap-3"' in source
    assert "lg:flex-row" not in source.split("{mode === 'media' &&", 1)[0]
    assert "shrink-0 items-center justify-center whitespace-nowrap" in source
    assert "视频生成笔记" in source
    assert "dash.viewTasks" in source


def test_frontend_explains_video_link_download_failures() -> None:
    source = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")

    assert "平台拒绝下载当前视频" in source
    assert "平台请求过于频繁" in source
    assert "视频下载时间过长" in source


def test_video_link_failures_are_preserved_in_background_tasks() -> None:
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    tasks = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")

    assert "export const cacheJobRecord" in mapper
    assert "cacheJobRecord" in shared
    assert "cacheJobRecord" in job_morph
    assert "persistFailedTaskJob" in dashboard
    assert "已保存在处理记录里" in dashboard
    assert "taskFailureDetail" in tasks
    assert "job.error_reason || job.result?.summary_error" in tasks


def test_video_link_submission_routes_to_single_task_detail_surface() -> None:
    media_text = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    agent_tasks = Path("frontend/src/routes/agent-tasks.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "navigate('/agent', {state: {job}})" in media_text
    assert "navigate('/agent', {state: {job: pendingJob}})" in dashboard
    assert 'path="/agent" element={guestMode ? <Dashboard/> : <AgentTasks/>}' in app_shell
    assert 'path="/processing" element={guestMode ? <Dashboard/> : <Navigate to="/agent" replace/>}' in app_shell
    assert 'path="/tasks" element={<Navigate to="/agent" replace/>}' in app_shell
    assert "mergeJobs(seededJob ? [seededJob] : [], readCachedJobs())" in agent_tasks
    assert "displayJobs.map((job) => (" in agent_tasks
    assert "Link to={`/tasks/${encodeURIComponent(taskId)}/agent`} state={{job}}" not in agent_tasks
    assert "查看详情" not in agent_tasks
    assert "subscribeJobEvents(job.task_id" not in media_text
    assert "TaskProgressOverview" in agent_trace
    assert "setInterval(() => loadTaskDetail(staleRef, {silent: true}), 3000)" in agent_trace


def test_public_landing_page_owns_root_and_app_keeps_dashboard_entry() -> None:
    app_entry = Path("frontend/src/app.jsx").read_text(encoding="utf-8")
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    side_nav = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")
    landing = Path("frontend/src/routes/landing.jsx").read_text(encoding="utf-8")
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    about = Path("frontend/src/routes/about.jsx").read_text(encoding="utf-8")

    assert "const Landing = lazy(() => import('./routes/landing.jsx'))" in app_entry
    assert '<Route path="/" element={<Landing/>}/>' in app_entry
    assert '<Route path="/*" element={' in app_entry
    assert 'path="/app" element={<Dashboard/>}' in app_shell
    assert 'path="*" element={<Navigate to="/app" replace/>}' in app_shell
    assert "{path:'/app', icon:LayoutGrid, k:'nav.dashboard'}" in side_nav
    assert 'to="/app"' in side_nav
    assert "Turn long videos into study-ready notes first." in landing
    assert "Upload a course, lecture, recording, or video link. FluentFlow prepares the note, transcript, and key moments before you study." in landing
    assert "Ready to keep studying later." in landing
    assert "Study with notes ready, not with a pause button under your finger." in landing
    assert "Accepted transcript fixes can show original text, corrected text, reason, confidence, and time." in landing
    assert "Public platforms may restrict access." in landing
    assert "A record you can study, review, and export." in landing
    assert "to=\"/media-text\"" in landing
    assert "href=\"#workflow\"" in landing
    assert "to=\"/agent\"" in landing
    assert "h-dvh overflow-y-auto" in landing
    assert "motion-reduce:scroll-auto" in landing
    assert "Techna Sans" in landing
    assert "Avenir_Next" in landing
    assert "lightGrain" in landing
    assert "feTurbulence" in landing
    assert "mix-blend-multiply" in landing
    assert "opacity-[0.16] mix-blend-multiply" in landing
    assert "opacity-[0.085] mix-blend-screen" in landing
    assert "width='96' height='96'" in landing
    assert "baseFrequency='.92'" in landing
    assert "lightPageFrost" in landing
    assert "darkPageFrost" in landing
    assert "baseFrequency='1.18'" in landing
    assert "opacity-[0.24] mix-blend-multiply" in landing
    assert "backgroundSize: '160px 160px, 5px 5px'" in landing
    assert "backdrop-blur-md" in landing
    assert "shadow-[inset_0_1px_0_rgba(255,255,255,.72)" in landing
    assert "font-black" not in landing
    assert "text-sm font-medium text-[#5f6a61]" in landing
    assert "text-sm font-semibold text-[#fff8ec]" in landing
    assert "text-[42px] font-bold leading-[1.06]" in landing
    assert "fluentflow-landing-language" in landing
    assert "fluentflow-landing-theme" in landing
    assert "setLanguage(value)" in landing
    assert "ThemeIcon" in landing
    assert "Use dark mode" in landing
    assert "使用暗黑模式" in landing
    assert "ff-motion-demo" in landing
    assert "ff-proof-stage" in landing
    assert "carouselStepMs = 6500" in landing
    assert "role=\"tablist\"" in landing
    assert "role=\"tab\"" in landing
    assert "aria-selected={isActive}" in landing
    assert "onMouseEnter={() => showStep(index)}" in landing
    assert "onFocus={() => showStep(index)}" in landing
    assert "onClick={() => selectStep(index)}" in landing
    assert "setIsManual(true)" in landing
    assert "rounded-[26px]" in landing
    assert "rounded-[22px]" in landing
    assert "fluentflow.app/video-note" in landing
    assert "prefers-reduced-motion: reduce" in landing
    assert "Study workspace" not in landing
    assert "学习工作区" not in landing
    assert "{copy.eyebrow}" not in landing
    assert "Upload / paste a long video" in landing
    assert "https://course.example.com/attention-lecture" in landing
    assert "Course lecture: attention mechanisms" in landing
    assert "Source check in progress" in landing
    assert "正在检查来源" in landing
    assert "ffInputType" in landing
    assert "ffCardPop" in landing
    assert "ffProgressGrow" in landing
    assert "course-link.mp4" not in landing
    assert "课程录屏链接.mp4" not in landing
    assert "ff-proof-panel-processing" in landing
    assert "ff-proof-panel-study" in landing
    assert "Processing the video" in landing
    assert "正在处理视频" in landing
    assert "Study / Review" in landing
    assert "学习 / 复查" in landing
    assert "Transcript and subtitles" in landing
    assert "Key moments" in landing
    assert "Study notes" in landing
    assert "Notes generated first" not in landing
    assert "dark:bg-[#20392f] dark:text-[#d7f8eb]" in landing
    assert "dark:border-[#8fd9c0]/48 dark:bg-[#20392f] dark:text-[#f7f1e5]" in landing
    assert "Compare and correct" not in landing
    assert "Export study asset" not in landing
    assert "Study beside the video" in landing
    assert "对照视频学习" in landing
    assert "Video and audio" in landing
    assert "视频和音频" in landing
    assert "Notes and review" in landing
    assert "笔记相关" in landing
    assert "Video file" in landing
    assert "Audio track" in landing
    assert "Subtitles" in landing
    assert "Key frames" in landing
    assert "Markdown" in landing
    assert "PDF" in landing
    assert "Feishu" in landing
    assert "Fix accepted" not in landing
    assert "MicVocal" in landing
    assert "MonitorPlay" in landing
    assert "FileVideo2" in landing
    assert "Link2" in landing
    assert "bg-[#f4d98c] text-[#5c4214]" in landing
    assert "bg-[#dff7e8]" not in landing
    assert "[text-wrap:balance]" in landing
    assert "transition-[color,background-color,border-color,box-shadow,transform,opacity]" in landing
    assert "dark:text-white/[0.68] md:flex" in landing
    assert "dark:bg-[#111612]" in landing
    assert 'id="sources" className="relative z-10 scroll-mt-24 border-y border-[#dce5d8] bg-[#f3fbf2]/72 shadow-[inset_0_1px_0_rgba(255,255,255,.58)] backdrop-blur-md dark:border-white/[0.10] dark:bg-[#8fd9c0]/6' in landing
    assert "flashcard" not in landing.lower()
    assert "quiz" not in landing.lower()
    assert "podcast" not in landing.lower()
    assert "to=\"/agent\"" in editor
    assert "edit.chooseRecord" in editor
    assert "to=\"/app\"" in about
    assert "—" not in landing
    assert "–" not in landing


def test_recent_activity_cards_open_editor_or_task_detail_not_history_list() -> None:
    dashboard = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    media_text = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")

    for source in (dashboard, media_text):
        assert "const cachedResult = historyEntryToResult" in source
        assert "const openCachedEditor = () => {" in source
        assert "h.status !== 'completed' || !hasTranscriptResult(cachedResult)" in source or "item.status !== 'completed' || !hasTranscriptResult(cachedResult)" in source
        assert "setLastResult(cachedResult);" in source
        assert "navigate('/editor');" in source
        assert "if (openCachedEditor()) return;" in source
        assert "navigate(`/tasks/${encodeURIComponent(" in source
        assert "}/agent`, {state: {job:" in source


def test_frontend_error_diagnostics_are_structured_and_reused() -> None:
    fmt = Path("frontend/src/lib/format.js").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "export const diagnoseTaskError" in fmt
    assert "return diagnoseTaskError(message, lang).detail;" in fmt
    assert "const diag = diagnoseTaskError(rawError, lang)" in fmt
    assert "auth_required" in fmt
    assert "platform_rate_limited" in fmt
    assert "source_file_missing" in fmt
    assert "unsupported_note_mode" in fmt
    assert "feishu_export_failed" in fmt
    assert "diagnoseTaskError" in shared


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
    editor = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "export const DEFAULT_STT_PROVIDER = 'elevenlabs_scribe'" in settings_model
    assert "export const DEFAULT_QWEN_MODEL = 'qwen3.7-plus'" in settings_model
    assert "'dashscopeApiKey'" in settings_model
    assert "'qwenApiKey'" in settings_model
    assert "dashscope_api_key: settings.dashscopeApiKey || settings.qwenApiKey || ''" in settings_model
    assert "allowedSttProviders: ['elevenlabs_scribe', 'local']" in settings_model
    assert "const localAwareAllowed = publicMode || uniqueAllowed.includes('local')" in settings_model
    assert "from '../lib/settingsModel.js'" in shared
    assert "from '../lib/settingsModel.js'" in job_morph
    assert "sttProvider: 'elevenlabs_scribe'" in settings
    assert '<option value="qwen">Qwen</option>' in settings
    assert "credentialConfigured(credentialStatus, 'dashscope_api_key')" in settings
    assert "set.dashscopeKey" in settings
    assert "'set.dashscopeKey':'百炼 / DashScope API Key'" in shared
    assert "用于 Qwen 视觉模型选择视频截图；摘要仍可使用 DeepSeek 或 OpenAI。" in settings
    assert "百炼 / DashScope API Key，用于 Qwen 视觉模型的局部截图选择" not in settings
    assert "已配置，留空则保留" in settings
    assert "已配置，输入新 Key 可替换" in settings
    assert "Qwen API Key" not in settings
    assert "isCloudSttConfigured(sttProvider, status)" in editor
    assert "本地处理转录；生成笔记仍使用账号和模型服务。" in settings
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
    assert "const getJobWithFallback = async (job) => {" in source
    assert "return getJob(taskId, {sttProvider: 'local'});" in source
    assert "const [openingTaskId, setOpeningTaskId] = useState('')" in source
    assert "setOpeningTaskId(taskId)" in source
    assert "这条记录暂时没有可打开的结果" in source
    assert "disabled={!canOpen || openingTaskId === taskId}" in source
    assert "err.status === 404 && job.result" in source
    assert "err.status = r.status" in shared
    assert "const {__cacheOnly, ...persistedJob} = job" in mapper


def test_tasks_polling_respects_local_cancel_and_delete_mutations() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "const locallyCancelledTaskIdsRef = useRef(new Set())" in source
    assert "const locallyDeletedTaskIdsRef = useRef(new Set())" in source
    assert "const results = await Promise.allSettled([" in source
    assert "setJobs((current) => {" in source
    assert "[...readCachedJobs(), ...current]" in source
    assert "const [jobs, setJobs] = useState(initialCachedJobs)" in source
    assert "const [loading, setLoading] = useState(() => initialCachedJobs().length === 0)" in source
    assert "map(markCachedOnlyJob)" not in source
    assert "locallyDeletedTaskIdsRef.current.has(taskId)" in source
    assert "locallyCancelledTaskIdsRef.current.has(taskId)" in source
    assert "status: TASK_STATE_CANCELLED" in source
    assert "记录刷新失败，已保留本地缓存。" in source


def test_history_failed_video_link_records_can_be_retried_without_status_flicker() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "createVideoSourceJob" in source
    assert "const retryInputForJob = (job) => {" in source
    assert "metadata.video_source_input_preview" in source
    assert "const canRetryJob = (job) => normalizeTaskState(job) === TASK_STATE_FAILED && !!retryInputForJob(job)" in source
    assert "const retryFailedJob = async (job) => {" in source
    assert "重新处理" in source
    assert "'live', lang === 'zh' ? '进行中' : 'Active', stats.live" in source
    assert "stats.live > 0" in source


def test_agent_task_failed_cards_do_not_render_as_full_progress() -> None:
    source = Path("frontend/src/routes/agent-tasks.jsx").read_text(encoding="utf-8")

    assert "const failedProgressLabel = state === TASK_STATE_CANCELLED" in source
    assert "failed ? ` · ${progressLabel}` : (!completed && ` · ${lang === 'zh' ? '进度' : 'Progress'}：${progressLabel}`)" in source
    assert "{!completed && !failed ? (" in source
    assert "{failed ? (" in source
    assert "rounded-[18px] border border-red-200 bg-red-50/80" in source
    assert "style={{width: `${progress}%`}}" in source
    assert "failed ? 'bg-red-500' : 'bg-[#111111] dark:bg-white'" not in source


def test_tasks_delete_cached_only_without_task_id_locally() -> None:
    source = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")

    assert "const taskIdForJob = (job)" in source
    assert "const isDeletableJob = (job) => !isLiveJob(job) && (!!taskIdForJob(job) || isCachedOnlyTask(job))" in source
    assert "if (!taskId) {" in source
    assert "removeLocalRecord();" in source
    assert "await deleteJob(taskId" in source
    assert "job.task_id ? (" not in source


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
    assert "writeCachedAccountJobs(accountCacheId, nextJobs)" in shared
    assert "mergeCachedJobs," in shared
    assert "sortJobsForHistoryView," in shared
    assert "rawFilename" in mapper
    assert "filename: h.rawFilename || h.name" in mapper
    assert "display_title: h.displayTitle || displayTitleForUser(h.name, h.rawFilename)" in mapper
    assert "const openCachedEditor = () => {" in dashboard
    assert "navigate('/editor');" in dashboard
    assert "const openCachedEditor = () => {" in media_text
    assert "navigate('/editor');" in media_text
    assert "historyEntryToResult(history.find" not in editor
    assert "historyEntryToResult(latestHistory)" not in processing
    assert "latestHistory" not in processing


def test_recent_activity_and_history_share_cached_job_source() -> None:
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")
    tasks = Path("frontend/src/routes/tasks.jsx").read_text(encoding="utf-8")
    media_text = Path("frontend/src/routes/media-text.jsx").read_text(encoding="utf-8")
    app_provider = Path("frontend/src/app/AppProvider.jsx").read_text(encoding="utf-8")
    job_morph = Path("frontend/src/app/jobMorph.js").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")

    assert "Promise.allSettled([" in shared
    assert "apiFetch(`${API_BASE}/jobs?limit=100`)" in shared
    assert "apiFetch(`${API_BASE}/jobs?limit=100`, {headers: localExecutionHeaders({sttProvider: 'local'})})" in shared
    assert "mergeCachedJobs," in shared
    assert "sortJobsForHistoryView(mergeCachedJobs(cachedJobs, fetchedJobs))" in shared
    assert "const initialCachedJobs = () => readCachedAccountJobs(cacheAccountId)" in tasks
    assert "const [jobs, setJobs] = useState(initialCachedJobs)" in tasks
    assert "const [loading, setLoading] = useState(() => initialCachedJobs().length === 0)" in tasks
    assert "sortJobsForHistoryView(" in tasks
    assert "const priority = {" not in tasks
    assert "timestampForJob(job) >= timestampForJob(existing)" in mapper
    assert "export const sortJobsForHistoryView" in mapper
    assert "[TASK_STATE_RUNNING]: 0" in mapper
    assert "[TASK_STATE_FAILED]: 2" in mapper
    assert "sortJobsForHistoryView" in job_morph
    assert "sortJobsForHistoryView(mergeCachedJobs(cachedJobs, fetchedJobs))" in app_provider
    assert "{t('dash.recent')}" in media_text
    assert "{t('dash.noActivity')}" in media_text
    assert "最近任务" not in media_text
    assert "Recent tasks" not in media_text


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
    assert "saveSummaryEdit(result.task_id, {" in source
    assert "}, resultJobOptions)" in source
    assert "const fetchJobSourceFile = async (taskId, filename='source', options={})" in shared
    assert "const saveTranscriptEdit = async (taskId, payload={}, options={})" in shared
    assert "const saveSummaryEdit = async (taskId, payload={}, options={})" in shared


def test_subtitle_import_is_a_note_generation_action() -> None:
    source = Path("frontend/src/routes/dashboard.jsx").read_text(encoding="utf-8")
    shared = Path("frontend/src/app/shared.jsx").read_text(encoding="utf-8")

    assert "导入字幕生成笔记" in shared
    assert "skipSummary: false" in source
    assert "summarizeTranscriptFile(file, {taskId, ...buildAiOptions(settings), skipSummary: false}" in source
    assert r"\.(srt|vtt|txt|md)$" in source


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


def test_editor_surfaces_transcript_correction_without_overwriting_raw_transcript() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    correction = Path("frontend/src/lib/transcriptCorrection.js").read_text(encoding="utf-8")

    assert "transcriptCorrectionInfo(result)" in source
    assert "transcriptCorrectionStatusText(correctionInfo, lang)" in source
    assert "const showCorrectionDisclosure = !!(" in source
    assert "字幕纠错记录" in source
    assert "查看修正" in source
    assert "这里只展示通过后端验证并被接受的高置信修正" in source
    assert "转录原文保留未覆盖" in source
    assert "const sourceSegments = pickTranscriptSegments(result);" in source
    assert "corrected_segments" not in source
    assert "const jobData = await readJsonWithLocalFallback(`/jobs/${encodeURIComponent(taskId)}`)" in agent_trace
    assert "mergeTranscriptCorrectionData(detailData, jobData)" in agent_trace
    assert "mergeTranscriptCorrectionData(detailData, packageData)" in agent_trace
    assert "TranscriptCorrectionDisclosure pageData={pageData} lang={lang}" in agent_trace
    assert "笔记使用了修正后的字幕" in agent_trace
    assert "原始转录未被覆盖" in agent_trace
    assert "payload.note_generation_transcript_source" in correction
    assert "transcript.note_input_source" in correction
    assert "payload.transcript_corrections || transcript.corrections" in correction
    assert "noteUsesCorrected" in correction


def test_editor_routes_generation_explanation_to_agent_workflow() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    mapper = Path("frontend/src/lib/jobMappers.js").read_text(encoding="utf-8")
    settings_model = Path("frontend/src/lib/settingsModel.js").read_text(encoding="utf-8")

    assert "summaryFailureNextStep" in source
    assert "agentWorkflowHref" in source
    assert "处理记录" in source
    assert "生成详情" not in source
    assert "summaryCompactMeta" not in source
    assert "summaryGenerationMeta" not in source
    assert "summaryReasonItems" not in source
    assert "prompt.activeHint" not in source
    assert "noteModeText" not in source
    assert "fixed bottom-16 right-8" not in source
    assert "to={`/tasks/${encodeURIComponent(targetTaskId)}/agent`}" in processing
    assert "state={targetJob ? {job: targetJob} : undefined}" in processing
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
    assert "summaryEditing ? (" in source
    assert "setSummaryEditing((value)=>!value)" in source
    assert "dangerouslySetInnerHTML={{__html: renderedSummary}}" in source
    assert "aria-label={lang === 'zh' ? '编辑笔记正文' : 'Edit note body'}" in source
    assert "fd.append('markdown', summary || '')" in source
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
    assert "visibleEditRecords.length > 0" in source
    assert "导出转录" not in source
    assert "lang === 'zh' ? '导出' : 'Export'" in source
    assert "const canDownloadSourceVideo = !!(" in source
    assert "const handleDownloadSourceVideo = async () =>" in source
    assert "fetchJobSourceFile(result.task_id" in source
    assert "label:t('dl.sourceVideo')" in source
    assert "source_video_downloaded" in source
    assert "inline-flex h-8 items-center justify-center gap-1.5 rounded-[13px] bg-[#111111] px-3" in source
    assert "inline-flex h-8 items-center justify-center gap-1.5 rounded-[13px] border border-[#e4e0e0] bg-white px-3" in source


def test_editor_video_review_uses_dense_clickable_subtitle_list() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "const [transcriptReviewMode, setTranscriptReviewMode] = useState('text')" in source
    assert "const canUseVideoReview = mediaKind === 'video' && !!mediaUrl && segments.length > 0" in source
    assert "const playbackMemoryKey = result ? `fluentflow_playback_position_${activeTaskId}` : ''" in source
    assert "localStorage.setItem(playbackMemoryKey" in source
    assert "restoreMediaPosition(e.currentTarget, e.currentTarget.duration || durSec || 0)" in source
    assert "const visibleEditRecords = useMemo" in source
    assert "visibleEditRecords.length > 0" in source
    assert "editRecords.length > 0" not in source
    assert "文本校对" in source
    assert "视频复查" in source
    assert "group grid grid-cols-[64px_minmax(0,1fr)] items-start gap-3 rounded-[16px] px-3 py-2.5" in source
    assert "grid grid-cols-[64px_minmax(0,1fr)] items-start gap-3 rounded-[16px] px-3 py-2.5" in source
    assert "grid grid-cols-[64px_minmax(0,1fr)] items-start gap-3 px-1 py-2" in source
    assert "visibleTranscriptView === 'bilingual' && bilingualTranscriptSegments.length > 0 ? bilingualTranscriptSegments.map((seg,i) => (" in source
    assert "key={`video-review-bilingual-${i}`}" in source
    assert "const currentVideoSegment = activeSegmentIndex >= 0 ? visibleTranscriptSegments[activeSegmentIndex] : null;" in source
    assert "const followIndex = activeSegmentIndex;" in source
    assert "seekToSegment(visibleTranscriptSegments[nextIndex]);" in source
    assert "activeRawSegmentIndex" not in source
    assert "segments.map((seg,i) => (" in source
    assert "sticky top-0 z-10" not in source
    assert "上一句" not in source
    assert "下一句" not in source
    assert "text-[18px] font-extrabold" not in source
    assert "text-[15px] font-semibold leading-relaxed" not in source
    assert "min-h-[1.45rem] w-full resize-none overflow-hidden border-none bg-transparent p-0 text-sm font-semibold leading-snug" in source
    assert "flex h-full min-h-[38px] items-center justify-start font-mono text-xs tabular-nums" not in source
    assert "pt-[1px] text-left font-mono text-xs tabular-nums" in source
    assert "min-h-[1.75rem] w-full resize-none overflow-hidden border-none bg-transparent p-0 text-sm font-medium leading-snug" in source
    assert "w-14 flex-shrink-0 pt-2 text-left font-mono" not in source
    assert "inline-flex h-9 items-center gap-1 rounded-[13px]" in source
    assert "inline-flex h-full items-center justify-center rounded-[10px]" in source
    assert "disabled:hover:bg-transparent" in source
    assert "currentVideoSegment" in source
    assert "当前字幕" not in source
    assert "handleVideoSegmentStep" in source
    assert "fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)" in source
    assert "max-h-[min(42vh,360px)]" not in source
    assert "max-h-[min(38vh,330px)]" in source
    assert "min-w-0 flex-1 accent-primary" not in source
    assert "w-full accent-primary" in source
    assert "结果编辑页只承载复查、修改、下载和导出" in design_system
    assert "结果编辑页只承载复查、修改、下载和导出" in design_system


def test_editor_playback_ignores_stale_last_source_file() -> None:
    source = Path("frontend/src/routes/editor.jsx").read_text(encoding="utf-8")

    assert "const localSourceFileMatchesResult = (file, result) =>" in source
    assert "const matchedLocalSourceFile = localSourceFileMatchesResult(lastSourceFile, result) ? lastSourceFile : null;" in source
    assert "if (matchedLocalSourceFile) {" in source
    assert "loadMediaFile(matchedLocalSourceFile)" in source
    assert "fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)" in source
    assert "if (lastSourceFile) {" not in source
    assert "loadMediaFile(lastSourceFile)" not in source
    assert "if(lastSourceFile) runRetranscribe(lastSourceFile)" not in source


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
    assert "const agentWorkflowHref = result?.task_id ? `/tasks/${encodeURIComponent(result.task_id)}/agent` : '/agent';" in source
    assert "encodeURIComponent(activeTaskId)}/agent" not in source


def test_agent_trace_uses_existing_api_fetch_helper() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "API_BASE, apiFetch, fmtTime, localExecutionHeaders, noteModeLabel, useApp, useI18n" in source
    assert "noteGenerationDiagnosis" in source
    assert "readJsonWithLocalFallback(`/jobs/${encodeURIComponent(taskId)}/detail`)" in source
    assert "readJsonWithLocalFallback(`/agent/v1/tasks/${encodeURIComponent(taskId)}/package`)" in source
    assert "localExecutionHeaders(currentJobOptions)" in source
    assert "return await readJson(path, {localExecution: true});" in source
    assert "actions: Array.isArray(snapshot.actions) && snapshot.actions.length ? snapshot.actions" in source
    assert "id: 'open_result'" in source
    assert "const canOpenResult = Boolean(" in source
    assert "const openResult = async () => {" in source
    assert "const job = await readJsonWithLocalFallback(`/jobs/${encodeURIComponent(taskId)}`)" in source
    assert "setLastResult(job.result);" in source
    assert "navigate('/editor');" in source
    assert "to=\"/editor\"" not in source
    assert "查看结果" in source
    assert "request: apiRequest" not in source
    assert "apiRequest(" not in source


def test_agent_trace_renders_cached_snapshot_before_silent_refresh() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "const pageDataFromJobSnapshot = (job, fallbackTaskId, lang) => {" in source
    assert "const videoProgress = videoSourceProgressFromJob(job)" in source
    assert "const status = videoProgress ? 'running' : (snapshot.overall_status || normalizeTaskState(job))" in source
    assert "const stage = videoProgress" in source
    assert "? (job.stage && job.stage !== 'queued' ? job.stage : 'downloading')" in source
    assert "video_source_progress: videoProgress" in source
    assert "mergeLiveSnapshotPageData(mergedDetailData, current || initialPageData)" in source
    assert "const initialPageData = pageDataFromJobSnapshot(initialJob, taskId, lang)" in source
    assert "const [loading, setLoading] = useState(!initialPageData)" in source
    assert "const [pageData, setPageData] = useState(() => initialPageData)" in source
    assert "cached: true" in source
    assert "decision_log: decisionLog" in source
    assert "noteGenerationDiagnosis(result, lang)" in source
    assert "loadTaskDetail(staleRef, {silent: !!seededPageData})" in source
    assert "!silent && !pageData" in source


def test_task_progress_overview_surfaces_video_download_progress() -> None:
    source = Path("frontend/src/components/TaskProgressOverview.jsx").read_text(encoding="utf-8")

    assert "const videoSourceProgress = task.video_source_progress || source.video_source_progress || null" in source
    assert "videoSourceProgress," in source
    assert "const videoSourceProgress = task.video_source_progress || source.video_source_progress || null" in source
    assert "videoSourceProgress," in source
    assert "const videoSourceFileSizeMb = videoSourceProgress?.total_bytes" in source
    assert "fileSizeMb: current?.fileSizeMb ?? task.file_size_mb ?? source.file_size_mb ?? videoSourceFileSizeMb" in source


def test_agent_trace_respects_sidebar_offset_in_all_states() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert source.count("ml-[var(--sidebar-offset)]") >= 3
    assert source.count("transition-[margin] duration-200 ease-out") >= 3
    assert "ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 items-center justify-center" in source
    assert "ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 flex-col items-center justify-center" in source
    assert "ml-[var(--sidebar-offset)] h-dvh flex-1 overflow-y-auto" in source


def test_app_shell_preserves_route_level_scroll_containers() -> None:
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    css = Path("frontend/src/tailwind.css").read_text(encoding="utf-8")

    assert "overflow: hidden;" in css
    assert "className=\"flex h-dvh w-full overflow-hidden bg-surface dark:bg-[#101010]\"" in app_shell
    assert "className=\"relative flex h-dvh min-h-0 w-full flex-1 flex-col overflow-hidden\"" in app_shell
    assert "flex min-h-screen w-full" not in app_shell
    assert "w-full h-full relative" not in app_shell


def test_agent_trace_prioritizes_material_specific_judgment() -> None:
    source = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")

    assert "decision_log" in source
    assert "decisionEntries" in source
    assert "fallbackDecisionEntries" in source
    assert "判断记录" in source
    assert "原始判断字段" in source
    assert "TaskProgressOverview" in source
    assert "执行记录" not in source
    assert "Actual task progress" not in source
    assert "ExecutionStep" not in source
    assert "executionSteps" not in source
    assert "THOUGHT_GENERATORS" not in source
    assert "inner monologue" not in source
    assert "内心独白" not in source


def test_agent_trace_moves_material_judgment_into_overview_without_truncation() -> None:
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    progress = Path("frontend/src/components/TaskProgressOverview.jsx").read_text(encoding="utf-8")

    assert "materialJudgment={materialJudgmentValue(materialEntry, lang)}" in agent_trace
    assert "MaterialJudgmentTile" not in agent_trace
    assert "materialJudgment = ''" in progress
    assert "{label: isZh ? '判断材料类型' : 'Material type', value: materialJudgment, wrap: true}" in progress
    assert "wrap ? 'whitespace-normal break-words leading-5' : 'truncate'" in progress


def test_agent_trace_overview_uses_task_card_for_all_task_states() -> None:
    progress = Path("frontend/src/components/TaskProgressOverview.jsx").read_text(encoding="utf-8")

    assert "const activeCurrentJob = running && currentJob?.taskId && currentJob.taskId === task.taskId ? currentJob : null;" in progress
    assert "const badgeText = activeCurrentJob" in progress
    assert "已完成记录" in progress
    assert "处理已完成，可以打开结果继续复查。" in progress
    assert "你可以离开本页，进度会在记录里继续更新。" in progress
    assert "to=\"/media-text?mode=media\"" in progress
    assert "添加新任务" in progress
    assert "添加到队列" not in progress
    assert "取消任务" in progress
    assert "await cancelJob(activeCurrentJob.taskId, {sttProvider: activeCurrentJob.sttProvider});" in progress
    assert "setCurrentJob((prev) => prev?.taskId === activeCurrentJob.taskId ? null : prev);" in progress
    assert "STT ${activeJobSttProgress}%" in progress
    assert "infoCards.map((item)" in progress
    assert "return isZh ? '本地视频文件' : 'local video file'" in progress
    assert "return platform || (isZh ? '视频平台链接' : 'video platform link')" in progress
    assert "return platform || localFileKindLabel(source?.sourceFilename, isZh) || (isZh ? '本地文件' : 'local file')" in progress
    assert "return isZh ? '素材' : 'material'" not in progress


def test_agent_trace_removes_duplicate_history_and_summary_card() -> None:
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    progress = Path("frontend/src/components/TaskProgressOverview.jsx").read_text(encoding="utf-8")

    assert "Clock3" not in agent_trace
    assert "Agent workflow" not in agent_trace
    assert "Agent 工作流" not in agent_trace
    assert "系统每一步为什么这样处理" not in agent_trace
    assert "判断数" not in agent_trace
    assert "任务状态" not in agent_trace
    assert "TaskProgressOverview pageData={pageData}" in agent_trace
    assert "to=\"/tasks\"" not in progress
    assert "任务已进入后台处理" not in progress
    assert "模型配置" not in progress
    assert "媒体时长" not in progress
    assert "stageItems" not in progress
    assert "ArtifactPill" not in progress
    assert "处理已完成，可以打开结果继续复查。" in progress
    assert "activeCurrentJob && (" in progress
    assert "dark:text-white/[0.74]" in agent_trace
    assert "dark:text-white/[0.62]" in progress
    assert "dark:text-white/78" not in agent_trace
    assert "dark:text-white/68" not in progress


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


def test_agent_workflow_surface_lists_expanded_processing_records() -> None:
    source = Path("frontend/src/routes/agent-tasks.jsx").read_text(encoding="utf-8")

    assert "readCachedAccountJobs(cacheAccountId)" in source
    assert "const {currentJob, setCurrentJob, setLastResult, addToHistory} = useApp()" in source
    assert "getJobs(100)," in source
    assert "getJobs(100, {sttProvider: 'local'})," in source
    assert "displayJobs" in source
    assert "displayJobs.map((job) => (" in source
    assert "liveJobs = useMemo(() => displayJobs.filter(isLiveTask)" in source
    assert "queuedCount" in source
    assert "runningCount" in source
    assert "历史记录" in source
    assert "{displayJobs.length}" in source
    assert "totalSizeMb" not in source
    assert "文件大小' : 'File size" not in source
    assert "处理记录" in source
    assert "每个视频就是一条完整处理记录" not in source
    assert "Each video is shown as one expanded processing record" not in source
    assert "点开单条任务，再看处理详情" not in source
    assert "查看详情" not in source
    assert "查看结果" in source
    assert "sourceLabel(job, lang)" in source
    assert "return isZh ? '素材' : 'Source'" not in source
    assert "return isZh ? '本地音频文件' : 'Local audio file'" in source
    assert "return isZh ? '视频平台链接' : 'Video platform link'" in source
    assert "routeLabel(job, lang)" in source
    assert "fileInfoLabel(job)" in source
    assert "materialLabel(job, lang)" in source
    assert "const materialTypeLabel = (value, lang) => {" in source
    assert "const materialDecisionFromLog = (job) => {" in source
    assert "job?.result?.processing_plan?.material?.type" in source
    assert "job?.result?.processing_plan?.goal?.primary" in source
    assert "id === 'material_classification'" in source
    assert "return lang === 'zh' ? '学习材料' : 'Learning material';" in source
    assert "const formatTaskDateTime = (value, lang) => {" in source
    assert "formatTaskDateTime(job?.updated_at || job?.created_at, lang)" in source
    assert "const taskProcessingTimeLabel = (job, lang) => {" in source
    assert "result.stt_elapsed_seconds" in source
    assert "result.audio_duration_seconds" in source
    assert "占原时长 ${percent}%" in source
    assert "const subtitle = completed ? taskProcessingTimeLabel(job, lang) : stageLabel(job, lang);" in source
    assert "timeAgo" not in source
    assert "t={t}" not in source
    assert 'to="/media-text?mode=media"' in source
    assert 'to="/tasks"' not in source
    assert "ml-[var(--sidebar-offset)]" in source


def test_processing_page_uses_timeline_not_card_stack() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")

    assert "const Card" not in source
    assert "<Card" not in source
    assert "执行路线" not in source
    assert "Agent 判断" not in source
    assert "processing_plan" not in source
    assert "planSteps" not in source
    assert "rounded-[14px] bg-[#f4f3f3] px-4 py-3" not in source


def test_processing_page_uses_compact_tool_header() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "<header" not in source
    assert "处理记录" in source
    assert "任务解释" not in source
    assert "展示本次任务的处理路线、判断依据和失败恢复建议。" not in source
    assert "{isZh ? '开始处理' : 'Start'}" in source
    assert "{isZh ? '处理记录' : 'Processing records'}" in source
    assert "{isZh ? '长期设置' : 'Settings'}" not in source
    assert "FLUENTFLOW AGENT" not in source
    assert "text-[34px]" not in source
    assert "lg:text-[44px]" not in source
    assert "Page Header Density" in design_system
    assert "不要在应用内页面顶部放大面积品牌标题" in design_system


def test_processing_page_constrains_long_task_titles() -> None:
    source = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "max-w-4xl" in source
    assert "text-[24px]" in source
    assert "md:text-[28px]" in source
    assert "只给文本节点加 `truncate` 不够" in design_system
    assert "minmax(0, 1fr)" in design_system
    assert "打开编辑器重生笔记" not in source
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

    assert "开始处理" in processing
    assert "记录" in processing
    assert "查看处理详情" in processing
    assert "结果可以复查" not in processing
    assert "任务正在运行" not in processing
    assert "还没有可解释的任务" not in processing
    assert "下一步：删除这条取消记录。" not in tasks
    assert "下一步：可以删除" not in tasks
    assert "查看结果" in agent_trace
    assert "处理已完成，可以打开结果继续复查。" in Path("frontend/src/components/TaskProgressOverview.jsx").read_text(encoding="utf-8")
    assert "可以随时下载或导出" not in agent_trace
    assert "Action-Oriented Copy" in design_system
    assert "避免把行动标题写成状态判断句" in design_system


def test_ui_copy_does_not_leak_internal_product_principles() -> None:
    processing = Path("frontend/src/routes/processing.jsx").read_text(encoding="utf-8")
    agent_trace = Path("frontend/src/routes/agent-trace.jsx").read_text(encoding="utf-8")
    design_system = Path("docs/ui_design_system.md").read_text(encoding="utf-8")

    assert "按执行顺序展示本次任务经过的处理步骤。" not in processing
    assert "提交链接或上传素材后，这里会直接打开当前任务的进度、判断依据、失败原因和下一步操作。" in processing
    assert "这不是多 Agent 表演" not in processing
    assert "decorative multi-agent theater" not in processing
    assert "判断记录" in agent_trace
    assert "原始判断字段" in agent_trace
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


def test_sidebar_uses_processing_records_without_history_entry() -> None:
    source = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")

    assert "const isAgentWorkflowRoute = (pathname) => (" in source
    assert "pathname === '/agent' || pathname === '/processing' || /^\\/tasks\\/[^/]+\\/agent\\/?$/.test(pathname)" in source
    assert "if (itemPath === '/agent') return isAgentWorkflowRoute(pathname);" in source
    assert "{path:'/agent', icon:SlidersHorizontal, k:'nav.processing'}" in source
    assert "{path:'/tasks'" not in source
    assert "if (itemPath === '/tasks')" not in source
    assert 'path="/tasks" element={<Navigate to="/agent" replace/>}' in app_shell
    assert "const active = isNavItemActive(it.path, loc.pathname);" in source


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
    assert "单次任务判断放在处理记录里解释" in settings


def test_about_terms_privacy_and_changelog_are_split_pages() -> None:
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    side_nav = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")
    about = Path("frontend/src/routes/about.jsx").read_text(encoding="utf-8")
    config_writer = Path("scripts/write_frontend_config.js").read_text(encoding="utf-8")
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
    assert "CHANGELOG_UPDATED_AT" in about
    assert "formatDateTimeMinute" in about
    assert "changelogTitleTime" in about
    assert "release.updatedAt || formatDateTimeMinute(CHANGELOG_UPDATED_AT, zh)" in about
    assert "更新于" in about
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
    assert "fileMtimeIso(path.join(root, \"docs\", \"changelog.md\"))" in config_writer
    assert "FLUENTFLOW_CHANGELOG_UPDATED_AT" in config_writer
    assert "changelogUpdatedAt" in config_writer


def test_sidebar_agent_access_stays_in_low_frequency_menu() -> None:
    app_shell = Path("frontend/src/app/AppShell.jsx").read_text(encoding="utf-8")
    side_nav = Path("frontend/src/components/SideNav.jsx").read_text(encoding="utf-8")
    panel = Path("frontend/src/components/AgentAccessPanel.jsx").read_text(encoding="utf-8")
    page = Path("frontend/src/routes/workspace-api.jsx").read_text(encoding="utf-8")

    assert "const [agentAccessOpen, setAgentAccessOpen] = useState(false)" in side_nav
    assert "setMenuOpen(false); setAgentAccessOpen(true);" in side_nav
    assert "Agent 接入" in side_nav
    assert "role=\"dialog\"" in side_nav
    assert "aria-labelledby=\"agent-access-title\"" in side_nav
    assert "max-h-[min(860px,calc(100dvh-48px))]" in side_nav
    assert "flex-col overflow-hidden" in side_nav
    assert "<AgentAccessPanel compact onClose={() => setAgentAccessOpen(false)}/>" in side_nav
    assert '<Route path="/workspace/api" element={<WorkspaceApi/>}/>' in app_shell
    assert "<AgentAccessPanel/>" in page
    assert "compact ? 'flex min-h-0 flex-1 flex-col'" in panel
    assert "compact ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4'" in panel
    assert "把 FluentFlow 接入你的 AI 工具" in panel
    assert "新建一把 API Key" in panel
    assert "粘贴到你的 AI 工具" in panel
    assert "发链接，自动出笔记" in panel
    assert "/account/api-keys" in panel
    assert "FLUENTFLOW_ACCESS_TOKEN" in panel
    assert "只显示一次的 API Key" in panel
    assert "请用 fluentflow MCP 帮我把这个视频做成笔记" in panel
    assert "scripts/fluentflow_mcp_server.py" in panel
    assert "npm run mcp:check:e2e" in panel
    assert "MCP Server 还不是可配置成品" not in panel
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
    assert "/tasks/${encodeURIComponent(taskId)}/agent" in source
    assert "state={{job}}" in source
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
