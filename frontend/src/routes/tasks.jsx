/* ═══════════════ Background Tasks ═══════════════ */
import {useCallback, useEffect, useMemo, useState} from 'react';
import {useLocation, useNavigate} from 'react-router-dom';
import {
    fmtBytes,
    fmtElapsed,
    fmtFileSize,
    friendlyTaskError,
    isSttProgressUnmeasured,
    jobToCurrentJob,
    jobToHistoryEntry,
    readCachedAccountJobs,
    timeAgo,
    useApi,
    useApp,
    useAuth,
    useI18n,
    writeCachedAccountJobs,
} from '../app.jsx';

const Tasks = () => {
    const {t, lang} = useI18n();
    const {authMode, user} = useAuth();
    const {currentJob, setLastResult, setCurrentJob, addToHistory} = useApp();
    const {getJobs, getJob, deleteJob, downloadJobArtifact} = useApi();
    const navigate = useNavigate();
    const location = useLocation();
    const cacheAccountId = authMode === 'accounts' ? user?.id : 'local';
    const [jobs, setJobs] = useState(() => readCachedAccountJobs(cacheAccountId));
    const [loading, setLoading] = useState(() => readCachedAccountJobs(cacheAccountId).length === 0);
    const [error, setError] = useState(() => location.state?.queueSubmitError || null);
    const [deletingTaskId, setDeletingTaskId] = useState('');
    const queueUploadJob = currentJob?.queueUpload ? currentJob : null;
    const isLiveJob = (job) => job.status === 'queued' || job.status === 'running';
    const [taskFilter, setTaskFilter] = useState('all');
    const stats = useMemo(() => ({
        live: jobs.filter(isLiveJob).length,
        failed: jobs.filter((job) => job.status === 'failed').length,
        completed: jobs.filter((job) => job.status === 'completed').length,
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
                if (taskFilter === 'failed') return job.status === 'failed';
                if (taskFilter === 'completed') return job.status === 'completed';
                return true;
            })
            .slice()
            .sort((a, b) => {
                const priorityDiff = (priority[a.status] ?? 9) - (priority[b.status] ?? 9);
                if (priorityDiff !== 0) return priorityDiff;
                return (Date.parse(b.updated_at || b.created_at || '') || 0) - (Date.parse(a.updated_at || a.created_at || '') || 0);
            });
    }, [jobs, taskFilter]);
    const hasLiveJobs = Boolean(queueUploadJob || jobs.some(isLiveJob));

    const loadJobs = useCallback(async () => {
        try {
            const next = await getJobs(100);
            writeCachedAccountJobs(cacheAccountId, next);
            setJobs(next);
            setError(null);
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setLoading(false);
        }
    }, [cacheAccountId, lang]);

    useEffect(() => {
        const cached = readCachedAccountJobs(cacheAccountId);
        if (cached.length) {
            setJobs(cached);
            setLoading(false);
        }
    }, [cacheAccountId]);

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
    const deleteFailedJob = async (job) => {
        if (job.status !== 'failed') return;
        if (!window.confirm(t('tasks.deleteConfirm'))) return;
        setDeletingTaskId(job.task_id);
        try {
            await deleteJob(job.task_id);
            setJobs((current) => {
                const next = current.filter((item) => item.task_id !== job.task_id);
                writeCachedAccountJobs(cacheAccountId, next);
                return next;
            });
            setError(null);
        } catch (err) {
            setError(friendlyTaskError(err.message || String(err), lang));
        } finally {
            setDeletingTaskId('');
        }
    };

    const statusLabel = (job) => {
        if (job.status === 'queued') return t('tasks.queued');
        if (job.status === 'completed') return t('tasks.completed');
        if (job.status === 'failed') return t('tasks.failed');
        return t('tasks.running');
    };
    const statusClass = (job) => (
        job.status === 'completed'
            ? 'bg-primary/10 text-primary border-primary/20'
            : job.status === 'failed'
                ? 'bg-error-container text-on-error-container border-error/20'
                : job.status === 'queued'
                    ? 'bg-surface-container text-on-surface-variant border-outline-variant/40'
                    : 'bg-tertiary/10 text-tertiary border-tertiary/20'
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
            <main className="px-8 py-10 max-w-[1500px] mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                <div className="space-y-5">
                    <header className="flex flex-col md:flex-row md:items-end justify-between gap-5">
                        <div className="max-w-3xl">
                            <h1 className="font-headline text-3xl font-extrabold text-on-surface mb-2">{t('tasks.title')}</h1>
                            <p className="text-sm leading-relaxed text-on-surface-variant max-w-[68ch]">{t('tasks.subtitle')}</p>
                        </div>
                        <button type="button" onClick={loadJobs} className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-surface-container-lowest text-on-surface font-bold text-sm border ff-border-muted hover:bg-surface-container-low transition-colors active:translate-y-px px-3.5">
                            <span className={`material-symbols-outlined text-base ${loading ? 'animate-spin' : ''}`}>refresh</span>
                            {t('tasks.refresh')}
                        </button>
                    </header>

                    <div className="flex flex-col gap-3 rounded-sm border ff-border-muted bg-surface-container-lowest px-3 py-3 md:flex-row md:items-center md:justify-between">
                        <div className="flex flex-wrap gap-1.5">
                            {taskFilters.map(([key, label, count]) => (
                                <button key={key} type="button" onClick={() => setTaskFilter(key)} className={`inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-xs font-bold transition ${taskFilter === key ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'}`}>
                                    {label}
                                    <span className={`tabular-nums ${taskFilter === key ? 'text-on-primary' : 'text-outline'}`}>{count}</span>
                                </button>
                            ))}
                        </div>
                        <p className="text-xs font-semibold text-on-surface-variant">
                            {hasLiveJobs
                                ? (lang === 'zh' ? '有任务进行中，5 秒自动刷新。' : 'Active jobs refresh every 5 seconds.')
                                : (lang === 'zh' ? '只有历史记录时，自动刷新会降频。' : 'History refreshes less often when no job is active.')}
                        </p>
                    </div>

                    {error && (
                        <div className="rounded-sm border border-error/20 bg-error-container px-4 py-3 text-sm font-semibold text-on-error-container">{error}</div>
                    )}

                    <section className="space-y-3">
                        {queueUploadJob && (
                            <article className="rounded-sm bg-surface-container-lowest border border-primary/20 shadow-sm p-5">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                                    <div className="flex items-start gap-3 min-w-0">
                                        <div className="w-10 h-10 rounded-sm bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                                            <span className="material-symbols-outlined text-lg animate-spin">sync</span>
                                        </div>
                                        <div className="min-w-0">
                                            <h2 className="text-base font-headline font-bold text-on-surface">
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
                                <div className="mt-4 h-2 rounded-full overflow-hidden bg-surface-container-highest progress-indeterminate"></div>
                            </article>
                        )}
                        {visibleJobs.length === 0 && !loading && !queueUploadJob && (
                            <div className="rounded-sm bg-surface-container-lowest border ff-border-muted p-10 text-center">
                                <span className="material-symbols-outlined text-4xl text-outline mb-3">pending_actions</span>
                                <p className="text-sm text-on-surface-variant">{taskFilter === 'all' ? t('tasks.empty') : (lang === 'zh' ? '这个分类下暂时没有任务。' : 'No jobs in this view.')}</p>
                            </div>
                        )}
                        {visibleJobs.map((job) => {
                            const progress = Math.max(0, Math.min(100, Number(job.progress) || (job.status === 'completed' ? 100 : 0)));
                            const result = job.result || {};
                            const artifacts = result.artifacts || {};
                            const availableArtifacts = artifactButtons.filter(([kind]) => artifacts[kind]);
                            const larkUrl = result.lark_response?.url || result.feishu_doc_url || null;
                            const canOpen = !!result && job.status === 'completed';
                            const showDetail = isLiveJob(job) || job.status === 'failed';
                            return (
                                <article key={job.task_id} className="rounded-sm bg-surface-container-lowest border ff-border-muted shadow-sm p-4">
                                    <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                                        <div className="min-w-0 flex-1 space-y-3">
                                            <div className="flex flex-wrap items-start gap-3">
                                                <div className={`w-9 h-9 rounded-sm flex items-center justify-center flex-shrink-0 ${isLiveJob(job) ? 'bg-tertiary/10 text-tertiary' : job.status === 'failed' ? 'bg-error-container text-on-error-container' : 'bg-primary/10 text-primary'}`}>
                                                    <span className="material-symbols-outlined text-lg">{job.source_type === 'transcript_file' ? 'subtitles' : 'movie'}</span>
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <h2 className="text-sm font-headline font-extrabold text-on-surface truncate" title={job.source_filename || job.task_id}>{job.source_filename || job.task_id}</h2>
                                                    <p className="text-xs text-on-surface-variant mt-1">
                                                        {formatUpdated(job)}
                                                        {job.source_file_size_mb ? ` • ${fmtFileSize(job.source_file_size_mb)}` : ''}
                                                        {result.audio_duration_seconds ? ` • ${fmtElapsed(result.audio_duration_seconds)}` : ''}
                                                        {` • ${providerLabel(job)}`}
                                                    </p>
                                                </div>
                                                <span className={`px-2.5 py-1 rounded-sm border text-[11px] font-bold ${statusClass(job)}`}>{statusLabel(job)}</span>
                                            </div>

                                            {showDetail && (
                                                <div className="ml-12 space-y-2">
                                                    {isLiveJob(job) && (
                                                        <div className={`h-1.5 rounded-full overflow-hidden bg-surface-container-highest ${isSttProgressUnmeasured(jobToCurrentJob(job)) ? 'progress-indeterminate' : ''}`}>
                                                            {!isSttProgressUnmeasured(jobToCurrentJob(job)) && <div className="h-full bg-primary transition-all duration-500" style={{width:`${progress}%`}}></div>}
                                                        </div>
                                                    )}
                                                    <p className={`rounded-sm px-3 py-2 text-xs font-semibold leading-relaxed ${job.status === 'failed' ? 'border border-error/20 bg-error-container text-on-error-container' : 'bg-surface-container-low text-on-surface-variant'}`}>
                                                        {job.status === 'failed' ? <span className="font-bold">{t('tasks.error')}： </span> : null}
                                                        {stageDetail(job)}
                                                    </p>
                                                </div>
                                            )}
                                        </div>

                                        <div className="lg:w-[430px] flex-shrink-0 space-y-2">
                                            {job.status === 'failed' ? (
                                                <button type="button" disabled={deletingTaskId === job.task_id} onClick={() => deleteFailedJob(job)} className="w-full inline-flex h-9 items-center justify-center gap-2 px-3.5 rounded-sm border border-error/20 bg-surface-container-low text-error font-bold text-xs hover:bg-error-container transition-colors disabled:opacity-40 disabled:cursor-not-allowed active:translate-y-px">
                                                    <span className="material-symbols-outlined text-base">{deletingTaskId === job.task_id ? 'sync' : 'delete'}</span>
                                                    {t('tasks.delete')}
                                                </button>
                                            ) : (
                                                <button type="button" disabled={!canOpen} onClick={() => openJob(job)} className="w-full inline-flex h-9 items-center justify-center gap-2 px-3.5 rounded-sm bg-primary text-on-primary font-bold text-xs hover:bg-primary-container transition-colors disabled:opacity-40 disabled:cursor-not-allowed active:translate-y-px">
                                                    <span className="material-symbols-outlined text-base">open_in_new</span>
                                                    {t('tasks.open')}
                                                </button>
                                            )}
                                            <div className="flex flex-wrap items-center justify-start gap-1.5 lg:justify-end">
                                                {availableArtifacts.length > 0 ? (
                                                    <>
                                                        <span className="mr-1 text-[11px] font-bold text-outline">{t('tasks.download')}</span>
                                                        {availableArtifacts.map(([kind, label]) => {
                                                        const artifact = artifacts[kind];
                                                        return (
                                                            <button key={kind} type="button" title={artifact?.filename || label} onClick={() => downloadArtifact(job, kind)} className="inline-flex h-7 items-center rounded-sm border ff-border-muted bg-surface-container-low px-2.5 text-[11px] font-bold text-on-surface transition hover:bg-surface-container active:translate-y-px">
                                                                {label}
                                                            </button>
                                                        );
                                                    })}
                                                    </>
                                                ) : (
                                                    <span className="text-[11px] font-semibold text-outline">{t('tasks.noOutputs')}</span>
                                                )}
                                                {larkUrl && (
                                                    <a href={larkUrl} target="_blank" rel="noopener noreferrer" className="inline-flex h-7 items-center justify-center gap-1.5 rounded-sm border border-primary/30 px-2.5 text-[11px] font-bold text-primary transition hover:bg-primary/10">
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

export default Tasks;
