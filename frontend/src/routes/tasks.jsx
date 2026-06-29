/* ═══════════════ Background Tasks ═══════════════ */
import {useCallback, useEffect, useMemo, useState} from 'react';
import {useLocation, useNavigate, Link} from 'react-router-dom';
import {
    Activity,
    Download,
    ExternalLink,
    FileVideo,
    ListTodo,
    LoaderCircle,
    RefreshCw,
    Subtitles,
    Trash2,
    XCircle,
} from 'lucide-react';
import {
    fmtBytes,
    fmtElapsed,
    fmtFileSize,
    friendlyTaskError,
    hasTranscriptResult,
    DropdownMenu,
    isSttProgressUnmeasured,
    jobToCurrentJob,
    jobDisplayTitle,
    jobToHistoryEntry,
    readCachedAccountJobs,
    timeAgo,
    useApi,
    useApp,
    useAuth,
    useI18n,
    writeCachedAccountJobs,
} from '../app/shared.jsx';
import {
    isCachedOnlyTask,
    isLiveTask,
    markBackendJob,
    markCachedOnlyJob,
    normalizeTaskState,
    TASK_STATE_CANCELLED,
    TASK_STATE_CACHED_ONLY,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_QUEUED,
    TASK_STATE_RUNNING,
} from '../lib/taskState.js';

const agentPlanSummary = (job, lang) => {
    const plan = job?.result?.processing_plan;
    const trace = job?.result?.tool_trace;
    if (!plan || typeof plan !== 'object') return null;
    const zh = lang === 'zh';
    const goal = (() => {
        const primary = plan.goal?.primary;
        if (primary === 'lecture_notes') return zh ? '讲座整理' : 'Lecture notes';
        if (primary === 'course_notes') return zh ? '课程笔记' : 'Course notes';
        return primary || null;
    })();
    const route = (() => {
        const strategy = plan.note_strategy || {};
        const mode = strategy.resolved_mode || strategy.selected_mode || strategy.requested_mode;
        if (mode === 'high_fidelity') return zh ? '高保真整理' : 'High fidelity';
        if (mode === 'chapter_coverage') return zh ? '章节覆盖' : 'Chapter coverage';
        if (mode === 'direct') return zh ? '直接生成' : 'Direct';
        return mode || null;
    })();
    const traceSteps = Array.isArray(trace?.steps) ? trace.steps : [];
    const friendlyTool = (step) => ({
        resolve_link: zh ? '解析链接' : 'Resolve link',
        download_video: zh ? '下载媒体' : 'Download media',
        extract_audio: zh ? '提取音频' : 'Extract audio',
        local_stt: zh ? '本机转录' : 'Local STT',
        cloud_stt: zh ? '云端转录' : 'Cloud STT',
        generate_note: zh ? '生成笔记' : 'Generate notes',
        save_artifacts: zh ? '保存产物' : 'Save artifacts',
        export_lark: zh ? '导出飞书' : 'Export Feishu',
    })[step.id] || step.label || step.tool;
    const completedTrace = traceSteps
        .filter((step) => step.status === 'completed')
        .map(friendlyTool)
        .filter(Boolean)
        .slice(0, 4);
    if (!goal && !route && completedTrace.length === 0) return null;
    return {goal, route, trace: completedTrace};
};

const Tasks = () => {
    const {t, lang} = useI18n();
    const {authMode, user} = useAuth();
    const {currentJob, setLastResult, setCurrentJob, addToHistory} = useApp();
    const {getJobs, getJob, cancelJob, deleteJob, downloadJobArtifact} = useApi();
    const navigate = useNavigate();
    const location = useLocation();
    const cacheAccountId = authMode === 'accounts' ? user?.id : 'local';
    const readCachedOnlyJobs = useCallback(() => readCachedAccountJobs(cacheAccountId).map(markCachedOnlyJob), [cacheAccountId]);
    const [jobs, setJobs] = useState(() => readCachedAccountJobs(cacheAccountId).map(markCachedOnlyJob));
    const [loading, setLoading] = useState(() => readCachedAccountJobs(cacheAccountId).length === 0);
    const [error, setError] = useState(() => location.state?.queueSubmitError || null);
    const [deletingTaskId, setDeletingTaskId] = useState('');
    const [cancellingTaskId, setCancellingTaskId] = useState('');
    const queueUploadJob = currentJob?.queueUpload ? currentJob : null;
    const isLiveJob = isLiveTask;
    const isDeletableJob = (job) => !isLiveJob(job);
    const isLocalJob = (job) => String(job.client_id || '').startsWith('local-') || job.metadata?.stt_provider === 'local';
    const [taskFilter, setTaskFilter] = useState('all');
    const stats = useMemo(() => ({
        live: jobs.filter(isLiveJob).length,
        failed: jobs.filter((job) => normalizeTaskState(job) === TASK_STATE_FAILED).length,
        completed: jobs.filter((job) => normalizeTaskState(job) === TASK_STATE_COMPLETED || isCachedOnlyTask(job)).length,
        all: jobs.length,
    }), [jobs]);
    const taskFilters = [
        ['all', lang === 'zh' ? '全部' : 'All', stats.all],
        ['live', lang === 'zh' ? '进行中' : 'Active', stats.live],
        ['failed', t('tasks.failed'), stats.failed],
        ['completed', t('tasks.completed'), stats.completed],
    ];
    const visibleJobs = useMemo(() => {
        const priority = {running: 0, queued: 1, failed: 2, completed: 3};
        return jobs
            .filter((job) => {
                if (taskFilter === 'live') return isLiveJob(job);
                const taskState = normalizeTaskState(job);
                if (taskFilter === 'failed') return taskState === TASK_STATE_FAILED || taskState === TASK_STATE_CANCELLED;
                if (taskFilter === 'completed') return taskState === TASK_STATE_COMPLETED || isCachedOnlyTask(job);
                return true;
            })
            .slice()
            .sort((a, b) => {
                const priorityDiff = (priority[normalizeTaskState(a)] ?? 9) - (priority[normalizeTaskState(b)] ?? 9);
                if (priorityDiff !== 0) return priorityDiff;
                return (Date.parse(b.updated_at || b.created_at || '') || 0) - (Date.parse(a.updated_at || a.created_at || '') || 0);
            });
    }, [jobs, taskFilter]);
    const hasLiveJobs = Boolean(queueUploadJob || jobs.some(isLiveJob));

    const loadJobs = useCallback(async () => {
        try {
            const [accountJobs, localJobs] = await Promise.all([
                getJobs(100).catch(() => []),
                getJobs(100, {sttProvider: 'local'}).catch(() => []),
            ]);
            const byId = new Map(readCachedOnlyJobs().map((job) => [job.task_id, job]).filter(([taskId]) => taskId));
            [...accountJobs, ...localJobs].forEach((job) => {
                if (!job?.task_id) return;
                const existing = byId.get(job.task_id);
                if (normalizeTaskState(existing) === TASK_STATE_CANCELLED && normalizeTaskState(job) !== TASK_STATE_CANCELLED) return;
                const existingTs = Date.parse(existing?.updated_at || existing?.created_at || '') || 0;
                const nextTs = Date.parse(job.updated_at || job.created_at || '') || 0;
                if (!existing || nextTs >= existingTs) byId.set(job.task_id, markBackendJob(job));
                else byId.set(job.task_id, markBackendJob(existing));
            });
            const next = Array.from(byId.values());
            writeCachedAccountJobs(cacheAccountId, next);
            setJobs(next);
            setError(null);
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setLoading(false);
        }
    }, [cacheAccountId, lang, readCachedOnlyJobs]);

    useEffect(() => {
        const cached = readCachedOnlyJobs();
        if (cached.length) {
            setJobs(cached);
            setLoading(false);
        }
    }, [readCachedOnlyJobs]);

    useEffect(() => {
        if(location.state?.queueSubmitError) {
            navigate('/tasks', {replace:true, state:{}});
            return;
        }
        if(location.state?.queueSubmittedAt) {
            setLoading(true);
            loadJobs();
            navigate('/tasks', {replace:true, state:{}});
        }
    }, [location.state?.queueSubmitError, location.state?.queueSubmittedAt, loadJobs]);

    useEffect(() => {
        let stale = false;
        const run = async () => { if (!stale) await loadJobs(); };
        run();
        const timer = setInterval(run, hasLiveJobs ? 5000 : 30000);
        return () => {
            stale = true;
            clearInterval(timer);
        };
    }, [loadJobs, hasLiveJobs]);

    const openJob = async (job) => {
        if (normalizeTaskState(job) === TASK_STATE_RUNNING) {
            setCurrentJob(jobToCurrentJob(job));
            return;
        }
        const openResult = (sourceJob, result) => {
            setLastResult(result);
            addToHistory(jobToHistoryEntry({...sourceJob, result}));
            navigate('/editor');
        };
        if (isCachedOnlyTask(job) && job.result) {
            openResult(job, job.result);
            return;
        }
        try {
            const fresh = await getJob(job.task_id, isLocalJob(job) ? {sttProvider: 'local'} : {});
            const result = fresh?.result || job.result;
            if (result) {
                openResult(job, result);
            }
        } catch (err) {
            if (err.status === 404 && job.result) {
                openResult(job, job.result);
                return;
            }
            setError(friendlyTaskError(err.message || String(err), lang));
        }
    };

    const downloadArtifact = async (job, kind) => {
        const artifact = job.result?.artifacts?.[kind];
        await downloadJobArtifact(job.task_id, kind, artifact?.filename, isLocalJob(job) ? {sttProvider: 'local'} : {});
    };
    const cancelLiveJob = async (job) => {
        if (!isLiveJob(job)) return;
        const confirmText = lang === 'zh'
            ? '取消这个正在处理的任务？已生成的完整结果不会保留。'
            : 'Cancel this active task? A complete result will not be kept.';
        if (!window.confirm(confirmText)) return;
        setCancellingTaskId(job.task_id);
        try {
            await cancelJob(job.task_id, isLocalJob(job) ? {sttProvider: 'local'} : {});
            setJobs((current) => {
                const next = current.map((item) => item.task_id === job.task_id ? {
                    ...item,
                    status: TASK_STATE_CANCELLED,
                    task_state: TASK_STATE_CANCELLED,
                    error_reason: 'user_cancelled',
                    updated_at: new Date().toISOString(),
                } : item);
                writeCachedAccountJobs(cacheAccountId, next);
                return next;
            });
            if (currentJob?.taskId === job.task_id) setCurrentJob(null);
            setError(null);
            loadJobs();
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setCancellingTaskId('');
        }
    };

    const deleteFinishedJob = async (job) => {
        if (!isDeletableJob(job)) return;
        if (!window.confirm(t('tasks.deleteConfirm'))) return;
        setDeletingTaskId(job.task_id);
        const removeLocalRecord = () => {
            setJobs((current) => {
                const next = current.filter((item) => item.task_id !== job.task_id);
                writeCachedAccountJobs(cacheAccountId, next);
                return next;
            });
        };
        try {
            await deleteJob(job.task_id, isLocalJob(job) ? {sttProvider: 'local'} : {});
            removeLocalRecord();
            setError(null);
        } catch (err) {
            if (err.status === 404) {
                removeLocalRecord();
                setError(null);
                return;
            }
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setDeletingTaskId('');
        }
    };

    const statusLabel = (job) => {
        const taskState = normalizeTaskState(job);
        if (taskState === TASK_STATE_QUEUED) return t('tasks.queued');
        if (taskState === TASK_STATE_COMPLETED || isCachedOnlyTask(job)) return t('tasks.completed');
        if (taskState === TASK_STATE_FAILED) return t('tasks.failed');
        if (taskState === TASK_STATE_CANCELLED) return lang === 'zh' ? '已取消' : 'Cancelled';
        return t('tasks.running');
    };
    const statusClass = (job) => {
        const taskState = normalizeTaskState(job);
        return (
        taskState === TASK_STATE_COMPLETED || isCachedOnlyTask(job)
            ? 'bg-primary/10 text-primary border-primary/20'
            : taskState === TASK_STATE_FAILED
                ? 'bg-error-container text-on-error-container border-error/20'
                : taskState === TASK_STATE_CANCELLED
                    ? 'bg-surface-container text-on-surface-variant border-outline-variant/40'
                : taskState === TASK_STATE_QUEUED
                    ? 'bg-surface-container text-on-surface-variant border-outline-variant/40'
                    : 'bg-tertiary/10 text-tertiary border-tertiary/20'
        );
    };
    const formatUpdated = (job) => {
        const ts = Date.parse(job.updated_at || job.created_at || '');
        if (!ts) return '-';
        return timeAgo(ts, t);
    };
    const stageLabel = (job) => t(`status.${job.stage || (normalizeTaskState(job) === TASK_STATE_FAILED ? 'failed' : 'idle')}`);
    const liveStageDetail = (job) => {
        const progressMeta = job.metadata?.video_source_progress || {};
        const loaded = progressMeta.loaded_bytes ? fmtBytes(progressMeta.loaded_bytes) : '';
        const total = progressMeta.total_bytes ? fmtBytes(progressMeta.total_bytes) : '';
        const byteText = loaded && total ? ` · ${loaded} / ${total}` : (loaded ? ` · ${loaded}` : '');
        if (progressMeta.message) return `${progressMeta.message}${byteText}`;
        const taskState = normalizeTaskState(job);
        if (taskState === TASK_STATE_QUEUED) return lang === 'zh' ? '等待后台转录开始。' : 'Waiting for background transcription.';
        if (taskState === TASK_STATE_RUNNING) return job.summary_status || stageLabel(job);
        return '-';
    };
    const taskFailureDetail = (job) => {
        const taskState = normalizeTaskState(job);
        if (taskState === TASK_STATE_CANCELLED) return lang === 'zh' ? '用户已取消这个任务。' : 'This task was cancelled by the user.';
        if (taskState !== TASK_STATE_FAILED) return '';
        const raw = job.error_reason || job.result?.summary_error || job.result?.error_reason || job.metadata?.raw_error || '';
        return raw
            ? friendlyTaskError(raw, lang)
            : (lang === 'zh' ? '任务处理失败，但后端没有返回具体原因。' : 'The task failed, but no detailed reason was returned.');
    };
    const artifactButtons = [
        ['transcript_srt', t('tasks.srt')],
        ['transcript_txt', t('tasks.txt')],
        ['transcript_vtt', t('tasks.vtt')],
        ['transcript_bilingual_srt', t('tasks.bilingualSrt')],
        ['transcript_bilingual_vtt', t('tasks.bilingualVtt')],
        ['summary_md', t('tasks.md')],
    ];

    return (
        <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="mx-auto h-dvh max-w-[1500px] overflow-y-auto px-8 py-7 hide-scrollbar">
                <div className="space-y-5">
                    <div className="flex flex-col gap-3 rounded-[22px] border border-[#e4e0e0] bg-white px-3 py-3 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] md:flex-row md:items-center md:justify-between dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex flex-wrap gap-1.5">
                            {taskFilters.map(([key, label, count]) => (
                                <button key={key} type="button" onClick={() => setTaskFilter(key)} className={`inline-flex h-9 items-center gap-1.5 rounded-[14px] px-3 text-xs font-bold transition ${taskFilter === key ? 'bg-[#111111] text-white dark:bg-white dark:text-[#111111]' : 'text-[#666] hover:bg-[#efeeee] hover:text-[#111111] dark:text-white/55 dark:hover:bg-white/[0.08] dark:hover:text-white'}`}>
                                    {label}
                                    <span className={`tabular-nums ${taskFilter === key ? 'text-white dark:text-[#111111]' : 'text-[#8a8a8a] dark:text-white/40'}`}>{count}</span>
                                </button>
                            ))}
                        </div>
                        <button type="button" onClick={loadJobs} className="inline-flex h-9 items-center justify-center gap-1.5 rounded-[14px] px-3 text-xs font-bold text-[#666] hover:bg-[#efeeee] hover:text-[#111111] dark:text-white/55 dark:hover:bg-white/[0.08] dark:hover:text-white">
                            <RefreshCw className={`size-4 ${loading ? 'animate-spin' : ''}`} strokeWidth={2.15}/>
                            {t('tasks.refresh')}
                        </button>
                    </div>

                    {error && (
                        <div className="rounded-[16px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">{error}</div>
                    )}

                    <section className="space-y-3">
                        {queueUploadJob && (
                            <article className="rounded-[24px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                                    <div className="flex items-start gap-3 min-w-0">
                                        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[14px] bg-[#efeeee] text-[#111111] dark:bg-white/[0.12] dark:text-white">
                                            <LoaderCircle className="size-5 animate-spin" strokeWidth={2.15}/>
                                        </div>
                                        <div className="min-w-0">
                                            <h2 className="text-base font-headline font-bold text-on-surface dark:text-white">
                                                {lang === 'zh' ? '正在上传到后台任务' : 'Uploading to background tasks'}
                                            </h2>
                                            <p className="text-sm text-on-surface-variant mt-1">
                                                {lang === 'zh'
                                                    ? `已选择 ${queueUploadJob.queueTotal || 0} 个文件，上传完成后会自动出现在任务列表。`
                                                    : `${queueUploadJob.queueTotal || 0} files selected. They will appear here after upload finishes.`}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3 lg:w-[280px]">
                                        <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                            <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('dash.elapsed')}</p>
                                            <p className="text-sm font-semibold text-on-surface mt-1">{fmtElapsed(Math.floor((Date.now() - (queueUploadJob.startedAt || Date.now())) / 1000))}</p>
                                        </div>
                                        <div className="rounded-sm bg-surface-container-low px-3 py-2">
                                            <p className="text-[10px] uppercase tracking-wider font-bold text-outline">{t('dash.fileSize')}</p>
                                            <p className="text-sm font-semibold text-on-surface mt-1">{fmtFileSize(queueUploadJob.fileSizeMb)}</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#efeeee] progress-indeterminate dark:bg-white/[0.12]"></div>
                            </article>
                        )}
                        {visibleJobs.length === 0 && !loading && !queueUploadJob && (
                            <div className="rounded-[24px] border border-[#e4e0e0] bg-white p-10 text-center shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                <ListTodo className="mx-auto mb-3 size-10 text-[#8a8a8a] dark:text-white/40" strokeWidth={2}/>
                                <p className="text-sm font-semibold text-[#777] dark:text-white/55">{taskFilter === 'all' ? t('tasks.empty') : (lang === 'zh' ? '这个分类下暂时没有任务。' : 'No jobs in this view.')}</p>
                            </div>
                        )}
                        {visibleJobs.map((job) => {
                            const taskState = normalizeTaskState(job);
                            const progress = Math.max(0, Math.min(100, Number(job.progress) || (taskState === TASK_STATE_COMPLETED || taskState === TASK_STATE_CACHED_ONLY ? 100 : 0)));
                            const result = job.result || {};
                            const artifacts = result.artifacts || {};
                            const availableArtifacts = artifactButtons.filter(([kind]) => artifacts[kind]);
                            const larkUrl = result.lark_response?.url || result.feishu_doc_url || null;
                            const canOpen = hasTranscriptResult(result) || (!!result && (taskState === TASK_STATE_COMPLETED || taskState === TASK_STATE_CACHED_ONLY));
                            const planSummary = agentPlanSummary(job, lang);
                            const displayTitle = jobDisplayTitle(job, lang);
                            const failureDetail = taskFailureDetail(job);
                            const downloadItems = [
                                ...availableArtifacts.map(([kind, label]) => ({icon:'download', label, badge:kind.endsWith('vtt')?'VTT':kind.endsWith('srt')?'SRT':kind.endsWith('txt')?'TXT':kind.endsWith('md')?'MD':kind, onClick:()=>downloadArtifact(job,kind)})),
                                ...(larkUrl ? [{divider:true},{icon:'open_in_new', label:t('tasks.larkDoc'), onClick:()=>window.open(larkUrl,'_blank','noopener')}] : []),
                            ];
                            return (
                                <article key={job.task_id} className="rounded-[24px] border border-[#e4e0e0] bg-white p-4 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                    <div className="flex items-start gap-3">
                                        <div className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-[14px] ${isLiveJob(job) ? 'bg-[#efeeee] text-[#111111] dark:bg-white/[0.12] dark:text-white' : taskState === TASK_STATE_FAILED ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300' : 'bg-[#efeeee] text-[#111111] dark:bg-white/[0.12] dark:text-white'}`}>
                                            {job.source_type === 'transcript_file'
                                                ? <Subtitles className="size-5" strokeWidth={2.15}/>
                                                : <FileVideo className="size-5" strokeWidth={2.15}/>}
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <h2 className="max-w-[520px] truncate font-headline text-sm font-extrabold text-[#111111] dark:text-white" title={displayTitle}>{displayTitle}</h2>
                                                <span className={`rounded-full border px-2.5 py-1 text-[11px] font-bold flex-shrink-0 ${statusClass(job)}`}>{statusLabel(job)}</span>
                                                <span className="text-xs font-medium text-[#777] dark:text-white/55 flex-shrink-0">{formatUpdated(job)}</span>
                                            </div>
                                            {planSummary && (
                                                <p className="mt-1.5 text-xs font-medium leading-relaxed text-on-surface-variant">
                                                    <span className="mr-1 font-semibold">{planSummary.goal}</span>
                                                    {[planSummary.route, ...(planSummary.trace.length > 0 ? [planSummary.trace.join(' → ')] : [])].filter(Boolean).join(' · ')}
                                                </p>
                                            )}
                                            {isLiveJob(job) && (
                                            <div className="mt-2 ml-0 space-y-2">
                                                <div className={`h-1.5 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12] ${isSttProgressUnmeasured(jobToCurrentJob(job)) ? 'progress-indeterminate' : ''}`}>
                                                    {!isSttProgressUnmeasured(jobToCurrentJob(job)) && <div className="h-full bg-[#111111] transition-all duration-500 dark:bg-white" style={{width:`${progress}%`}}></div>}
                                                </div>
                                                <p className="rounded-sm bg-surface-container-low px-3 py-2 text-xs font-semibold leading-relaxed text-on-surface-variant">
                                                    {liveStageDetail(job)}
                                                </p>
                                            </div>
                                            )}
                                            {failureDetail && (
                                                <p className="mt-2 rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-relaxed text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">
                                                    {failureDetail}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-1.5 flex-shrink-0">
                                            {isLiveJob(job) ? (
                                                <button type="button" disabled={cancellingTaskId === job.task_id} onClick={() => cancelLiveJob(job)} className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] border border-red-200 bg-red-50 px-3.5 text-xs font-bold text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20">
                                                    {cancellingTaskId === job.task_id
                                                        ? <LoaderCircle className="size-4 animate-spin" strokeWidth={2.15}/>
                                                        : <XCircle className="size-4" strokeWidth={2.15}/>}
                                                    {lang === 'zh' ? '取消' : 'Cancel'}
                                                </button>
                                            ) : (
                                                <>
                                                    <button type="button" disabled={!canOpen} onClick={() => openJob(job)} className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] bg-[#111111] px-3.5 text-xs font-bold text-white transition-colors hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
                                                        <ExternalLink className="size-4" strokeWidth={2.15}/>
                                                        {t('tasks.open')}
                                                    </button>
                                                    {job.task_id ? (
                                                        <Link to={`/tasks/${encodeURIComponent(job.task_id)}/agent`} className="inline-flex h-10 items-center justify-center gap-1.5 rounded-[14px] border border-[#dedada] bg-[#f4f3f3] px-3 text-xs font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]">
                                                            <Activity className="size-3.5" strokeWidth={2.15}/>
                                                            Agent
                                                        </Link>
                                                    ) : null}
                                                    {downloadItems.length > 0 ? (
                                                        <DropdownMenu
                                                            align="right"
                                                            trigger={<button type="button" className="inline-flex h-10 items-center justify-center gap-1.5 rounded-[14px] border border-[#dedada] bg-[#f4f3f3] px-3 text-xs font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]"><Download className="size-4" strokeWidth={2.15}/></button>}
                                                            items={downloadItems}
                                                        />
                                                    ) : null}
                                                    <button type="button" disabled={!isDeletableJob(job) || deletingTaskId === job.task_id} onClick={() => deleteFinishedJob(job)} className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] border border-red-200 bg-red-50 px-3.5 text-xs font-bold text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20">
                                                        {deletingTaskId === job.task_id
                                                            ? <LoaderCircle className="size-4 animate-spin" strokeWidth={2.15}/>
                                                            : <Trash2 className="size-4" strokeWidth={2.15}/>}
                                                    </button>
                                                </>
                                            )}
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

export default Tasks;
