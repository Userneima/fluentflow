import {
    fmtBytes,
    isSttProgressUnmeasured,
    jobProgressLabel,
    sttProgressFraction,
    sttStatusLabel,
    useApp,
    useI18n,
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

const normalizeTask = (pageData, currentJob) => {
    const task = pageData?.task || {};
    const source = pageData?.source || {};
    const videoSourceProgress = task.video_source_progress || source.video_source_progress || null;
    const videoSourceFileSizeMb = videoSourceProgress?.total_bytes ? Number(videoSourceProgress.total_bytes) / 1024 / 1024 : null;
    const sameCurrentJob = currentJob?.taskId && currentJob.taskId === task.task_id;
    const current = sameCurrentJob ? currentJob : null;
    return {
        taskId: task.task_id || current?.taskId,
        title: task.title || source.display_title || pageData?.title || current?.fileName || task.filename,
        stage: current?.stage || task.stage || (task.status === 'completed' ? 'done' : task.status || 'queued'),
        status: task.status || current?.taskState || null,
        progress: current?.progress ?? task.progress ?? (task.status === 'completed' ? 100 : 0),
        sttStatus: current?.sttStatus || null,
        videoSourceProgress,
        sourceType: current?.sourceType || task.source_type || source.type || null,
        fileSizeMb: current?.fileSizeMb ?? task.file_size_mb ?? source.file_size_mb ?? videoSourceFileSizeMb,
    };
};

const videoSourceProgressText = (progress, isZh) => {
    if (!progress || typeof progress !== 'object') return '';
    const loaded = fmtBytes(progress.loaded_bytes);
    const total = fmtBytes(progress.total_bytes);
    const byteText = loaded && total ? ` · ${loaded} / ${total}` : (loaded ? ` · ${loaded}` : '');
    if (progress.message) return `${progress.message}${byteText}`;
    return byteText ? `${isZh ? '下载进度' : 'Download progress'}${byteText}` : '';
};

const ArtifactPill = ({children}) => (
    <span className="inline-flex h-8 items-center rounded-[12px] border border-[#dedada] bg-[#fbfbfb] px-3 text-[12px] font-extrabold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/[0.68]">
        {children}
    </span>
);

const TaskProgressOverview = ({pageData}) => {
    const {lang, t} = useI18n();
    const {currentJob} = useApp();
    const task = normalizeTask(pageData, currentJob);
    const isZh = lang === 'zh';
    const progress = Math.max(0, Math.min(100, Number(task.progress) || 0));
    const progressText = task.taskId === currentJob?.taskId
        ? jobProgressLabel({...currentJob, progress}, t)
        : `${Math.round(progress)}%`;
    const sttUnknown = task.taskId === currentJob?.taskId && isSttProgressUnmeasured(currentJob);
    const sttProgressPct = task.taskId === currentJob?.taskId ? Math.round(sttProgressFraction(currentJob) * 100) : null;
    const stateText = String(task.stage || task.status || '').toLowerCase();
    const failed = ['failed', 'error', 'cancelled'].includes(stateText);
    const completed = !failed && (stateText === 'done' || stateText === 'completed' || String(task.status || '').toLowerCase() === 'completed' || progress >= 100);
    const running = !completed && !failed;
    const videoProgressDetail = videoSourceProgressText(task.videoSourceProgress, isZh);
    const transcriptAvailable = !!pageData?.transcript?.available;
    const noteReady = !!String(pageData?.note?.markdown || '').trim() || pageData?.note?.status === 'completed';
    const artifactCount = Array.isArray(pageData?.artifacts)
        ? pageData.artifacts.length
        : Object.keys(pageData?.artifacts || {}).length;
    const diagnosis = pageData?.diagnosis || pageData?.note?.diagnosis || {};

    return (
        <section className={`rounded-[22px] border p-5 shadow-[0_18px_44px_-38px_rgba(17,17,17,.45)] dark:shadow-none ${
            failed
                ? 'border-red-200 bg-red-50 dark:border-red-500/20 dark:bg-red-500/10'
                : 'border-[#dedada] bg-white dark:border-white/[0.10] dark:bg-white/[0.055]'
        }`}>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-3 py-1 text-[12px] font-extrabold ${
                            failed
                                ? 'border-red-200 bg-white text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200'
                                : completed
                                    ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-100'
                                    : 'border-[#dedada] bg-[#f4f3f3] text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white/[0.60]'
                        }`}>
                            {failed
                                ? (isZh ? '处理失败' : 'Failed')
                                : completed
                                    ? (isZh ? '结果已生成' : 'Result ready')
                                    : stageLabel(task.stage, lang)}
                        </span>
                        {running && (
                            <span className="rounded-full border border-[#dedada] bg-white px-3 py-1 text-[12px] font-extrabold tabular-nums text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/[0.60]">
                            {progressText}
                        </span>
                        )}
                    </div>
                    <h2 className="mt-3 font-headline text-[22px] font-extrabold leading-tight text-[#111111] dark:text-white">
                        {failed
                            ? (isZh ? '需要处理这个失败任务' : 'This task needs attention')
                            : completed
                                ? (isZh ? '结果可以复查' : 'Ready to review')
                                : (isZh ? '正在处理任务' : 'Processing task')}
                    </h2>
                    <p className="mt-2 max-w-[76ch] text-[13px] font-semibold leading-5 text-[#676970] dark:text-white/[0.60]">
                        {failed
                            ? (diagnosis.detail || diagnosis.next_action || (isZh ? '查看失败原因，按建议重新处理或打开历史记录。' : 'Review the failure reason and retry or return to history.'))
                            : completed
                                ? (isZh ? '转录、笔记和可下载产物会在结果页集中复查。' : 'Transcript, note, and downloadable outputs are reviewed from the result page.')
                                : (isZh ? '这里仅显示当前阶段和必要进度；完成后会自动变为可复查结果。' : 'Only the current stage and essential progress are shown here; it becomes reviewable when complete.')}
                    </p>
                    {videoProgressDetail && (
                        <p className="mt-3 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-[12px] font-semibold leading-5 text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/[0.62]">
                            {videoProgressDetail}
                        </p>
                    )}
                </div>
                {running && (
                    <div className="w-full shrink-0 lg:w-[320px]">
                    <div className={`h-2.5 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12] ${sttUnknown ? 'progress-indeterminate' : ''}`}>
                        {!sttUnknown && <div className="h-full rounded-full bg-[#111111] transition-all duration-500 dark:bg-white" style={{width: `${progress}%`}}/>}
                    </div>
                </div>
                )}
            </div>

            {completed && (
                <div className="mt-4 flex flex-wrap gap-2">
                    {transcriptAvailable && <ArtifactPill>{isZh ? '转录可复查' : 'Transcript ready'}</ArtifactPill>}
                    {noteReady && <ArtifactPill>{isZh ? '笔记已生成' : 'Note ready'}</ArtifactPill>}
                    {artifactCount > 0 && <ArtifactPill>{isZh ? `${artifactCount} 个产物` : `${artifactCount} outputs`}</ArtifactPill>}
                    {task.fileSizeMb ? <ArtifactPill>{fmtBytes(task.fileSizeMb * 1024 * 1024)}</ArtifactPill> : null}
                </div>
            )}

            {running && task.stage === 'stt' && (
                <div className="mt-4 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-[12px] font-semibold leading-5 text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/[0.62]">
                    {sttUnknown
                        ? sttStatusLabel(task.sttStatus, t)
                        : `${isZh ? '转录进度' : 'Transcribed'}: ${sttProgressPct ?? Math.round(progress)}%`}
                </div>
            )}
        </section>
    );
};

export default TaskProgressOverview;
