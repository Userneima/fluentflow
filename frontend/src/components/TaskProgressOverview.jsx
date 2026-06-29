import {Link} from 'react-router-dom';
import SvgIcon from './SvgIcon.jsx';
import {
    effectiveSttProvider,
    fmtElapsed,
    fmtFileSize,
    isCloudSttProvider,
    isSttProgressUnmeasured,
    jobProgressLabel,
    noteModeLabel,
    sttProgressFraction,
    sttStatusLabel,
    useApp,
    useI18n,
    useSettings,
} from '../app/shared.jsx';

const stageLabel = (stage, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        queued: isZh ? '排队中' : 'Queued',
        upload: isZh ? '接收材料' : 'Receiving',
        resolving: isZh ? '解析链接' : 'Resolving link',
        downloading: isZh ? '下载视频' : 'Downloading',
        saving: isZh ? '保存来源' : 'Saving source',
        audio: isZh ? '提取音频' : 'Extracting audio',
        stt: isZh ? '转录中' : 'Transcribing',
        transcript_ready: isZh ? '转录完成' : 'Transcript ready',
        cleanup: isZh ? '整理转录' : 'Cleaning transcript',
        summary: isZh ? '生成笔记' : 'Generating note',
        export: isZh ? '导出飞书' : 'Exporting',
        failed: isZh ? '失败' : 'Failed',
        error: isZh ? '失败' : 'Failed',
        cancelled: isZh ? '已取消' : 'Cancelled',
        done: isZh ? '已完成' : 'Done',
    };
    return labels[stage] || (isZh ? '处理中' : 'Processing');
};

const routeLabel = (provider, lang) => {
    if (provider === 'elevenlabs_scribe') return lang === 'zh' ? 'ElevenLabs 云端转录' : 'ElevenLabs cloud STT';
    if (provider === 'azure_batch') return lang === 'zh' ? '历史云端转录' : 'Legacy cloud STT';
    if (provider === 'local') return lang === 'zh' ? '本地 faster-whisper' : 'Local faster-whisper';
    return provider || (lang === 'zh' ? '按任务配置' : 'Task route');
};

const stageItems = (sourceType, lang) => {
    if (sourceType === 'transcript_file') {
        return [
            ['summary', lang === 'zh' ? '生成笔记' : 'Note'],
            ['export', lang === 'zh' ? '导出' : 'Export'],
        ];
    }
    if (sourceType === 'video_link') {
        return [
            ['resolving', lang === 'zh' ? '解析' : 'Resolve'],
            ['downloading', lang === 'zh' ? '获取' : 'Fetch'],
            ['audio', lang === 'zh' ? '音频' : 'Audio'],
            ['stt', lang === 'zh' ? '转录' : 'STT'],
            ['summary', lang === 'zh' ? '笔记' : 'Note'],
            ['export', lang === 'zh' ? '导出' : 'Export'],
        ];
    }
    return [
        ['upload', lang === 'zh' ? '接收' : 'Receive'],
        ['audio', lang === 'zh' ? '音频' : 'Audio'],
        ['stt', lang === 'zh' ? '转录' : 'STT'],
        ['summary', lang === 'zh' ? '笔记' : 'Note'],
        ['export', lang === 'zh' ? '导出' : 'Export'],
    ];
};

const stageRank = {
    queued: 0,
    upload: 0,
    resolving: 1,
    downloading: 2,
    saving: 2,
    audio: 3,
    stt: 4,
    transcript_ready: 5,
    cleanup: 5,
    summary: 6,
    export: 7,
    done: 8,
    failed: 99,
    error: 99,
    cancelled: 99,
};

const normalizeTask = (pageData, currentJob) => {
    const task = pageData?.task || {};
    const source = pageData?.source || {};
    const sameCurrentJob = currentJob?.taskId && currentJob.taskId === task.task_id;
    const current = sameCurrentJob ? currentJob : null;
    return {
        taskId: task.task_id || current?.taskId,
        title: task.title || source.display_title || pageData?.title || current?.fileName || task.filename,
        stage: current?.stage || task.stage || (task.status === 'completed' ? 'done' : task.status || 'queued'),
        status: task.status || current?.taskState || null,
        progress: current?.progress ?? task.progress ?? (task.status === 'completed' ? 100 : 0),
        sourceType: current?.sourceType || task.source_type || source.type || null,
        fileSizeMb: current?.fileSizeMb ?? task.file_size_mb ?? source.file_size_mb ?? null,
        durationSeconds: current?.durationSeconds ?? task.duration_seconds ?? source.duration_seconds ?? null,
        startedAt: current?.startedAt || (task.created_at ? Date.parse(task.created_at) : null),
        updatedAt: task.updated_at || null,
        sttProvider: current?.sttProvider || pageData?.transcript?.stt_provider || null,
        sttModel: current?.sttModel || null,
        sttSpeed: current?.sttSpeed || null,
        sttLanguage: current?.sttLanguage || pageData?.transcript?.source_language || pageData?.transcript?.detected_language || null,
        sttStatus: current?.sttStatus || null,
        transcribedSeconds: current?.transcribedSeconds || null,
        sttElapsedSeconds: current?.sttElapsedSeconds || null,
        azureBatchAudioSizeMb: current?.azureBatchAudioSizeMb ?? null,
        skipSummary: current?.skipSummary ?? null,
        noteMode: current?.noteMode || pageData?.note?.resolved_mode || pageData?.note?.requested_mode || null,
    };
};

const Metric = ({label, value}) => (
    <div className="rounded-[14px] bg-[#f4f3f3] px-3 py-2 dark:bg-white/[0.08]">
        <p className="text-[10px] font-extrabold uppercase tracking-wide text-[#777] dark:text-white/45">{label}</p>
        <p className="mt-1 truncate text-[13px] font-extrabold text-[#111111] dark:text-white" title={String(value || '-')}>{value || '-'}</p>
    </div>
);

const TaskProgressOverview = ({pageData}) => {
    const {lang, t} = useI18n();
    const {currentJob, runtimeConfig} = useApp();
    const {loadSettings} = useSettings();
    const settings = loadSettings();
    const task = normalizeTask(pageData, currentJob);
    const isZh = lang === 'zh';
    const progress = Math.max(0, Math.min(100, Number(task.progress) || 0));
    const currentRank = stageRank[task.stage] ?? 0;
    const provider = task.sttProvider || effectiveSttProvider(settings, runtimeConfig);
    const elapsedSec = task.startedAt ? Math.max(0, Math.floor((Date.now() - task.startedAt) / 1000)) : null;
    const sttProfile = task.sourceType === 'transcript_file'
        ? (isZh ? '跳过语音转写' : 'Transcript import')
        : [
            isCloudSttProvider(provider) ? (isZh ? '云端' : 'cloud') : (isZh ? '本地' : 'local'),
            task.sttModel || settings.sttModel || '-',
            task.sttSpeed || settings.sttSpeed || 'balanced',
            task.sttLanguage || 'auto',
        ].join(' / ');
    const noteMode = task.skipSummary
        ? (isZh ? '仅转录' : 'Transcript only')
        : `${isZh ? '生成笔记' : 'Note on'} / ${noteModeLabel(task.noteMode || settings.noteMode || 'auto', lang)}`;
    const progressText = task.taskId === currentJob?.taskId
        ? jobProgressLabel({...currentJob, progress}, t)
        : `${Math.round(progress)}%`;
    const sttUnknown = task.taskId === currentJob?.taskId && isSttProgressUnmeasured(currentJob);
    const sttProgressPct = task.taskId === currentJob?.taskId ? Math.round(sttProgressFraction(currentJob) * 100) : null;
    const failed = ['failed', 'error', 'cancelled'].includes(String(task.stage || task.status || '').toLowerCase());

    return (
        <section className="rounded-[22px] border border-[#dedada] bg-white p-5 shadow-[0_18px_44px_-38px_rgba(17,17,17,.45)] dark:border-white/[0.10] dark:bg-white/[0.055] dark:shadow-none">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-3 py-1 text-[12px] font-extrabold ${failed ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200' : 'border-[#dedada] bg-[#f4f3f3] text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white/60'}`}>
                            {stageLabel(task.stage, lang)}
                        </span>
                        <span className="rounded-full border border-[#dedada] bg-white px-3 py-1 text-[12px] font-extrabold tabular-nums text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                            {progressText}
                        </span>
                    </div>
                    <h2 className="mt-3 truncate font-headline text-[24px] font-extrabold leading-tight text-[#111111] dark:text-white" title={task.title}>
                        {task.title || (isZh ? '当前任务' : 'Current task')}
                    </h2>
                    <p className="mt-2 max-w-[76ch] text-[13px] font-semibold leading-5 text-[#676970] dark:text-white/60">
                        {isZh
                            ? '任务已进入后台处理，当前阶段、处理配置和判断依据会在这里同步更新。'
                            : 'This task is running in the background. Current stage, route, and decision context update here.'}
                    </p>
                </div>
                <div className="w-full shrink-0 lg:w-[320px]">
                    <div className={`h-2.5 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12] ${sttUnknown ? 'progress-indeterminate' : ''}`}>
                        {!sttUnknown && <div className="h-full rounded-full bg-[#111111] transition-all duration-500 dark:bg-white" style={{width: `${progress}%`}}/>}
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        <Metric label={isZh ? '耗时' : 'Elapsed'} value={elapsedSec == null ? '-' : fmtElapsed(elapsedSec)}/>
                        <Metric label={isZh ? '文件大小' : 'File'} value={fmtFileSize(task.fileSizeMb)}/>
                    </div>
                </div>
            </div>

            <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label={isZh ? '转录路线' : 'Route'} value={routeLabel(provider, lang)}/>
                <Metric label={isZh ? '模型配置' : 'STT profile'} value={sttProfile}/>
                <Metric label={isZh ? '笔记模式' : 'Note mode'} value={noteMode}/>
                <Metric label={isZh ? '媒体时长' : 'Duration'} value={task.durationSeconds ? fmtElapsed(task.durationSeconds) : '-'}/>
            </div>

            {task.stage === 'stt' && (
                <div className="mt-4 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-[12px] font-semibold leading-5 text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/62">
                    {sttUnknown
                        ? sttStatusLabel(task.sttStatus, t)
                        : `${isZh ? '转录进度' : 'Transcribed'}: ${sttProgressPct ?? Math.round(progress)}%`}
                </div>
            )}

            <div className="mt-5 grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
                {stageItems(task.sourceType, lang).map(([key, label]) => {
                    const rank = stageRank[key] ?? 0;
                    const state = failed
                        ? 'waiting'
                        : rank < currentRank || task.stage === 'done'
                            ? 'done'
                            : rank === currentRank
                                ? 'current'
                                : 'waiting';
                    return (
                        <div key={key} className={`rounded-[14px] border px-3 py-2 ${state === 'current' ? 'border-[#111111] bg-[#111111] text-white dark:border-white dark:bg-white dark:text-[#111111]' : state === 'done' ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-100' : 'border-[#dedada] bg-[#fbfbfb] text-[#777] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/48'}`}>
                            <div className="flex items-center gap-2">
                                <SvgIcon name={state === 'done' ? 'check_circle' : 'hourglass_top'} className="size-4 shrink-0"/>
                                <span className="truncate text-[12px] font-extrabold">{label}</span>
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
                <Link to="/tasks" className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-3 text-[12px] font-extrabold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]">
                    <SvgIcon name="monitoring" className="size-4"/>
                    {isZh ? '后台任务' : 'Tasks'}
                </Link>
            </div>
        </section>
    );
};

export default TaskProgressOverview;
