import {useMemo} from 'react';
import {Link} from 'react-router-dom';
import SvgIcon from '../components/SvgIcon.jsx';
import {
    effectiveSttProvider,
    displayTitleForUser,
    fmtElapsed,
    fmtFileSize,
    isCloudSttProvider,
    noteModeLabel,
    useApp,
    useI18n,
    useSettings,
} from '../app/shared.jsx';

const STAGE_ORDER = {
    queued: 0,
    upload: 0,
    resolving: 1,
    downloading: 1,
    audio: 2,
    stt: 3,
    cleanup: 4,
    summary: 5,
    export: 6,
    done: 7,
    error: 99,
    cancelled: 99,
};

const languageLabel = (value, lang) => {
    const normalized = String(value || '').toLowerCase();
    if (!normalized || normalized === 'auto') return lang === 'zh' ? '自动识别' : 'Auto detect';
    if (normalized.startsWith('en')) return lang === 'zh' ? '英文' : 'English';
    if (normalized.startsWith('zh') || normalized.startsWith('cmn')) return lang === 'zh' ? '中文' : 'Chinese';
    return value;
};

const stageLabel = (stage, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        queued: isZh ? '排队中' : 'Queued',
        upload: isZh ? '接收材料' : 'Receiving',
        resolving: isZh ? '解析链接' : 'Resolving link',
        downloading: isZh ? '下载视频' : 'Downloading',
        audio: isZh ? '提取音频' : 'Extracting audio',
        stt: isZh ? '转录中' : 'Transcribing',
        cleanup: isZh ? '整理转录' : 'Cleaning transcript',
        summary: isZh ? '生成笔记' : 'Generating note',
        export: isZh ? '导出飞书' : 'Exporting',
        done: isZh ? '已完成' : 'Done',
        error: isZh ? '失败' : 'Failed',
        cancelled: isZh ? '已取消' : 'Cancelled',
    };
    return labels[stage] || (isZh ? '处理中' : 'Processing');
};

const routeLabel = (provider, lang) => {
    if (provider === 'elevenlabs_scribe') return lang === 'zh' ? 'ElevenLabs 云端转录' : 'ElevenLabs cloud STT';
    if (provider === 'azure_batch') return lang === 'zh' ? '历史云端转录' : 'Legacy cloud STT';
    if (provider === 'local') return lang === 'zh' ? '本地 faster-whisper' : 'Local faster-whisper';
    return isCloudSttProvider(provider) ? (lang === 'zh' ? '云端转录' : 'Cloud STT') : (lang === 'zh' ? '按设置决定' : 'From Settings');
};

const executionScopeLabel = (scope, lang) => {
    if (scope === 'cloud') return lang === 'zh' ? '云端执行' : 'Cloud execution';
    if (scope === 'local') return lang === 'zh' ? '本机执行' : 'Local execution';
    return lang === 'zh' ? '执行位置待确认' : 'Execution scope unknown';
};

const materialTypeLabel = (type, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        course_transcript_file: isZh ? '课程字幕文件' : 'Course transcript file',
        course_material: isZh ? '课程材料' : 'Course material',
        lecture_material: isZh ? '讲座材料' : 'Lecture material',
        course_video_pending_content: isZh ? '待转录课程视频' : 'Course video pending transcript',
        lecture_video_pending_content: isZh ? '待转录讲座视频' : 'Lecture video pending transcript',
    };
    return labels[type] || type || (isZh ? '待判断' : 'Pending');
};

const planStepIcon = (id, tool) => {
    const value = `${id || ''} ${tool || ''}`.toLowerCase();
    if (value.includes('ingest')) return 'upload_file';
    if (value.includes('transcribe') || value.includes('stt') || value.includes('whisper')) return 'mic_external_on';
    if (value.includes('subtitle')) return 'closed_caption';
    if (value.includes('note') || value.includes('summary')) return 'subject';
    if (value.includes('export')) return 'ios_share';
    return 'route';
};

const planStepRank = (id) => {
    const value = String(id || '').toLowerCase();
    if (value.includes('ingest')) return 0;
    if (value.includes('transcribe')) return 3;
    if (value.includes('subtitle') || value.includes('prepare')) return 4;
    if (value.includes('note') || value.includes('summary')) return 5;
    if (value.includes('export')) return 6;
    return 4;
};

const statusClass = (status) => {
    if (status === 'done') return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200';
    if (status === 'current') return 'border-[#111111] bg-[#111111] text-white dark:border-white dark:bg-white dark:text-[#111111]';
    if (status === 'failed') return 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200';
    return 'border-[#dedada] bg-white text-[#777] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/55';
};

const SectionHeading = ({icon, title, desc}) => (
    <div className="mb-4 border-b border-[#dedada] pb-3 dark:border-white/[0.10]">
        <div className="flex items-center gap-2.5">
            <SvgIcon name={icon} className="text-[18px] text-[#57585d] dark:text-white/58"/>
            <h2 className="font-headline text-[15px] font-extrabold leading-tight text-[#111111] dark:text-white">{title}</h2>
        </div>
        {desc && <p className="mt-1.5 text-[13px] leading-5 text-[#6f7177] dark:text-white/60">{desc}</p>}
    </div>
);

const Metric = ({label, value}) => (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 border-b border-[#dedada]/70 py-2.5 last:border-b-0 dark:border-white/[0.08]">
        <p className="text-[12px] font-bold text-[#85868c] dark:text-white/45">{label}</p>
        <p className="truncate text-[13px] font-extrabold text-[#111111] dark:text-white" title={String(value || '-')}>{value || '-'}</p>
    </div>
);

const Processing = () => {
    const {lang} = useI18n();
    const {currentJob, lastResult, runtimeConfig} = useApp();
    const {loadSettings} = useSettings();
    const settings = useMemo(() => loadSettings(), [loadSettings]);
    const isZh = lang === 'zh';

    const result = lastResult || null;
    const processingPlan = result?.processing_plan || null;
    const planMaterial = processingPlan?.material || {};
    const planExecution = processingPlan?.execution || {};
    const planNoteStrategy = processingPlan?.note_strategy || {};
    const planEvidence = Array.isArray(planMaterial.evidence) ? planMaterial.evidence.filter(Boolean) : [];
    const planRiskNotes = Array.isArray(processingPlan?.risk_notes) ? processingPlan.risk_notes.filter(Boolean) : [];
    const planSteps = Array.isArray(processingPlan?.steps) ? processingPlan.steps : [];
    const active = currentJob && currentJob.stage !== 'done' ? currentJob : null;
    const rawTitle = active?.fileName || result?.display_title || result?.filename || '';
    const title = displayTitleForUser(rawTitle, result?.filename || rawTitle) || (isZh ? '等待任务' : 'Waiting for task');
    const stage = active?.stage || (result ? 'done' : 'queued');
    const stageRank = STAGE_ORDER[stage] ?? 0;
    const provider = active?.sttProvider || result?.stt_provider || effectiveSttProvider(settings, runtimeConfig);
    const sourceLanguage = result?.source_language || result?.detected_language || settings.sttLanguage || 'auto';
    const noteMode = planNoteStrategy.resolved_mode || result?.resolved_note_mode || result?.note_mode_plan_selected_mode || result?.requested_note_mode || settings.noteMode || 'auto';
    const segmentCount = Array.isArray(result?.display_segments)
        ? result.display_segments.length
        : Array.isArray(result?.raw_segments)
            ? result.raw_segments.length
            : Array.isArray(result?.segments)
                ? result.segments.length
                : null;
    const transcriptChars = result?.transcript_text ? result.transcript_text.length : null;
    const durationSeconds = result?.audio_duration_seconds || active?.durationSeconds || null;
    const progress = Math.max(0, Math.min(100, Number(active?.progress) || (result ? 100 : 0)));
    const noteReason = planNoteStrategy.reason || result?.note_mode_plan_reason
        || (settings.noteMode && settings.noteMode !== 'auto'
            ? (isZh ? '来自设置页的长期偏好。' : 'From the long-term preference in Settings.')
            : (isZh ? '自动模式会根据转录长度和内容结构选择直接生成或高保真笔记。' : 'Auto mode chooses direct or high-fidelity notes from transcript length and structure.'));
    const promptLabel = result?.prompt_preset_label || result?.prompt_preset_name || settings.promptPreset || (isZh ? '默认模板' : 'Default template');
    const summaryFailed = result?.summary_status === 'failed' || result?.summary_error;

    const fallbackSteps = [
        {
            key: 'receive',
            rank: 0,
            icon: 'upload_file',
            title: isZh ? '接收材料' : 'Receive material',
            desc: active?.sourceType === 'video_link' || result?.source === 'douyin'
                ? (isZh ? '解析分享链接，保存原始标题和来源。' : 'Resolve the shared link and preserve source title metadata.')
                : (isZh ? '接收音视频或字幕文件，建立可恢复任务。' : 'Receive media or transcript files and create a recoverable task.'),
        },
        {
            key: 'audio',
            rank: 2,
            icon: 'graphic_eq',
            title: isZh ? '准备转录输入' : 'Prepare transcript input',
            desc: active?.sourceType === 'transcript_file' || result?.source === 'transcript_file'
                ? (isZh ? '字幕文件会跳过语音转文字，直接进入正文整理。' : 'Transcript files skip STT and go straight to text cleanup.')
                : (isZh ? '从视频中抽取音频，并按路线要求整理格式。' : 'Extract audio from video and normalize it for the selected route.'),
        },
        {
            key: 'stt',
            rank: 3,
            icon: isCloudSttProvider(provider) ? 'cloud_done' : 'mic_external_on',
            title: isZh ? '转录与语言识别' : 'Transcribe and detect language',
            desc: isCloudSttProvider(provider)
                ? (isZh ? '默认走云端转录；公开产品由后端统一管理凭证和额度。' : 'Cloud STT is the default; credentials and quota are managed by the backend.')
                : (isZh ? '本地路线会留在本机执行，适合开发、私人材料和兜底处理。' : 'Local STT stays on this machine for development, private material, and fallback work.'),
        },
        {
            key: 'judge',
            rank: 4,
            icon: 'psychology',
            title: isZh ? '判断材料与策略' : 'Judge material and strategy',
            desc: isZh ? '以转录正文为主，文件名只作弱信号，判断是否像课程或讲座。' : 'Use transcript content as the primary evidence; filename is only a weak signal.',
        },
        {
            key: 'note',
            rank: 5,
            icon: 'subject',
            title: isZh ? '生成结构化笔记' : 'Generate structured note',
            desc: noteReason,
        },
        {
            key: 'save',
            rank: 6,
            icon: 'ios_share',
            title: isZh ? '保存产物和后续动作' : 'Save artifacts and next actions',
            desc: settings.exportToLark
                ? (isZh ? '结果保存后会按设置尝试导出飞书。' : 'After saving, FluentFlow will attempt Lark export according to Settings.')
                : (isZh ? '结果保存后可在编辑器继续校对、下载或手动导出。' : 'After saving, continue reviewing, downloading, or exporting from the editor.'),
        },
    ];
    const steps = planSteps.length
        ? planSteps.map((step) => ({
            key: step.id || step.label || step.tool,
            rank: planStepRank(step.id),
            icon: planStepIcon(step.id, step.tool),
            title: step.label || step.id || (isZh ? '处理步骤' : 'Processing step'),
            desc: step.reason || step.tool || (isZh ? '来自本次 Processing Plan。' : 'From this Processing Plan.'),
        }))
        : fallbackSteps;

    const stepStatus = (step) => {
        if (summaryFailed && step.key === 'note') return 'failed';
        if (result && !active) return 'done';
        if (step.rank < stageRank) return 'done';
        if (step.rank === stageRank || (stage === 'stt' && step.key === 'stt')) return 'current';
        return 'waiting';
    };

    const evidence = [
        {label: isZh ? '材料标题' : 'Title', value: title},
        {label: isZh ? '转录路线' : 'Route', value: routeLabel(provider, lang)},
        {label: isZh ? '执行范围' : 'Execution scope', value: planExecution.scope ? executionScopeLabel(planExecution.scope, lang) : null},
        {label: isZh ? '材料类型' : 'Material type', value: materialTypeLabel(planMaterial.type, lang)},
        {label: isZh ? '判断置信度' : 'Confidence', value: planMaterial.confidence || null},
        {label: isZh ? '音频语言' : 'Language', value: languageLabel(sourceLanguage, lang)},
        {label: isZh ? '时长' : 'Duration', value: durationSeconds ? fmtElapsed(durationSeconds) : null},
        {label: isZh ? '转录长度' : 'Transcript length', value: transcriptChars ? `${transcriptChars.toLocaleString()} ${isZh ? '字' : 'chars'}` : null},
        {label: isZh ? '字幕段数' : 'Segments', value: segmentCount ? `${segmentCount}` : null},
        {label: isZh ? '文件大小' : 'File size', value: fmtFileSize(active?.fileSizeMb)},
        {label: isZh ? '提示词模板' : 'Prompt', value: promptLabel},
    ];

    const nextActionTitle = summaryFailed
        ? (isZh ? '重生笔记' : 'Regenerate note')
        : active
            ? (isZh ? '查看运行状态' : 'Review run status')
            : result
                ? (isZh ? '复查结果' : 'Review result')
                : (isZh ? '开始处理任务' : 'Start a task');
    const nextActionDesc = summaryFailed
        ? (result?.summary_error || (isZh ? '保留已完成的转录，建议在编辑器重生笔记。' : 'Transcript is preserved. Regenerate the note from the editor.'))
        : active
            ? (isZh ? '实时进度仍在开始处理页和后台任务页显示，这里解释当前路线和判断依据。' : 'Live progress is still shown on Start and Tasks. This page explains the route and evidence.')
            : result
                ? (isZh ? '打开编辑器校对笔记、下载字幕，或进入后台任务查看完整记录。' : 'Open the editor to review notes and subtitles, or inspect the full task record in Tasks.')
                : (isZh ? '从开始处理页上传课程、讲座或字幕文件后，这里会展示 Agent 的处理路线。' : 'Upload a course, lecture, or transcript from Start, then this page will explain the Agent route.');
    const editorActionLabel = summaryFailed
        ? (isZh ? '打开编辑器重生笔记' : 'Open editor to regenerate note')
        : (isZh ? '打开编辑器' : 'Open editor');

    return (
        <main className="ml-[var(--sidebar-offset)] h-dvh overflow-y-auto bg-[#f8f7fb] px-6 py-5 text-[#111111] transition-[margin] duration-200 ease-out hide-scrollbar dark:bg-[#101010] dark:text-white/[0.92] lg:px-10">
            <div className="mx-auto max-w-7xl space-y-5">
                <div className="grid min-w-0 gap-7 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.55fr)]">
                    <div className="min-w-0 space-y-7">
                        <section className="min-w-0 overflow-hidden border-b border-[#dedada] pb-5 dark:border-white/[0.10]">
                            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                                <div className="min-w-0 max-w-full flex-1 overflow-hidden">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="rounded-full border border-[#dedada] bg-white px-3 py-1 text-[12px] font-extrabold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                            {stageLabel(stage, lang)}
                                        </span>
                                        {active && (
                                            <span className="rounded-full border border-[#dedada] bg-white px-3 py-1 text-[12px] font-extrabold tabular-nums text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                                {Math.round(progress)}%
                                            </span>
                                        )}
                                    </div>
                                    <h2 className="mt-3 max-w-full truncate font-headline text-[21px] font-extrabold text-[#111111] dark:text-white" title={title}>{title}</h2>
                                    <p className="mt-2 text-[13px] leading-5 text-[#6f7177] dark:text-white/60">
                                        {active
                                            ? (isZh ? '这是当前正在执行的任务。' : 'This is the task currently running.')
                                            : result
                                                ? (isZh ? '这是最近一次可解释的处理结果。' : 'This is the latest explainable result.')
                                                : (isZh ? '上传材料后，这里会显示当前任务。' : 'Upload material and the current task will appear here.')}
                                    </p>
                                </div>
                                {active && (
                                    <div className="w-full md:w-52">
                                        <div className="h-2 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.10]">
                                            <div className="h-full rounded-full bg-[#111111] transition-[width] duration-200 ease-out dark:bg-white" style={{width: `${progress}%`}}/>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </section>

                        <section>
                            <SectionHeading
                                icon="route"
                                title={isZh ? '执行路线' : 'Execution route'}
                                desc={isZh ? '按执行顺序展示本次任务经过的处理步骤。' : 'Shows the processing steps for this task in execution order.'}
                            />
                            <div>
                                {steps.map((step, index) => {
                                    const status = stepStatus(step);
                                    const isLast = index === steps.length - 1;
                                    return (
                                        <div key={step.key} className="relative grid grid-cols-[44px_minmax(0,1fr)] gap-4">
                                            {!isLast && <span className="absolute left-[21px] top-10 bottom-0 w-px bg-[#dedada] dark:bg-white/[0.12]"/>}
                                            <div className={`relative z-10 flex size-10 items-center justify-center rounded-[14px] border ${statusClass(status)}`}>
                                                <SvgIcon name={status === 'done' ? 'check_circle' : step.icon} className="text-[18px]"/>
                                            </div>
                                            <div className={`min-w-0 ${isLast ? 'pb-0' : 'border-b border-[#dedada]/70 pb-5 dark:border-white/[0.08]'}`}>
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <h3 className="text-[14px] font-extrabold text-[#111111] dark:text-white">{step.title}</h3>
                                                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${statusClass(status)}`}>
                                                        {status === 'done' ? (isZh ? '完成' : 'Done') : status === 'current' ? (isZh ? '当前' : 'Now') : status === 'failed' ? (isZh ? '失败' : 'Failed') : (isZh ? '等待' : 'Waiting')}
                                                    </span>
                                                </div>
                                                <p className="mt-1 text-[13px] leading-5 text-[#6f7177] dark:text-white/58">{step.desc}</p>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </section>
                    </div>

                    <aside className="space-y-7 xl:border-l xl:border-[#dedada] xl:pl-6 xl:dark:border-white/[0.10]">
                        <section>
                            <SectionHeading
                                icon="psychology"
                                title={isZh ? 'Agent 判断' : 'Agent judgment'}
                                desc={isZh ? '把真正影响结果的判断讲清楚，调参入口留在设置页。' : 'Explain the decisions that affect the result. Long-term controls stay in Settings.'}
                            />
                            <div>
                                <Metric label={isZh ? '转录路线' : 'Transcription route'} value={routeLabel(provider, lang)}/>
                                <Metric label={isZh ? '执行工具' : 'Execution tool'} value={planExecution.transcription_tool || null}/>
                                <Metric label={isZh ? '笔记策略' : 'Note strategy'} value={noteModeLabel(noteMode, lang)}/>
                                <div className="border-b border-[#dedada]/70 py-2.5 dark:border-white/[0.08]">
                                    <p className="text-[12px] font-bold text-[#85868c] dark:text-white/45">{isZh ? '策略原因' : 'Strategy reason'}</p>
                                    <p className="mt-1 text-[13px] leading-5 text-[#111111] dark:text-white/82">{noteReason}</p>
                                </div>
                                <div className="py-2.5">
                                    <p className="text-[12px] font-bold text-[#85868c] dark:text-white/45">{isZh ? '字幕处理' : 'Subtitle handling'}</p>
                                    <p className="mt-1 text-[13px] leading-5 text-[#111111] dark:text-white/82">
                                        {String(sourceLanguage).toLowerCase().startsWith('en')
                                            ? (isZh ? '英文材料保留原文字幕，并生成中文参考；笔记基于原文理解后输出中文。' : 'English material keeps original subtitles and adds Chinese reference translations.')
                                            : (isZh ? '中文材料按原文转录和整理，不额外制造双语字幕。' : 'Chinese material is transcribed and organized as source-language subtitles.')}
                                    </p>
                                </div>
                                {planRiskNotes.length > 0 && (
                                    <div className="border-l-2 border-orange-400 py-1 pl-3 text-[#9a3412] dark:text-orange-100">
                                        <p className="text-[12px] font-bold opacity-70">{isZh ? '风险提示' : 'Risk notes'}</p>
                                        <ul className="mt-1 space-y-1 text-[13px] font-semibold leading-5">
                                            {planRiskNotes.map((item) => <li key={item}>- {item}</li>)}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        </section>

                        <section>
                            <SectionHeading
                                icon="fact_check"
                                title={isZh ? '使用依据' : 'Evidence used'}
                                desc={isZh ? '文件名只是弱信号，完成转录后以正文结构和长度为主。' : 'Filename is weak evidence. Transcript structure and length matter more after STT.'}
                            />
                            <div>
                                {evidence.map((item) => <Metric key={item.label} label={item.label} value={item.value}/>)}
                            </div>
                            {planEvidence.length > 0 && (
                                <div className="mt-3">
                                    <p className="text-[12px] font-bold text-[#85868c] dark:text-white/45">{isZh ? '计划依据' : 'Plan evidence'}</p>
                                    <div className="mt-2 flex flex-wrap gap-1.5">
                                        {planEvidence.map((item) => (
                                            <span key={item} className="rounded-full border border-[#dedada] bg-white px-2.5 py-1 text-[11px] font-bold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                                {item}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </section>

                        <section className="border-t border-[#dedada] pt-5 dark:border-white/[0.10]">
                            <SectionHeading icon={summaryFailed ? 'error' : 'arrow_forward'} title={nextActionTitle} desc={nextActionDesc}/>
                            <div className="flex flex-wrap gap-2">
                                {result && (
                                    <Link to="/editor" className="inline-flex h-10 items-center gap-2 rounded-[14px] bg-[#111111] px-4 text-[13px] font-extrabold text-white transition hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
                                        <SvgIcon name="open_in_new" className="text-base"/>
                                        {editorActionLabel}
                                    </Link>
                                )}
                                <Link to="/tasks" className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-[#dedada] bg-white px-4 text-[13px] font-extrabold text-[#111111] transition hover:bg-[#f4f3f3] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]">
                                    <SvgIcon name="monitoring" className="text-base"/>
                                    {isZh ? '后台任务' : 'Tasks'}
                                </Link>
                            </div>
                        </section>
                    </aside>
                </div>

                <section className="border-t border-[#dedada] pt-4 dark:border-white/[0.10]">
                    <details>
                        <summary className="cursor-pointer list-none text-[14px] font-extrabold text-[#111111] dark:text-white">
                            {isZh ? '高级详情' : 'Advanced details'}
                        </summary>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            <Metric label="Task ID" value={active?.taskId || result?.task_id}/>
                            <Metric label="Plan version" value={processingPlan?.processing_plan_version}/>
                            <Metric label="Planning stage" value={processingPlan?.planning_stage}/>
                            <Metric label="Provider" value={provider}/>
                            <Metric label="Model" value={result?.stt_model || active?.sttModel || settings.sttModel}/>
                            <Metric label="Prompt" value={promptLabel}/>
                            <Metric label="Summary status" value={result?.summary_status || (settings.skipAiSummary ? 'skipped by setting' : null)}/>
                            <Metric label="Chunk count" value={result?.note_mode_chunk_count}/>
                            <Metric label="Elapsed" value={result?.stt_elapsed_seconds ? fmtElapsed(result.stt_elapsed_seconds) : active?.sttElapsedSeconds ? fmtElapsed(active.sttElapsedSeconds) : null}/>
                            <Metric label="Runtime default" value={runtimeConfig.defaultSttProvider}/>
                        </div>
                    </details>
                </section>
            </div>
        </main>
    );
};

export default Processing;
