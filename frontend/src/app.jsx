const {useState,useEffect,useRef,useCallback,useMemo,createContext,useContext} = React;
const {createRoot} = ReactDOM;
const {BrowserRouter,Routes,Route,Link,useNavigate,useLocation} = ReactRouterDOM;

/** API 根路径：线上与后端同域时用相对路径；本地前端单独跑在其它端口时指向本机 8000。 */
const API_BASE = (() => {
    const normalize = (value) => String(value || '').trim().replace(/\/+$/, '');
    const configured = normalize(window.FLUENTFLOW_CONFIG?.apiBase || localStorage.getItem('fluentflow_api_base'));
    if (configured) return configured;
    const { hostname, port } = window.location;
    if (!hostname) return "http://127.0.0.1:8000";
    const local = hostname === "localhost" || hostname === "127.0.0.1";
    if (local && port === "5185") return "http://127.0.0.1:8000";
    return "";
})();

const ACCESS_TOKEN_KEY = 'fluentflow_access_token';
const CLIENT_ID_KEY = 'fluentflow_client_id';
const getAccessToken = () => (localStorage.getItem(ACCESS_TOKEN_KEY) || '').trim();
const setAccessToken = (token) => {
    const value = String(token || '').trim();
    if (value) localStorage.setItem(ACCESS_TOKEN_KEY, value);
    else localStorage.removeItem(ACCESS_TOKEN_KEY);
};
const createClientId = () => (
    window.crypto?.randomUUID?.()
    || `client_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
);
const getClientId = () => {
    const existing = (localStorage.getItem(CLIENT_ID_KEY) || '').trim();
    if (existing) return existing;
    const next = createClientId();
    localStorage.setItem(CLIENT_ID_KEY, next);
    return next;
};
const apiFetch = (input, init={}) => {
    const token = getAccessToken();
    const headers = new Headers(init.headers || {});
    if (!headers.has('X-FluentFlow-Client-Id')) {
        headers.set('X-FluentFlow-Client-Id', getClientId());
    }
    if (token && !headers.has('X-FluentFlow-Access-Token')) {
        headers.set('X-FluentFlow-Access-Token', token);
    }
    return fetch(input, {...init, credentials: init.credentials || 'include', headers});
};

const fileNameStem = (name) => (name || "").replace(/\.[^/.]+$/, "") || "";
const SENSITIVE_SETTING_KEYS = ['deepseekApiKey', 'openaiApiKey', 'larkAppId', 'larkAppSecret', 'azureSpeechKey', 'azureSpeechEndpoint', 'azureBlobContainerSasUrl'];
const sanitizeSettings = (settings={}) => {
    const next = {...settings};
    SENSITIVE_SETTING_KEYS.forEach((key) => delete next[key]);
    return next;
};
const sensitivePatchFromSettings = (settings={}) => ({
    deepseek_api_key: settings.deepseekApiKey || '',
    openai_api_key: settings.openaiApiKey || '',
    lark_app_id: settings.larkAppId || '',
    lark_app_secret: settings.larkAppSecret || '',
    azure_speech_key: settings.azureSpeechKey || '',
    azure_speech_endpoint: settings.azureSpeechEndpoint || '',
    azure_blob_container_sas_url: settings.azureBlobContainerSasUrl || '',
});
const minimizeHistoryEntry = (entry) => ({
    ...entry,
    transcriptText: entry.transcriptText ? String(entry.transcriptText).slice(0, 240) : '',
    summary: entry.summary ? String(entry.summary).slice(0, 240) : '',
    segments: entry.taskId ? [] : (entry.segments || []),
    rawTranscriptText: null,
    cleanedTranscriptText: null,
    cleanedSegments: null,
    rawSegments: null,
});
const resultToHistoryEntry = (result, fallback={}) => {
    const durSec = result.audio_duration_seconds || 0;
    return {
        id: fallback.id || Date.now(),
        taskId: result.task_id || fallback.taskId,
        name: result.filename || fallback.name || 'Untitled',
        timestamp: fallback.timestamp || Date.now(),
        durationMin: Math.round(durSec/60*10)/10,
        status: result.status === 'completed' ? 'completed' : (result.status || 'failed'),
        transcriptText: result.transcript_text||result.transcript_text_preview||'',
        segments: pickTranscriptSegments(result),
        summary: result.summary_markdown||'',
        summarySkipped: !!result.summary_skipped,
        summaryStatus: result.summary_status||null,
        summaryError: result.summary_error||null,
        larkUrl: result.lark_response?.url || null,
        larkError: result.lark_error||null,
        audioDurationSec: durSec,
        sttElapsedSec: result.stt_elapsed_seconds||0,
        sttRealtimeFactor: result.stt_realtime_factor||null,
        sttProvider: result.stt_provider||null,
        sttProviderLabel: result.stt_provider_label||null,
        sttModel: result.stt_model||null,
        sttSpeed: result.stt_speed||null,
        sttLanguage: result.stt_language||null,
        detectedLanguage: result.detected_language||null,
        sourceFingerprint: result.source_fingerprint||null,
        rawTranscriptText: result.raw_transcript_text||null,
        cleanedTranscriptText: result.cleaned_transcript_text||null,
        cleanedSegments: result.cleaned_segments||null,
        rawSegments: result.raw_segments||null,
        transcriptCleanup: result.transcript_cleanup||null,
        transcriptEdited: !!result.transcript_edited,
        transcriptEditedAt: result.transcript_edited_at||null,
        editedTranscriptPath: result.edited_transcript_path||null,
        editedTranscriptSavedAt: result.edited_transcript_saved_at||null,
        transcriptEditRecords: result.transcript_edit_records||[],
        transcriptEditRecordsPath: result.transcript_edit_records_path||null,
        artifacts: result.artifacts||null,
        requestedNoteMode: result.requested_note_mode||fallback.requestedNoteMode||null,
        resolvedNoteMode: result.resolved_note_mode||null,
        noteModeChunkCount: result.note_mode_chunk_count||null,
        source: result.source||fallback.source||null,
        sourceFileAvailable: !!result.source_file_available,
    };
};
const jobToHistoryEntry = (job) => {
    const result = job.result || {};
    return resultToHistoryEntry(result, {
        taskId: job.task_id,
        name: job.source_filename,
        timestamp: Date.parse(job.updated_at || job.created_at || '') || Date.now(),
        source: job.source_type,
    });
};
const jobToCurrentJob = (job) => ({
    taskId: job.task_id,
    fileName: job.source_filename || 'Running task',
    stage: job.stage || 'upload',
    progress: job.progress ?? 0,
    startedAt: Date.parse(job.created_at || '') || Date.now(),
    sourceType: job.source_type || null,
    fileSizeMb: job.source_file_size_mb || null,
    resume: true,
    sttProvider: job.metadata?.stt_provider || job.result?.stt_provider || null,
    sttProgress: job.metadata?.stt_progress,
    transcribedSeconds: job.metadata?.transcribed_seconds,
    durationSeconds: job.metadata?.duration_seconds,
    sttElapsedSeconds: job.metadata?.stt_elapsed_seconds,
    sttStatus: job.metadata?.stt_status,
    azureBatchAudioSizeMb: job.metadata?.azure_batch_audio_size_mb,
});
const historyEntryToResult = (h) => h ? ({
    task_id: h.taskId,
    source: h.source||null,
    transcript_text: h.transcriptText,
    segments: h.segments,
    summary_markdown: h.summary,
    summary_skipped: !!h.summarySkipped,
    filename: h.name,
    audio_duration_seconds: h.audioDurationSec,
    stt_elapsed_seconds: h.sttElapsedSec||0,
    stt_realtime_factor: h.sttRealtimeFactor||null,
    stt_provider: h.sttProvider||null,
    stt_provider_label: h.sttProviderLabel||null,
    stt_model: h.sttModel||null,
    stt_speed: h.sttSpeed||null,
    stt_language: h.sttLanguage||null,
    detected_language: h.detectedLanguage||null,
    source_fingerprint: h.sourceFingerprint||null,
    raw_transcript_text: h.rawTranscriptText||null,
    cleaned_transcript_text: h.cleanedTranscriptText||null,
    cleaned_segments: h.cleanedSegments||null,
    raw_segments: h.rawSegments||null,
    transcript_cleanup: h.transcriptCleanup||null,
    transcript_edited: !!h.transcriptEdited,
    transcript_edited_at: h.transcriptEditedAt||null,
    edited_transcript_path: h.editedTranscriptPath||null,
    edited_transcript_saved_at: h.editedTranscriptSavedAt||null,
    transcript_edit_records: h.transcriptEditRecords||[],
    transcript_edit_records_path: h.transcriptEditRecordsPath||null,
    artifacts: h.artifacts||null,
    requested_note_mode: h.requestedNoteMode||null,
    resolved_note_mode: h.resolvedNoteMode||null,
    note_mode_chunk_count: h.noteModeChunkCount||null,
    source_file_available: !!h.sourceFileAvailable,
}) : null;
const createTaskId = () => (
    window.crypto?.randomUUID?.() ||
    `task_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
);
const NOTE_MODE_OPTIONS = [
    {value: 'auto', labelEn: 'Auto', labelZh: '自动选择'},
    {value: 'direct', labelEn: 'Direct long context', labelZh: '直接长上下文'},
    {value: 'high_fidelity', labelEn: 'High-fidelity', labelZh: '高保真笔记'},
];
const noteModeLabel = (mode, lang) => {
    const found = NOTE_MODE_OPTIONS.find((item) => item.value === (mode || 'auto'));
    return found ? (lang === 'zh' ? found.labelZh : found.labelEn) : (mode || 'auto');
};

/* 与 backend/core/ai_summarizer.py 中 FLUENTFLOW_SYSTEM_PROMPT 保持一致，便于本地编辑默认「课程笔记」 */
const DEFAULT_COURSE_PROMPT = `# Role: FluentFlow 知识架构师

# Task: 你将接收一段由 Whisper 转录的原始课程录音文本。这段文本可能包含口癖、重复和错别字。你的任务是将其转化为一份高质量、结构化、可直接用于复习的飞书云文档笔记。

# Writing Style:
- 严谨、专业、富有启发性。
- 使用二级和三级标题建立层级感。
- 重点术语使用 **加粗**。
- 核心金句使用 > 引用块。

# Output Structure:
1. 📌 **一句话概览**：用一句话总结本段视频的核心主题。
2. 🔑 **核心概念盘点**：列出视频中提到的所有关键词及简要解释（使用无序列表）。
3. 🚀 **深度逻辑拆解**：
   - 将内容拆分为 3-5 个逻辑模块。
   - 采用「背景-原理-结论」或「问题-对策-案例」的逻辑编写。
   - 如果涉及代码或公式，请用标准 Markdown 格式包裹（如 $$...$$）。
4. 📝 **老师的「敲黑板」**：提炼老师反复强调的考点或实践建议。
5. 💡 **延伸思考/Next Step**：基于本课内容，提出一个值得深入研究的问题或后续实践任务。

# Constraints:
- 保持原意，不要虚构事实。
- 剔除「呃」、「那个」、「其实」等口头语。
- 保持内容的高度浓缩，去除冗余解释。
- 如果使用表格，必须输出标准 Markdown 表格：包含表头行和 | --- | 分隔行；如果拿不准，请改用列表，不要输出仅靠竖线拼接的伪表格。
- 输出为可直接粘贴飞书云文档的 Markdown，不要使用代码围栏包裹整篇文档。`;

/* ═══════════════ Prompt Presets ═══════════════ */
const PROMPT_PRESETS = {
    default: {
        labelEn: 'Course Notes (Default)',
        labelZh: '课程笔记（默认）',
        prompt: '', // 实际正文用 getDefaultPromptBody(settings)
    },
    meeting: {
        labelEn: 'Meeting Minutes',
        labelZh: '会议纪要',
        prompt: `# Role: FluentFlow 会议纪要助手

# Task: 将 Whisper 转录的原始会议录音文本转化为一份清晰、可执行的会议纪要。

# Writing Style:
- 简洁、条理清晰、突出行动项。
- 使用二级和三级标题建立层级感。
- 人名和关键决策使用 **加粗**。
- 重要决定使用 > 引用块。

# Output Structure:
1. 📌 **会议概述**：一句话总结会议主题、时间与参会人。
2. 📋 **议题与讨论要点**：按议题分组，列出各方发言要点。
3. ✅ **决议与共识**：列出明确达成的决定。
4. 🎯 **行动项 (Action Items)**：
   - 格式：负责人 | 任务 | 截止时间
   - 如使用表格，必须输出标准 Markdown 表格（含表头行和 | --- | 分隔行）；若拿不准则改用清晰列表。
5. 📅 **后续安排**：下次会议时间或待跟进事项。

# Constraints:
- 保持原意，不要虚构发言。
- 剔除口头语和无意义填充词。
- 保持内容高度浓缩。
- 输出为可直接粘贴飞书云文档的 Markdown。`,
    },
    research: {
        labelEn: 'Research / Paper Summary',
        labelZh: '研究/论文摘要',
        prompt: `# Role: FluentFlow 学术摘要助手

# Task: 将 Whisper 转录的学术讲座/论文讨论录音转化为结构化的学术摘要。

# Writing Style:
- 学术化、精确、逻辑严密。
- 使用标准学术论文结构。
- 术语首次出现时加粗并附英文原文。
- 公式和引用使用标准 Markdown 格式。

# Output Structure:
1. 📌 **主题与背景**：研究领域、问题背景、研究动机。
2. 🔬 **核心方法/理论**：研究方法论、关键假设、实验设计。
3. 📊 **主要发现/结论**：核心结果与数据支撑。
4. 💡 **创新点与局限**：方法或结论的独到之处，以及已知局限。
5. 📚 **延伸阅读建议**：基于内容推荐的相关研究方向。

# Constraints:
- 严格保持学术中立，不添加主观评价。
- 保留所有关键数据、公式和专业术语。
- 输出为 Markdown 格式。`,
    },
    quickBullets: {
        labelEn: 'Quick Bullet Points',
        labelZh: '快速要点提炼',
        prompt: `# Role: FluentFlow 快速提炼助手

# Task: 将 Whisper 转录文本快速浓缩为核心要点列表，适合快速浏览。

# Writing Style:
- 极简、精炼、一目了然。
- 每条要点不超过两句话。
- 关键词加粗。

# Output Structure:
1. **一句话总结**
2. **核心要点**（无序列表，5-15 条）
3. **关键数据/事实**（如有）
4. **TODO / 下一步**（如有）

# Constraints:
- 总输出不超过 500 字。
- 不要使用大段描述。
- 输出为 Markdown 格式。`,
    },
    custom: {
        labelEn: 'Custom Prompt',
        labelZh: '自定义提示词',
        prompt: '',
    },
};

const getDefaultPromptBody = (settings) => {
    const o = settings && settings.defaultPromptOverride;
    if (o != null && String(o).trim() !== '') return String(o);
    return DEFAULT_COURSE_PROMPT;
};

/** 内置模板 meeting / research / quickBullets：可经 settings.promptOverrides[key] 覆盖 */
const getBuiltinExtraPromptBody = (key, settings) => {
    const base = PROMPT_PRESETS[key]?.prompt || '';
    const o = settings && settings.promptOverrides && settings.promptOverrides[key];
    if (o != null && String(o).trim() !== '') return String(o);
    return base;
};

const normalizeUserPresets = (settings) => (Array.isArray(settings?.userPromptPresets) ? settings.userPromptPresets : []);

const getHiddenBuiltinPromptPresets = (settings) => (Array.isArray(settings?.hiddenPromptPresets) ? settings.hiddenPromptPresets : []);

const isBuiltinPromptPresetHidden = (key, settings) => (
    (key === 'meeting' || key === 'research' || key === 'quickBullets') &&
    getHiddenBuiltinPromptPresets(settings).includes(key)
);

const resolveSystemPromptFromSettings = (settings) => {
    const key = (settings && settings.promptPreset) || 'default';
    if (key === 'custom') return (settings.customPromptText || '').trim();
    if (key === 'default') return getDefaultPromptBody(settings).trim();
    if (key === 'meeting' || key === 'research' || key === 'quickBullets') {
        if (isBuiltinPromptPresetHidden(key, settings)) return getDefaultPromptBody(settings).trim();
        return getBuiltinExtraPromptBody(key, settings).trim();
    }
    const ups = normalizeUserPresets(settings);
    const found = ups.find((p) => p.id === key);
    if (found) return (found.prompt || '').trim();
    return (PROMPT_PRESETS[key]?.prompt || '').trim();
};

const allPresetSelectKeys = (settings) => {
    const ups = normalizeUserPresets(settings);
    const hidden = getHiddenBuiltinPromptPresets(settings);
    return [...Object.keys(PROMPT_PRESETS).filter((k) => !hidden.includes(k)), ...ups.map((p) => p.id)];
};

const presetDisplayLabel = (key, settings, lang) => {
    if (key && key.startsWith('user_')) {
        const p = normalizeUserPresets(settings).find((x) => x.id === key);
        if (p) return lang === 'zh' ? p.nameZh : p.nameEn;
    }
    const p = PROMPT_PRESETS[key];
    return p ? (lang === 'zh' ? p.labelZh : p.labelEn) : key;
};

const editorPresetKeyOrder = (settings) => {
    const ups = normalizeUserPresets(settings).map((p) => p.id);
    const hidden = getHiddenBuiltinPromptPresets(settings);
    return [
        'default',
        'meeting',
        'research',
        'quickBullets',
        ...ups,
        'custom',
    ].filter((k) => !((k === 'meeting' || k === 'research' || k === 'quickBullets') && hidden.includes(k)));
};

const DEFAULT_STT_MODEL = 'medium';
const DEFAULT_STT_PROVIDER = 'azure_batch';
const normalizeSttProvider = (provider) => (
    provider === 'local' || provider === 'azure_batch' || provider === 'azure_fast'
        ? (provider === 'azure_fast' ? 'azure_batch' : provider)
        : DEFAULT_STT_PROVIDER
);
const isAzureCloudProvider = (provider) => (
    normalizeSttProvider(provider) === 'azure_batch'
);
const isAzureSpeechConfigured = (status) => (
    !!status?.azure_speech_endpoint_configured && !!status?.azure_speech_key_configured
);
const isAzureBatchConfigured = (status) => (
    isAzureSpeechConfigured(status) && !!status?.azure_blob_container_sas_url_configured
);
const DEFAULT_RUNTIME_CONFIG = {
    publicMode: false,
    allowedSttProviders: ['azure_batch', 'local'],
    defaultSttProvider: DEFAULT_STT_PROVIDER,
    showMaintainerSettings: true,
};
const normalizeRuntimeConfig = (config={}) => {
    const allowed = Array.isArray(config.allowed_stt_providers)
        ? config.allowed_stt_providers.map(normalizeSttProvider)
        : DEFAULT_RUNTIME_CONFIG.allowedSttProviders;
    const uniqueAllowed = [...new Set(allowed.filter((item) => item === 'azure_batch' || item === 'local'))];
    const fallbackAllowed = uniqueAllowed.length ? uniqueAllowed : DEFAULT_RUNTIME_CONFIG.allowedSttProviders;
    const defaultProvider = normalizeSttProvider(config.default_stt_provider || DEFAULT_STT_PROVIDER);
    return {
        publicMode: !!config.public_mode,
        allowedSttProviders: fallbackAllowed,
        defaultSttProvider: fallbackAllowed.includes(defaultProvider) ? defaultProvider : fallbackAllowed[0],
        showMaintainerSettings: config.show_maintainer_settings !== false,
        limits: config.limits || {},
    };
};
const effectiveSttProvider = (settings={}, runtimeConfig=DEFAULT_RUNTIME_CONFIG) => {
    const wanted = normalizeSttProvider(settings.sttProvider);
    return runtimeConfig.allowedSttProviders.includes(wanted) ? wanted : runtimeConfig.defaultSttProvider;
};
const azureSpeechMissingMessage = (lang) => (
    lang === 'zh'
        ? '云端转录暂不可用，请联系产品维护者检查后台配置。'
        : 'Cloud transcription is unavailable. Ask the product maintainer to check backend configuration.'
);
const normalizeSttModel = (model) => (
    model === 'large-v3' || model === 'medium' ? model : DEFAULT_STT_MODEL
);
/* ═══════════════ i18n ═══════════════ */
const msgs = {
  en:{
    'nav.subtitle':'Video-to-Lark AI','nav.dashboard':'Start','nav.tasks':'Tasks','nav.processing':'Run Settings','nav.editor':'Editor','nav.settings':'Settings','nav.newProject':'New Project','nav.search':'Search projects...','nav.projects':'Projects','nav.integrations':'Integrations',
    'status.ready':'System ready','status.idle':'Awaiting task','status.queued':'Queued','status.resolving':'Resolving link…','status.downloading':'Downloading video…','status.saving':'Saving video…','status.upload':'Uploading…','status.audio':'Extracting audio…','status.stt':'Transcribing…','status.transcript_ready':'Transcript ready','status.summary':'AI summarizing…','status.export':'Exporting to Lark…','status.done':'Done','status.failed':'Failed',
    'dash.welcome':'Start a transcription.','dash.subtitle':'Upload a video or audio file. FluentFlow handles the transcription route in the background.','dash.totalMin':'Total Minutes','dash.noteGen':'Notes Generated','dash.minUnit':'min','dash.docUnit':'docs','dash.proTag':'Ready','dash.heroTitle':'Drop a video here to transcribe it.','dash.heroDesc':'FluentFlow extracts audio, transcribes it in the background, and prepares transcript, subtitles, and notes.','dash.selectFile':'Select Audio/Video','dash.selectSubtitle':'Import Subtitle/Text','dash.subtitleHint':'Drop audio/video to start transcription; import existing subtitles to generate notes directly.','dash.processing':'Processing…','dash.dragHint':'Drop audio/video to start transcription; import existing subtitles to generate notes directly.','dash.linkPlaceholder':'Paste Douyin share text or a video link','dash.linkSubmit':'Fetch by link','dash.linkSubmitting':'Fetching…','dash.linkEmpty':'Paste a share text or video link first.','dash.linkQueued':'Video link is being fetched in Background tasks.','dash.azureUploadHint':'Cloud transcription runs in the background. You can leave this page and watch it from Tasks.','dash.uploading':'Uploading and processing','dash.done':'Processing complete','dash.subtitleDone':'Summary generated from transcript file','dash.viewEditor':'View in Editor','dash.recent':'Recent Activity','dash.viewAll':'View All','dash.fileError':'Unsupported format. Please select a video or audio file.','dash.subtitleFileError':'Unsupported transcript file. Please select SRT, VTT, TXT, or MD.','dash.noActivity':'No activity yet. Completed jobs will appear here.','dash.justNow':'just now','dash.mAgo':'m ago','dash.hAgo':'h ago','dash.dAgo':'d ago',
    'dash.statusCompleted':'Completed','dash.statusFailed':'Failed','dash.statusProcessing':'Processing','dash.cancel':'Cancel','dash.activeTask':'Active Task','dash.elapsed':'Elapsed','dash.fileSize':'File Size','dash.azureUploadAudio':'Cloud Audio','dash.pipeline':'Pipeline','dash.modelProfile':'Route','dash.summaryMode':'Summary Mode','dash.summaryOn':'AI summary on','dash.summaryOff':'Transcript only','dash.exportOn':'Auto Lark export','dash.exportOff':'Manual export later','dash.currentStage':'Current Stage','dash.waitingForTranscript':'You can leave this page; progress continues under Tasks.','dash.transcribedTo':'Transcribed','dash.waitingSegment':'Waiting for first transcript segment','dash.progressUnknown':'Working','dash.sttMeasuring':'STT measuring','dash.sttStarting':'Starting transcription engine','dash.sttLoadingModel':'Loading local model','dash.sttChunking':'Preparing progress tracking','dash.sttPreparingAudio':'Preparing audio features','dash.sttWaitingFirst':'Waiting for the first transcript segment','dash.sttChunks':'Transcribing audio','dash.sttSegments':'Receiving transcript segments','dash.sttAzure':'Cloud transcription in progress','dash.sttAzureUpload':'Uploading audio','dash.sttAzureSubmit':'Submitting cloud job','dash.sttAzureWait':'Waiting for cloud transcription','dash.sttAzureDownload':'Downloading cloud result','dash.sttNoProgressHint':'The first transcript segment has not been produced yet. Progress will advance once local transcription emits real segments.',
    'tasks.title':'Background tasks','tasks.subtitle':'Track long-running transcription jobs without keeping the Start page open.','tasks.refresh':'Refresh','tasks.open':'Open result','tasks.download':'Download','tasks.progress':'Progress','tasks.route':'Route','tasks.updated':'Updated','tasks.empty':'No background tasks yet. Start with an upload from Start.','tasks.queued':'Queued','tasks.running':'Running','tasks.completed':'Completed','tasks.failed':'Failed','tasks.error':'Failure reason','tasks.source':'Source','tasks.summary':'Summary','tasks.detail':'Stage detail','tasks.artifacts':'Outputs','tasks.outputsReady':'Ready outputs','tasks.noOutputs':'Outputs appear here after completion.','tasks.larkDoc':'Lark doc','tasks.srt':'SRT','tasks.txt':'TXT','tasks.vtt':'VTT','tasks.md':'Summary',
    'proc.title':'Run settings','proc.subtitle':'Set the few choices that affect every upload. Cloud infrastructure is managed by the product owner.','proc.noJob':'No active processing','proc.noJobDesc':'Upload a video from Start when you are ready.','proc.audioExtract':'Audio Extraction','proc.transcription':'Transcription','proc.aiSumm':'AI Summarization','proc.larkExport':'Lark Export','proc.waiting':'Waiting…','proc.running':'Running…','proc.done':'Done','proc.pipeline':'Pipeline Progress',
    'edit.title':'Editor','edit.noResult':'No results yet','edit.noResultDesc':'Process a video from the Dashboard, then view the transcript and summary here.','edit.transcript':'Full Transcript','edit.aiSummary':'AI Summary','edit.summaryPending':'AI summary is still generating.','edit.summarySkipped':'Transcript-only mode is enabled. Click Regenerate when you need an AI summary.','edit.share':'Share','edit.export':'Export to Lark','edit.confidence':'AI Generated','edit.regenerate':'Regenerate','edit.retranscribe':'Retranscribe','edit.retranscribing':'Retranscribing…','edit.pickSourceAgain':'Choose source file','edit.retranscribeDone':'Retranscription complete','edit.retranscribeConfirmTitle':'Retranscribe this audio?','edit.retranscribeConfirmDesc':'FluentFlow will run STT again with the current Workbench settings and replace the transcript and summary for this result.','edit.retranscribeUnavailableTitle':'Source file is not available','edit.retranscribeUnavailableDesc':'Browsers cannot reopen a local file from history without your permission. Choose the original audio/video file to retranscribe it with current settings.','edit.retranscribeConfirmAction':'Start retranscription','edit.retranscribeChooseAction':'Choose original file','edit.cancel':'Cancel','edit.segments':'segments','edit.duration':'Duration','edit.sttElapsed':'Transcription time','edit.exportDone':'Export request sent','edit.exportFail':'Export failed','edit.regenDone':'Summary regenerated','edit.clearHistory':'Clear History','edit.clearConfirm':'All history cleared','edit.clearConfirmAgain':'Click again to confirm','edit.reviewButton':'Review changes','edit.reviewTitle':'Transcript review changes','edit.reviewDesc':'Check the AI-confirmed term corrections with nearby context.','edit.reviewEmpty':'No obvious term issues were found.','edit.reviewApplied':'Applied','edit.reviewPending':'Suggested only','edit.reviewOriginal':'Original','edit.reviewSuggested':'Suggested','edit.reviewContext':'Context','edit.reviewReason':'Reason','edit.copySuggestion':'Copy suggested sentence','edit.copied':'Copied','edit.editedTranscript':'Edited transcript','edit.transcriptSaving':'Saving…','edit.transcriptSaved':'Saved','edit.transcriptSaveFailed':'Save failed','edit.editRecords':'Edit records','edit.editRecordsTitle':'Transcript edit records','edit.editRecordsDesc':'Each record keeps the changed sentence and nearby context. These records are saved locally with the edited transcript.','edit.editRecordsEmpty':'No changed segment has been recorded yet.','edit.before':'Before','edit.after':'After','edit.previousSentence':'Previous sentence','edit.nextSentence':'Next sentence','edit.followPlayback':'Follow playback','edit.audioUnavailable':'Choose the original audio/video to listen while editing.','edit.chooseAudio':'Choose source audio','edit.sourceLoading':'Loading source audio…',
    'prompt.label':'Prompt Template','prompt.select':'Select prompt style','prompt.customPlaceholder':'Enter your custom system prompt here...','prompt.expanded':'Collapse prompt','prompt.collapsed':'Change prompt','prompt.activeHint':'Active: ','prompt.editHint':'Edit prompt before regenerating','prompt.saveAsPreset':'Save custom as preset',
    'dl.transcript':'Export Transcript','dl.summary':'Download Summary','dl.txt':'Plain Text (.txt)','dl.md':'Markdown (.md)','dl.srt':'Subtitles (.srt)','dl.vtt':'WebVTT (.vtt)','dl.pdf':'PDF Document','dl.word':'Word Document (.docx)','dl.generating':'Generating…','dl.success':'Download started',
    'set.title':'Settings','set.subtitle':'Keep template maintenance, export history, and app preferences here.','set.larkTitle':'Lark / Feishu Credentials','set.larkDesc':'Store credentials only. Export behavior now lives in Run Settings.','set.autoExport':'Auto-export to Lark after processing','set.larkViaCli':'Export via local lark-cli (My Library)','set.larkViaCliHint':'Uses your lark-cli login; App ID not required. Backend must run lark-cli on PATH.','set.larkHistory':'Export History','set.sttProvider':'Transcription Route','set.providerLocal':'Local transcription','set.providerAzureBatch':'Cloud transcription','set.sttModel':'STT Model','set.modelSel':'Model Selection','set.sttLanguage':'Audio Language','set.langAuto':'Auto detect','set.langZh':'Chinese','set.langEn':'English','set.sttSpeed':'Transcription Speed','set.speedFast':'Fast','set.speedBalanced':'Balanced','set.speedAccurate':'Accurate','set.optTiny':'tiny (Fastest)','set.optBase':'base','set.optSmall':'small (Not recommended)','set.optMedium':'medium (Minimum usable)','set.optLarge':'large-v3 (Most Accurate)','set.intelligence':'Intelligence','set.skipSummary':'Transcript-only mode','set.skipSummaryHint':'Skip AI summary after audio transcription or subtitle import. You can regenerate later in the editor.','set.provider':'Provider','set.aiModel':'AI Model','set.openaiKey':'OpenAI API Key','set.deepseekKey':'DeepSeek API Key','set.prefs':'App Preferences','set.theme':'Interface Theme','set.light':'Light','set.dark':'Dark','set.saved':'Saved!','set.saveAll':'Save All Changes','set.promptTitle':'Prompt Template Library','set.promptDesc':'Edit reusable prompt templates here. Choose the active default in Run Settings.','set.defaultPrompt':'Default Prompt','set.templateToEdit':'Template to edit','set.editCoursePrompt':'Edit “Course Notes” system prompt','set.editBuiltinTemplate':'Edit this template','set.resetBuiltinPrompt':'Reset to built-in default','set.deleteBuiltinPrompt':'Delete this template category','set.deleteBuiltinPromptConfirm':'Delete this template category (remove it from the UI)?','set.myPresets':'Saved presets','set.presetNamePh':'Preset name','set.saveAsPreset':'Save as preset','set.deletePreset':'Delete','set.deletePresetConfirm':'Delete this saved preset?','set.presetSaved':'Preset saved',
    'work.defaults':'Run defaults','work.defaultsDesc':'These values are used by Dashboard uploads, subtitle imports, and editor reruns.','work.activePrompt':'Default prompt template','work.transcription':'Transcription','work.hotwordLibrary':'Hotword library','work.integratedHotwordLibrary':'Integrated hotword library','work.hotwordHint':'All domain terms and conservative correction candidates are used together for STT prompts and transcript review.','work.viewHotwords':'View contents','work.hotwordDialogTitle':'Hotword library contents','work.hotwordDialogDesc':'Review the terms and conservative correction candidates currently used by FluentFlow.','work.effectiveLibraries':'Included sources','work.hotwordTerms':'Terms','work.confusionPairs':'Confusion candidates','work.autoApply':'auto apply','work.suggestOnly':'suggest only','work.noTerms':'No terms in this preset.','work.noConfusions':'No confusion candidates.','work.hotwordsUnavailable':'Hotword details are unavailable. Restart the backend if this keeps showing.','work.close':'Close','work.reviewMode':'Subtitle review','work.reviewModeHint':'Optional. Raw transcript is always preserved.','work.reviewUseAi':'Use AI to verify suggestions','work.reviewUseAiHint':'AI can only confirm minimal obvious corrections, never rewrite freely.','work.reviewSuggestions':'Review suggestions','work.reviewApplied':'Applied corrections','work.summary':'Summary AI','work.summaryMode':'Note generation mode','work.noteModeAuto':'Auto switches by transcript length: direct under about 20k chars, high-fidelity above it.','work.noteModeDirect':'Sends the transcript in one pass. Faster, best for shorter materials.','work.noteModeHighFidelity':'Extracts evidence in chunks, then writes and checks coverage. Slower, better for long courses.','work.export':'Feishu export','work.currentRun':'Current run','work.activeRunHint':'Dashboard now shows the detailed live progress. Workbench stays focused on run defaults.','work.viewProgress':'View progress','work.saved':'Saved automatically','work.credentialsLink':'Credentials stay in Settings',
  },
  zh:{
    'nav.subtitle':'视频转飞书 AI','nav.dashboard':'开始处理','nav.tasks':'后台任务','nav.processing':'处理设置','nav.editor':'编辑器','nav.settings':'设置','nav.newProject':'新建项目','nav.search':'搜索项目…','nav.projects':'项目','nav.integrations':'集成',
    'status.ready':'系统就绪','status.idle':'等待任务','status.queued':'排队中','status.resolving':'解析链接中…','status.downloading':'下载视频中…','status.saving':'保存视频中…','status.upload':'上传中…','status.audio':'音频提取中…','status.stt':'转录中…','status.transcript_ready':'转录已完成','status.summary':'AI 摘要中…','status.export':'导出到飞书…','status.done':'完成','status.failed':'失败',
    'dash.welcome':'开始一次转录','dash.subtitle':'上传视频或音频，FluentFlow 会在后台完成转录、字幕和笔记。','dash.totalMin':'累计时长','dash.noteGen':'已生成笔记','dash.minUnit':'分钟','dash.docUnit':'份','dash.proTag':'就绪','dash.heroTitle':'把视频拖到这里开始转录。','dash.heroDesc':'FluentFlow 会自动提取音频，在后台转录，并生成转录文本、字幕和结构化笔记。','dash.selectFile':'选择音视频','dash.selectSubtitle':'导入字幕/文本','dash.subtitleHint':'拖放音视频开始转录；已有字幕可直接导入生成笔记。','dash.processing':'处理中…','dash.dragHint':'拖放音视频开始转录；已有字幕可直接导入生成笔记。','dash.linkPlaceholder':'粘贴抖音分享文本或视频链接','dash.linkSubmit':'通过链接获取','dash.linkSubmitting':'获取中…','dash.linkEmpty':'请先粘贴分享文本或视频链接。','dash.linkQueued':'视频链接已进入后台任务获取。','dash.azureUploadHint':'云端转录会在后台继续运行，你可以离开本页并在后台任务里查看进度。','dash.uploading':'正在上传并处理','dash.done':'处理完成','dash.subtitleDone':'已根据字幕文件生成摘要','dash.viewEditor':'在编辑器中查看','dash.recent':'最近活动','dash.viewAll':'查看全部','dash.fileError':'不支持的格式，请选择视频或音频文件。','dash.subtitleFileError':'不支持的字幕/转录文件，请选择 SRT、VTT、TXT 或 MD。','dash.noActivity':'暂无活动记录，完成的任务会显示在这里。','dash.justNow':'刚刚','dash.mAgo':'分钟前','dash.hAgo':'小时前','dash.dAgo':'天前',
    'dash.statusCompleted':'已完成','dash.statusFailed':'失败','dash.statusProcessing':'处理中','dash.cancel':'取消','dash.activeTask':'当前任务','dash.elapsed':'已用时间','dash.fileSize':'文件大小','dash.azureUploadAudio':'云端音频','dash.pipeline':'处理流水线','dash.modelProfile':'转录路线','dash.summaryMode':'摘要模式','dash.summaryOn':'生成 AI 摘要','dash.summaryOff':'仅转录','dash.exportOn':'自动导出飞书','dash.exportOff':'完成后手动导出','dash.currentStage':'当前阶段','dash.waitingForTranscript':'你可以离开本页，进度会在后台任务中继续更新。','dash.transcribedTo':'已转录','dash.waitingSegment':'等待第一段转录结果','dash.progressUnknown':'处理中','dash.sttMeasuring':'STT 计算中','dash.sttStarting':'正在启动转录引擎','dash.sttLoadingModel':'正在加载本地模型','dash.sttChunking':'正在准备进度追踪','dash.sttPreparingAudio':'正在准备音频特征','dash.sttWaitingFirst':'等待第一段转录结果','dash.sttChunks':'正在转录音频','dash.sttSegments':'正在接收转录片段','dash.sttAzure':'云端转录中','dash.sttAzureUpload':'正在上传音频','dash.sttAzureSubmit':'正在提交云端任务','dash.sttAzureWait':'等待云端转录','dash.sttAzureDownload':'正在下载云端结果','dash.sttNoProgressHint':'第一段转录结果还没有产出。后续会按本地转录真实返回的片段推进进度。',
    'tasks.title':'后台任务','tasks.subtitle':'长时间转录不需要停留在开始页，这里统一查看进度、失败原因和产物。','tasks.refresh':'刷新','tasks.open':'打开结果','tasks.download':'下载','tasks.progress':'进度','tasks.route':'路线','tasks.updated':'更新于','tasks.empty':'暂无后台任务。从开始处理页上传文件后会出现在这里。','tasks.queued':'排队中','tasks.running':'运行中','tasks.completed':'已完成','tasks.failed':'失败','tasks.error':'失败原因','tasks.source':'来源','tasks.summary':'摘要','tasks.detail':'阶段详情','tasks.artifacts':'结果产物','tasks.outputsReady':'可下载产物','tasks.noOutputs':'完成后会在这里显示下载入口。','tasks.larkDoc':'飞书文档','tasks.srt':'SRT','tasks.txt':'TXT','tasks.vtt':'VTT','tasks.md':'摘要',
    'proc.title':'处理设置','proc.subtitle':'这里只保留每次上传前会影响结果的少量选择；云端基础设施由产品维护者管理。','proc.noJob':'当前没有任务','proc.noJobDesc':'参数确认后，从开始处理页上传文件。','proc.audioExtract':'音频提取','proc.transcription':'语音转录','proc.aiSumm':'AI 摘要','proc.larkExport':'飞书导出','proc.waiting':'等待中…','proc.running':'运行中…','proc.done':'完成','proc.pipeline':'流水线进度',
    'edit.title':'编辑器','edit.noResult':'暂无结果','edit.noResultDesc':'从仪表盘处理一个视频后，在此查看转录和摘要。','edit.transcript':'完整转录','edit.aiSummary':'AI 摘要','edit.summaryPending':'AI 摘要仍在生成中。','edit.summarySkipped':'当前是仅转录模式，未生成 AI 摘要。需要时可点击重新生成。','edit.share':'分享','edit.export':'导出到飞书','edit.confidence':'AI 生成','edit.regenerate':'重新生成','edit.retranscribe':'重新转录','edit.retranscribing':'重新转录中…','edit.pickSourceAgain':'选择原文件','edit.retranscribeDone':'重新转录完成','edit.retranscribeConfirmTitle':'重新转录当前音频？','edit.retranscribeConfirmDesc':'FluentFlow 会使用当前工作台设置重新执行 STT，并替换当前结果里的转录文本和摘要。','edit.retranscribeUnavailableTitle':'当前没有可直接重转的原文件','edit.retranscribeUnavailableDesc':'浏览器不会在历史记录里长期保留本地音视频文件权限。请选择原始音视频文件，再用当前设置重新转录。','edit.retranscribeConfirmAction':'确认重新转录','edit.retranscribeChooseAction':'选择原始文件','edit.cancel':'取消','edit.segments':'段','edit.duration':'时长','edit.sttElapsed':'转录耗时','edit.exportDone':'导出请求已发送','edit.exportFail':'导出失败','edit.regenDone':'摘要已重新生成','edit.clearHistory':'清除记录','edit.clearConfirm':'所有记录已清除','edit.clearConfirmAgain':'再次点击确认','edit.reviewButton':'查看审阅','edit.reviewTitle':'字幕审阅修改点','edit.reviewDesc':'查看 AI 确认过的术语修正，并对照前后文判断是否合理。','edit.reviewEmpty':'没有发现明显术语错误。','edit.reviewApplied':'已应用','edit.reviewPending':'仅建议','edit.reviewOriginal':'原句','edit.reviewSuggested':'建议句','edit.reviewContext':'上下文','edit.reviewReason':'原因','edit.copySuggestion':'复制建议句','edit.copied':'已复制','edit.editedTranscript':'已修改转录','edit.transcriptSaving':'保存中…','edit.transcriptSaved':'已保存','edit.transcriptSaveFailed':'保存失败','edit.editRecords':'修改记录','edit.editRecordsTitle':'转录稿修改记录','edit.editRecordsDesc':'每条记录会保留修改句子和相邻上下文，并随编辑稿一起保存到本地。','edit.editRecordsEmpty':'还没有记录到分段修改。','edit.before':'修改前','edit.after':'修改后','edit.previousSentence':'上一句','edit.nextSentence':'下一句','edit.followPlayback':'跟随播放','edit.audioUnavailable':'选择原始音视频后，可边听边校对。','edit.chooseAudio':'选择原音频','edit.sourceLoading':'正在读取原音频…',
    'prompt.label':'提示词模板','prompt.select':'选择提示词风格','prompt.customPlaceholder':'在此输入自定义系统提示词…','prompt.expanded':'收起提示词','prompt.collapsed':'更换提示词','prompt.activeHint':'当前：','prompt.editHint':'重新生成前可编辑提示词','prompt.saveAsPreset':'将自定义保存为预设',
    'dl.transcript':'导出转录文本','dl.summary':'下载摘要','dl.txt':'纯文本 (.txt)','dl.md':'Markdown (.md)','dl.srt':'字幕文件 (.srt)','dl.vtt':'WebVTT (.vtt)','dl.pdf':'PDF 文档','dl.word':'Word 文档 (.docx)','dl.generating':'生成中…','dl.success':'已开始下载',
    'set.title':'设置','set.subtitle':'这里只保留模板维护、导出历史和应用偏好。','set.larkTitle':'飞书凭证','set.larkDesc':'这里只保存连接凭证；是否自动导出等处理选项已移到处理设置。','set.autoExport':'处理完成后自动导出到飞书','set.larkViaCli':'用本机 lark-cli 导出到「我的文档库」','set.larkViaCliHint':'使用你已登录的 lark-cli，无需填 App 凭证；后端进程需能调用本机 PATH 上的 lark-cli。','set.larkHistory':'导出记录','set.sttProvider':'转录路线','set.providerLocal':'本地转录','set.providerAzureBatch':'云端转录','set.sttModel':'STT 模型','set.modelSel':'模型选择','set.sttLanguage':'音频语言','set.langAuto':'自动识别','set.langZh':'中文','set.langEn':'英文','set.sttSpeed':'转录速度','set.speedFast':'快速','set.speedBalanced':'均衡','set.speedAccurate':'高准确率','set.optTiny':'tiny（最快）','set.optBase':'base','set.optSmall':'small（不推荐）','set.optMedium':'medium（最低可用）','set.optLarge':'large-v3（最准确）','set.intelligence':'AI 智能','set.skipSummary':'仅转录模式','set.skipSummaryHint':'音视频转录或字幕导入后跳过 AI 摘要；之后可在编辑器里重新生成。','set.provider':'服务商','set.aiModel':'AI 模型','set.openaiKey':'OpenAI API Key','set.deepseekKey':'DeepSeek API Key','set.prefs':'应用偏好','set.theme':'界面主题','set.light':'浅色','set.dark':'深色','set.saved':'已保存！','set.saveAll':'保存所有更改','set.promptTitle':'提示词模板库','set.promptDesc':'在这里维护可复用提示词；当前默认使用哪个在处理设置中选择。','set.defaultPrompt':'默认提示词','set.templateToEdit':'要编辑的模板','set.editCoursePrompt':'编辑「课程笔记」系统提示词','set.editBuiltinTemplate':'编辑该模板内容','set.resetBuiltinPrompt':'恢复为内置默认','set.deleteBuiltinPrompt':'删除该模板类目','set.deleteBuiltinPromptConfirm':'确定删除该模板类目（从界面移除）？','set.myPresets':'已保存的预设','set.presetNamePh':'预设名称','set.saveAsPreset':'保存为预设','set.deletePreset':'删除','set.deletePresetConfirm':'确定删除该保存的预设？','set.presetSaved':'已保存预设',
    'work.defaults':'处理默认值','work.defaultsDesc':'仪表盘上传、字幕导入、编辑器重新生成都会使用这些设置。','work.activePrompt':'默认提示词模板','work.transcription':'转录','work.hotwordLibrary':'热词库','work.integratedHotwordLibrary':'综合热词库','work.hotwordHint':'所有领域词和保守错词候选会一起用于 STT 提示词和字幕审阅。','work.viewHotwords':'查看内容','work.hotwordDialogTitle':'热词库内容','work.hotwordDialogDesc':'查看 FluentFlow 当前用于转录提示和保守审阅的领域词、错词候选。','work.effectiveLibraries':'包含来源','work.hotwordTerms':'领域词','work.confusionPairs':'错词候选','work.autoApply':'自动应用','work.suggestOnly':'仅建议','work.noTerms':'当前没有领域词。','work.noConfusions':'没有错词候选。','work.hotwordsUnavailable':'暂时无法读取热词详情。如果一直如此，请重启后端。','work.close':'关闭','work.reviewMode':'字幕审阅','work.reviewModeHint':'可选。原始转录会始终保留。','work.reviewUseAi':'使用 AI 复核建议','work.reviewUseAiHint':'AI 只能确认明显的最小修正，不能自由改写。','work.reviewSuggestions':'审阅建议','work.reviewApplied':'已应用修正','work.summary':'摘要 AI','work.summaryMode':'笔记生成模式','work.noteModeAuto':'按转录长度自动切换：约 2 万字以内直接生成，超过后用高保真模式。','work.noteModeDirect':'整段一次发送给模型，速度更快，适合较短材料。','work.noteModeHighFidelity':'先分段提取证据，再成文并检查覆盖率，耗时更久，适合长课程。','work.export':'飞书导出','work.currentRun':'当前任务','work.activeRunHint':'主页已经展示更完整的实时进度，工作台只保留本次运行参数。','work.viewProgress':'查看进度','work.saved':'自动保存','work.credentialsLink':'凭证仍在设置页',
  },
};
const I18nCtx = createContext();
const I18nProvider = ({children}) => {
    const [lang,setLang] = useState(() => localStorage.getItem('fluentflow_lang')||'zh');
    const t = (k) => msgs[lang]?.[k] ?? msgs.en[k] ?? k;
    const toggleLang = () => { const n = lang==='en'?'zh':'en'; setLang(n); localStorage.setItem('fluentflow_lang',n); };
    return <I18nCtx.Provider value={{t,lang,toggleLang}}>{children}</I18nCtx.Provider>;
};
const useI18n = () => useContext(I18nCtx);

const AuthCtx = createContext({authMode:'open', user:null, logout:async()=>{}});
const useAuth = () => useContext(AuthCtx);

/* ═══════════════ App-level state ═══════════════ */
const AppCtx = createContext();

const AppProvider = ({children}) => {
    const [history, setHistory] = useState(() => {
        try { return JSON.parse(localStorage.getItem('fluentflow_history')||'[]'); } catch(_){ return []; }
    });
    const [larkExports, setLarkExports] = useState(() => {
        try { return JSON.parse(localStorage.getItem('fluentflow_lark_exports')||'[]'); } catch(_){ return []; }
    });
    const [currentJob, setCurrentJob] = useState(null);
    const [lastResult, setLastResult] = useState(null);
    const [lastSourceFile, setLastSourceFile] = useState(null);
    const [runtimeConfig, setRuntimeConfig] = useState(DEFAULT_RUNTIME_CONFIG);

    useEffect(() => {
        apiFetch(`${API_BASE}/runtime-config`)
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
                if (data) setRuntimeConfig(normalizeRuntimeConfig(data));
            })
            .catch(() => {});
        try {
            const rawSettings = JSON.parse(localStorage.getItem("fluentflow_settings")||"{}");
            const hasLegacySecrets = SENSITIVE_SETTING_KEYS.some((key) => rawSettings[key]);
            if (hasLegacySecrets) {
                apiFetch(`${API_BASE}/credentials`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(sensitivePatchFromSettings(rawSettings)),
                }).finally(() => {
                    localStorage.setItem("fluentflow_settings", JSON.stringify(sanitizeSettings(rawSettings)));
                });
            }
        } catch(_) {}
        apiFetch(`${API_BASE}/jobs?limit=100`)
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
                if (!Array.isArray(data?.jobs)) return;
                const entries = data.jobs
                    .filter((job) => job.result)
                    .map(jobToHistoryEntry);
                if (entries.length) setHistory(entries);
                const running = data.jobs.find((job) => job.status === 'running');
                if (running) setCurrentJob(jobToCurrentJob(running));
            })
            .catch(() => {});
    }, []);

    const persistHistory = (h) => { setHistory(h); localStorage.setItem('fluentflow_history', JSON.stringify(h.map(minimizeHistoryEntry))); };
    const addToHistory = (entry) => persistHistory([
        entry,
        ...history.filter((item) => !(entry.taskId && item.taskId === entry.taskId)),
    ].slice(0, 100));
    const clearHistory = () => { persistHistory([]); persistLarkExports([]); };

    const persistLarkExports = (e) => { setLarkExports(e); localStorage.setItem('fluentflow_lark_exports', JSON.stringify(e)); };
    const addLarkExport = (entry) => persistLarkExports([entry, ...larkExports].slice(0, 50));

    const stats = {
        totalMinutes: Math.round(history.reduce((s,h) => s + (h.durationMin||0), 0)),
        notesGenerated: history.filter(h => h.status==='completed').length,
    };

    return <AppCtx.Provider value={{history,addToHistory,clearHistory,currentJob,setCurrentJob,lastResult,setLastResult,lastSourceFile,setLastSourceFile,stats,larkExports,addLarkExport,runtimeConfig}}>{children}</AppCtx.Provider>;
};
const useApp = () => useContext(AppCtx);

/* ═══════════════ helpers ═══════════════ */
const fmtTime = (sec) => { const m=Math.floor(sec/60); const s=Math.floor(sec%60); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; };
const autoSizeTextarea = (node) => {
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${node.scrollHeight}px`;
};
const composeTranscriptText = (segments, fallback='') => (
    Array.isArray(segments) && segments.length > 0
        ? segments.map((seg) => (seg?.text || '').trim()).filter(Boolean).join('\n')
        : (fallback || '')
);
const normalizeTranscriptSegments = (value) => (
    Array.isArray(value)
        ? value
            .filter((seg) => seg && typeof seg === 'object' && String(seg.text || '').trim())
            .map((seg) => ({...seg, text: String(seg.text || '')}))
        : []
);
const pickTranscriptSegments = (source={}) => {
    for (const key of ['segments', 'cleaned_segments', 'raw_segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
};
const pickTranscriptBaselineSegments = (source={}) => {
    for (const key of ['cleaned_segments', 'raw_segments', 'segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
};
const buildTranscriptEditRecords = (beforeSegments=[], afterSegments=[], source={}) => {
    if (!Array.isArray(beforeSegments) || !Array.isArray(afterSegments) || beforeSegments.length === 0) return source?.transcript_edit_records || [];
    const now = new Date().toISOString();
    const limit = Math.max(beforeSegments.length, afterSegments.length);
    const records = [];
    for (let i = 0; i < limit; i += 1) {
        const before = beforeSegments[i] || {};
        const after = afterSegments[i] || {};
        const beforeText = String(before.text || '').trim();
        const afterText = String(after.text || '').trim();
        if (!beforeText && !afterText) continue;
        if (beforeText === afterText) continue;
        records.push({
            index: i,
            start: Number(before.start ?? after.start ?? 0) || 0,
            end: Number(before.end ?? after.end ?? before.start ?? after.start ?? 0) || 0,
            before: beforeText,
            after: afterText,
            previous_before: String(beforeSegments[i - 1]?.text || '').trim(),
            next_before: String(beforeSegments[i + 1]?.text || '').trim(),
            previous_after: String(afterSegments[i - 1]?.text || '').trim(),
            next_after: String(afterSegments[i + 1]?.text || '').trim(),
            created_at: now,
        });
    }
    return records;
};
const fmtElapsed = (sec) => {
    const n = Math.max(0, Number(sec) || 0);
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    const s = Math.floor(n % 60);
    return h > 0
        ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
        : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
};
const fmtFileSize = (mb) => {
    const n = Number(mb);
    if(!Number.isFinite(n) || n <= 0) return '-';
    if(n >= 1024) return `${(n/1024).toFixed(n >= 10240 ? 0 : 1)} GB`;
    return `${n.toFixed(n >= 10 ? 1 : 2)} MB`;
};
const fmtBytes = (bytes) => {
    const n = Number(bytes);
    if(!Number.isFinite(n) || n <= 0) return '';
    return fmtFileSize(n / 1024 / 1024);
};
const friendlyTaskError = (message, lang='zh') => {
    const raw = String(message || '').trim();
    if(!raw) return lang === 'zh' ? '处理失败，但没有返回具体原因。请重试一次。' : 'The task failed without a specific reason. Try again.';
    const lower = raw.toLowerCase();
    if(lower.includes('only "standard" subscriptions') || lower.includes('only \\"standard\\" subscriptions') || lower.includes('invalidsubscription')) return lang === 'zh' ? '云端转录提交失败：当前区域的 Speech 资源不是 Batch 支持的 Standard 订阅。请检查 Azure Speech 区域和定价层。' : 'Cloud transcription failed: the Speech resource is not a Standard subscription supported for Batch in this region.';
    if(lower.includes('invalidlocale') || lower.includes('specified locale is not supported')) return lang === 'zh' ? '云端转录提交失败：当前音频语言不被 Azure 支持。请切换为中文/英文，或改用本地转录。' : 'Cloud transcription failed: this locale is not supported by Azure.';
    if(lower.includes('invalidmodel') || lower.includes('specified model is not supported')) return lang === 'zh' ? '云端转录提交失败：当前 Azure 资源不支持所选模型。请切换云端默认模型或改用本地转录。' : 'Cloud transcription failed: the selected model is not supported by this Azure resource.';
    if(lower.includes('diarization is currently not supported')) return lang === 'zh' ? '云端转录提交失败：当前 Azure 路线不支持说话人区分。请关闭说话人区分后重试。' : 'Cloud transcription failed: diarization is not supported by this route.';
    if(lower.includes('eof occurred in violation of protocol') || lower.includes('broken pipe')) return lang === 'zh' ? '云端上传中断：通常是网络或 Azure 边缘服务断开连接。请重试；如果文件很大，优先使用 Azure Batch 或减小音频体积。' : 'Cloud upload was interrupted. Retry, or reduce the audio size for very large files.';
    if(lower.includes('queued processing request failed')) return lang === 'zh' ? '后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务。' : 'The background task could not call the transcription endpoint. Retry or restart the backend.';
    if(lower.includes('no position encodings are defined')) return lang === 'zh' ? '本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。' : 'Local diarization cannot handle this audio length. Disable diarization or use cloud transcription.';
    if(lower.includes('downloaded video is too large') || lower.includes('file is too large')) return lang === 'zh' ? '文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。' : 'The file exceeds the current upload limit.';
    return raw;
};
	const fmtSttRelative = (factor, lang) => {
	    const n = Number(factor);
	    if(!Number.isFinite(n) || n <= 0) return '';
	    if(n * 100 < 1) return lang === 'zh' ? '低于原时长 1%' : '<1% of media duration';
	    const pct = Math.round(n * 100);
	    return lang === 'zh' ? `约为原时长 ${pct}%` : `${pct}% of media duration`;
	};
const sttStatusLabel = (status, t) => {
    const key = {
        starting: 'dash.sttStarting',
        loading_model: 'dash.sttLoadingModel',
        chunking_audio: 'dash.sttChunking',
        preparing_audio: 'dash.sttPreparingAudio',
        waiting_first_segment: 'dash.sttWaitingFirst',
        transcribing_chunks: 'dash.sttChunks',
        transcribing_segments: 'dash.sttSegments',
        azure_transcribing: 'dash.sttAzure',
        azure_batch_uploading: 'dash.sttAzureUpload',
        azure_batch_submitting: 'dash.sttAzureSubmit',
        azure_batch_waiting: 'dash.sttAzureWait',
        azure_batch_downloading: 'dash.sttAzureDownload',
    }[status || ''];
    return key ? t(key) : t('dash.waitingSegment');
};
const sttProgressFraction = (job) => Math.max(0, Math.min(1, Number(job?.sttProgress) || 0));
const isSttProgressUnmeasured = (job) => (
    job?.stage === 'stt'
    && sttProgressFraction(job) <= 0
    && job?.sttStatus !== 'transcribing_segments'
);
const jobProgressLabel = (job, t) => isSttProgressUnmeasured(job)
    ? t('dash.progressUnknown')
    : `${Math.round(Math.max(0, Math.min(100, Number(job?.progress) || 0)))}%`;

const timeAgo = (ts, t) => {
    const d = Date.now()-ts, m=Math.floor(d/60000), h=Math.floor(d/3600000), dy=Math.floor(d/86400000);
    if(m<1) return t('dash.justNow');
    if(m<60) return `${m} ${t('dash.mAgo')}`;
    if(h<24) return `${h} ${t('dash.hAgo')}`;
    return `${dy} ${t('dash.dAgo')}`;
};

const MD_TABLE_ALIGN_RE = /^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$/;

const splitMdTableRow = (line) => {
    let text = (line || '').trim();
    if(text.startsWith('|')) text = text.slice(1);
    if(text.endsWith('|')) text = text.slice(0, -1);
    return text.split('|').map(cell => cell.trim());
};

const isPipeTableRow = (line) => {
    const text = (line || '').trim();
    return text.startsWith('|') && text.endsWith('|') && splitMdTableRow(text).length >= 2;
};

const looksLikeMdTable = (lines, index) => {
    if(index + 1 >= lines.length) return false;
    const head = (lines[index] || '').trim();
    const align = (lines[index + 1] || '').trim();
    return head.includes('|') && align.includes('|') && MD_TABLE_ALIGN_RE.test(align);
};

const looksLikeLoosePipeTable = (lines, index) => {
    let rowCount = 0;
    let cols = -1;
    for(let i = index; i < lines.length; i += 1){
        const text = (lines[i] || '').trim();
        if(!text) break;
        if(!isPipeTableRow(text)) break;
        const cells = splitMdTableRow(text);
        if(cols === -1) cols = cells.length;
        if(cells.length !== cols) break;
        rowCount += 1;
    }
    return rowCount >= 2;
};

const renderTableHtml = (headerCells, bodyRows, renderInline) => {
    const columnCount = Math.max(
        headerCells?.length || 0,
        ...bodyRows.map(row => row.length),
        0
    );
    if(!columnCount) return '';
    const pad = (cells) => Array.from({length: columnCount}, (_, idx) => cells[idx] || '');
    const thead = headerCells && headerCells.length ? `<thead class="bg-slate-50">
        <tr>${pad(headerCells).map(cell => `<th class="px-3 py-2 text-left text-xs font-bold uppercase tracking-wide text-slate-500 border-b border-slate-200">${renderInline(cell)}</th>`).join('')}</tr>
    </thead>` : '';
    const tbody = `<tbody>
        ${bodyRows.map((row, rowIdx) => `<tr class="${rowIdx > 0 ? 'border-t border-slate-200' : ''}">
            ${pad(row).map((cell, cellIdx) => `<td class="px-3 py-2 align-top text-sm ${!headerCells && cellIdx === 0 ? 'font-semibold text-on-surface' : 'text-on-surface-variant'}">${renderInline(cell)}</td>`).join('')}
        </tr>`).join('')}
    </tbody>`;
    return `<div class="my-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table class="min-w-full border-collapse">${thead}${tbody}</table>
    </div>`;
};

const simpleMd = (md) => {
    if(!md) return '';
    const esc = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
    const renderInline = (s) => esc(s)
        .replace(/`([^`]+)`/g,'<code class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[0.92em]">$1</code>')
        .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');

    const lines = md.replace(/\r\n/g, '\n').split('\n');
    let html = '';
    let inUl = false;
    let inOl = false;

    const closeLists = () => {
        if(inUl){ html += '</ul>'; inUl = false; }
        if(inOl){ html += '</ol>'; inOl = false; }
    };

    let i = 0;
    while(i < lines.length){
        const raw = lines[i] || '';
        const line = raw.trimEnd();
        const trimmed = line.trim();

        if(!trimmed){
            closeLists();
            html += '<br/>';
            i += 1;
            continue;
        }

        if(trimmed.startsWith('```')){
            closeLists();
            const codeLines = [];
            i += 1;
            while(i < lines.length && !lines[i].trim().startsWith('```')){
                codeLines.push(lines[i]);
                i += 1;
            }
            if(i < lines.length) i += 1;
            html += `<pre class="my-4 overflow-x-auto rounded-lg bg-slate-100 px-4 py-3 text-sm leading-relaxed text-on-surface"><code>${esc(codeLines.join('\n'))}</code></pre>`;
            continue;
        }

        if(looksLikeMdTable(lines, i)){
            closeLists();
            const headerCells = splitMdTableRow(lines[i]);
            const bodyRows = [];
            i += 2;
            while(i < lines.length){
                const row = (lines[i] || '').trim();
                if(!row || !row.includes('|')) break;
                bodyRows.push(splitMdTableRow(row));
                i += 1;
            }
            html += renderTableHtml(headerCells, bodyRows, renderInline);
            continue;
        }

        if(looksLikeLoosePipeTable(lines, i)){
            closeLists();
            const bodyRows = [];
            while(i < lines.length){
                const row = (lines[i] || '').trim();
                if(!row || !isPipeTableRow(row)) break;
                bodyRows.push(splitMdTableRow(row));
                i += 1;
            }
            html += renderTableHtml(null, bodyRows, renderInline);
            continue;
        }

        if(/^#{1,6}\s+/.test(trimmed)){
            closeLists();
            const level = Math.min((trimmed.match(/^#+/) || ['#'])[0].length, 6);
            const content = trimmed.slice(level + 1);
            const tag = level <= 1 ? 'h2' : level === 2 ? 'h3' : level === 3 ? 'h4' : 'h5';
            const klass = level <= 1
                ? 'text-xl font-headline font-bold mt-6 mb-2'
                : level === 2
                    ? 'text-lg font-headline font-bold mt-5 mb-2'
                    : level === 3
                        ? 'text-base font-headline font-bold mt-4 mb-1'
                        : 'text-sm font-headline font-bold mt-3 mb-1';
            html += `<${tag} class="${klass}">${renderInline(content)}</${tag}>`;
            i += 1;
            continue;
        }

        if(/^[-*] /.test(trimmed)){
            if(inOl){ html += '</ol>'; inOl = false; }
            if(!inUl){ html += '<ul class="space-y-1 my-2">'; inUl = true; }
            html += `<li class="flex gap-2 text-sm text-on-surface"><span class="text-tertiary mt-0.5">•</span><span>${renderInline(trimmed.slice(2))}</span></li>`;
            i += 1;
            continue;
        }

        const ordered = trimmed.match(/^\d+[.）]\s+(.+)/);
        if(ordered){
            if(inUl){ html += '</ul>'; inUl = false; }
            if(!inOl){ html += '<ol class="list-decimal space-y-1 my-2 pl-5">'; inOl = true; }
            html += `<li class="text-sm text-on-surface">${renderInline(ordered[1])}</li>`;
            i += 1;
            continue;
        }

        if(trimmed.startsWith('> ')){
            closeLists();
            html += `<blockquote class="my-3 border-l-4 border-tertiary/40 bg-purple-50 px-4 py-2 text-sm leading-relaxed text-on-surface-variant">${renderInline(trimmed.slice(2))}</blockquote>`;
            i += 1;
            continue;
        }

        if(trimmed === '---' || trimmed === '***' || trimmed === '___'){
            closeLists();
            html += '<hr class="my-4 border-slate-200"/>';
            i += 1;
            continue;
        }

        closeLists();
        html += `<p class="text-sm text-on-surface-variant leading-relaxed mb-1">${renderInline(trimmed)}</p>`;
        i += 1;
    }

    closeLists();
    return html;
};

/* ═══════════════ download utils ═══════════════ */
const _dl = (blob, name) => { const u=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=u; a.download=name; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(u); };
const _baseName = (fn) => (fn||'FluentFlow').replace(/\.[^/.]+$/,'');

const _fmtSrtTime = (sec) => {
    const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=Math.floor(sec%60), ms=Math.round((sec%1)*1000);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')},${String(ms).padStart(3,'0')}`;
};
const _fmtVttTime = (sec) => {
    const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=Math.floor(sec%60), ms=Math.round((sec%1)*1000);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;
};

const dlTranscriptTxt = (text, filename) => {
    _dl(new Blob([text],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'.txt');
};
const dlTranscriptSrt = (segments, filename) => {
    const lines = segments.map((s,i) => `${i+1}\n${_fmtSrtTime(s.start)} --> ${_fmtSrtTime(s.end)}\n${s.text.trim()}\n`);
    _dl(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'.srt');
};
const dlTranscriptVtt = (segments, filename) => {
    const lines = ['WEBVTT\n', ...segments.map(s => `${_fmtVttTime(s.start)} --> ${_fmtVttTime(s.end)}\n${s.text.trim()}\n`)];
    _dl(new Blob([lines.join('\n')],{type:'text/vtt;charset=utf-8'}), _baseName(filename)+'.vtt');
};

const dlSummaryTxt = (md, filename) => {
    _dl(new Blob([md],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'_summary.txt');
};

const dlSummaryMd = (md, filename) => {
    _dl(new Blob([md],{type:'text/markdown;charset=utf-8'}), _baseName(filename)+'_summary.md');
};

const dlSummaryWord = (md, filename) => {
    const rendered = simpleMd(md);
    const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><style>body{font-family:'Microsoft YaHei','Segoe UI',sans-serif;font-size:12pt;line-height:1.8;color:#1a1a1a;max-width:700px;margin:0 auto;padding:40px}h2{font-size:18pt;margin-top:24pt}h3{font-size:15pt;margin-top:18pt}h4{font-size:13pt;margin-top:14pt}ul{margin-left:20pt}li{margin-bottom:4pt}strong{font-weight:bold}</style></head>
<body>${rendered}</body></html>`;
    _dl(new Blob([html],{type:'application/vnd.ms-word;charset=utf-8'}), _baseName(filename)+'_summary.doc');
};

const dlSummaryPdf = async (summaryElRef, filename) => {
    if(!window.html2pdf) throw new Error('html2pdf not loaded');
    const el = summaryElRef.current;
    if(!el) return;
    await html2pdf().set({
        margin: [12,12,12,12],
        filename: _baseName(filename)+'_summary.pdf',
        image: {type:'jpeg', quality:0.95},
        html2canvas: {scale:2, useCORS:true, scrollY:0, windowHeight:el.scrollHeight},
        jsPDF: {unit:'mm', format:'a4', orientation:'portrait'},
    }).from(el).save();
};

const dlSummaryImage = async (summaryElRef, filename) => {
    // Disabled by user request (remove PNG export feature).
    throw new Error('PNG export disabled');
    const el = summaryElRef.current;
    if(!el) return;

    // 稳定导出策略：
    // 1) 不直接克隆 summary 的外层 flex/scroll 容器（会导致高度计算异常）
    // 2) 改为用一个“纯 block 容器”渲染 summary 内部内容，再交给 html2canvas 截图
    const isDark = document.documentElement.classList.contains('dark');
    const bg = isDark ? '#0c0e11' : '#ffffff';
    const fg = isDark ? '#e2e2e6' : '#171c1f';

    const temp = document.createElement('div');
    temp.style.position = 'fixed';
    temp.style.left = '0';
    temp.style.top = '0';
    // 用很高的 zIndex，确保 html2canvas 能“看到”该节点
    temp.style.zIndex = '9999';
    // html2canvas 对 visibility:hidden 会直接跳过渲染，导致空 canvas
    temp.style.visibility = 'visible';
    temp.style.opacity = '0';
    temp.style.pointerEvents = 'none';
    temp.style.background = bg;
    temp.style.color = fg;
    temp.style.padding = '32px'; // 对应 p-8
    temp.style.boxSizing = 'border-box';
    temp.style.width = (el.getBoundingClientRect().width || 800) + 'px';
    temp.innerHTML = el.innerHTML;

    document.body.appendChild(temp);

    // 等待两帧，确保样式与布局完成
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    try {
        if(window.html2canvas){
            const canvas = await window.html2canvas(temp, {
                scale: 2,
                useCORS: true,
                backgroundColor: bg,
                scrollX: 0,
                scrollY: 0,
                windowWidth: temp.scrollWidth,
                windowHeight: temp.scrollHeight,
            });
            const canvasObj = canvas?.canvas || canvas;
            if(canvasObj){
                if(typeof canvasObj.toBlob === 'function'){
                    canvasObj.toBlob(blob => { if(blob) _dl(blob, _baseName(filename)+'_summary.png'); }, 'image/png');
                    return;
                }
                if(typeof canvasObj.toDataURL === 'function'){
                    const dataUrl = canvasObj.toDataURL('image/png');
                    const blob = await (await fetch(dataUrl)).blob();
                    _dl(blob, _baseName(filename)+'_summary.png');
                    return;
                }
            }
        }

        // Fallback：回退到 html2pdf -> toCanvas（仍使用 temp 容器）
        const canvasResult = await html2pdf()
            .set({
                html2canvas: {scale:2, useCORS:true, scrollY:0, backgroundColor: bg, windowHeight: temp.scrollHeight},
            })
            .from(temp)
            .toCanvas();
        const canvas = canvasResult?.canvas || canvasResult;
        if(!canvas) throw new Error('Image export failed: canvas is empty');

        if(typeof canvas.toBlob === 'function'){
            canvas.toBlob(blob => { if(blob) _dl(blob, _baseName(filename)+'_summary.png'); }, 'image/png');
            return;
        }
        if(typeof canvas.toDataURL === 'function'){
            const dataUrl = canvas.toDataURL('image/png');
            const blob = await (await fetch(dataUrl)).blob();
            _dl(blob, _baseName(filename)+'_summary.png');
            return;
        }
        throw new Error('Image export failed: canvas has no toBlob/toDataURL');
    } finally {
        document.body.removeChild(temp);
    }
};

const DropdownMenu = ({trigger, items, align='right'}) => {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        const handler = (e) => { if(ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);
    return (
        <div className="relative" ref={ref}>
            <div onClick={()=>setOpen(!open)}>{trigger}</div>
            {open && (
                <div className={`absolute top-full mt-1 ${align==='right'?'right-0':'left-0'} z-50 bg-white rounded-lg shadow-xl border border-slate-200 py-1 min-w-[180px] animate-[fadeIn_0.15s_ease-out]`}>
                    {items.map((it,i) => it.divider ? (
                        <div key={i} className="border-t border-slate-100 my-1"/>
                    ) : (
                        <button key={i} onClick={()=>{setOpen(false); it.onClick?.();}} disabled={it.disabled} className="w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 flex items-center gap-3 text-on-surface disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                            {it.icon && <span className="material-symbols-outlined text-base text-slate-400">{it.icon}</span>}
                            <span className="flex-1">{it.label}</span>
                            {it.badge && <span className="text-[10px] text-slate-400 font-medium">{it.badge}</span>}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

/* ═══════════════ hooks ═══════════════ */
const useApi = () => {
    const appendAiOptions = (fd, options={}) => {
        if(options.aiProvider) fd.append("ai_provider", options.aiProvider);
        if(options.aiModel) fd.append("ai_model", options.aiModel);
        if(options.systemPrompt) fd.append("system_prompt", options.systemPrompt);
        if(options.noteMode) fd.append("note_mode", options.noteMode);
    };
    const appendProcessOptions = (fd, options={}) => {
        if(options.exportToLark) {
            fd.append("export_to_lark","true");
            fd.append("lark_via_cli", options.larkViaCli ? "true" : "false");
        }
        if(options.title) fd.append("title", options.title);
        if(options.folderToken) fd.append("folder_token", options.folderToken); // kept for future use
        if(options.skipSummary) fd.append("skip_summary", "true");
        appendAiOptions(fd, options);
        if(options.sttProvider) fd.append("stt_provider", options.sttProvider);
        if(options.sttModel) fd.append("stt_model", options.sttModel);
        if(options.sttSpeed) fd.append("stt_speed", options.sttSpeed);
        if(options.sttLanguage) fd.append("stt_language", options.sttLanguage);
        if(options.speakerDiarization) fd.append("speaker_diarization", "true");
    };
    const readSseResult = async (r, onProgress) => {
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = '', result = null;
        while(true){
            const {value,done} = await reader.read();
            if(done) break;
            buf += decoder.decode(value,{stream:true});
            const parts = buf.split('\n\n');
            buf = parts.pop() || '';
            for(const part of parts){
                const dl = part.split('\n').find(l=>l.startsWith('data: '));
                if(!dl) continue;
                try{
                    const data = JSON.parse(dl.slice(6));
                    if(data.stage==='done'){ result=data.result; onProgress?.({stage:'done',progress:100,result:data.result}); }
                    else if(data.stage==='transcript_ready'){ onProgress?.({stage:'transcript_ready',progress:data.progress||60,result:data.result}); }
                    else if(data.stage==='error'){ throw new Error(data.error||'Processing failed'); }
                    else { onProgress?.(data); }
                }catch(pe){ if(pe.message && !pe.message.startsWith('Unexpected')) throw pe; }
            }
        }
        if(!result) throw new Error('No result received from server');
        return result;
    };
    const processVideoSSE = async (file, options={}, onProgress, signal) => {
        const fd = new FormData();
        fd.append("file", file);
        if(options.taskId) fd.append("task_id", options.taskId);
        if(options.sourceLastModifiedMs) fd.append("source_last_modified_ms", String(options.sourceLastModifiedMs));
        appendProcessOptions(fd, options);
        const r = await apiFetch(`${API_BASE}/process`,{method:"POST",body:fd,signal});
        if(!r.ok){ const e = await r.json().catch(()=>({})); throw new Error(e.detail||`HTTP ${r.status}`); }
        return await readSseResult(r, onProgress);
    };
    const enqueueProcessFiles = async (files, options={}, signal) => {
        const fd = new FormData();
        Array.from(files || []).forEach((file) => fd.append("files", file));
        appendProcessOptions(fd, options);
        const r = await apiFetch(`${API_BASE}/queue/process`, {method:"POST", body:fd, signal});
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
    };
    const createVideoSourceJob = async (input, options={}, signal) => {
        const payloadOptions = {};
        if(options.exportToLark) {
            payloadOptions.export_to_lark = "true";
            payloadOptions.lark_via_cli = options.larkViaCli ? "true" : "false";
        }
        if(options.title) payloadOptions.title = options.title;
        if(options.skipSummary) payloadOptions.skip_summary = "true";
        if(options.aiProvider) payloadOptions.ai_provider = options.aiProvider;
        if(options.aiModel) payloadOptions.ai_model = options.aiModel;
        if(options.systemPrompt) payloadOptions.system_prompt = options.systemPrompt;
        if(options.noteMode) payloadOptions.note_mode = options.noteMode;
        if(options.sttProvider) payloadOptions.stt_provider = options.sttProvider;
        if(options.sttModel) payloadOptions.stt_model = options.sttModel;
        if(options.sttSpeed) payloadOptions.stt_speed = options.sttSpeed;
        if(options.sttLanguage) payloadOptions.stt_language = options.sttLanguage;
        if(options.speakerDiarization) payloadOptions.speaker_diarization = "true";
        const r = await apiFetch(`${API_BASE}/video-sources/jobs`, {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({input, options: payloadOptions}),
            signal,
        });
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
    };
    const subscribeJobEvents = async (taskId, onProgress, signal) => {
        const r = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}/events`, {signal});
        if(!r.ok){ const e = await r.json().catch(()=>({})); throw new Error(e.detail||`HTTP ${r.status}`); }
        return await readSseResult(r, onProgress);
    };
    const summarizeTranscriptFile = async (file, options={}, signal) => {
        const fd = new FormData();
        fd.append("file", file);
        if(options.taskId) fd.append("task_id", options.taskId);
        if(options.skipSummary) fd.append("skip_summary", "true");
        appendAiOptions(fd, options);
        const r = await apiFetch(`${API_BASE}/summarize-transcript-file`, {method:"POST", body:fd, signal});
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
    };
    const recordEvent = async (payload) => {
        try {
            await apiFetch(`${API_BASE}/events`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload || {}),
            });
        } catch(_) {}
    };
    const getJob = async (taskId) => {
        const r = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}`);
        if(!r.ok) throw new Error('Job not found');
        return await r.json();
    };
    const fetchJobSourceFile = async (taskId, filename='source') => {
        const r = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}/source`);
        if(!r.ok) throw new Error('Source file not found');
        const blob = await r.blob();
        return new File([blob], filename || 'source', {type: blob.type || 'application/octet-stream'});
    };
    const getJobs = async (limit=100) => {
        const r = await apiFetch(`${API_BASE}/jobs?limit=${encodeURIComponent(limit)}`);
        if(!r.ok) throw new Error('Jobs unavailable');
        const data = await r.json();
        return Array.isArray(data?.jobs) ? data.jobs : [];
    };
    const downloadJobArtifact = async (taskId, kind, filename) => {
        const r = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}/artifacts/${encodeURIComponent(kind)}`);
        if(!r.ok) throw new Error('Artifact not found');
        const blob = await r.blob();
        _dl(blob, filename || `${kind}.txt`);
    };
    const saveTranscriptEdit = async (taskId, payload={}) => {
        const r = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}/transcript`, {
            method: "PATCH",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify(payload),
        });
        const data = await r.json().catch(()=>({}));
        if(!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
        return data;
    };
    const getCredentialsStatus = async () => {
        const r = await apiFetch(`${API_BASE}/credentials/status`);
        if(!r.ok) throw new Error('Credential status unavailable');
        return await r.json();
    };
    const getSpeakerDiarizationStatus = async () => {
        const r = await apiFetch(`${API_BASE}/speaker-diarization/status`);
        if(!r.ok) throw new Error('Speaker diarization status unavailable');
        return await r.json();
    };
    const saveCredentials = async (payload) => {
        const r = await apiFetch(`${API_BASE}/credentials`, {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify(payload || {}),
        });
        if(!r.ok) throw new Error('Credential save failed');
        return await r.json();
    };
    const checkHealth = async () => { try{ const r = await apiFetch(`${API_BASE}/health`); return r.ok ? await r.json() : false;}catch(_){return false;} };
    return {processVideoSSE, enqueueProcessFiles, createVideoSourceJob, subscribeJobEvents, summarizeTranscriptFile, recordEvent, getJob, getJobs, fetchJobSourceFile, downloadJobArtifact, saveTranscriptEdit, getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus, checkHealth};
};

const useSettings = () => {
    const loadSettings = () => {
        try{
            const raw = JSON.parse(localStorage.getItem("fluentflow_settings")||"{}");
            const clean = sanitizeSettings(raw);
            if (JSON.stringify(raw) !== JSON.stringify(clean)) {
                localStorage.setItem("fluentflow_settings", JSON.stringify(clean));
            }
            return clean;
        } catch(_){return {};}
    };
    const saveSettings = (s) => localStorage.setItem("fluentflow_settings", JSON.stringify(sanitizeSettings(s)));
    return {loadSettings, saveSettings};
};

/* ═══════════════ shared components ═══════════════ */
const SideNav = () => {
    const {t, lang, toggleLang} = useI18n();
    const {authMode, user, logout} = useAuth();
    const loc = useLocation();
    const items = [
        {path:'/',icon:'dashboard',k:'nav.dashboard'},
        {path:'/tasks',icon:'monitoring',k:'nav.tasks'},
        {path:'/processing',icon:'tune',k:'nav.processing'},
        {path:'/editor',icon:'subject',k:'nav.editor'},
        {path:'/settings',icon:'settings',k:'nav.settings'},
    ];
            return (
                <aside className="h-screen w-64 fixed left-0 top-0 flex flex-col bg-slate-50 border-r border-slate-200 z-50">
                    <div className="flex flex-col h-full p-4">
                        <div className="flex items-center gap-3 px-4 py-6 mb-8">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary-container flex items-center justify-center text-white shadow-lg">
                        <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>auto_videocam</span>
                            </div>
                            <div>
                                <h1 className="text-xl font-bold text-slate-900 leading-tight font-headline">FluentFlow</h1>
                        <p className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">{t('nav.subtitle')}</p>
                            </div>
                        </div>
                        <nav className="flex-1 space-y-1">
                    {items.map(it => {
                        const active = loc.pathname===it.path;
                        return <Link key={it.path} to={it.path} className={`px-4 py-3 rounded-lg flex items-center gap-3 transition-colors text-sm tracking-tight ${active?'bg-blue-50 text-blue-700 font-semibold':'text-slate-500 hover:text-slate-900 hover:bg-slate-200/50'}`}>
                            <span className="material-symbols-outlined">{it.icon}</span><span>{t(it.k)}</span>
                        </Link>;
                            })}
                        </nav>
                        <div className="mt-auto border-t border-slate-200/60 px-2 pt-3">
                    {authMode === 'accounts' && user && (
                        <div className="mb-3 rounded-lg bg-white/70 px-3 py-3 shadow-sm ring-1 ring-slate-200/70">
                            <p className="truncate text-[11px] font-bold uppercase tracking-wider text-slate-400">
                                {lang==='zh'?'当前账号':'Account'}
                            </p>
                            <p className="mt-1 truncate text-sm font-semibold text-slate-800" title={user.email || ''}>
                                {user.email}
                            </p>
                            <button
                                type="button"
                                onClick={logout}
                                className="mt-2 inline-flex items-center gap-1.5 rounded-md px-0 text-xs font-semibold text-slate-500 transition hover:text-red-600"
                            >
                                <span className="material-symbols-outlined text-[16px]">logout</span>
                                {lang==='zh'?'退出登录':'Sign out'}
                            </button>
                        </div>
                    )}
                    <button
                        onClick={toggleLang}
                        className="group flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[13px] font-semibold text-slate-500 transition-colors hover:bg-slate-200/60 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                        aria-label={lang==='zh'?'切换界面语言':'Switch interface language'}
                    >
                        <span className="material-symbols-outlined text-[20px] leading-none text-slate-400 group-hover:text-slate-700">translate</span>
                        <span className="min-w-0 flex-1 truncate text-left">{lang==='zh'?'界面语言':'Language'}</span>
                        <span className="min-w-8 rounded-md bg-blue-50 px-2 py-1 text-center text-[11px] font-bold leading-none text-primary">
                            {lang==='en'?'中文':'EN'}
                        </span>
                    </button>
                        </div>
                    </div>
                </aside>
            );
        };

/* ═══════════════ Dashboard ═══════════════ */
const Dashboard = () => {
    const {t, lang} = useI18n();
    const {history, addToHistory, currentJob, setCurrentJob, setLastResult, setLastSourceFile, stats, addLarkExport, runtimeConfig} = useApp();
            const [uploadError, setUploadError] = useState(null);
            const [processingResult, setProcessingResult] = useState(null);
            const fileInputRef = useRef(null);
            const subtitleInputRef = useRef(null);
    const {processVideoSSE, enqueueProcessFiles, createVideoSourceJob, subscribeJobEvents, summarizeTranscriptFile, recordEvent, checkHealth, getJob, getCredentialsStatus} = useApi();
    const {loadSettings} = useSettings();
            const navigate = useNavigate();
    const abortRef = useRef(null);
    const currentTaskRef = useRef(null);
    const settledJobRef = useRef(new Set());
    const [now, setNow] = useState(Date.now());
    const [videoLinkInput, setVideoLinkInput] = useState('');
    const [videoLinkSubmitting, setVideoLinkSubmitting] = useState(false);

    useEffect(() => { checkHealth(); }, []);
    useEffect(() => {
        if(!currentJob || currentJob.stage === 'done') return;
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [currentJob?.taskId, currentJob?.stage]);

    const handleCancel = () => {
        const task = currentTaskRef.current;
        if(task){
            recordEvent({
                event_name: "task_cancelled",
                task_id: task.taskId,
                source_type: task.sourceType,
                source_filename: task.fileName,
                source_file_size_mb: task.fileSizeMb,
                stage: currentJob?.stage || "cancelled",
                success: false,
                metadata: {trigger: "user_cancel"},
            });
        }
        if(abortRef.current){ abortRef.current.abort(); abortRef.current=null; }
        currentTaskRef.current = null;
        setCurrentJob(null);
    };

    const buildAiOptions = (settings) => ({
        aiProvider: settings.aiProvider||'deepseek',
        aiModel: settings.aiModel||null,
        systemPrompt: resolveSystemPromptFromSettings(settings)||null,
        noteMode: settings.noteMode||'auto',
        speakerDiarization: !!settings.speakerDiarization,
        sttProvider: effectiveSttProvider(settings, runtimeConfig),
    });

    const openHistoryEntry = async (h) => {
        if(!h.taskId) {
            if(h.status==='completed'){ setLastResult(historyEntryToResult(h)); navigate('/editor'); }
            return;
        }
        try {
            const job = await getJob(h.taskId);
            if(job?.result) {
                setLastResult(job.result);
                navigate('/editor');
                return;
            }
        } catch(_) {}
        if(h.status==='completed'){ setLastResult(historyEntryToResult(h)); navigate('/editor'); }
    };

    const settleCompletedJob = (job, fallbackJob = currentJob) => {
        const result = job?.result;
        const taskId = job?.task_id || result?.task_id || fallbackJob?.taskId;
        if(!result || !taskId) return false;
        if(settledJobRef.current.has(taskId)) return true;
        settledJobRef.current.add(taskId);
        if(abortRef.current){
            abortRef.current.abort();
            abortRef.current = null;
        }
        currentTaskRef.current = null;
        const fileName = result.filename || job?.source_filename || fallbackJob?.fileName;
        setCurrentJob({taskId, fileName, stage:'done', progress:100});
        setLastResult(result);
        setProcessingResult(result);
        const larkUrl = result.lark_response?.url || null;
        addToHistory(resultToHistoryEntry(result, {taskId, name:fileName}));
        if(larkUrl) addLarkExport({url:larkUrl, title: result.lark_doc_title || fileNameStem(fileName), timestamp:Date.now()});
        setTimeout(() => {
            setCurrentJob((prev) => prev?.taskId === taskId ? null : prev);
        }, 3000);
        return true;
    };

    const applyProgressEvent = (ev) => {
        setCurrentJob(prev => prev ? {
            ...prev,
            stage:ev.stage,
            progress:ev.progress,
            sttProgress: ev.stt_progress ?? prev.sttProgress,
            transcribedSeconds: ev.transcribed_seconds ?? prev.transcribedSeconds,
            durationSeconds: ev.duration_seconds ?? prev.durationSeconds,
            sttElapsedSeconds: ev.stt_elapsed_seconds ?? prev.sttElapsedSeconds,
            sttStatus: ev.stt_status ?? prev.sttStatus,
            sttProvider: ev.stt_provider ?? prev.sttProvider,
            azureBatchAudioSizeMb: ev.azure_batch_audio_size_mb ?? prev.azureBatchAudioSizeMb,
        } : null);
        if(ev.stage === 'transcript_ready' && ev.result) {
            setLastResult(ev.result);
            setProcessingResult(ev.result);
        }
    };

    useEffect(() => {
        if(!currentJob?.taskId || currentJob.stage === 'done') return;
        let stale = false;
        const syncCurrentJob = async () => {
            try {
                const job = await getJob(currentJob.taskId);
                if(stale) return;
                if(job?.status === 'completed' && job.result) {
                    settleCompletedJob(job, currentJob);
                    return;
                }
                if(job?.status === 'failed') {
                    if(abortRef.current){
                        abortRef.current.abort();
                        abortRef.current = null;
                    }
                    currentTaskRef.current = null;
                    setUploadError(job.error_reason || 'Task failed.');
                    addToHistory({
                        id: Date.now(),
                        taskId: job.task_id || currentJob.taskId,
                        name: job.source_filename || currentJob.fileName,
                        timestamp: Date.now(),
                        durationMin: 0,
                        status: 'failed',
                    });
                    setCurrentJob(null);
                }
            } catch(_) {}
        };
        syncCurrentJob();
        const timer = setInterval(syncCurrentJob, 5000);
        return () => {
            stale = true;
            clearInterval(timer);
        };
    }, [currentJob?.taskId, currentJob?.stage]);

    useEffect(() => {
        if(!currentJob?.resume || !currentJob.taskId || currentJob.stage === 'done' || abortRef.current) return;
        const ac = new AbortController();
        abortRef.current = ac;
        currentTaskRef.current = {
            taskId: currentJob.taskId,
            fileName: currentJob.fileName,
            sourceType: currentJob.sourceType,
            fileSizeMb: currentJob.fileSizeMb,
        };
        let stale = false;
        subscribeJobEvents(currentJob.taskId, applyProgressEvent, ac.signal).then((result) => {
            if(stale) return;
            settleCompletedJob({task_id: currentJob.taskId, source_filename: currentJob.fileName, result}, currentJob);
        }).catch((err) => {
            if(!stale && err.name !== 'AbortError') setUploadError(err.message || 'Failed to resume task.');
        }).finally(() => {
            if(abortRef.current === ac) abortRef.current = null;
        });
        return () => {
            stale = true;
            ac.abort();
            if(abortRef.current === ac) abortRef.current = null;
        };
    }, [currentJob?.taskId, currentJob?.resume]);

    const mediaExts = /\.(mp4|mov|avi|mkv|wmv|flv|webm|m4v|mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;
    const transcriptExts = /\.(srt|vtt|txt|md)$/i;
    const audioExts = /\.(mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;

    const ensureCloudReady = async (sttProvider) => {
        if (!isAzureCloudProvider(sttProvider)) return true;
        try {
            const status = await getCredentialsStatus();
            const configured = sttProvider === 'azure_batch'
                ? isAzureBatchConfigured(status)
                : isAzureSpeechConfigured(status);
            if (configured) return true;
        } catch (_) {}
        setUploadError(azureSpeechMissingMessage(lang));
        return false;
    };

    const startMediaFiles = async (files) => {
        const selectedFiles = Array.from(files || []);
        if(selectedFiles.length === 0) return;
        if(!selectedFiles.every((file) => mediaExts.test(file.name))){
            setUploadError(t('dash.fileError')); return;
        }
                setUploadError(null);
                setProcessingResult(null);
                setLastResult(null);

        const settings = loadSettings();
        const sttModel = normalizeSttModel(settings.sttModel);
        const sttProvider = effectiveSttProvider(settings, runtimeConfig);
        if (!(await ensureCloudReady(sttProvider))) return;

        if(selectedFiles.length > 1) {
            setLastSourceFile(null);
            try {
                await enqueueProcessFiles(selectedFiles, {
                    exportToLark: settings.exportToLark||false,
                    larkViaCli: !!settings.larkViaCli,
                    ...buildAiOptions(settings),
                    skipSummary: !!settings.skipAiSummary,
                    sttProvider,
                    sttModel,
                    sttSpeed: settings.sttSpeed||'balanced',
                    sttLanguage: settings.sttLanguage||'auto',
                });
                setCurrentJob(null);
                navigate('/tasks');
            } catch(err) {
                setUploadError(err.message || "Queue failed.");
            }
            return;
        }

        const file = selectedFiles[0];
                setLastSourceFile(file);

        const ac = new AbortController();
        const taskId = createTaskId();
        const sourceType = audioExts.test(file.name) ? "audio" : "video";
        const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
        abortRef.current = ac;
        currentTaskRef.current = {
            taskId,
            fileName: file.name,
            sourceType,
            fileSizeMb,
        };
        setCurrentJob({
            taskId,
            fileName:file.name,
            stage:'upload',
            progress:2,
            startedAt: Date.now(),
            sourceType,
            fileSizeMb,
            sttProvider,
            sttModel,
            sttSpeed: settings.sttSpeed||'balanced',
            sttLanguage: settings.sttLanguage||'auto',
            skipSummary: !!settings.skipAiSummary,
            exportToLark: !!settings.exportToLark,
            noteMode: settings.noteMode||'auto',
        });

                try {
            let openedTranscript = false;
            const result = await processVideoSSE(file, {
                taskId,
                sourceLastModifiedMs: file.lastModified||null,
                exportToLark: settings.exportToLark||false,
                larkViaCli: !!settings.larkViaCli,
                title: file.name.replace(/\.[^/.]+$/,""),
                ...buildAiOptions(settings),
	                skipSummary: !!settings.skipAiSummary,
	                sttProvider,
	                sttModel,
	                sttSpeed: settings.sttSpeed||'balanced',
	                sttLanguage: settings.sttLanguage||'auto',
            }, (ev) => {
                applyProgressEvent(ev);
                if(ev.stage === 'transcript_ready' && ev.result && !openedTranscript) {
                    openedTranscript = true;
                    setLastResult(ev.result);
                    setProcessingResult(ev.result);
                    navigate('/editor');
                }
            }, ac.signal);

            abortRef.current = null;
            currentTaskRef.current = null;
            setCurrentJob({fileName:file.name, stage:'done', progress:100});
            setLastResult(result);
                    setProcessingResult(result);

            const larkUrl = result.lark_response?.url || null;
            addToHistory(resultToHistoryEntry(result, {taskId, name:file.name, requestedNoteMode: settings.noteMode||'auto'}));
            if(larkUrl) addLarkExport({url:larkUrl, title: result.lark_doc_title || fileNameStem(file.name), timestamp:Date.now()});
            setTimeout(() => setCurrentJob(null), 3000);
        } catch(err) {
            abortRef.current = null;
            currentTaskRef.current = null;
            setCurrentJob(null);
            if(err.name !== 'AbortError'){
                setUploadError(err.message || "Processing failed.");
                addToHistory({id:Date.now(), taskId, name:file.name, timestamp:Date.now(), durationMin:0, status:'failed'});
            }
                }
            };

            const handleVideoLinkSubmit = async () => {
                const input = videoLinkInput.trim();
                if(!input){
                    setUploadError(t('dash.linkEmpty'));
                    return;
                }
                setUploadError(null);
                setProcessingResult(null);
                setLastResult(null);
                setLastSourceFile(null);
                const settings = loadSettings();
                const sttModel = normalizeSttModel(settings.sttModel);
                const sttProvider = effectiveSttProvider(settings, runtimeConfig);
                if (!(await ensureCloudReady(sttProvider))) return;
                setVideoLinkSubmitting(true);
                try {
                    await createVideoSourceJob(input, {
                        exportToLark: settings.exportToLark||false,
                        larkViaCli: !!settings.larkViaCli,
                        ...buildAiOptions(settings),
                        skipSummary: !!settings.skipAiSummary,
                        sttProvider,
                        sttModel,
                        sttSpeed: settings.sttSpeed||'balanced',
                        sttLanguage: settings.sttLanguage||'auto',
                    });
                    setVideoLinkInput('');
                    setCurrentJob(null);
                    navigate('/tasks');
                } catch(err) {
                    setUploadError(err.message || "Video link fetch failed.");
                } finally {
                    setVideoLinkSubmitting(false);
                }
            };

            const handleFileSelect = async (e) => {
                const files = Array.from(e.target.files || []);
                if(fileInputRef.current) fileInputRef.current.value = '';
                await startMediaFiles(files);
            };

            const handleSubtitleSelect = async (e) => {
                const file = e.target.files?.[0];
                if(!file) return;
                if(subtitleInputRef.current) subtitleInputRef.current.value = '';
                if(!transcriptExts.test(file.name)){
                    setUploadError(t('dash.subtitleFileError')); return;
                }
                setUploadError(null);
                setProcessingResult(null);
                setLastResult(null);
                setLastSourceFile(null);

                const ac = new AbortController();
                const taskId = createTaskId();
                const settings = loadSettings();
                const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
                abortRef.current = ac;
                currentTaskRef.current = {
                    taskId,
                    fileName: file.name,
                    sourceType: "transcript_file",
                    fileSizeMb,
                };
                setCurrentJob({
                    taskId,
                    fileName:file.name,
                    stage:'summary',
                    progress:20,
                    startedAt: Date.now(),
                    sourceType: "transcript_file",
                    fileSizeMb,
	                    skipSummary: !!settings.skipAiSummary,
	                    exportToLark: false,
	                    noteMode: settings.noteMode||'auto',
	                });
                try {
                    const result = await summarizeTranscriptFile(file, {taskId, ...buildAiOptions(settings), skipSummary: !!settings.skipAiSummary}, ac.signal);
                    abortRef.current = null;
                    currentTaskRef.current = null;
                    setCurrentJob({fileName:file.name, stage:'done', progress:100});
                    setLastResult(result);
                    setProcessingResult(result);
                    addToHistory(resultToHistoryEntry(result, {taskId, name:file.name, requestedNoteMode: settings.noteMode||'auto', source:'transcript_file'}));
                    navigate('/editor');
                    setTimeout(() => setCurrentJob(null), 3000);
                } catch(err) {
                    abortRef.current = null;
                    currentTaskRef.current = null;
                    setCurrentJob(null);
                    if(err.name !== 'AbortError'){
                        setUploadError(err.message || "Summary generation failed.");
                        addToHistory({id:Date.now(), taskId, name:file.name, timestamp:Date.now(), durationMin:0, status:'failed'});
                    }
                }
            };

            const handleDrop = (e) => {
                e.preventDefault();
                const files = Array.from(e.dataTransfer.files || []);
                if(files.length === 0) return;
                const file = files[0];
        if(files.length === 1 && file && transcriptExts.test(file.name) && subtitleInputRef.current){
            const dt = new DataTransfer(); dt.items.add(file);
            subtitleInputRef.current.files = dt.files;
            handleSubtitleSelect({target:subtitleInputRef.current});
        } else {
            startMediaFiles(files);
        }
    };

    const uploading = !!currentJob && currentJob.stage !== 'done';
    const elapsedSec = uploading ? Math.max(0, Math.floor((now - (currentJob.startedAt||now)) / 1000)) : 0;
    const activeProgress = Math.max(0, Math.min(100, Number(currentJob?.progress)||0));
    const activeStageLabel = currentJob ? (t(`status.${currentJob.stage}`)||t('dash.uploading')) : '';
    const jobStages = currentJob?.sourceType === 'transcript_file'
        ? [{key:'summary', label:'proc.aiSumm'}, {key:'export', label:'proc.larkExport'}]
        : [{key:'audio', label:'proc.audioExtract'}, {key:'stt', label:'proc.transcription'}, {key:'summary', label:'proc.aiSumm'}, {key:'export', label:'proc.larkExport'}];
    const stageRank = {upload:0, audio:1, stt:2, transcript_ready:3, summary:3, export:4, done:5};
    const currentRank = stageRank[currentJob?.stage] ?? 0;
    const sttProfile = currentJob?.sourceType === 'transcript_file'
        ? '-'
        : [
            isAzureCloudProvider(currentJob?.sttProvider) ? 'Azure' : 'local',
            currentJob?.sttModel||DEFAULT_STT_MODEL,
            currentJob?.sttSpeed||'balanced',
            currentJob?.sttLanguage||'auto',
        ].join(' / ');
    const sttProgressPct = Math.round(sttProgressFraction(currentJob) * 100);
    const sttProgressUnknown = isSttProgressUnmeasured(currentJob);
    const hasSttTiming = currentJob?.stage === 'stt' && currentJob?.durationSeconds > 0 && !sttProgressUnknown;
    const sttElapsedForHint = Math.max(elapsedSec, Number(currentJob?.sttElapsedSeconds) || 0);
    const sttWaitedLong = sttProgressUnknown && !isAzureCloudProvider(currentJob?.sttProvider) && sttElapsedForHint >= 60;
    const selectedSttProvider = currentJob?.sttProvider || effectiveSttProvider(loadSettings(), runtimeConfig);
    const taskInfoCards = [
        {label:t('dash.elapsed'), value:fmtElapsed(elapsedSec)},
        {label:t('dash.fileSize'), value:fmtFileSize(currentJob?.fileSizeMb)},
        ...(isAzureCloudProvider(currentJob?.sttProvider) && currentJob?.azureBatchAudioSizeMb != null
            ? [{label:t('dash.azureUploadAudio'), value:fmtFileSize(currentJob.azureBatchAudioSizeMb)}]
            : []),
        {label:t('dash.modelProfile'), value:sttProfile},
        {label:t('dash.summaryMode'), value:currentJob?.skipSummary?t('dash.summaryOff'):`${t('dash.summaryOn')} / ${noteModeLabel(currentJob?.noteMode, lang)}`},
    ];

            return (
            <div className="ml-64 min-h-screen relative pb-8">
                <section className="p-12 max-w-7xl mx-auto space-y-12 h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
                        <div>
                    <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface mb-2">{t('dash.welcome')}</h2>
                    <p className="text-on-surface-variant font-body">{t('dash.subtitle')}</p>
                        </div>
                        <div className="flex gap-4">
	                    <div className="bg-surface-container-lowest editorial-shadow p-6 rounded-sm flex items-center gap-4 min-w-[220px] border border-outline-variant/20 dark:border-white/5">
	                                <div className="w-12 h-12 rounded-sm bg-primary/10 flex items-center justify-center text-primary dark:bg-blue-400/10 dark:text-blue-300">
	                            <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>timer</span>
	                                </div>
                                <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-outline">{t('dash.totalMin')}</p>
                            <p className="text-2xl font-headline font-bold text-on-surface">{stats.totalMinutes.toLocaleString()} {t('dash.minUnit')}</p>
                                </div>
                            </div>
	                    <div className="bg-surface-container-lowest editorial-shadow p-6 rounded-sm flex items-center gap-4 min-w-[220px] border border-outline-variant/20 dark:border-white/5">
	                                <div className="w-12 h-12 rounded-sm bg-tertiary/10 flex items-center justify-center text-tertiary dark:bg-blue-400/10 dark:text-blue-300">
	                            <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>description</span>
	                                </div>
                                <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-outline">{t('dash.noteGen')}</p>
                            <p className="text-2xl font-headline font-bold text-on-surface">{stats.notesGenerated} {t('dash.docUnit')}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-6">
                        <form
                            onSubmit={(e)=>{e.preventDefault(); handleVideoLinkSubmit();}}
                            className="flex items-stretch gap-2"
                        >
                            <input
                                type="text"
                                value={videoLinkInput}
                                onChange={(e)=>setVideoLinkInput(e.target.value)}
                                disabled={videoLinkSubmitting}
                                className="h-12 min-w-0 flex-1 appearance-none rounded-sm border border-outline-variant/35 bg-surface-container-lowest/70 px-4 text-sm font-semibold text-on-surface shadow-none outline-none ring-0 placeholder:text-on-surface-variant/60 transition-colors focus:border-primary/45 focus:bg-surface-container-lowest focus:outline-none focus:ring-0 disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.035] dark:placeholder:text-slate-500 dark:focus:border-blue-300/40"
                                placeholder={t('dash.linkPlaceholder')}
                                aria-label={t('dash.linkPlaceholder')}
                            />
                            <button
                                type="submit"
                                disabled={videoLinkSubmitting}
                                className="flex h-12 flex-shrink-0 items-center justify-center gap-2 rounded-sm border border-primary/20 bg-primary/10 px-5 text-sm font-extrabold text-primary transition-colors duration-200 hover:bg-primary/15 active:translate-y-px disabled:opacity-50 dark:border-blue-300/20 dark:bg-blue-400/10 dark:text-blue-200 dark:hover:bg-blue-400/15"
                            >
                                <span className={`material-symbols-outlined text-[18px] ${videoLinkSubmitting ? 'animate-spin' : ''}`}>{videoLinkSubmitting ? 'sync' : 'arrow_forward'}</span>
                                {videoLinkSubmitting ? t('dash.linkSubmitting') : t('dash.linkSubmit')}
                            </button>
                        </form>

                    <div className="grid grid-cols-12 gap-8">
                        <div className="col-span-12 lg:col-span-9 group">
                    <div className={`relative h-[480px] rounded-sm overflow-hidden bg-slate-900 shadow-2xl transition-transform duration-500 ${uploading?'':'hover:scale-[1.01]'}`} onDrop={handleDrop} onDragOver={e=>e.preventDefault()}>
                                <div className="absolute inset-0 opacity-40" aria-hidden="true">
                            <div className="w-full h-full bg-gradient-to-br from-slate-800 via-indigo-950/90 to-blue-900/70" style={{backgroundImage:'linear-gradient(135deg,#1e293b 0%,#312e81 35%,#1e3a5f 70%,#0f172a 100%)'}} />
                                </div>
                                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent"></div>
	                                <div className="relative h-full flex flex-col justify-end items-center p-10 space-y-6">
	                                    {!uploading && (
	                                    <div className="w-full max-w-[720px] mx-auto">
                                <span className="bg-white/[0.08] text-blue-100 border border-white/[0.12] px-3 py-1 rounded-sm text-[10px] font-bold tracking-widest uppercase mb-4 inline-block">{t('dash.proTag')}</span>
                                <h3 className="font-headline text-3xl font-bold text-white leading-tight">{t('dash.heroTitle')}</h3>
                                <p className="text-slate-300 mt-4 text-sm leading-relaxed">{t('dash.heroDesc')}</p>
                                    </div>
                                    )}
                                    {uploading && currentJob && (
                                    <div className="w-full max-w-[760px] mx-auto space-y-6">
                                        <div className="flex items-start justify-between gap-6">
                                            <div className="min-w-0">
                                                <span className="bg-blue-400/15 text-blue-100 border border-blue-300/30 px-3 py-1 rounded-sm text-[10px] font-bold tracking-widest uppercase mb-4 inline-block">{t('dash.activeTask')}</span>
                                                <h3 className="font-headline text-3xl font-bold text-white leading-tight truncate">{currentJob.fileName}</h3>
                                                <p className="text-slate-300 mt-3 text-sm">{t('dash.waitingForTranscript')}</p>
                                            </div>
                                            <button onClick={handleCancel} className="text-red-300 hover:text-white border border-red-300/40 hover:bg-red-500/20 px-3 py-2 rounded-sm text-xs font-bold flex items-center gap-2 flex-shrink-0 transition-colors">
                                                <span className="material-symbols-outlined text-sm">cancel</span>{t('dash.cancel')}
                                            </button>
                                        </div>
                                        <div>
                                            <div className="flex items-end justify-between gap-4 mb-2">
                                                <div>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{t('dash.currentStage')}</p>
                                                    <p className="text-lg font-bold text-white">{activeStageLabel}</p>
                                                </div>
                                                <p className="font-headline text-3xl font-extrabold text-white">{jobProgressLabel(currentJob, t)}</p>
                                            </div>
                                            <div className={`w-full h-3 bg-slate-700/80 rounded-full overflow-hidden ${sttProgressUnknown ? 'progress-indeterminate' : ''}`}>
                                                {!sttProgressUnknown && <div className="h-full bg-gradient-to-r from-blue-400 to-cyan-300 transition-all duration-700" style={{width:`${activeProgress}%`}}></div>}
                                            </div>
                                            {currentJob.stage === 'stt' && (
                                                <div className="flex flex-wrap items-center justify-between gap-2 mt-3 text-xs text-slate-300">
	                                                    <span>
	                                                        {hasSttTiming
	                                                            ? `${t('dash.transcribedTo')}: ${fmtElapsed(currentJob.transcribedSeconds||0)} / ${fmtElapsed(currentJob.durationSeconds||0)}`
	                                                            : sttStatusLabel(currentJob.sttStatus, t)}
	                                                    </span>
	                                                    <span className="font-bold text-cyan-200">{sttProgressUnknown ? t('dash.sttMeasuring') : `STT ${sttProgressPct}%`}</span>
	                                                    {sttWaitedLong && (
	                                                        <span className="basis-full text-[11px] text-amber-200 leading-snug">{t('dash.sttNoProgressHint')}</span>
	                                                    )}
	                                                </div>
	                                            )}
                                        </div>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                            {taskInfoCards.map((item) => (
	                                                <div key={item.label} className="bg-white/[0.08] border border-white/10 rounded-sm p-3 min-w-0">
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">{item.label}</p>
                                                    <p className="text-sm font-bold text-white truncate">{item.value}</p>
                                                </div>
                                            ))}
                                        </div>
                                        <div className="bg-white/[0.07] border border-white/10 rounded-sm p-4">
                                            <div className="flex items-center justify-between mb-4">
                                                <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{t('dash.pipeline')}</p>
                                                <p className="text-xs text-slate-300">{currentJob.exportToLark?t('dash.exportOn'):t('dash.exportOff')}</p>
                                            </div>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                                {jobStages.map((stage) => {
                                                    const rank = stageRank[stage.key] ?? 0;
                                                    const isActive = currentJob.stage === stage.key || (currentJob.stage === 'transcript_ready' && stage.key === 'summary');
                                                    const isDone = currentRank > rank;
                                                    return (
                                                        <div key={stage.key} className={`flex items-center gap-2 text-xs font-bold ${isDone?'text-blue-100':isActive?'text-white':'text-slate-500'}`}>
                                                            <span className={`material-symbols-outlined text-base ${isDone?'text-cyan-300':isActive?'text-blue-300 animate-spin':'text-slate-600'}`}>{isDone?'check_circle':isActive?'sync':'radio_button_unchecked'}</span>
                                                            <span className="truncate">{t(stage.label)}</span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </div>
                                    )}
                                    {!uploading && (
		                                    <div className="w-full max-w-[720px] mx-auto space-y-5">
		                                        <div className="grid grid-cols-1 sm:grid-cols-[auto_auto] gap-3 w-full max-w-[560px]">
		                                <input ref={fileInputRef} type="file" multiple accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus" onChange={handleFileSelect} className="hidden"/>
		                                <input ref={subtitleInputRef} type="file" accept=".srt,.vtt,.txt,.md,text/plain,text/markdown" onChange={handleSubtitleSelect} className="hidden"/>
		                                <button onClick={()=>fileInputRef.current?.click()} disabled={uploading} className="min-h-[56px] bg-white/[0.92] text-slate-950 font-bold px-5 py-4 rounded-sm flex items-center gap-3 hover:bg-blue-50 transition-colors shadow-[0_16px_46px_-30px_rgba(255,255,255,0.8)] active:translate-y-px disabled:opacity-50 justify-center dark:bg-white/90 dark:hover:bg-white">
		                                            <span className="material-symbols-outlined">upload_file</span>
		                                    <span>{uploading ? t('dash.processing') : t('dash.selectFile')}</span>
		                                        </button>
		                                <button onClick={()=>subtitleInputRef.current?.click()} disabled={uploading} className="min-h-[56px] bg-white/[0.07] text-white border border-white/15 font-bold px-5 py-4 rounded-sm flex items-center gap-3 hover:bg-white/[0.12] transition-colors active:translate-y-px disabled:opacity-50 justify-center">
		                                    <span className="material-symbols-outlined">subtitles</span>
		                                    <span>{t('dash.selectSubtitle')}</span>
		                                </button>
		                                        </div>
		                                <div className="text-slate-400 text-sm font-bold max-w-xl">{t('dash.dragHint')}</div>
	                                {isAzureCloudProvider(selectedSttProvider) && (
		                                    <div className="text-cyan-100/85 text-xs leading-relaxed max-w-xl bg-white/[0.08] border border-white/10 rounded-sm px-3 py-2">
	                                        {t('dash.azureUploadHint')}
	                                    </div>
	                                )}
	                                    </div>
                                    )}
                            {uploadError && <div className="bg-red-500/15 border border-red-400/30 text-red-200 px-4 py-2 rounded-sm text-sm">{uploadError}</div>}
	                                    {processingResult && (
	                                        <div className="bg-green-500/15 border border-green-400/30 text-green-200 px-4 py-2 rounded-sm text-sm">
	                                    {processingResult.source==='transcript_file' ? t('dash.subtitleDone') : t('dash.done')} <button onClick={()=>navigate("/editor")} className="underline hover:no-underline">{t('dash.viewEditor')}</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="col-span-12 lg:col-span-3 flex flex-col gap-5">
                            <div className="flex items-center justify-between px-2">
                        <h4 className="font-headline text-xl font-bold text-on-surface">{t('dash.recent')}</h4>
                        <Link to="/tasks" className="text-xs font-bold text-primary hover:underline">{t('dash.viewAll')}</Link>
                            </div>
                            <div className="space-y-3">
                        {history.length === 0 && (
                            <div className="text-center py-12 text-on-surface-variant text-sm">{t('dash.noActivity')}</div>
                        )}
                        {history.slice(0,3).map(h => (
		                            <div key={h.id} className="bg-surface-container-low p-4 rounded-sm flex gap-3 items-start hover:bg-surface-container transition-all cursor-pointer" onClick={() => openHistoryEntry(h)}>
                                <div className={`w-10 h-10 rounded-sm flex items-center justify-center flex-shrink-0 ${h.status==='completed'?'bg-blue-50':'bg-red-50'}`}>
                                    <span className={`material-symbols-outlined ${h.status==='completed'?'text-primary':'text-red-500'}`}>{h.status==='completed'?'check_circle':'error'}</span>
                                        </div>
                                <div className="flex-1 min-w-0">
                                            <div className="flex justify-between items-start mb-1">
                                        <h5 className="font-bold text-on-surface text-sm truncate pr-2">{h.name}</h5>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm uppercase tracking-tighter flex-shrink-0 ${h.status==='completed'?'text-primary bg-primary-fixed':'text-red-600 bg-red-50'}`}>
                                            {t(h.status==='completed'?'dash.statusCompleted':'dash.statusFailed')}
                                                </span>
                                            </div>
                                    <p className="text-xs text-on-surface-variant">
	                                        {timeAgo(h.timestamp, t)}
	                                        {h.durationMin > 0 && ` • ${h.durationMin} ${t('dash.minUnit')}`}
	                                        {h.sttElapsedSec > 0 && ` • ${t('edit.sttElapsed')} ${fmtElapsed(h.sttElapsedSec)}`}
	                                        {h.sttElapsedSec > 0 && h.audioDurationSec > 0 && ` (${fmtSttRelative(h.sttElapsedSec / h.audioDurationSec, lang)})`}
	                                        {h.sttModel && ` • STT ${[h.sttModel,h.sttSpeed,h.sttLanguage].filter(Boolean).join('/')}`}
	                                        {h.larkUrl && <> • <a href={h.larkUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline" onClick={e=>e.stopPropagation()}>Lark</a></>}
                                    </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                    </div>
                </section>
            </div>
            );
        };

/* ═══════════════ Background Tasks ═══════════════ */
const Tasks = () => {
    const {t, lang} = useI18n();
    const {setLastResult, setCurrentJob, addToHistory} = useApp();
    const {getJobs, getJob, downloadJobArtifact} = useApi();
    const navigate = useNavigate();
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const loadJobs = useCallback(async () => {
        try {
            const next = await getJobs(100);
            setJobs(next);
            setError(null);
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setLoading(false);
        }
    }, [lang]);

    useEffect(() => {
        let stale = false;
        const run = async () => { if (!stale) await loadJobs(); };
        run();
        const timer = setInterval(run, 5000);
        return () => {
            stale = true;
            clearInterval(timer);
        };
    }, [loadJobs]);

    const openJob = async (job) => {
        if (job.status === 'running') {
            setCurrentJob(jobToCurrentJob(job));
            return;
        }
        try {
            const fresh = await getJob(job.task_id);
            const result = fresh?.result || job.result;
            if (result) {
                setLastResult(result);
                addToHistory(jobToHistoryEntry({...job, result}));
                navigate('/editor');
            }
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        }
    };

    const downloadArtifact = async (job, kind) => {
        const artifact = job.result?.artifacts?.[kind];
        await downloadJobArtifact(job.task_id, kind, artifact?.filename);
    };

    const statusLabel = (job) => {
        if (job.status === 'queued') return t('tasks.queued');
        if (job.status === 'completed') return t('tasks.completed');
        if (job.status === 'failed') return t('tasks.failed');
        return t('tasks.running');
    };
    const statusClass = (job) => (
        job.status === 'completed'
            ? 'bg-blue-50 text-primary border-blue-100'
            : job.status === 'failed'
                ? 'bg-red-50 text-red-600 border-red-100'
                : job.status === 'queued'
                    ? 'bg-slate-50 text-slate-600 border-slate-200'
                    : 'bg-amber-50 text-amber-700 border-amber-100'
    );
    const formatUpdated = (job) => {
        const ts = Date.parse(job.updated_at || job.created_at || '');
        if (!ts) return '-';
        return timeAgo(ts, t);
    };
    const providerLabel = (job) => (
        job.source_type === 'video_link'
            ? (lang === 'zh' ? '视频链接获取' : 'Video link fetch')
            :
        job.metadata?.stt_provider_label ||
        job.result?.stt_provider_label ||
        (job.metadata?.stt_provider === 'azure_batch' || job.result?.stt_provider === 'azure_batch'
            ? (lang === 'zh' ? '云端转录' : 'Cloud transcription')
            : 'faster-whisper')
    );
    const stageLabel = (job) => t(`status.${job.stage || (job.status === 'failed' ? 'failed' : 'idle')}`);
    const stageDetail = (job) => {
        const progressMeta = job.metadata?.video_source_progress || {};
        const loaded = progressMeta.loaded_bytes ? fmtBytes(progressMeta.loaded_bytes) : '';
        const total = progressMeta.total_bytes ? fmtBytes(progressMeta.total_bytes) : '';
        const byteText = loaded && total ? ` · ${loaded} / ${total}` : (loaded ? ` · ${loaded}` : '');
        if (progressMeta.message) return `${progressMeta.message}${byteText}`;
        if (job.status === 'queued') return lang === 'zh' ? '等待后台转录开始。' : 'Waiting for background transcription.';
        if (job.status === 'running') return job.summary_status || stageLabel(job);
        if (job.status === 'completed') return lang === 'zh' ? '结果已保存，可打开编辑器或下载产物。' : 'Result saved. Open it in the editor or download outputs.';
        if (job.status === 'failed') return friendlyTaskError(job.error_reason, lang);
        return '-';
    };
    const artifactButtons = [
        ['transcript_srt', t('tasks.srt')],
        ['transcript_txt', t('tasks.txt')],
        ['transcript_vtt', t('tasks.vtt')],
        ['summary_md', t('tasks.md')],
    ];

    return (
        <div className="ml-64 min-h-screen relative pb-8">
            <main className="p-12 max-w-7xl mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                <div className="space-y-8">
                    <header className="flex flex-col md:flex-row md:items-end justify-between gap-5">
                        <div className="max-w-3xl">
                            <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface mb-2">{t('tasks.title')}</h1>
                            <p className="text-on-surface-variant font-body max-w-2xl">{t('tasks.subtitle')}</p>
                        </div>
                        <button type="button" onClick={loadJobs} className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-sm bg-surface-container-lowest text-on-surface font-bold text-sm border ff-border-muted hover:bg-surface-container-low transition-colors">
                            <span className={`material-symbols-outlined text-base ${loading ? 'animate-spin' : ''}`}>refresh</span>
                            {t('tasks.refresh')}
                        </button>
                    </header>

                    {error && (
                        <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</div>
                    )}

                    <section className="space-y-3">
                        {jobs.length === 0 && !loading && (
                            <div className="rounded-sm bg-surface-container-lowest border ff-border-muted p-10 text-center">
                                <span className="material-symbols-outlined text-4xl text-outline mb-3">pending_actions</span>
                                <p className="text-sm text-on-surface-variant">{t('tasks.empty')}</p>
                            </div>
                        )}
                        {jobs.map((job) => {
                            const progress = Math.max(0, Math.min(100, Number(job.progress) || (job.status === 'completed' ? 100 : 0)));
                            const result = job.result || {};
                            const artifacts = result.artifacts || {};
                            const availableArtifacts = artifactButtons.filter(([kind]) => artifacts[kind]);
                            const larkUrl = result.lark_response?.url || result.feishu_doc_url || null;
                            const canOpen = !!result && job.status === 'completed';
                            return (
                                <article key={job.task_id} className="rounded-sm bg-surface-container-lowest border ff-border-muted shadow-sm p-5">
                                    <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
                                        <div className="min-w-0 flex-1 space-y-4">
                                            <div className="flex flex-wrap items-start gap-3">
                                                <div className="w-10 h-10 rounded-sm bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                                                    <span className="material-symbols-outlined text-lg">{job.source_type === 'transcript_file' ? 'subtitles' : 'movie'}</span>
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <h2 className="text-base font-headline font-bold text-on-surface truncate">{job.source_filename || job.task_id}</h2>
                                                    <p className="text-xs text-on-surface-variant mt-1">
                                                        {t('tasks.updated')} {formatUpdated(job)}
                                                        {job.source_file_size_mb ? ` • ${fmtFileSize(job.source_file_size_mb)}` : ''}
                                                        {result.audio_duration_seconds ? ` • ${fmtElapsed(result.audio_duration_seconds)}` : ''}
                                                    </p>
                                                </div>
                                                <span className={`px-2.5 py-1 rounded-sm border text-[11px] font-bold ${statusClass(job)}`}>{statusLabel(job)}</span>
                                            </div>

                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                                <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                                    <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('tasks.progress')}</p>
                                                    <p className="text-sm font-semibold text-on-surface mt-1">{stageLabel(job)} · {Math.round(progress)}%</p>
                                                </div>
                                                <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                                    <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('tasks.route')}</p>
                                                    <p className="text-sm font-semibold text-on-surface mt-1 truncate">{providerLabel(job)}</p>
                                                </div>
                                                <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                                    <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('tasks.summary')}</p>
                                                    <p className="text-sm font-semibold text-on-surface mt-1 truncate">{result.summary_skipped ? t('dash.summaryOff') : (job.summary_status || result.summary_status || '-')}</p>
                                                </div>
                                            </div>

                                            <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                                <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('tasks.detail')}</p>
                                                <p className="text-sm font-semibold text-on-surface mt-1 leading-relaxed">{stageDetail(job)}</p>
                                            </div>

                                            {job.status === 'running' && (
                                                <div className={`h-2 rounded-full overflow-hidden bg-surface-container-highest ${isSttProgressUnmeasured(jobToCurrentJob(job)) ? 'progress-indeterminate' : ''}`}>
                                                    {!isSttProgressUnmeasured(jobToCurrentJob(job)) && <div className="h-full bg-primary transition-all duration-500" style={{width:`${progress}%`}}></div>}
                                                </div>
                                            )}
                                            {job.status === 'failed' && job.error_reason && (
                                                <p className="text-xs leading-relaxed text-red-600 bg-red-50 border border-red-100 rounded-sm px-3 py-2">
                                                    <span className="font-bold">{t('tasks.error')}：</span>{friendlyTaskError(job.error_reason, lang)}
                                                </p>
                                            )}
                                        </div>

                                        <div className="lg:w-[320px] flex-shrink-0 space-y-3">
                                            <button type="button" disabled={!canOpen} onClick={() => openJob(job)} className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-sm bg-primary text-white font-bold text-sm hover:bg-primary-container transition-colors disabled:opacity-40">
                                                <span className="material-symbols-outlined text-base">open_in_new</span>
                                                {t('tasks.open')}
                                            </button>
                                            <div className="rounded-sm border ff-border-muted p-3">
                                                <div className="flex items-center justify-between gap-3 mb-2">
                                                    <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('tasks.artifacts')}</p>
                                                    <span className="text-[11px] font-bold text-on-surface-variant">
                                                        {availableArtifacts.length ? `${availableArtifacts.length} ${t('tasks.outputsReady')}` : t('tasks.noOutputs')}
                                                    </span>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2">
                                                    {artifactButtons.map(([kind, label]) => {
                                                        const artifact = artifacts[kind];
                                                        return (
                                                        <button key={kind} type="button" disabled={!artifact} title={artifact?.filename || label} onClick={() => downloadArtifact(job, kind)} className={`px-3 py-2 rounded-sm text-xs font-bold transition-colors ${artifact ? 'bg-surface-container-low text-on-surface hover:bg-surface-container border ff-border-muted' : 'bg-surface-container-low text-outline opacity-45'}`}>
                                                            <span className="block truncate">{label}</span>
                                                        </button>
                                                    );})}
                                                </div>
                                                {larkUrl && (
                                                    <a href={larkUrl} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex w-full items-center justify-center gap-2 px-3 py-2 rounded-sm border border-primary/30 text-xs font-bold text-primary hover:bg-primary/10 transition-colors">
                                                        <span className="material-symbols-outlined text-sm">open_in_new</span>
                                                        {t('tasks.larkDoc')}
                                                    </a>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </article>
                            );
                        })}
                    </section>
                </div>
            </main>
        </div>
    );
};

/* ═══════════════ Processing ═══════════════ */
const Processing = () => {
    const {t, lang} = useI18n();
    const {currentJob, runtimeConfig} = useApp();
    const {loadSettings, saveSettings} = useSettings();
    const {getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus} = useApi();
    const [settings, setSettings] = useState(() => loadSettings());
    const [credentialStatus, setCredentialStatus] = useState(null);
    const [diarizationStatus, setDiarizationStatus] = useState(null);
    const [secretDraft, setSecretDraft] = useState({});
    const [secretSaving, setSecretSaving] = useState(false);
    const [secretFeedback, setSecretFeedback] = useState(null);

    const updateSettingNow = (patch) => {
        setSettings((s) => {
            const next = {...s, ...patch};
            saveSettings(next);
            return next;
        });
    };

    useEffect(() => {
        const pk = settings.promptPreset || 'default';
        if (isBuiltinPromptPresetHidden(pk, settings)) updateSettingNow({promptPreset: 'default'});
        const normalizedSttModel = normalizeSttModel(settings.sttModel);
        if (settings.sttModel !== normalizedSttModel) updateSettingNow({sttModel: normalizedSttModel});
        getCredentialsStatus().then(setCredentialStatus).catch(() => {});
        getSpeakerDiarizationStatus().then((status) => {
            setDiarizationStatus(status);
            if (!status?.available && effectiveSttProvider(settings, runtimeConfig) === 'local' && settings.speakerDiarization) {
                updateSettingNow({speakerDiarization:false});
            }
        }).catch(() => {});
    }, []);

    const saveSecret = async (key) => {
        const value = secretDraft[key];
        if (value === undefined) return;
        setSecretSaving(true);
        setSecretFeedback(null);
        try {
            const next = await saveCredentials({[key]: value});
            const fresh = await getCredentialsStatus().catch(() => next);
            setCredentialStatus(fresh);
            if (key === 'pyannote_auth_token') {
                const status = await getSpeakerDiarizationStatus();
                setDiarizationStatus(status);
            }
            setSecretDraft((draft) => ({...draft, [key]: ''}));
            setSecretFeedback({key, ok: true});
        } catch (err) {
            setSecretFeedback({key, ok: false, message: err.message || String(err)});
        } finally {
            setSecretSaving(false);
        }
    };

    const secretStatusText = (configured) => configured
        ? (lang === 'zh' ? '已配置' : 'Configured')
        : (lang === 'zh' ? '未配置' : 'Not configured');

    const SecretFeedback = ({keyName}) => (
        secretFeedback?.key === keyName ? (
            <p className={`text-[11px] font-semibold ${secretFeedback.ok ? 'text-green-600' : 'text-red-600'}`}>
                {secretFeedback.ok
                    ? (lang === 'zh' ? '已保存' : 'Saved')
                    : `${lang === 'zh' ? '保存失败' : 'Save failed'}：${secretFeedback.message || ''}`}
            </p>
        ) : null
    );

    const aiProvider = settings.aiProvider || 'deepseek';
    const aiModel = settings.aiModel || (aiProvider === 'openai' ? 'gpt-5.4-mini' : 'deepseek-chat');
    const activeAiSecretKey = aiProvider === 'openai' ? 'openai_api_key' : 'deepseek_api_key';
    const activeAiConfigured = aiProvider === 'openai'
        ? credentialStatus?.openai_api_key_configured
        : credentialStatus?.deepseek_api_key_configured;
    const sttProvider = effectiveSttProvider(settings, runtimeConfig);
    const canChooseSttProvider = runtimeConfig.allowedSttProviders.length > 1;
    const showMaintainerSettings = runtimeConfig.showMaintainerSettings;
    const speakerDiarizationAvailable = sttProvider === 'azure_batch' || (sttProvider === 'local' && !!diarizationStatus?.available);
    const speakerDiarizationHint = sttProvider === 'azure_batch'
        ? (lang==='zh'?'云端转录支持可选说话人区分，效果取决于音频质量。':'Cloud transcription can optionally label speakers. Results depend on audio quality.')
        : diarizationStatus?.available
        ? (lang==='zh'?'使用 pyannote 为字幕段标记 SPEAKER。':'Use pyannote to label transcript segments.')
        : !diarizationStatus
            ? (lang==='zh'?'正在检测本机说话人区分依赖。':'Checking local speaker diarization dependency.')
            : !diarizationStatus.dependency_installed
                ? (lang==='zh'?'需要本机安装 pyannote.audio。':'Requires pyannote.audio installed locally.')
                : (lang==='zh'?'pyannote.audio 已安装，还需要配置 Hugging Face token。':'pyannote.audio is installed. Hugging Face token is still required.');
    const inputClass = "w-full bg-surface-container-lowest border ff-border-control rounded-sm px-3.5 py-2.5 text-sm text-on-surface focus:border-primary focus:ring-2 focus:ring-primary/15 transition-colors";
    const sectionClass = "bg-surface-container-lowest rounded-sm border ff-border-muted shadow-sm p-5 space-y-4";
    const fieldLabelClass = "text-[11px] font-bold uppercase tracking-wider text-on-surface-variant";

    const SectionTitle = ({icon, title, desc}) => (
        <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-sm bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                <span className="material-symbols-outlined text-lg">{icon}</span>
            </div>
            <div className="min-w-0">
                <h3 className="font-headline font-bold text-base text-on-surface">{title}</h3>
                {desc && <p className="text-xs text-on-surface-variant leading-snug mt-0.5">{desc}</p>}
            </div>
        </div>
    );

    const ToggleRow = ({id, checked, onChange, label, hint, icon, disabled=false}) => (
        <label htmlFor={id} className={`flex items-start gap-3 p-3 rounded-sm bg-surface-container-low transition-colors ${disabled?'opacity-60 cursor-not-allowed':'hover:bg-surface-container cursor-pointer'}`}>
            <span className="material-symbols-outlined text-primary text-lg mt-0.5">{icon}</span>
            <span className="flex-1 min-w-0">
                <span className="block text-sm font-semibold text-on-surface">{label}</span>
                {hint && <span className="block text-[11px] text-on-surface-variant mt-0.5 leading-snug">{hint}</span>}
            </span>
            <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={onChange} className="w-4 h-4 mt-1 rounded border-outline-variant text-primary focus:ring-primary disabled:opacity-40"/>
        </label>
    );

    return (
             <div className="ml-64 min-h-screen relative pb-8">
                <main className="p-12 max-w-7xl mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
            <div className="space-y-8">
                        <header className="max-w-3xl pt-2">
                    <div className="min-w-0 pt-2">
                    <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface mb-2">{t('proc.title')}</h1>
                    <p className="text-on-surface-variant font-body max-w-2xl">{t('proc.subtitle')}</p>
                        </div>
                </header>

                {currentJob && (
                    <section className="bg-surface-container-lowest rounded-sm p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded-sm bg-primary-fixed flex items-center justify-center text-primary flex-shrink-0">
                                <span className="material-symbols-outlined">monitoring</span>
                            </div>
                            <div className="min-w-0">
                                <p className="text-sm font-bold text-on-surface truncate">{currentJob.fileName}</p>
                                <p className="text-xs text-on-surface-variant">{t('work.activeRunHint')}</p>
                            </div>
                        </div>
                        <Link to="/" className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-primary text-white font-bold rounded-sm hover:bg-primary-container transition-colors text-sm flex-shrink-0">
                            <span className="material-symbols-outlined text-base">arrow_back</span>{t('work.viewProgress')}
                        </Link>
                    </section>
                )}

                    <section className="space-y-5">
                        <div className={sectionClass}>
                            <SectionTitle icon="mic_external_on" title={t('work.transcription')} desc={lang==='zh'?'选择转录路线和音频语言；云端基础设施由后台统一管理。':'Choose the transcription route and audio language. Cloud infrastructure is managed in the backend.'}/>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                {canChooseSttProvider ? (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.sttProvider')}</label>
                                        <select className={inputClass} value={sttProvider} onChange={e=>updateSettingNow({sttProvider:e.target.value})}>
                                            {runtimeConfig.allowedSttProviders.includes('azure_batch') && <option value="azure_batch">{t('set.providerAzureBatch')}</option>}
                                            {runtimeConfig.allowedSttProviders.includes('local') && <option value="local">{t('set.providerLocal')}</option>}
                                        </select>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.sttProvider')}</label>
                                        <div className={`${inputClass} flex items-center justify-between bg-surface-container-low`}>
                                            <span>{sttProvider === 'azure_batch' ? t('set.providerAzureBatch') : t('set.providerLocal')}</span>
                                            <span className="material-symbols-outlined text-base text-primary">lock</span>
                                        </div>
                                    </div>
                                )}
                                {sttProvider === 'local' && (
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.modelSel')}</label>
                                    <select className={inputClass} value={normalizeSttModel(settings.sttModel)} onChange={e=>updateSettingNow({sttModel:e.target.value})}>
                                        <option value="medium">{t('set.optMedium')}</option>
                                        <option value="large-v3">{t('set.optLarge')}</option>
                                    </select>
                                </div>
                                )}
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.sttLanguage')}</label>
                                    <select className={inputClass} value={settings.sttLanguage||"auto"} onChange={e=>updateSettingNow({sttLanguage:e.target.value})}>
                                        <option value="auto">{t('set.langAuto')}</option>
                                        <option value="zh">{t('set.langZh')}</option>
                                        <option value="en">{t('set.langEn')}</option>
                                    </select>
                                </div>
                                {sttProvider === 'local' && (
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.sttSpeed')}</label>
                                    <select className={inputClass} value={settings.sttSpeed||"balanced"} onChange={e=>updateSettingNow({sttSpeed:e.target.value})}>
                                        <option value="fast">{t('set.speedFast')}</option>
                                        <option value="balanced">{t('set.speedBalanced')}</option>
                                        <option value="accurate">{t('set.speedAccurate')}</option>
                                    </select>
                                </div>
                                )}
                            </div>
                            {isAzureCloudProvider(sttProvider) && (
                                <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                    <span className="material-symbols-outlined text-primary text-lg mt-0.5">cloud_done</span>
                                    <p className="text-xs text-on-surface-variant leading-relaxed">
                                        {lang==='zh'
                                            ? '云端转录由后台统一配置。你只需要上传文件，长任务会继续在后台运行。'
                                            : 'Cloud transcription is configured by the product owner. Upload a file and the long-running job will continue in the background.'}
                                    </p>
                                </div>
                            )}
                            <ToggleRow
                                id="workSpeakerDiarization"
                                checked={!!settings.speakerDiarization && speakerDiarizationAvailable}
                                onChange={e=>updateSettingNow({speakerDiarization:e.target.checked})}
                                label={lang==='zh'?'区分不同讲话人':'Speaker diarization'}
                                hint={speakerDiarizationHint}
                                icon="record_voice_over"
                                disabled={!speakerDiarizationAvailable}
                            />
                            {showMaintainerSettings && sttProvider === 'local' && (
                            <div className="space-y-2 rounded-sm border ff-border-muted bg-surface-container-low p-3">
                                <label className={fieldLabelClass}>PYANNOTE AUTH TOKEN</label>
                                <div className="flex gap-2">
                                    <input className={inputClass} placeholder={secretStatusText(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured)} type="password" value={secretDraft.pyannote_auth_token||""} onChange={e=>setSecretDraft(d=>({...d,pyannote_auth_token:e.target.value}))}/>
                                    <button type="button" disabled={secretSaving || !secretDraft.pyannote_auth_token} onClick={()=>saveSecret('pyannote_auth_token')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                </div>
                                <p className="text-[11px] text-on-surface-variant">
                                    {(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured)
                                        ? (lang==='zh'?'已保存。需要更换 token 时直接粘贴新 token 再保存。':'Stored. Paste a new token here to replace it.')
                                        : (lang==='zh'?'粘贴 Hugging Face 的 hf_... token；只写入本机后端配置，不写入浏览器。':'Paste the Hugging Face hf_... token. It is stored only in the local backend config.')}
                                </p>
                            </div>
                            )}
                        </div>

                        <div className={sectionClass}>
                            <SectionTitle icon="psychology" title={t('work.summary')} desc={lang==='zh'?'控制是否生成笔记、默认模板和使用的摘要模型。':'Control note generation, default prompt, and summary model.'}/>
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{t('work.activePrompt')}</label>
                                <select className={inputClass} value={settings.promptPreset||'default'} onChange={e=>updateSettingNow({promptPreset:e.target.value})}>
                                    {allPresetSelectKeys(settings).map((key) => (
                                        <option key={key} value={key}>{presetDisplayLabel(key, settings, lang)}</option>
                                    ))}
                                </select>
                            </div>
                            <ToggleRow
                                id="workSkipSummary"
                                checked={settings.skipAiSummary||false}
                                onChange={e=>updateSettingNow({skipAiSummary:e.target.checked})}
                                label={t('set.skipSummary')}
                                hint={t('set.skipSummaryHint')}
                                icon="subject"
                            />
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('work.summaryMode')}</label>
                                    <select className={inputClass} value={settings.noteMode||"auto"} onChange={e=>updateSettingNow({noteMode:e.target.value})}>
                                        {NOTE_MODE_OPTIONS.map((item) => (
                                            <option key={item.value} value={item.value}>{lang === 'zh' ? item.labelZh : item.labelEn}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.provider')}</label>
                                    <select className={inputClass} value={aiProvider} onChange={e=>updateSettingNow({aiProvider:e.target.value,aiModel:e.target.value==='openai'?'gpt-5.4-mini':'deepseek-chat'})}>
                                        <option value="deepseek">DeepSeek</option>
                                        <option value="openai">OpenAI</option>
                                    </select>
                                </div>
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.aiModel')}</label>
                                    {aiProvider === 'openai' ? (
                                        <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                            <option value="gpt-5.4-mini">gpt-5.4-mini</option>
                                            <option value="gpt-5.4">gpt-5.4</option>
                                            <option value="gpt-5.5">gpt-5.5</option>
                                        </select>
                                    ) : (
                                        <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                            <option value="deepseek-chat">deepseek-chat</option>
                                            <option value="deepseek-reasoner">deepseek-reasoner</option>
                                        </select>
                                    )}
                                </div>
                            </div>
                            {showMaintainerSettings ? (
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{aiProvider==='openai'?t('set.openaiKey'):t('set.deepseekKey')}</label>
                                <div className="flex gap-2">
                                    <input className={inputClass} placeholder={secretStatusText(activeAiConfigured)} type="password" value={secretDraft[activeAiSecretKey]||""} onChange={e=>setSecretDraft(d=>({...d,[activeAiSecretKey]:e.target.value}))}/>
                                    <button type="button" disabled={secretSaving || !secretDraft[activeAiSecretKey]} onClick={()=>saveSecret(activeAiSecretKey)} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                </div>
                                <p className="text-[11px] text-on-surface-variant">{secretStatusText(activeAiConfigured)}。{lang==='zh'?'不会写入浏览器 localStorage。':'Not stored in browser localStorage.'}</p>
                            </div>
                            ) : (
                            <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                <span className="material-symbols-outlined text-primary text-lg mt-0.5">admin_panel_settings</span>
                                <p className="text-xs text-on-surface-variant leading-relaxed">
                                    {lang==='zh'?'摘要模型由后台统一配置，普通用户不需要填写 API Key。':'The summary model is configured in the backend. Users do not need to enter API keys.'}
                                </p>
                            </div>
                            )}
                        </div>

                        <div className={sectionClass}>
                            <SectionTitle icon="cloud_upload" title={t('work.export')} desc={lang==='zh'?'只放与飞书导出直接相关的开关和连接信息。':'Only export-related switches and connection details live here.'}/>
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                <ToggleRow
                                    id="workExportToLark"
                                    checked={settings.exportToLark||false}
                                    onChange={e=>updateSettingNow({exportToLark:e.target.checked})}
                                    label={t('set.autoExport')}
                                    icon="ios_share"
                                />
                                {showMaintainerSettings && <ToggleRow
                                    id="workLarkViaCli"
                                    checked={settings.larkViaCli||false}
                                    onChange={e=>updateSettingNow({larkViaCli:e.target.checked})}
                                    label={t('set.larkViaCli')}
                                    hint={t('set.larkViaCliHint')}
                                    icon="terminal"
                                />}
                            </div>
                            {showMaintainerSettings && !settings.larkViaCli && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>App ID</label>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_id_configured)} value={secretDraft.lark_app_id||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_id:e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft.lark_app_id} onClick={()=>saveSecret('lark_app_id')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>App Secret</label>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_secret_configured)} type="password" value={secretDraft.lark_app_secret||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_secret:e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft.lark_app_secret} onClick={()=>saveSecret('lark_app_secret')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {!showMaintainerSettings && (
                                <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                    <span className="material-symbols-outlined text-primary text-lg mt-0.5">cloud_done</span>
                                    <p className="text-xs text-on-surface-variant leading-relaxed">
                                        {lang==='zh'?'飞书导出连接由后台统一配置；用户只需要选择是否自动导出。':'Lark export credentials are configured in the backend. Users only choose whether to export automatically.'}
                                    </p>
                                </div>
                            )}
                        </div>
                    </section>
                </div>
        </main>
    </div>
    );
};

/* ═══════════════ Editor ═══════════════ */
const Editor = () => {
    const {t, lang} = useI18n();
    const {
        lastResult,
        setLastResult,
        lastSourceFile,
        setLastSourceFile,
        history,
        addToHistory,
        currentJob,
        setCurrentJob,
        addLarkExport,
        runtimeConfig,
    } = useApp();
    const {processVideoSSE, fetchJobSourceFile, recordEvent, getJob, saveTranscriptEdit, getCredentialsStatus} = useApi();
    const {loadSettings, saveSettings} = useSettings();
    const [exporting, setExporting] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const [retranscribing, setRetranscribing] = useState(false);
    const [downloading, setDownloading] = useState(null);
    const [toast, setToast] = useState(null);
    const [larkUrl, setLarkUrl] = useState(null);
    const [retranscribeConfirmOpen, setRetranscribeConfirmOpen] = useState(false);
    const summaryRef = useRef(null);
    const retranscribeInputRef = useRef(null);
    const fallbackTaskIdRef = useRef(createTaskId());
    const hydratedTaskIdsRef = useRef(new Set());
    const transcriptSaveSeqRef = useRef(0);

    const initSettings = loadSettings();
    let initPk = initSettings.promptPreset || 'default';
    if (isBuiltinPromptPresetHidden(initPk, initSettings)) initPk = 'default';
    const [promptKey, setPromptKey] = useState(initPk);
    const [customText, setCustomText] = useState(initSettings.customPromptText || '');
    const [defaultPromptEdit, setDefaultPromptEdit] = useState(() => getDefaultPromptBody(initSettings));
    const [meetingEdit, setMeetingEdit] = useState(() => getBuiltinExtraPromptBody('meeting', initSettings));
    const [researchEdit, setResearchEdit] = useState(() => getBuiltinExtraPromptBody('research', initSettings));
    const [quickBulletsEdit, setQuickBulletsEdit] = useState(() => getBuiltinExtraPromptBody('quickBullets', initSettings));
    const [userPresetEdit, setUserPresetEdit] = useState(() => {
        if (initPk.startsWith('user_')) {
            const p = (initSettings.userPromptPresets || []).find((x) => x.id === initPk);
            return p?.prompt || '';
        }
        return '';
    });
    const [presetNameInput, setPresetNameInput] = useState('');
    const [presetListTick, setPresetListTick] = useState(0);
    const [promptOpen, setPromptOpen] = useState(false);

    useEffect(() => {
        if (!promptOpen) return;
        const s = loadSettings();
        const pkRaw = s.promptPreset || 'default';
        const pk = isBuiltinPromptPresetHidden(pkRaw, s) ? 'default' : pkRaw;
        setPromptKey(pk);
        setDefaultPromptEdit(getDefaultPromptBody(s));
        setMeetingEdit(getBuiltinExtraPromptBody('meeting', s));
        setResearchEdit(getBuiltinExtraPromptBody('research', s));
        setQuickBulletsEdit(getBuiltinExtraPromptBody('quickBullets', s));
        setCustomText(s.customPromptText || '');
        if (pk.startsWith('user_')) {
            const p = (s.userPromptPresets || []).find((x) => x.id === pk);
            setUserPresetEdit(p?.prompt || '');
        }
    }, [promptOpen]);

    const result = lastResult || (!currentJob ? historyEntryToResult(history.find(h=>h.status==='completed')) : null);
    const resultSegmentCount = pickTranscriptSegments(result).length;
    const resultTextLength = (result?.transcript_text || '').length;
    const resultKey = result
        ? `${result.task_id || result.filename || 'current_result'}:${result.transcript_edited ? 'edited' : `${resultSegmentCount}:${resultTextLength}`}`
        : 'empty_result';
    const mediaSourceKey = result
        ? [
            result.task_id || result.filename || 'current_result',
            result.source_file_available ? 'stored' : 'unstored',
            lastSourceFile ? `${lastSourceFile.name}:${lastSourceFile.size}:${lastSourceFile.lastModified || 0}` : 'no-local-file',
        ].join(':')
        : 'empty_media_source';
    const [editedSegments, setEditedSegments] = useState([]);
    const [editedTranscript, setEditedTranscript] = useState('');
    const [baselineSegments, setBaselineSegments] = useState([]);
    const [transcriptDirty, setTranscriptDirty] = useState(false);
    const [transcriptUnsaved, setTranscriptUnsaved] = useState(false);
    const [mediaUrl, setMediaUrl] = useState('');
    const [mediaLoading, setMediaLoading] = useState(false);
    const [mediaError, setMediaError] = useState('');
    const [mediaCurrentTime, setMediaCurrentTime] = useState(0);
    const [mediaDuration, setMediaDuration] = useState(0);
    const [mediaPlaying, setMediaPlaying] = useState(false);
    const [followPlayback, setFollowPlayback] = useState(true);
    const [transcriptSaveStatus, setTranscriptSaveStatus] = useState('idle');
    const [editRecordsOpen, setEditRecordsOpen] = useState(false);
    const mediaRef = useRef(null);
    const mediaInputRef = useRef(null);
    const transcriptScrollRef = useRef(null);
    const segmentRefs = useRef({});

    useEffect(() => {
        if (!result?.task_id || transcriptUnsaved) return;
        const currentSegments = pickTranscriptSegments(result);
        const currentText = result.transcript_text || '';
        const needsHydration = currentSegments.length === 0 || currentText.length <= 260;
        if (!needsHydration || hydratedTaskIdsRef.current.has(result.task_id)) return;
        hydratedTaskIdsRef.current.add(result.task_id);
        let cancelled = false;
        getJob(result.task_id)
            .then((job) => {
                const full = job?.result;
                if (cancelled || !full) return;
                const fullSegments = pickTranscriptSegments(full);
                const fullText = full.transcript_text || '';
                if (fullSegments.length > currentSegments.length || fullText.length > currentText.length) {
                    const fullBaselineSegments = pickTranscriptBaselineSegments(full);
                    setLastResult(full);
                    setEditedSegments(fullSegments.map((seg) => ({...seg})));
                    setEditedTranscript(composeTranscriptText(fullSegments, fullText));
                    setBaselineSegments((prev) => {
                        if (fullBaselineSegments.length > 0) return fullBaselineSegments.map((seg) => ({...seg}));
                        if (full.transcript_edited && prev.length > 0) return prev;
                        return fullSegments.map((seg) => ({...seg}));
                    });
                    setTranscriptDirty(!!full.transcript_edited);
                    setTranscriptSaveStatus(full.transcript_edited ? 'saved' : 'idle');
                }
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [resultKey, transcriptUnsaved]);

    useEffect(() => {
        if (!result) {
            setEditedSegments([]);
            setEditedTranscript('');
            setBaselineSegments([]);
            setTranscriptDirty(false);
            setTranscriptUnsaved(false);
            return;
        }
        if (result.transcript_edited && transcriptUnsaved) return;
        const sourceSegments = pickTranscriptSegments(result);
        const baselineSourceSegments = pickTranscriptBaselineSegments(result);
        const sourceText = result.transcript_text || '';
        setEditedSegments(sourceSegments.map((seg) => ({...seg})));
        setEditedTranscript(composeTranscriptText(sourceSegments, sourceText));
        setBaselineSegments((prev) => {
            if (baselineSourceSegments.length > 0) return baselineSourceSegments.map((seg) => ({...seg}));
            if (result.transcript_edited && prev.length > 0) return prev;
            return sourceSegments.map((seg) => ({...seg}));
        });
        setTranscriptDirty(!!result.transcript_edited);
        setTranscriptUnsaved(false);
        setTranscriptSaveStatus(result.transcript_edited ? 'saved' : 'idle');
    }, [resultKey, transcriptUnsaved]);

    const applyTranscriptEdit = useCallback((nextSegments, nextText) => {
        if (!result) return;
        const nextEditRecords = buildTranscriptEditRecords(baselineSegments, nextSegments, result);
        const updated = {
            ...result,
            segments: nextSegments,
            transcript_text: nextText,
            transcript_edit_records: nextEditRecords,
            transcript_edit_record_count: nextEditRecords.length,
            transcript_edited: true,
            transcript_edited_at: new Date().toISOString(),
        };
        setEditedSegments(nextSegments);
        setEditedTranscript(nextText);
        setTranscriptDirty(true);
        setTranscriptUnsaved(true);
        setTranscriptSaveStatus(result.task_id ? 'saving' : 'failed');
        setLastResult(updated);
    }, [baselineSegments, result, setLastResult]);

    const handleSegmentTextChange = (index, text) => {
        const nextSegments = editedSegments.map((seg, i) => i === index ? {...seg, text} : seg);
        applyTranscriptEdit(nextSegments, composeTranscriptText(nextSegments, editedTranscript));
    };

    const handlePlainTranscriptChange = (text) => {
        applyTranscriptEdit([], text);
    };

    const loadMediaFile = useCallback((file) => {
        if (!file) return;
        const url = URL.createObjectURL(file);
        setMediaUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
        });
        setMediaError('');
        setMediaLoading(false);
    }, []);

    useEffect(() => {
        let cancelled = false;
        setMediaUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return '';
        });
        setMediaError('');
        setMediaLoading(false);
        if (!result) return () => { cancelled = true; };
        if (lastSourceFile) {
            loadMediaFile(lastSourceFile);
            return () => { cancelled = true; };
        }
        if (result.task_id && result.source_file_available) {
            setMediaLoading(true);
            fetchJobSourceFile(result.task_id, result.filename || 'source')
                .then((file) => { if (!cancelled) loadMediaFile(file); })
                .catch((err) => {
                    if (!cancelled) {
                        setMediaError(err.message || 'Source file unavailable');
                        setMediaLoading(false);
                    }
                });
        }
        return () => { cancelled = true; };
    }, [mediaSourceKey]);

    const segments = editedSegments;
    const transcript = editedTranscript || result?.transcript_text || '';
    const editRecords = useMemo(
        () => buildTranscriptEditRecords(baselineSegments, segments, result),
        [baselineSegments, segments, result?.transcript_edit_records]
    );
    const summary = result?.summary_markdown || '';
    const canUseStoredSource = !!result?.source_file_available && !!result?.task_id;
    const durSec = result?.audio_duration_seconds || 0;
    const sttElapsedSec = result?.stt_elapsed_seconds || 0;
    const sttRealtimeFactor = result?.stt_realtime_factor || (durSec > 0 && sttElapsedSec > 0 ? sttElapsedSec / durSec : null);
    const sttProfile = result?.stt_model ? [isAzureCloudProvider(result.stt_provider) ? 'Azure' : 'local', result.stt_model, result.stt_speed, result.stt_language].filter(Boolean).join(' / ') : '';
    const activeTaskId = result?.task_id || fallbackTaskIdRef.current;
    const resolvedNoteMode = result?.resolved_note_mode || result?.requested_note_mode || null;
    const noteModeText = resolvedNoteMode ? noteModeLabel(resolvedNoteMode, lang) : null;
    const playbackDuration = mediaDuration || durSec || 0;
    const activeSegmentIndex = segments.length > 0
        ? (() => {
            const found = segments.findIndex((seg, index) => {
            const start = Number(seg.start) || 0;
            const nextStart = Number(segments[index + 1]?.start);
            const end = Number(seg.end) || (Number.isFinite(nextStart) ? nextStart : start + 6);
            return mediaCurrentTime >= start && mediaCurrentTime < end;
            });
            return found >= 0 ? found : -1;
        })()
        : -1;

    useEffect(() => {
        if (!followPlayback || activeSegmentIndex < 0 || !mediaPlaying) return;
        const node = segmentRefs.current[activeSegmentIndex];
        if (node) node.scrollIntoView({block:'center', behavior:'smooth'});
    }, [activeSegmentIndex, followPlayback, mediaPlaying]);

    useEffect(() => {
        const root = transcriptScrollRef.current;
        if (!root) return;
        root.querySelectorAll('textarea[data-transcript-segment="true"]').forEach(autoSizeTextarea);
    }, [segments]);

    useEffect(() => () => {
        if (mediaUrl) URL.revokeObjectURL(mediaUrl);
    }, [mediaUrl]);

    useEffect(() => {
        if (!result?.task_id || !transcriptUnsaved) return;
        const seq = ++transcriptSaveSeqRef.current;
        setTranscriptSaveStatus('saving');
        const timer = setTimeout(() => {
            saveTranscriptEdit(result.task_id, {
                transcript_text: transcript,
                segments,
                edit_records: editRecords,
            })
                .then((data) => {
                    if (seq !== transcriptSaveSeqRef.current) return;
                    setTranscriptUnsaved(false);
                    setTranscriptDirty(true);
                    setTranscriptSaveStatus('saved');
                    if (data?.result) {
                        setLastResult((prev) => (
                            prev?.task_id === result.task_id
                                ? {...prev, ...data.result}
                                : prev
                        ));
                    }
                })
                .catch(() => {
                    if (seq !== transcriptSaveSeqRef.current) return;
                    setTranscriptSaveStatus('failed');
                });
        }, 800);
        return () => clearTimeout(timer);
    }, [result?.task_id, transcriptUnsaved, transcript, segments, editRecords]);

    const seekToSegment = (seg) => {
        const media = mediaRef.current;
        if (!media || seg?.start == null) return;
        media.currentTime = Math.max(0, Number(seg.start) || 0);
        setMediaCurrentTime(media.currentTime);
        setFollowPlayback(true);
    };

    const togglePlayback = () => {
        const media = mediaRef.current;
        if (!media) return;
        if (media.paused) media.play().catch((err) => setMediaError(err.message || 'Playback failed'));
        else media.pause();
    };

    const showToast = (msg, ok=true) => { setToast({msg,ok}); setTimeout(()=>setToast(null), 3000); };
    const buildAiOptions = (settings) => ({
        aiProvider: settings.aiProvider||'deepseek',
        aiModel: settings.aiModel||null,
        systemPrompt: resolveSystemPromptFromSettings(settings)||null,
        noteMode: settings.noteMode||'auto',
        speakerDiarization: !!settings.speakerDiarization,
        sttProvider: effectiveSttProvider(settings, runtimeConfig),
    });

    const presetLabel = (key) => presetDisplayLabel(key, loadSettings(), lang);

    const handlePromptKeyChange = (newKey) => {
        setPromptKey(newKey);
        const s = loadSettings();
        saveSettings({ ...s, promptPreset: newKey });
        if (newKey === 'default') setDefaultPromptEdit(getDefaultPromptBody({ ...s, promptPreset: newKey }));
        if (newKey === 'meeting') setMeetingEdit(getBuiltinExtraPromptBody('meeting', { ...s, promptPreset: newKey }));
        if (newKey === 'research') setResearchEdit(getBuiltinExtraPromptBody('research', { ...s, promptPreset: newKey }));
        if (newKey === 'quickBullets') setQuickBulletsEdit(getBuiltinExtraPromptBody('quickBullets', { ...s, promptPreset: newKey }));
        if (newKey.startsWith('user_')) {
            const p = (s.userPromptPresets || []).find((x) => x.id === newKey);
            setUserPresetEdit(p?.prompt || '');
        }
    };

    const handleCustomTextChange = (val) => {
        setCustomText(val);
        const s = loadSettings();
        saveSettings({ ...s, customPromptText: val });
    };

    const handleDefaultPromptChange = (val) => {
        setDefaultPromptEdit(val);
        const s = loadSettings();
        saveSettings({ ...s, defaultPromptOverride: val });
    };

    const handleBuiltinExtraChange = (key, val) => {
        if (key === 'meeting') setMeetingEdit(val);
        else if (key === 'research') setResearchEdit(val);
        else if (key === 'quickBullets') setQuickBulletsEdit(val);
        const s = loadSettings();
        saveSettings({ ...s, promptOverrides: { ...(s.promptOverrides || {}), [key]: val } });
    };

    const resetBuiltinExtra = (key) => {
        if (!window.confirm(t('set.deleteBuiltinPromptConfirm'))) return;
        const s = loadSettings();
        const hidden = new Set(Array.isArray(s.hiddenPromptPresets) ? s.hiddenPromptPresets : []);
        hidden.add(key);
        const next = { ...s, hiddenPromptPresets: Array.from(hidden) };
        if (next.promptPreset === key) next.promptPreset = 'default';
        saveSettings(next);
        // 如果当前选中该模板，则切回默认，避免面板状态与选中项不一致
        if (promptKey === key) {
            setPromptKey('default');
            setDefaultPromptEdit(getDefaultPromptBody(next));
        }
        // 触发面板重新渲染：否则 hiddenPromptPresets 更新了但 UI 不会立刻消失
        setPresetListTick((x) => x + 1);
    };

    const handleUserPresetChange = (val) => {
        setUserPresetEdit(val);
        const s = loadSettings();
        const ups = (s.userPromptPresets || []).map((p) => (p.id === promptKey ? { ...p, prompt: val } : p));
        saveSettings({ ...s, userPromptPresets: ups });
    };

    const saveCustomAsPresetFromEditor = () => {
        const name = presetNameInput.trim();
        if (!name || !customText.trim()) {
            showToast(lang === 'zh' ? '请填写预设名称和提示词内容' : 'Enter a name and prompt text', false);
            return;
        }
        const s = loadSettings();
        const id = 'user_' + Date.now();
        const next = {
            ...s,
            userPromptPresets: [{ id, nameZh: name, nameEn: name, prompt: customText }, ...(s.userPromptPresets || [])],
        };
        saveSettings(next);
        setPresetNameInput('');
        setPresetListTick((x) => x + 1);
        showToast(t('set.presetSaved'));
    };

    const handleDeleteUserPreset = (id, e) => {
        e.stopPropagation();
        e.preventDefault();
        if (!window.confirm(t('set.deletePresetConfirm'))) return;
        const s = loadSettings();
        const ups = normalizeUserPresets(s).filter((p) => p.id !== id);
        const next = { ...s, userPromptPresets: ups };
        if (next.promptPreset === id) next.promptPreset = 'default';
        saveSettings(next);
        if (promptKey === id) {
            setPromptKey('default');
            setDefaultPromptEdit(getDefaultPromptBody(next));
        }
        setPresetListTick((x) => x + 1);
        showToast(lang === 'zh' ? '已删除预设' : 'Preset deleted', true);
    };

    const handleExportLark = async () => {
        if(!result || exporting) return;
        setExporting(true);
        try {
            const settings = loadSettings();
            const fd = new FormData();
            fd.append('markdown', result.summary_markdown||'');
            fd.append('title', fileNameStem(result.filename));
            fd.append('task_id', activeTaskId);
            if(result.source) fd.append('source_type', result.source);
            if(result.filename) fd.append('source_filename', result.filename);
            if(durSec > 0) fd.append('source_duration_seconds', String(durSec));
            fd.append('lark_via_cli', settings.larkViaCli ? 'true' : 'false');
            const r = await apiFetch(`${API_BASE}/export-lark`, {method:'POST', body:fd});
            const data = await r.json().catch(()=>({}));
            if(!r.ok) {
                const d = data.detail;
                const msg = Array.isArray(d) ? d.map(x=>x.msg||x).join('; ') : (d || 'Export failed');
                throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
            }
            const exportUrl = data.url || null;
            if(!exportUrl && !data.dry_run) throw new Error(data.msg || 'No document URL returned');
            setLarkUrl(exportUrl);
            const dispTitle = data.doc_title || fileNameStem(result.filename) || "Export";
            if(exportUrl) addLarkExport({url:exportUrl, title: dispTitle, timestamp:Date.now()});
            showToast(t('edit.exportDone'));
        } catch(err) { showToast(t('edit.exportFail')+': '+err.message, false); }
        finally { setExporting(false); }
    };

    const handleRegenerate = async () => {
        if(!transcript || regenerating) return;
        setRegenerating(true);
        try {
            const settings = loadSettings();
            const fd = new FormData();
            fd.append('transcript', transcript);
            fd.append('task_id', activeTaskId);
            if(result.source) fd.append('source_type', result.source);
            if(result.filename) fd.append('source_filename', result.filename);
            if(durSec > 0) fd.append('source_duration_seconds', String(durSec));
            if(settings.aiProvider) fd.append('ai_provider', settings.aiProvider);
            if(settings.aiModel) fd.append('ai_model', settings.aiModel);
            if(settings.noteMode) fd.append('note_mode', settings.noteMode);
            const activePrompt = resolveSystemPromptFromSettings(settings);
            if(activePrompt) fd.append('system_prompt', activePrompt);
            const r = await apiFetch(`${API_BASE}/regenerate-summary`, {method:'POST', body:fd});
            if(!r.ok) throw new Error((await r.json().catch(()=>({}))).detail||'Regeneration failed');
            const data = await r.json();
		            setLastResult({
		                ...result,
		                task_id: data.task_id || activeTaskId,
		                transcript_text: transcript,
		                segments,
		                transcript_edited: transcriptDirty || !!result.transcript_edited,
		                summary_markdown: data.summary_markdown,
		                summary_skipped: false,
		                requested_note_mode: data.requested_note_mode||settings.noteMode||'auto',
		                resolved_note_mode: data.resolved_note_mode||null,
		                note_mode_chunk_count: data.note_mode_chunk_count||null,
		            });
            showToast(t('edit.regenDone'));
        } catch(err) { showToast(err.message, false); }
        finally { setRegenerating(false); }
    };

    const runRetranscribe = async (file) => {
        if(!file || retranscribing) return;
        const validExts = /\.(mp4|mov|avi|mkv|wmv|flv|webm|m4v|mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;
        if(!validExts.test(file.name)){
            showToast(t('dash.fileError'), false);
            return;
        }
        const settings = loadSettings();
        const sttModel = normalizeSttModel(settings.sttModel);
        const sttProvider = effectiveSttProvider(settings, runtimeConfig);
        if (isAzureCloudProvider(sttProvider)) {
            try {
                const status = await getCredentialsStatus();
                const configured = sttProvider === 'azure_batch'
                    ? isAzureBatchConfigured(status)
                    : isAzureSpeechConfigured(status);
                if (!configured) {
                    showToast(azureSpeechMissingMessage(lang), false);
                    return;
                }
            } catch (_) {
                showToast(azureSpeechMissingMessage(lang), false);
                return;
            }
        }
        const taskId = createTaskId();
        const sourceType = /\.(mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i.test(file.name) ? "audio" : "video";
        const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
        setRetranscribing(true);
        setLastSourceFile(file);
        setCurrentJob({
            taskId,
            fileName:file.name,
            stage:'upload',
            progress:2,
            startedAt: Date.now(),
            sourceType,
            fileSizeMb,
            sttProvider,
            sttModel,
            sttSpeed: settings.sttSpeed||'balanced',
            sttLanguage: settings.sttLanguage||'auto',
            skipSummary: !!settings.skipAiSummary,
            exportToLark: !!settings.exportToLark,
            noteMode: settings.noteMode||'auto',
        });
        try {
            const resultData = await processVideoSSE(file, {
                taskId,
                sourceLastModifiedMs: file.lastModified||null,
                exportToLark: settings.exportToLark||false,
                larkViaCli: !!settings.larkViaCli,
                title: file.name.replace(/\.[^/.]+$/,""),
                ...buildAiOptions(settings),
                skipSummary: !!settings.skipAiSummary,
                sttProvider,
                sttModel,
                sttSpeed: settings.sttSpeed||'balanced',
                sttLanguage: settings.sttLanguage||'auto',
            }, (ev) => {
                setCurrentJob(prev => prev ? {
                    ...prev,
                    stage:ev.stage,
	                    progress:ev.progress,
	                    sttProgress: ev.stt_progress ?? prev.sttProgress,
	                    transcribedSeconds: ev.transcribed_seconds ?? prev.transcribedSeconds,
		                    durationSeconds: ev.duration_seconds ?? prev.durationSeconds,
		                    sttElapsedSeconds: ev.stt_elapsed_seconds ?? prev.sttElapsedSeconds,
		                    sttStatus: ev.stt_status ?? prev.sttStatus,
		                    sttProvider: ev.stt_provider ?? prev.sttProvider,
		                    azureBatchAudioSizeMb: ev.azure_batch_audio_size_mb ?? prev.azureBatchAudioSizeMb,
		                } : null);
                if(ev.stage === 'transcript_ready' && ev.result) setLastResult(ev.result);
            });

            setLastResult(resultData);
            const larkUrl = resultData.lark_response?.url || null;
            addToHistory(resultToHistoryEntry(resultData, {taskId, name:file.name, requestedNoteMode: settings.noteMode||'auto'}));
            if(larkUrl) addLarkExport({url:larkUrl, title: resultData.lark_doc_title || fileNameStem(file.name), timestamp:Date.now()});
            setCurrentJob({fileName:file.name, stage:'done', progress:100});
            setTimeout(() => setCurrentJob(null), 3000);
            showToast(t('edit.retranscribeDone'));
        } catch(err) {
            setCurrentJob(null);
            showToast(err.message || 'Retranscription failed', false);
        } finally {
            setRetranscribing(false);
        }
    };

    const handleRetranscribe = () => {
        setRetranscribeConfirmOpen(true);
    };

    const confirmRetranscribe = async () => {
        setRetranscribeConfirmOpen(false);
        if(lastSourceFile) runRetranscribe(lastSourceFile);
        else if(result?.task_id && result?.source_file_available) {
            try {
                const sourceFile = await fetchJobSourceFile(result.task_id, result.filename || 'source');
                runRetranscribe(sourceFile);
            } catch (err) {
                showToast(err.message || t('edit.retranscribeUnavailableTitle'), false);
                retranscribeInputRef.current?.click();
            }
        } else retranscribeInputRef.current?.click();
    };

    if(!result) return (
        <div className="ml-64 min-h-screen relative pb-8">
            <main className="flex items-center justify-center h-[calc(100vh-2rem)]">
                <div className="text-center">
                    <span className="material-symbols-outlined text-6xl text-slate-300 mb-4">edit_note</span>
                    <h2 className="font-headline text-2xl font-bold text-on-surface mb-2">{t('edit.noResult')}</h2>
                    <p className="text-on-surface-variant mb-6">{t('edit.noResultDesc')}</p>
                    <Link to="/" className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white font-bold rounded-sm hover:bg-primary-container transition-colors">
                        <span className="material-symbols-outlined">upload_file</span>{t('dash.selectFile')}
                    </Link>
                                            </div>
            </main>
                                                </div>
    );

    const recordDownload = (eventName, format) => {
        recordEvent({
            event_name: eventName,
            task_id: activeTaskId,
            source_type: result.source || null,
            source_filename: result.filename,
            source_duration_seconds: durSec,
            transcript_length: transcript.length,
            summary_length: summary.length,
            stage: "download",
            success: true,
            metadata: {format},
        });
    };
    const mediaProgress = playbackDuration > 0 ? Math.min(100, Math.max(0, mediaCurrentTime / playbackDuration * 100)) : 0;

    return (
    <div className="ml-64 min-h-screen relative pb-8">
        {toast && (
            <div className={`fixed top-6 right-8 z-50 px-5 py-3 rounded-lg shadow-lg text-sm font-medium animate-pulse ${toast.ok?'bg-green-500 text-white':'bg-red-500 text-white'}`}>
                {toast.msg}
                                            </div>
        )}
        {larkUrl && (
            <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 bg-white shadow-xl border border-green-200 rounded-xl px-6 py-4 flex items-center gap-4 max-w-lg">
                <span className="material-symbols-outlined text-green-500 text-2xl" style={{fontVariationSettings:"'FILL' 1"}}>check_circle</span>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-on-surface">{t('edit.exportDone')}</p>
                    <a href={larkUrl} target="_blank" rel="noopener noreferrer" className="text-primary text-sm hover:underline truncate block">{larkUrl}</a>
                                                </div>
                <button onClick={()=>setLarkUrl(null)} className="text-slate-400 hover:text-slate-600 flex-shrink-0">
                    <span className="material-symbols-outlined text-sm">close</span>
                </button>
                                                </div>
        )}
        {retranscribeConfirmOpen && (
            <div className="fixed inset-0 z-50 bg-slate-950/45 backdrop-blur-sm flex items-center justify-center p-6">
                <div className="w-full max-w-lg bg-surface-container-lowest rounded-sm shadow-2xl border ff-border-muted overflow-hidden">
                    <div className="px-6 py-5 border-b border-surface-container-highest flex items-start gap-4">
                        <div className="w-11 h-11 rounded-sm bg-blue-50 text-primary flex items-center justify-center flex-shrink-0">
                            <span className="material-symbols-outlined">record_voice_over</span>
                        </div>
                        <div className="min-w-0">
                            <h2 className="font-headline text-xl font-extrabold text-on-surface">
                                {(lastSourceFile || canUseStoredSource) ? t('edit.retranscribeConfirmTitle') : t('edit.retranscribeUnavailableTitle')}
                            </h2>
                            <p className="text-sm text-on-surface-variant mt-2 leading-relaxed">
                                {(lastSourceFile || canUseStoredSource) ? t('edit.retranscribeConfirmDesc') : t('edit.retranscribeUnavailableDesc')}
                            </p>
                            <div className="mt-4 rounded-sm bg-surface-container-low p-3">
                                <p className="text-[10px] uppercase tracking-wider text-on-surface-variant font-bold mb-1">{(lastSourceFile || canUseStoredSource) ? 'Source file' : 'Current result'}</p>
                                <p className="text-sm font-bold text-on-surface truncate">{lastSourceFile?.name || result.filename || t('edit.title')}</p>
                            </div>
                        </div>
                    </div>
                    <div className="px-6 py-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-3">
                        <button
                            type="button"
                            onClick={()=>setRetranscribeConfirmOpen(false)}
                            className="px-4 py-2 rounded-sm bg-surface-container text-on-surface text-sm font-bold hover:bg-surface-container-high transition"
                        >
                            {t('edit.cancel')}
                        </button>
                        <button
                            type="button"
                            onClick={confirmRetranscribe}
                            className="px-4 py-2 rounded-sm bg-primary text-white text-sm font-bold hover:bg-primary-container transition inline-flex items-center justify-center gap-2"
                        >
                            <span className="material-symbols-outlined text-base">{(lastSourceFile || canUseStoredSource) ? 'sync' : 'upload_file'}</span>
                            {(lastSourceFile || canUseStoredSource) ? t('edit.retranscribeConfirmAction') : t('edit.retranscribeChooseAction')}
                        </button>
                    </div>
                </div>
            </div>
        )}
        {editRecordsOpen && (
            <div className="fixed inset-0 z-50 bg-slate-950/45 backdrop-blur-sm flex items-center justify-center p-6">
                <div className="w-full max-w-3xl max-h-[82vh] bg-surface-container-lowest rounded-sm shadow-2xl border ff-border-muted overflow-hidden flex flex-col">
                    <div className="px-6 py-5 border-b border-surface-container-highest flex items-start justify-between gap-4">
                        <div className="min-w-0">
                            <h2 className="font-headline text-xl font-extrabold text-on-surface flex items-center gap-2">
                                <span className="material-symbols-outlined text-primary">edit_note</span>
                                {t('edit.editRecordsTitle')}
                                <span className="text-xs font-bold text-primary bg-primary/10 px-2 py-0.5 rounded-sm">{editRecords.length}</span>
                            </h2>
                            <p className="text-sm text-on-surface-variant mt-2 leading-relaxed">{t('edit.editRecordsDesc')}</p>
                        </div>
                        <button
                            type="button"
                            onClick={()=>setEditRecordsOpen(false)}
                            className="w-9 h-9 rounded-sm bg-surface-container text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high flex items-center justify-center transition"
                        >
                            <span className="material-symbols-outlined text-lg">close</span>
                        </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-5 space-y-4">
                        {editRecords.length === 0 ? (
                            <div className="rounded-sm bg-surface-container-low px-5 py-8 text-center text-sm text-on-surface-variant">
                                {t('edit.editRecordsEmpty')}
                            </div>
                        ) : editRecords.map((record, idx) => (
                            <article key={`${record.index}-${record.start}-${idx}`} className="rounded-sm border ff-border-muted bg-surface-container-lowest overflow-hidden">
                                <div className="px-4 py-3 bg-surface-container-low flex items-center gap-3">
                                    <button
                                        type="button"
                                        onClick={()=>{ setEditRecordsOpen(false); seekToSegment(record); }}
                                        className="font-mono text-xs font-bold text-primary hover:underline"
                                    >
                                        {fmtTime(record.start || 0)}
                                    </button>
                                    <span className="text-xs font-semibold text-on-surface-variant">#{record.index + 1}</span>
                                </div>
                                <div className="p-4 space-y-3">
                                    <div className="grid md:grid-cols-2 gap-3">
                                        <div className="rounded-sm bg-red-50/70 border border-red-500/10 p-3">
                                            <p className="text-[10px] font-bold text-red-600 mb-1">{t('edit.before')}</p>
                                            <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">{record.before}</p>
                                        </div>
                                        <div className="rounded-sm bg-green-50/80 border border-green-500/10 p-3">
                                            <p className="text-[10px] font-bold text-green-700 mb-1">{t('edit.after')}</p>
                                            <p className="text-sm text-on-surface leading-relaxed whitespace-pre-wrap">{record.after}</p>
                                        </div>
                                    </div>
                                    <div className="grid md:grid-cols-2 gap-3 text-xs text-on-surface-variant">
                                        <div className="rounded-sm bg-surface-container-low p-3">
                                            <p className="font-bold mb-1">{t('edit.previousSentence')}</p>
                                            <p className="leading-relaxed whitespace-pre-wrap">{record.previous_before || record.previous_after || '-'}</p>
                                        </div>
                                        <div className="rounded-sm bg-surface-container-low p-3">
                                            <p className="font-bold mb-1">{t('edit.nextSentence')}</p>
                                            <p className="leading-relaxed whitespace-pre-wrap">{record.next_before || record.next_after || '-'}</p>
                                        </div>
                                    </div>
                                </div>
                            </article>
                        ))}
                    </div>
                </div>
            </div>
        )}
        <input
            ref={retranscribeInputRef}
            type="file"
            accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus"
            className="hidden"
            onChange={e=>{
                const file=e.target.files?.[0];
                if(e.target) e.target.value='';
                if(file) runRetranscribe(file);
            }}
        />
        <input
            ref={mediaInputRef}
            type="file"
            accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus"
            className="hidden"
            onChange={e=>{
                const file=e.target.files?.[0];
                if(e.target) e.target.value='';
                if(file) {
                    setLastSourceFile(file);
                    loadMediaFile(file);
                }
            }}
        />
        <main className="pt-6 pb-4 px-8 h-screen overflow-hidden">
            <div className="max-w-7xl mx-auto h-full min-h-0 flex flex-col gap-4">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                                            <div className="min-w-0 pr-2">
                        <h1 className="max-w-[34ch] text-[clamp(1.75rem,2.15vw,2.35rem)] leading-tight font-extrabold font-headline text-on-surface text-balance">{result.filename || t('edit.title')}</h1>
	                        <p className="max-w-[68ch] text-on-surface-variant mt-1 text-sm leading-snug">
	                            {durSec > 0 && <>{t('edit.duration')}: {fmtTime(durSec)} &bull; </>}
		                            {sttElapsedSec > 0 && <>{t('edit.sttElapsed')}: {fmtElapsed(sttElapsedSec)} {sttRealtimeFactor ? `(${fmtSttRelative(sttRealtimeFactor, lang)})` : ''} &bull; </>}
		                            {sttProfile && <>STT: {sttProfile} &bull; </>}
		                            {noteModeText && <>{t('work.summaryMode')}: {noteModeText} &bull; </>}
		                            {segments.length > 0 && <>{segments.length} {t('edit.segments')} &bull; </>}
                            <span className="text-tertiary font-semibold uppercase tracking-wider text-[10px]">{t('edit.confidence')}</span>
                        </p>
                                            </div>
                    <div className="grid grid-cols-4 gap-3 w-[360px] flex-shrink-0">
	                        <button onClick={()=>setPromptOpen(!promptOpen)} className="h-[86px] min-w-0 flex flex-col items-center justify-center gap-1.5 px-2 py-2 bg-amber-50 text-amber-700 font-semibold text-xs rounded-lg hover:bg-amber-100 transition border border-amber-200/50">
	                            <span className="material-symbols-outlined text-lg">tune</span>
	                            <span className="leading-tight text-center whitespace-normal break-keep">{promptOpen ? t('prompt.expanded') : t('prompt.collapsed')}</span>
	                        </button>
	                        <button onClick={handleRegenerate} disabled={regenerating||!transcript} className="h-[86px] min-w-0 flex flex-col items-center justify-center gap-1.5 px-2 py-2 bg-tertiary/10 text-tertiary font-semibold text-xs rounded-lg hover:bg-tertiary/20 transition disabled:opacity-40">
                            <span className={`material-symbols-outlined text-lg ${regenerating?'animate-spin':''}`}>{regenerating?'sync':'refresh'}</span>
                            <span className="leading-tight text-center whitespace-normal break-keep">{t('edit.regenerate')}</span>
                        </button>
	                        <button onClick={handleRetranscribe} disabled={retranscribing||!!currentJob} className="h-[86px] min-w-0 flex flex-col items-center justify-center gap-1.5 px-2 py-2 bg-slate-100 text-slate-700 font-semibold text-xs rounded-lg hover:bg-slate-200 transition disabled:opacity-40">
                            <span className={`material-symbols-outlined text-lg ${retranscribing?'animate-spin':''}`}>{retranscribing?'sync':'record_voice_over'}</span>
                            <span className="leading-tight text-center whitespace-normal break-keep">{retranscribing ? t('edit.retranscribing') : t('edit.retranscribe')}</span>
                        </button>
                        <button onClick={handleExportLark} disabled={exporting||!summary} className="h-[86px] min-w-0 flex flex-col items-center justify-center gap-1.5 px-2 py-2 bg-primary text-white font-semibold text-xs rounded-lg hover:bg-primary-container transition disabled:opacity-40">
                            <span className={`material-symbols-outlined text-lg ${exporting?'animate-spin':''}`}>{exporting?'sync':'cloud_upload'}</span>
                            <span className="leading-tight text-center whitespace-normal break-keep">{t('edit.export')}</span>
                        </button>
                                        </div>
                                    </div>
                                    
                {promptOpen && (
                    <div className="bg-amber-50/50 border border-amber-200/60 rounded-lg p-5 flex flex-col gap-3 animate-[fadeIn_0.2s_ease-out]">
                                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-amber-600 text-lg">auto_fix_high</span>
                                <span className="font-headline font-bold text-sm text-on-surface">{t('prompt.label')}</span>
                                <span className="text-[10px] text-amber-600/70 font-medium ml-2">{t('prompt.editHint')}</span>
                                        </div>
                                    </div>
                        <div className="flex gap-2 flex-wrap">
                            {editorPresetKeyOrder(loadSettings()).map((key) => (
                                key.startsWith('user_') ? (
                                    <span key={key} className={`inline-flex items-center gap-0.5 rounded-full border text-xs font-semibold transition-all ${
                                        promptKey===key
                                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                        : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                    }`}>
                                        <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                            className={`px-3 py-1.5 rounded-l-full ${promptKey===key?'':'hover:bg-amber-50/50'}`}>
                                            {presetLabel(key)}
                                        </button>
                                        <button type="button" title={t('set.deletePreset')} onClick={(e)=>handleDeleteUserPreset(key,e)}
                                            className={`pr-1.5 py-1 rounded-r-full flex items-center justify-center ${promptKey===key?'hover:bg-amber-700/30':'hover:bg-red-50 text-red-600'}`}>
                                            <span className="material-symbols-outlined text-[16px] leading-none">close</span>
                                        </button>
                                    </span>
                                ) : (key === 'meeting' || key === 'research' || key === 'quickBullets') ? (
                                    <span key={key} className={`inline-flex items-center gap-0.5 rounded-full border text-xs font-semibold transition-all ${
                                        promptKey===key
                                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                        : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                    }`}>
                                        <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                            className={`px-3 py-1.5 rounded-l-full ${promptKey===key?'':'hover:bg-amber-50/50'}`}>
                                            {presetLabel(key)}
                                        </button>
                                        <button
                                            type="button"
                                            title={t('set.deleteBuiltinPrompt')}
                                            onClick={(e)=>{ e.stopPropagation(); e.preventDefault(); resetBuiltinExtra(key); }}
                                            className={`pr-1.5 py-1 rounded-r-full flex items-center justify-center ${promptKey===key?'hover:bg-amber-700/30':'hover:bg-red-50 text-red-600'}`}
                                        >
                                            <span className="material-symbols-outlined text-[16px] leading-none">close</span>
                                        </button>
                                    </span>
                                ) : (
                                <button key={key} onClick={()=>handlePromptKeyChange(key)}
                                    className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all border ${
                                        promptKey===key
                                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                        : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                    }`}>
                                    {presetLabel(key)}
                                </button>
                                )
                            ))}
                                </div>
                        {promptKey === 'default' ? (
                            <div className="space-y-2">
                                <label className="text-xs font-medium text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                                <textarea
                                    className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                    value={defaultPromptEdit}
                                    onChange={(e)=>handleDefaultPromptChange(e.target.value)}
                                />
                            </div>
                        ) : promptKey.startsWith('user_') ? (
                            <div className="space-y-2">
                                <label className="text-xs font-medium text-on-surface-variant">{lang==='zh'?'编辑该预设':'Edit this preset'}</label>
                                <textarea
                                    className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                    value={userPresetEdit}
                                    onChange={(e)=>handleUserPresetChange(e.target.value)}
                                />
                        </div>
                        ) : promptKey === 'custom' ? (
                            <div className="space-y-3">
                                <textarea
                                    className="w-full h-32 bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface placeholder-slate-400 focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                    placeholder={t('prompt.customPlaceholder')}
                                    value={customText}
                                    onChange={e=>handleCustomTextChange(e.target.value)}
                                />
                                <div className="flex flex-wrap items-end gap-2">
                                    <input type="text" className="flex-1 min-w-[160px] bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder={t('set.presetNamePh')} value={presetNameInput} onChange={e=>setPresetNameInput(e.target.value)} />
                                    <button type="button" onClick={saveCustomAsPresetFromEditor} className="px-4 py-2 bg-amber-600 text-white text-sm font-semibold rounded-lg hover:bg-amber-700 transition">
                                        {t('prompt.saveAsPreset')}
                                    </button>
                    </div>
            </div>
                        ) : promptKey === 'meeting' || promptKey === 'research' || promptKey === 'quickBullets' ? (
                            <div className="space-y-2">
                                <div className="flex flex-wrap justify-between items-center gap-2">
                                    <label className="text-xs font-medium text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                    <button type="button" onClick={()=>resetBuiltinExtra(promptKey)} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                            </div>
                                <textarea
                                    className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                    value={promptKey === 'meeting' ? meetingEdit : promptKey === 'research' ? researchEdit : quickBulletsEdit}
                                    onChange={(e)=>handleBuiltinExtraChange(promptKey, e.target.value)}
                                />
                            </div>
                        ) : null}
                        </div>
                )}

                        <div className="flex-1 min-h-0 flex gap-4 overflow-hidden">
                            <section className="flex-1 min-h-0 bg-surface-container-low rounded-sm flex flex-col overflow-hidden">
                                <div className="p-5 flex justify-between items-center border-b border-surface-container-highest">
                                    <div className="min-w-0">
                                        <h2 className="font-headline font-bold text-lg flex items-center gap-2">
                                            <span className="material-symbols-outlined text-primary">subject</span>
                                            {t('edit.transcript')}
	                                            {transcriptDirty && <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200/50 px-2 py-0.5 rounded-full">{t('edit.editedTranscript')}</span>}
                                                {segments.length === 0 && <span className="text-[10px] font-bold text-slate-600 bg-white/60 border border-slate-200/60 px-2 py-0.5 rounded-full">{lang==='zh'?'纯文本模式':'Plain text'}</span>}
	                                            {transcriptSaveStatus !== 'idle' && (
                                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                                    transcriptSaveStatus === 'failed'
                                                        ? 'text-red-600 bg-red-50 border border-red-500/20'
                                                        : 'text-emerald-700 bg-green-50 border border-green-500/20'
                                                }`}>
                                                    {transcriptSaveStatus === 'saving'
                                                        ? t('edit.transcriptSaving')
                                                        : transcriptSaveStatus === 'failed'
                                                            ? t('edit.transcriptSaveFailed')
                                                            : t('edit.transcriptSaved')}
                                                </span>
                                            )}
                                        </h2>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={()=>setEditRecordsOpen(true)}
                                    className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-primary bg-blue-50 hover:bg-blue-100 rounded-lg transition border border-blue-200/50"
                                >
                                    <span className="material-symbols-outlined text-sm">edit_note</span>
                                    {t('edit.editRecords')} {editRecords.length}
                                </button>
                                <DropdownMenu
                                    trigger={
                                        <button className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-primary bg-blue-50 hover:bg-blue-100 rounded-lg transition border border-blue-200/50">
                                            <span className="material-symbols-outlined text-sm">download</span>
                                            {t('dl.transcript')}
                                        </button>
                                    }
                                    items={[
                                        {icon:'description', label:t('dl.txt'), badge:'TXT', onClick:()=>{dlTranscriptTxt(transcript,result.filename); recordDownload('transcript_downloaded','txt'); showToast(t('dl.success'));}},
                                        {icon:'subtitles', label:t('dl.srt'), badge:'SRT', disabled:segments.length===0, onClick:()=>{dlTranscriptSrt(segments,result.filename); recordDownload('transcript_downloaded','srt'); showToast(t('dl.success'));}},
                                        {icon:'closed_caption', label:t('dl.vtt'), badge:'VTT', disabled:segments.length===0, onClick:()=>{dlTranscriptVtt(segments,result.filename); recordDownload('transcript_downloaded','vtt'); showToast(t('dl.success'));}},
                                    ]}
                                />
                                </div>
                                            </div>
                        <div ref={transcriptScrollRef} className="flex-1 min-h-0 overflow-y-auto p-5 space-y-2 hide-scrollbar">
                            {segments.length > 0 ? segments.map((seg,i) => (
                                <div
                                    key={i}
                                    ref={(node)=>{ if(node) segmentRefs.current[i]=node; }}
                                    className={`flex gap-4 group rounded-sm px-2 py-2 transition-colors ${i===activeSegmentIndex && mediaUrl ? 'bg-primary/10' : 'hover:bg-surface-container'}`}
                                >
                                    <button
                                        type="button"
                                        onClick={()=>seekToSegment(seg)}
                                        className={`text-xs font-mono pt-2 w-14 flex-shrink-0 text-left transition ${i===activeSegmentIndex && mediaUrl ? 'text-primary font-bold' : 'text-slate-400 hover:text-primary'}`}
                                    >
                                        {fmtTime(seg.start)}
                                    </button>
                                    <textarea
                                        data-transcript-segment="true"
                                        value={seg.text || ''}
                                        ref={autoSizeTextarea}
                                        onChange={(e)=>{ autoSizeTextarea(e.target); handleSegmentTextChange(i, e.target.value); }}
                                        onFocus={()=>setFollowPlayback(false)}
                                        rows={1}
                                        className="flex-1 resize-none overflow-hidden min-h-[2rem] bg-transparent border-none p-0 text-on-surface text-sm leading-relaxed focus:ring-0"
                                    />
                                        </div>
	                            )) : (
                                    <div className="min-h-full flex flex-col gap-3">
                                        <div className="rounded-sm border border-amber-200/60 bg-amber-50/60 px-3 py-2 flex items-start gap-2">
                                            <span className="material-symbols-outlined text-amber-700 text-base mt-0.5">info</span>
                                            <p className="text-xs leading-relaxed text-slate-700">
                                                {lang==='zh'
                                                    ? '当前结果没有时间戳分段，只能按纯文本编辑。常见原因是旧历史记录、纯文本导入，或任务结果没有成功写入后端。重新转录原音频后会恢复左侧时间戳分段。'
                                                    : 'This result has no timestamped segments, so it is shown as plain text. This usually comes from old history, plain-text import, or a result that was not saved to the backend. Retranscribing the source audio restores timestamped segments.'}
                                            </p>
                                        </div>
	                                <textarea
	                                    value={transcript}
	                                    onChange={(e)=>handlePlainTranscriptChange(e.target.value)}
	                                    onFocus={()=>setFollowPlayback(false)}
	                                    className="w-full flex-1 min-h-[320px] resize-none bg-transparent border-none p-0 text-on-surface text-sm leading-relaxed whitespace-pre-wrap focus:ring-0"
	                                />
                                    </div>
	                            )}
                                </div>
                                <div className="border-t border-surface-container-highest bg-surface-container-lowest/80 p-4">
                                    <video
                                        ref={mediaRef}
                                        src={mediaUrl || undefined}
                                        className="hidden"
                                        onTimeUpdate={(e)=>setMediaCurrentTime(e.currentTarget.currentTime || 0)}
                                        onLoadedMetadata={(e)=>setMediaDuration(e.currentTarget.duration || durSec || 0)}
                                        onPlay={()=>setMediaPlaying(true)}
                                        onPause={()=>setMediaPlaying(false)}
                                        onEnded={()=>setMediaPlaying(false)}
                                    />
                                    {mediaUrl ? (
                                        <div className="space-y-3">
                                            <div className="flex items-center gap-3">
                                                <button type="button" onClick={togglePlayback} className="w-9 h-9 rounded-sm bg-primary text-white flex items-center justify-center hover:bg-primary-container transition">
                                                    <span className="material-symbols-outlined text-lg">{mediaPlaying ? 'pause' : 'play_arrow'}</span>
                                                </button>
                                                <button type="button" onClick={()=>setFollowPlayback(v=>!v)} className={`px-2.5 py-1.5 rounded-sm text-xs font-bold transition ${followPlayback?'bg-blue-50 text-primary':'bg-surface-container text-on-surface-variant'}`}>
                                                    {t('edit.followPlayback')}
                                                </button>
                                                <span className="text-xs font-mono text-on-surface-variant ml-auto">{fmtTime(mediaCurrentTime)} / {fmtTime(playbackDuration || mediaCurrentTime)}</span>
                                            </div>
                                            <input
                                                type="range"
                                                min="0"
                                                max={Math.max(1, playbackDuration)}
                                                step="0.1"
                                                value={Math.min(mediaCurrentTime, Math.max(1, playbackDuration))}
                                                onChange={(e)=>{
                                                    const next = Number(e.target.value) || 0;
                                                    if(mediaRef.current) mediaRef.current.currentTime = next;
                                                    setMediaCurrentTime(next);
                                                }}
                                                className="w-full accent-primary"
                                                style={{background:`linear-gradient(90deg, #3B82F6 ${mediaProgress}%, var(--c-surface-container-highest) ${mediaProgress}%)`}}
                                            />
                                        </div>
                                    ) : (
                                        <div className="flex items-center justify-between gap-3">
                                            <p className="text-xs text-on-surface-variant">{mediaLoading ? t('edit.sourceLoading') : (mediaError || t('edit.audioUnavailable'))}</p>
                                            <button type="button" onClick={()=>mediaInputRef.current?.click()} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-sm bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-container-high transition">
                                                <span className="material-symbols-outlined text-sm">audio_file</span>{t('edit.chooseAudio')}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </section>

                            <section className="flex-1 min-h-0 bg-surface-container-lowest rounded-sm flex flex-col shadow-sm overflow-hidden">
                                <div className="p-5 flex justify-between items-center bg-tertiary/5 border-b border-surface-container-highest">
                                    <h2 className="font-headline font-bold text-lg flex items-center gap-2">
                                        <span className="material-symbols-outlined text-tertiary">psychology</span>
                                {t('edit.aiSummary')}
                                    </h2>
                            <div className="flex items-center gap-2">
                            <span className="text-[10px] font-semibold text-amber-600 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200/50">
                                {t('prompt.activeHint')}{presetLabel(promptKey)}
                            </span>
                                <DropdownMenu
                                    trigger={
                                        <button disabled={!summary || !!downloading} className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-tertiary bg-purple-50 hover:bg-purple-100 rounded-lg transition border border-purple-200/50 disabled:opacity-40">
                                            <span className={`material-symbols-outlined text-sm ${downloading?'animate-spin':''}`}>{downloading?'sync':'download'}</span>
                                            {downloading ? t('dl.generating') : t('dl.summary')}
                                    </button>
                                    }
                                    items={[
                                        {icon:'description', label:t('dl.txt'), badge:'TXT', disabled:!summary, onClick:()=>{dlSummaryTxt(summary,result.filename); recordDownload('summary_downloaded','txt'); showToast(t('dl.success'));}},
                                        {icon:'markdown', label:t('dl.md'), badge:'MD', disabled:!summary, onClick:()=>{dlSummaryMd(summary,result.filename); recordDownload('summary_downloaded','md'); showToast(t('dl.success'));}},
                                        {divider:true},
                                        {icon:'picture_as_pdf', label:t('dl.pdf'), badge:'PDF', disabled:!summary, onClick:async()=>{
                                            setDownloading('pdf');
                                            try{ await dlSummaryPdf(summaryRef,result.filename); recordDownload('summary_downloaded','pdf'); showToast(t('dl.success')); }catch(e){showToast(e.message,false);}
                                            finally{setDownloading(null);}
                                        }},
                                        {icon:'article', label:t('dl.word'), badge:'DOC', disabled:!summary, onClick:()=>{dlSummaryWord(summary,result.filename); recordDownload('summary_downloaded','doc'); showToast(t('dl.success'));}},
                                    ]}
                                />
                            </div>
                                </div>
                                <div className="flex-1 min-h-0 overflow-y-auto p-8 hide-scrollbar">
	                            {summary ? (
	                                <div ref={summaryRef} dangerouslySetInnerHTML={{__html: simpleMd(summary)}}></div>
	                            ) : result.summary_skipped ? (
	                                <p className="text-on-surface-variant text-sm italic">{t('edit.summarySkipped')}</p>
	                            ) : (
	                                <p className="text-on-surface-variant text-sm italic">{t('edit.summaryPending')}</p>
                            )}
                                </div>
                                <div className="p-4 bg-tertiary-fixed border-t border-tertiary/20 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-tertiary text-sm" style={{fontVariationSettings:"'FILL' 1"}}>verified</span>
                                <span className="text-[10px] font-bold text-on-tertiary-fixed-variant uppercase tracking-widest">{t('edit.confidence')}</span>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                </main>
            </div>
        );
};

/* ═══════════════ Settings ═══════════════ */
        const Settings = () => {
    const {t, lang} = useI18n();
    const {loadSettings,saveSettings} = useSettings();
    const {clearHistory,history,larkExports} = useApp();
    const [settings,setSettings] = useState(() => loadSettings());
    const [saved,setSaved] = useState(false);
    const [cleared,setCleared] = useState(false);
    const [clearArmed,setClearArmed] = useState(false);
    const templateCount = allPresetSelectKeys(settings).length;

    // 如果当前已被隐藏的内置模板仍被选中，兜底切回 default
    useEffect(() => {
        const pk = (settings && settings.promptPreset) || 'default';
        if (isBuiltinPromptPresetHidden(pk, settings)) {
            const next = { ...settings, promptPreset: 'default' };
            setSettings(next);
            saveSettings(next);
        }
    }, []);

    const isDark = settings.theme === 'dark';
    const applyTheme = (theme) => {
        const next = {...settings, theme};
        setSettings(next);
        saveSettings(next);
        document.documentElement.classList.toggle('dark', theme==='dark');
    };

    const handleSave = () => { saveSettings(settings); setSaved(true); setTimeout(()=>setSaved(false),2000); };
    const updateSettingNow = (patch) => {
        setSettings((s) => {
            const next = {...s, ...patch};
            saveSettings(next);
            return next;
        });
    };

    const resetDefaultPromptInSettings = () => {
        setSettings((s) => {
            const next = { ...s, defaultPromptOverride: '' };
            saveSettings(next);
            return next;
        });
    };

    const resetBuiltinOverrideInSettings = (key) => {
        if (!window.confirm(t('set.deleteBuiltinPromptConfirm'))) return;
        setSettings((s) => {
            const hidden = new Set(Array.isArray(s.hiddenPromptPresets) ? s.hiddenPromptPresets : []);
            hidden.add(key);
            const next = {
                ...s,
                hiddenPromptPresets: Array.from(hidden),
                promptPreset: s.promptPreset === key ? 'default' : s.promptPreset,
            };
            saveSettings(next);
            return next;
        });
        if (templateEditKey === key) setTemplateEditKey('default');
    };

    const [newPresetNameSettings, setNewPresetNameSettings] = useState('');
    const initialTemplateEditKey = (() => {
        const key = settings.promptPreset || 'default';
        return isBuiltinPromptPresetHidden(key, settings) ? 'default' : key;
    })();
    const [templateEditKey, setTemplateEditKey] = useState(initialTemplateEditKey);

    const saveCustomAsPresetInSettings = () => {
        const name = newPresetNameSettings.trim();
        if (!name || !(settings.customPromptText || '').trim()) return;
        const id = 'user_' + Date.now();
        setSettings((s) => {
            const next = {
                ...s,
                userPromptPresets: [{ id, nameZh: name, nameEn: name, prompt: s.customPromptText }, ...(s.userPromptPresets || [])],
            };
            saveSettings(next);
            return next;
        });
        setNewPresetNameSettings('');
    };

    const deleteUserPresetInSettings = (id) => {
        if (!window.confirm(t('set.deletePresetConfirm'))) return;
        setSettings((s) => {
            const ups = normalizeUserPresets(s).filter((p) => p.id !== id);
            const next = { ...s, userPromptPresets: ups };
            if (next.promptPreset === id) next.promptPreset = 'default';
            saveSettings(next);
            return next;
        });
    };

    const handleClear = () => {
        if(history.length === 0) return;
        if(!clearArmed){
            setClearArmed(true);
            setTimeout(()=>setClearArmed(false), 5000); // 5秒内二次确认
            return;
        }
        setClearArmed(false);
        clearHistory();
        setCleared(true);
        setTimeout(()=>setCleared(false),2000);
            };

    const preferencesPanel = (
        <section className="bg-surface-container-lowest/95 backdrop-blur-xl rounded-sm p-4 shadow-sm border ff-border-muted w-full xl:w-[420px] flex-shrink-0">
            <div className="flex items-center justify-between gap-3 mb-3">
                <h2 className="text-sm font-bold font-headline text-on-surface">{t('set.prefs')}</h2>
                <div className="grid grid-cols-2 gap-1 p-1 bg-surface-container-low rounded-sm">
                    <button onClick={()=>applyTheme('light')} className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm text-xs font-semibold transition ${!isDark?'bg-primary text-white shadow-sm':'text-on-surface-variant hover:bg-surface-container-high'}`}>
                        <span className="material-symbols-outlined text-sm">light_mode</span>{t('set.light')}
                    </button>
                    <button onClick={()=>applyTheme('dark')} className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm text-xs font-semibold transition ${isDark?'bg-primary text-white shadow-sm':'text-on-surface-variant hover:bg-surface-container-high'}`}>
                        <span className="material-symbols-outlined text-sm">dark_mode</span>{t('set.dark')}
                    </button>
                </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
                <button onClick={handleClear} disabled={history.length===0} className={`py-3 px-3 rounded-sm font-semibold text-xs transition disabled:opacity-30 flex items-center justify-center gap-2 ${clearArmed?'bg-red-600 text-white ring-2 ring-red-300/70':'bg-red-50 text-red-600 hover:bg-red-100'}`}>
                    <span className="material-symbols-outlined text-sm">delete_sweep</span>
                    {cleared ? t('edit.clearConfirm') : (clearArmed ? t('edit.clearConfirmAgain') : `${t('edit.clearHistory')} (${history.length})`)}
                </button>
                <button onClick={handleSave} className="py-3 px-3 bg-primary-container text-white rounded-sm font-bold text-xs shadow-lg shadow-primary/20 hover:scale-[1.02] transition-all flex items-center justify-center gap-2">
                    <span className="material-symbols-outlined text-sm">{saved?"check":"save"}</span>
                    {saved ? t('set.saved') : t('set.saveAll')}
                </button>
            </div>
            {clearArmed && (
                <p className="mt-2 text-[11px] font-medium text-red-600 text-center">{t('edit.clearConfirmAgain')}</p>
            )}
        </section>
    );

            return (
            <div className="ml-64 min-h-screen relative pb-8">
                <main className="p-12 max-w-7xl mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                    <header className="mb-8 flex flex-col xl:flex-row xl:items-start justify-between gap-6">
                <div className="min-w-0 pt-2">
                    <h1 className="text-4xl font-extrabold tracking-tight text-on-surface mb-2 font-headline">{t('set.title')}</h1>
                    <p className="text-on-surface-variant font-medium max-w-2xl">{lang==='zh'?'这里保留提示词模板、导出历史和应用偏好；运行凭证已移到工作台。':'Keep prompt templates, export history, and app preferences here; run credentials moved to Workbench.'}</p>
                    <div className="mt-5 flex flex-wrap gap-2">
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">auto_fix_high</span>{lang==='zh'?`模板 ${templateCount}`:`Templates ${templateCount}`}
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">history</span>{lang==='zh'?`导出 ${larkExports.length}`:`Exports ${larkExports.length}`}
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">folder_open</span>{lang==='zh'?`历史 ${history.length}`:`History ${history.length}`}
                        </span>
                    </div>
                </div>
                {preferencesPanel}
                    </header>
                    <div className="space-y-8">
                    {larkExports.length > 0 && (
                    <section className="bg-surface-container-lowest rounded-sm p-8 shadow-sm">
                        <div className="flex items-center gap-4 mb-6">
                            <div className="w-10 h-10 rounded-sm bg-green-50 flex items-center justify-center text-green-600">
                                <span className="material-symbols-outlined">history</span>
                                    </div>
                            <div>
                                <h2 className="text-lg font-bold tracking-tight font-headline">{t('set.larkHistory')}</h2>
                                <p className="text-xs text-on-surface-variant">{larkExports.length} {t('dash.docUnit')}</p>
                            </div>
                        </div>
                        <div className="space-y-3 max-h-64 overflow-y-auto hide-scrollbar">
                            {larkExports.map((ex,i) => (
                                <a key={i} href={ex.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 p-4 rounded-lg bg-surface-container-low hover:bg-blue-50 transition group">
                                    <span className="material-symbols-outlined text-primary text-lg" style={{fontVariationSettings:"'FILL' 1"}}>description</span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-on-surface truncate group-hover:text-primary">{ex.title}</p>
                                        <p className="text-[10px] text-slate-400">{timeAgo(ex.timestamp, t)}</p>
                                    </div>
                                    <span className="material-symbols-outlined text-slate-300 group-hover:text-primary text-sm">open_in_new</span>
                                </a>
                            ))}
                                </div>
                            </section>
                    )}
                    <section className="bg-surface-container-lowest rounded-sm shadow-sm overflow-hidden">
                        <div className="px-8 py-6 border-b ff-border-muted flex flex-col lg:flex-row lg:items-center justify-between gap-5">
                            <div className="flex items-center gap-4 min-w-0">
                            <div className="w-11 h-11 rounded-sm bg-amber-50 flex items-center justify-center text-amber-600 flex-shrink-0">
                                <span className="material-symbols-outlined text-2xl">auto_fix_high</span>
                            </div>
                            <div className="min-w-0">
                                <h2 className="text-xl font-bold tracking-tight font-headline">{t('set.promptTitle')}</h2>
                                <p className="text-sm text-on-surface-variant">{t('set.promptDesc')}</p>
                            </div>
                        </div>
                            <div className="w-full lg:w-[320px] space-y-2 flex-shrink-0">
                                <label className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">{t('set.templateToEdit')}</label>
                                <select className="w-full bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20" value={templateEditKey} onChange={e=>setTemplateEditKey(e.target.value)}>
                                    {allPresetSelectKeys(settings).map((key) => (
                                        <option key={key} value={key}>{presetDisplayLabel(key, settings, lang)}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="p-8 space-y-5">
                            {templateEditKey==='default' && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                                        <button type="button" onClick={resetDefaultPromptInSettings} className="text-xs font-semibold text-primary hover:underline">{t('set.resetBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getDefaultPromptBody(settings)} onChange={e=>setSettings(s=>({...s,defaultPromptOverride:e.target.value}))}/>
                                </div>
                            )}
                            {templateEditKey==='custom' && (
                                <div className="space-y-3">
                                    <div className="space-y-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{lang==='zh'?'自定义提示词':'Custom Prompt'}</label>
                                        <textarea className="w-full h-40 bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" placeholder={t('prompt.customPlaceholder')} value={settings.customPromptText||''} onChange={e=>setSettings(s=>({...s,customPromptText:e.target.value}))}/>
                                    </div>
                                    <div className="flex flex-wrap items-end gap-2">
                                        <input type="text" className="flex-1 min-w-[200px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm" placeholder={t('set.presetNamePh')} value={newPresetNameSettings} onChange={e=>setNewPresetNameSettings(e.target.value)} />
                                        <button type="button" onClick={saveCustomAsPresetInSettings} className="px-4 py-3 bg-amber-600 text-white text-sm font-semibold rounded-sm hover:bg-amber-700 transition">{t('set.saveAsPreset')}</button>
                                    </div>
                                </div>
                            )}
                            {templateEditKey==='meeting' && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                        <button type="button" onClick={()=>resetBuiltinOverrideInSettings('meeting')} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getBuiltinExtraPromptBody('meeting', settings)} onChange={e=>setSettings(s=>({...s,promptOverrides:{...(s.promptOverrides||{}),meeting:e.target.value}}))}/>
                                </div>
                            )}
                            {templateEditKey==='research' && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                        <button type="button" onClick={()=>resetBuiltinOverrideInSettings('research')} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getBuiltinExtraPromptBody('research', settings)} onChange={e=>setSettings(s=>({...s,promptOverrides:{...(s.promptOverrides||{}),research:e.target.value}}))}/>
                                </div>
                            )}
                            {templateEditKey==='quickBullets' && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                        <button type="button" onClick={()=>resetBuiltinOverrideInSettings('quickBullets')} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getBuiltinExtraPromptBody('quickBullets', settings)} onChange={e=>setSettings(s=>({...s,promptOverrides:{...(s.promptOverrides||{}),quickBullets:e.target.value}}))}/>
                                </div>
                            )}
                            {normalizeUserPresets(settings).length > 0 && (
                                <div className="space-y-2">
                                    <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.myPresets')}</label>
                                    <ul className="space-y-2">
                                        {normalizeUserPresets(settings).map((p) => (
                                            <li key={p.id} className="flex items-center justify-between gap-3 p-3 rounded-sm bg-surface-container-low">
                                                <span className="text-sm text-on-surface truncate flex-1" title={lang==='zh'?p.nameZh:p.nameEn}>{lang==='zh'?p.nameZh:p.nameEn}</span>
                                                <button type="button" onClick={()=>deleteUserPresetInSettings(p.id)} className="text-xs font-semibold text-red-600 hover:underline flex-shrink-0">{t('set.deletePreset')}</button>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    </section>
                    </div>
                </main>
            </div>
            );
        };

/* ═══════════════ App root ═══════════════ */
const AccessGate = ({children}) => {
    const {lang} = useI18n();
    const [checking, setChecking] = useState(true);
    const [required, setRequired] = useState(false);
    const [authenticated, setAuthenticated] = useState(false);
    const [authMode, setAuthMode] = useState('open');
    const [allowSignups, setAllowSignups] = useState(false);
    const [bootstrapRequired, setBootstrapRequired] = useState(false);
    const [user, setUser] = useState(null);
    const [formMode, setFormMode] = useState('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [token, setToken] = useState(getAccessToken());
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const refreshStatus = useCallback(async () => {
        setChecking(true);
        try {
            const r = await apiFetch(`${API_BASE}/auth/status`);
            const data = await r.json().catch(()=>({}));
            const nextMode = data.auth_mode || (data.access_required ? 'access_code' : 'open');
            const nextRequired = !!(data.account_required || data.access_required);
            setAuthMode(nextMode);
            setRequired(nextRequired);
            setAuthenticated(!nextRequired || !!data.authenticated);
            setAllowSignups(!!data.allow_signups);
            setBootstrapRequired(!!data.bootstrap_required);
            setUser(data.user || null);
            if (data.bootstrap_required) setFormMode('register');
        } catch(_) {
            setAuthMode('open');
            setRequired(false);
            setAuthenticated(true);
            setUser(null);
        } finally {
            setChecking(false);
        }
    }, []);

    useEffect(() => { refreshStatus(); }, [refreshStatus]);

    const logout = useCallback(async () => {
        try {
            await apiFetch(`${API_BASE}/auth/logout`, {method:'POST'});
        } catch(_) {}
        setAccessToken('');
        setToken('');
        setUser(null);
        setAuthenticated(false);
        await refreshStatus();
    }, [refreshStatus]);

    const submit = async (e) => {
        e.preventDefault();
        setError('');
        setSubmitting(true);
        try {
            const accountFlow = authMode === 'accounts';
            const endpoint = accountFlow && formMode === 'register' ? '/auth/register' : '/auth/login';
            const body = accountFlow
                ? {email: email.trim(), password}
                : {access_token: token.trim()};
            const r = await apiFetch(`${API_BASE}${endpoint}`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body),
            });
            const data = await r.json().catch(()=>({}));
            if(!r.ok) {
                const fallback = accountFlow
                    ? (lang === 'zh' ? '账号验证失败' : 'Account authentication failed')
                    : (lang === 'zh' ? '访问码不正确' : 'Invalid access code');
                throw new Error(data.detail || fallback);
            }
            if (accountFlow) {
                setUser(data.user || null);
                setPassword('');
            } else {
                setAccessToken(token.trim());
            }
            setAuthenticated(true);
        } catch(err) {
            setError(err.message || (lang === 'zh' ? '无法进入' : 'Access failed'));
        } finally {
            setSubmitting(false);
        }
    };

    if (checking) {
        return <div className="min-h-screen bg-surface flex items-center justify-center text-sm font-semibold text-on-surface-variant">{lang === 'zh' ? '正在检查访问权限…' : 'Checking access…'}</div>;
    }
    if (!required || authenticated) {
        return <AuthCtx.Provider value={{authMode, user, logout}}>{children}</AuthCtx.Provider>;
    }

    const accountFlow = authMode === 'accounts';
    const canRegister = allowSignups || bootstrapRequired;
    const registerMode = accountFlow && formMode === 'register';
    const title = accountFlow
        ? (registerMode
            ? (bootstrapRequired ? (lang === 'zh' ? '创建管理员账号' : 'Create admin account') : (lang === 'zh' ? '创建账号' : 'Create account'))
            : (lang === 'zh' ? '登录 FluentFlow' : 'Sign in to FluentFlow'))
        : (lang === 'zh' ? '输入访问码' : 'Enter access code');
    const description = accountFlow
        ? (registerMode
            ? (lang === 'zh' ? '首次部署需要创建一个管理员账号。之后任务历史和额度会跟随账号。' : 'Create the first admin account. Jobs and quota will follow this account.')
            : (lang === 'zh' ? '登录后继续查看你的转录任务、字幕和笔记。' : 'Sign in to continue with your transcription jobs, subtitles, and notes.'))
        : (lang === 'zh' ? '当前版本用于小范围试用。访问码由产品维护者提供。' : 'This beta is invite-only. Ask the product maintainer for an access code.');

    return (
        <main className="min-h-screen bg-surface flex items-center justify-center px-6">
            <form onSubmit={submit} className="w-full max-w-[460px] rounded-sm bg-surface-container-lowest p-8 shadow-xl border border-outline-variant/30 dark:border-white/10">
                <div className="space-y-2 mb-6">
                    <p className="text-xs font-bold uppercase tracking-widest text-primary">FluentFlow</p>
                    <h1 className="text-3xl font-headline font-bold text-on-surface">{title}</h1>
                    <p className="text-sm leading-relaxed text-on-surface-variant">
                        {description}
                    </p>
                </div>
                {accountFlow ? (
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang === 'zh' ? '邮箱' : 'Email'}
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e)=>setEmail(e.target.value)}
                                className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                placeholder="you@example.com"
                                autoFocus
                                autoComplete="email"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang === 'zh' ? '密码' : 'Password'}
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e)=>setPassword(e.target.value)}
                                className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                placeholder={lang === 'zh' ? '至少 8 位' : 'At least 8 characters'}
                                autoComplete={registerMode ? 'new-password' : 'current-password'}
                            />
                        </div>
                    </div>
                ) : (
                    <div className="space-y-2">
                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                            {lang === 'zh' ? '访问码' : 'Access code'}
                        </label>
                        <input
                            type="password"
                            value={token}
                            onChange={(e)=>setToken(e.target.value)}
                            className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                            placeholder={lang === 'zh' ? '访问码' : 'Access code'}
                            autoFocus
                        />
                    </div>
                )}
                {error && <p className="mt-4 text-sm font-semibold text-red-600">{error}</p>}
                <div className="mt-6 flex flex-col gap-3">
                    <button
                        type="submit"
                        disabled={submitting || (accountFlow ? (!email.trim() || !password) : !token.trim())}
                        className="h-12 rounded-sm bg-primary px-5 text-sm font-extrabold text-white transition hover:bg-primary/90 disabled:opacity-50"
                    >
                        {submitting
                            ? (lang === 'zh' ? '处理中' : 'Working')
                            : (registerMode ? (lang === 'zh' ? '创建并进入' : 'Create and enter') : (lang === 'zh' ? '进入' : 'Enter'))}
                    </button>
                    {accountFlow && canRegister && !bootstrapRequired && (
                        <button
                            type="button"
                            onClick={()=>{setError(''); setFormMode(registerMode ? 'login' : 'register');}}
                            className="h-11 rounded-sm bg-surface-container-low px-4 text-sm font-bold text-on-surface-variant transition hover:bg-surface-container-high hover:text-on-surface"
                        >
                            {registerMode
                                ? (lang === 'zh' ? '已有账号，去登录' : 'Already have an account')
                                : (lang === 'zh' ? '没有账号，创建一个' : 'Create an account')}
                        </button>
                    )}
                </div>
            </form>
        </main>
    );
};

const App = () => (
                <div className="flex min-h-screen w-full bg-surface">
        <SideNav/>
                    <div className="flex-1 flex flex-col w-full h-full relative">
                        <Routes>
                <Route path="/" element={<Dashboard/>}/>
                <Route path="/tasks" element={<Tasks/>}/>
                <Route path="/processing" element={<Processing/>}/>
                <Route path="/editor" element={<Editor/>}/>
                <Route path="/settings" element={<Settings/>}/>
                        </Routes>
                    </div>
                </div>
            );

createRoot(document.getElementById('root')).render(
    <BrowserRouter><I18nProvider><AccessGate><AppProvider><App/></AppProvider></AccessGate></I18nProvider></BrowserRouter>
        );
