import {useEffect, useMemo, useState} from 'react';
import {Link, useLocation, useNavigate, useParams} from 'react-router-dom';
import {
    AlertTriangle,
    ArrowLeft,
    CheckCircle2,
    CircleDashed,
    Clock3,
    FileText,
    GitBranch,
    LoaderCircle,
    XCircle,
} from 'lucide-react';
import {API_BASE, apiFetch, localExecutionHeaders, noteModeLabel, useApp, useI18n} from '../app/shared.jsx';
import TaskProgressOverview from '../components/TaskProgressOverview.jsx';

const statusText = (status, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        completed: isZh ? '已完成' : 'Completed',
        running: isZh ? '进行中' : 'Running',
        pending: isZh ? '等待中' : 'Pending',
        failed: isZh ? '失败' : 'Failed',
        skipped: isZh ? '已跳过' : 'Skipped',
        cancelled: isZh ? '已取消' : 'Cancelled',
    };
    return labels[status] || status || (isZh ? '未记录' : 'Not recorded');
};

const sourceText = (source, lang) => {
    if (source === 'recorded') return lang === 'zh' ? '真实记录' : 'Recorded';
    if (source === 'inferred') return lang === 'zh' ? '兼容推导' : 'Inferred';
    return source || (lang === 'zh' ? '未记录' : 'Not recorded');
};

const confidenceText = (value, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        high: isZh ? '高置信度' : 'High confidence',
        medium: isZh ? '中置信度' : 'Medium confidence',
        low: isZh ? '低置信度' : 'Low confidence',
    };
    return labels[value] || value || '';
};

const statusTone = (status) => {
    if (status === 'failed') return {
        dot: 'border-red-200 bg-red-50 text-red-600 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200',
        badge: 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200',
        Icon: XCircle,
    };
    if (status === 'running') return {
        dot: 'border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-200',
        badge: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-200',
        Icon: LoaderCircle,
    };
    if (status === 'pending') return {
        dot: 'border-[#dedada] bg-white text-[#85868c] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/50',
        badge: 'border-[#dedada] bg-white text-[#85868c] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/50',
        Icon: CircleDashed,
    };
    if (status === 'skipped' || status === 'cancelled') return {
        dot: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100',
        badge: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100',
        Icon: AlertTriangle,
    };
    return {
        dot: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200',
        badge: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200',
        Icon: CheckCircle2,
    };
};

const compactValues = (items, limit = 5) => (
    (Array.isArray(items) ? items : [])
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .slice(0, limit)
);

const chapterCoverageData = (pageData) => {
    const detailCoverage = pageData?.chapter_coverage;
    if (detailCoverage && typeof detailCoverage === 'object') return detailCoverage;
    const packageCoverage = pageData?.note?.chapter_coverage;
    if (packageCoverage && typeof packageCoverage === 'object') return packageCoverage;
    return null;
};

const formatSeconds = (value) => {
    const total = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const rangeText = (item, lang) => {
    const startSeconds = Number(item?.start_seconds);
    const endSeconds = Number(item?.end_seconds);
    if (Number.isFinite(startSeconds) && Number.isFinite(endSeconds) && endSeconds > startSeconds) {
        return `${formatSeconds(startSeconds)}-${formatSeconds(endSeconds)}`;
    }
    const start = Number(item?.char_start);
    const end = Number(item?.char_end);
    if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
        return lang === 'zh' ? `字符 ${start}-${end}` : `Chars ${start}-${end}`;
    }
    const ids = compactValues(item?.source_segment_ids, 3);
    if (ids.length) return ids.join(', ');
    return lang === 'zh' ? '未记录' : 'Not recorded';
};

function fallbackDecisionEntries(packageData, lang) {
    const plan = packageData?.processing_plan || {};
    const material = plan.material || {};
    const note = packageData?.note || {};
    const noteMode = plan.note_strategy?.resolved_mode || note.resolved_mode || plan.note_strategy?.selected_mode || note.requested_mode || 'auto';
    const fallback = [
        {
            id: 'material_classification',
            title: lang === 'zh' ? '判断材料类型' : 'Material classification',
            status: material.type ? 'completed' : 'pending',
            decision: material.type || (lang === 'zh' ? '待判断' : 'Pending'),
            reason: plan.goal?.reason || (lang === 'zh' ? '根据来源、时长和正文线索判断材料用途。' : 'Judged from source, duration, and transcript signals.'),
            evidence: compactValues(material.evidence),
            impact: plan.goal?.reason || (lang === 'zh' ? '影响后续笔记结构和重点保留方式。' : 'Affects note structure and what gets preserved.'),
            source: 'inferred',
            confidence: material.confidence,
        },
        {
            id: 'note_mode_selection',
            title: lang === 'zh' ? '选择笔记生成方式' : 'Note mode selection',
            status: noteMode ? 'completed' : 'pending',
            decision: noteModeLabel(noteMode, lang),
            reason: plan.note_strategy?.reason || (lang === 'zh' ? '按当前自动模式和材料信息选择。' : 'Chosen from automatic mode and material signals.'),
            evidence: compactValues([
                material.duration_seconds ? `${lang === 'zh' ? '时长' : 'Duration'}：${Math.round(Number(material.duration_seconds) / 60)} min` : '',
                plan.note_strategy?.confidence ? `${lang === 'zh' ? '置信度' : 'Confidence'}：${plan.note_strategy.confidence}` : '',
            ]),
            impact: lang === 'zh' ? '影响生成速度、结构完整度和证据覆盖。' : 'Affects speed, structure, and evidence coverage.',
            source: 'inferred',
            confidence: plan.note_strategy?.confidence,
        },
        {
            id: 'note_generation_outcome',
            title: lang === 'zh' ? '判断笔记生成结果' : 'Note result',
            status: note.status || note.diagnosis?.status || 'pending',
            decision: note.diagnosis?.title || (lang === 'zh' ? '等待结果' : 'Waiting for result'),
            reason: note.diagnosis?.detail || '',
            evidence: compactValues([
                note.markdown_chars ? `${lang === 'zh' ? '笔记字数' : 'Note chars'}：${Number(note.markdown_chars).toLocaleString()}` : '',
            ]),
            impact: note.diagnosis?.next_action || '',
            source: 'inferred',
        },
    ];
    return fallback.filter((entry) => entry.title || entry.decision);
}

function decisionEntries(packageData, lang) {
    const entries = packageData?.decision_log?.entries;
    if (Array.isArray(entries) && entries.length) return entries;
    return fallbackDecisionEntries(packageData, lang);
}

const DecisionEntry = ({entry, index, isLast, lang}) => {
    const tone = statusTone(entry.status);
    const Icon = tone.Icon;
    const evidence = compactValues(entry.evidence, 6);
    const warnings = compactValues(entry.warnings, 3);
    return (
        <article className="grid grid-cols-[42px_minmax(0,1fr)] gap-3">
            <div className="relative flex justify-center">
                {!isLast && <div className="absolute top-11 h-[calc(100%-1rem)] w-px bg-[#dedada] dark:bg-white/[0.12]"/>}
                <div className={`relative z-10 flex size-9 items-center justify-center rounded-[13px] border ${tone.dot}`}>
                    <Icon className={`size-[18px] ${entry.status === 'running' ? 'animate-spin' : ''}`} strokeWidth={2.15}/>
                </div>
            </div>
            <div className="min-w-0 rounded-[18px] border border-[#dedada] bg-white p-4 shadow-[0_18px_44px_-38px_rgba(17,17,17,.42)] dark:border-white/[0.10] dark:bg-white/[0.055] dark:shadow-none">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-extrabold text-[#85868c] dark:text-white/45">
                        {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${tone.badge}`}>
                        {statusText(entry.status, lang)}
                    </span>
                    <span className="rounded-full border border-[#dedada] bg-[#f7f7f7] px-2 py-0.5 text-[10px] font-extrabold text-[#676970] dark:border-white/[0.10] dark:bg-white/[0.06] dark:text-white/55">
                        {sourceText(entry.source, lang)}
                    </span>
                    {entry.confidence && (
                        <span className="rounded-full border border-[#dedada] px-2 py-0.5 text-[10px] font-extrabold text-[#676970] dark:border-white/[0.10] dark:text-white/55">
                            {confidenceText(entry.confidence, lang)}
                        </span>
                    )}
                </div>
                <div className="mt-3 min-w-0">
                    <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">{entry.title}</p>
                    <h2 className="mt-1 text-[18px] font-extrabold leading-snug text-[#111111] dark:text-white">
                        {entry.decision || (lang === 'zh' ? '等待判断' : 'Pending decision')}
                    </h2>
                </div>
                {entry.reason && (
                    <p className="mt-3 text-[13px] font-semibold leading-6 text-[#2f3035] dark:text-white/78">
                        {entry.reason}
                    </p>
                )}
                {evidence.length > 0 && (
                    <div className="mt-4">
                        <p className="mb-2 text-[11px] font-extrabold text-[#85868c] dark:text-white/40">
                            {lang === 'zh' ? '证据摘要' : 'Evidence summary'}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                            {evidence.map((item) => (
                                <span key={item} className="rounded-[10px] border border-[#dedada] bg-[#fbfbfb] px-2.5 py-1 text-[12px] font-bold leading-5 text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/62">
                                    {item}
                                </span>
                            ))}
                        </div>
                    </div>
                )}
                {entry.impact && (
                    <div className="mt-4 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-[12px] font-semibold leading-5 text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.04] dark:text-white/62">
                        <span className="mr-1 font-extrabold text-[#111111] dark:text-white/82">{lang === 'zh' ? '影响：' : 'Impact: '}</span>
                        {entry.impact}
                    </div>
                )}
                {warnings.length > 0 && (
                    <div className="mt-3 space-y-1.5">
                        {warnings.map((item) => (
                            <p key={item} className="rounded-[12px] border border-amber-300/50 bg-amber-50 px-3 py-2 text-[12px] font-bold leading-5 text-amber-900 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100">
                                {item}
                            </p>
                        ))}
                    </div>
                )}
            </div>
        </article>
    );
};

const StatBlock = ({label, value}) => (
    <div className="rounded-[14px] border border-[#dedada] bg-[#fbfbfb] p-3 dark:border-white/[0.10] dark:bg-white/[0.04]">
        <p className="text-[11px] font-extrabold text-[#85868c] dark:text-white/45">{label}</p>
        <p className="mt-1 truncate text-[14px] font-extrabold text-[#111111] dark:text-white">{value}</p>
    </div>
);

const ChapterCoverageEvidence = ({coverage, lang}) => {
    if (!coverage) return null;
    const isZh = lang === 'zh';
    const summary = coverage.summary || {};
    const chapters = Array.isArray(coverage.chapters) ? coverage.chapters : [];
    const evidence = Array.isArray(coverage.evidence) ? coverage.evidence : [];
    if (!evidence.length && !chapters.length) return null;
    const visibleEvidence = evidence.slice(0, 12);
    const hiddenCount = Math.max(evidence.length - visibleEvidence.length, 0);
    return (
        <section className="border-y border-[#dedada] py-5 dark:border-white/[0.10]">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                <div>
                    <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">
                        {isZh ? 'Chapter Coverage 证据表' : 'Chapter coverage evidence'}
                    </p>
                    <h2 className="font-headline text-[20px] font-extrabold text-[#111111] dark:text-white">
                        {isZh ? '这份笔记覆盖了哪些原文证据' : 'Source evidence behind this note'}
                    </h2>
                </div>
                <div className="grid grid-cols-3 gap-2 text-[12px] sm:min-w-[26rem]">
                    <StatBlock label={isZh ? '证据' : 'Evidence'} value={summary.evidence_count ?? evidence.length}/>
                    <StatBlock label={isZh ? '章节' : 'Chapters'} value={summary.chapter_count ?? chapters.length}/>
                    <StatBlock
                        label={isZh ? '重点覆盖' : 'Important'}
                        value={`${summary.covered_important_evidence_count ?? '-'} / ${summary.important_evidence_count ?? '-'}`}
                    />
                </div>
            </div>

            {chapters.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                    {chapters.map((chapter) => (
                        <span key={chapter.chapter_id || chapter.title} className="rounded-full border border-[#dedada] bg-white px-3 py-1 text-[12px] font-bold text-[#57585d] dark:border-white/[0.10] dark:bg-white/[0.055] dark:text-white/62">
                            {chapter.order ? `${chapter.order}. ` : ''}{chapter.title || chapter.chapter_id}
                            <span className="ml-1 text-[#85868c] dark:text-white/40">({chapter.evidence_count ?? 0})</span>
                        </span>
                    ))}
                </div>
            )}

            {visibleEvidence.length > 0 && (
                <div className="mt-4 overflow-x-auto rounded-[16px] border border-[#dedada] dark:border-white/[0.10]">
                    <div className="grid min-w-[46rem] grid-cols-[5rem_7rem_minmax(0,1fr)_9rem] border-b border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-[11px] font-extrabold text-[#85868c] dark:border-white/[0.10] dark:bg-white/[0.035] dark:text-white/42">
                        <span>ID</span>
                        <span>{isZh ? '重要性' : 'Weight'}</span>
                        <span>{isZh ? '证据内容' : 'Evidence'}</span>
                        <span>{isZh ? '来源' : 'Source'}</span>
                    </div>
                    <div className="min-w-[46rem] divide-y divide-[#dedada] bg-white dark:divide-white/[0.08] dark:bg-white/[0.035]">
                        {visibleEvidence.map((item) => (
                            <div key={item.evidence_id} className="grid grid-cols-[5rem_7rem_minmax(0,1fr)_9rem] gap-0 px-3 py-3 text-[12px] leading-5">
                                <span className="font-extrabold text-[#111111] dark:text-white">{item.evidence_id}</span>
                                <span className="font-bold text-[#676970] dark:text-white/58">
                                    {item.importance ?? '-'} / 5
                                    {item.covered === false && <span className="ml-1 text-amber-700 dark:text-amber-200">{isZh ? '待补' : 'open'}</span>}
                                </span>
                                <span className="min-w-0 pr-4 font-semibold text-[#2f3035] dark:text-white/76">
                                    {item.text}
                                    {Array.isArray(item.keywords) && item.keywords.length > 0 && (
                                        <span className="ml-2 text-[#85868c] dark:text-white/42">
                                            {item.keywords.slice(0, 3).join(' / ')}
                                        </span>
                                    )}
                                    {Array.isArray(item.covered_by_chapter_ids) && item.covered_by_chapter_ids.length > 0 && (
                                        <span className="ml-2 text-[#85868c] dark:text-white/42">
                                            {isZh ? '章节' : 'Chapter'} {item.covered_by_chapter_ids.slice(0, 3).join(', ')}
                                        </span>
                                    )}
                                </span>
                                <span className="font-bold text-[#676970] dark:text-white/54">{rangeText(item, lang)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {hiddenCount > 0 && (
                <p className="mt-2 text-[12px] font-bold text-[#85868c] dark:text-white/45">
                    {isZh ? `还有 ${hiddenCount} 条证据未在此处展开。` : `${hiddenCount} more evidence rows hidden here.`}
                </p>
            )}
        </section>
    );
};

const actionToneClass = (tone) => {
    if (tone === 'danger') {
        return 'border-red-200 bg-red-50 text-red-700 hover:bg-red-100 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200 dark:hover:bg-red-400/15';
    }
    if (tone === 'primary') {
        return 'border-[#111111] bg-[#111111] text-white hover:bg-[#2a2a2a] dark:border-white dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]';
    }
    return 'border-[#dedada] bg-white text-[#111111] hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]';
};

const visibleActions = (actions=[]) => (
    (Array.isArray(actions) ? actions : [])
        .filter((action) => action?.enabled !== false)
        .filter((action) => ['open_result', 'regenerate_note', 'cancel', 'delete', 'resubmit'].includes(action.id))
);

const AgentTrace = () => {
    const {taskId} = useParams();
    const navigate = useNavigate();
    const location = useLocation();
    const {lang} = useI18n();
    const {currentJob, setLastResult} = useApp();
    const initialJob = location.state?.job && location.state.job.task_id === taskId ? location.state.job : null;
    const [loading, setLoading] = useState(!initialJob);
    const [error, setError] = useState(null);
    const [pageData, setPageData] = useState(() => initialJob ? {
        ok: true,
        task: {
            task_id: initialJob.task_id,
            status: initialJob.status,
            stage: initialJob.stage,
            progress: initialJob.progress,
            source_type: initialJob.source_type,
            title: initialJob.metadata?.display_title || initialJob.source_filename,
            filename: initialJob.source_filename,
            created_at: initialJob.created_at,
            updated_at: initialJob.updated_at,
        },
        title: initialJob.metadata?.display_title || initialJob.source_filename || taskId,
        decision_log: {entries: []},
        actions: [],
    } : null);
    const [actionBusy, setActionBusy] = useState(null);
    const [actionError, setActionError] = useState(null);
    const isZh = lang === 'zh';

    const readJson = async (path, options={}) => {
        const response = await apiFetch(`${API_BASE}${path}`, {headers: localExecutionHeaders(options)});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const exc = new Error(data?.detail || `HTTP ${response.status}`);
            exc.status = response.status;
            throw exc;
        }
        return data;
    };

    const readJsonWithLocalFallback = async (path) => {
        const currentJobOptions = currentJob?.taskId === taskId ? {sttProvider: currentJob.sttProvider} : {};
        const currentIsLocal = !!localExecutionHeaders(currentJobOptions)['X-FluentFlow-Execution-Target'];
        try {
            return await readJson(path, currentJobOptions);
        } catch (exc) {
            if (exc.status !== 404 || currentIsLocal) throw exc;
            return await readJson(path, {localExecution: true});
        }
    };

    const loadTaskDetail = async (staleRef={current:false}, {silent=false} = {}) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            const detailData = await readJsonWithLocalFallback(`/jobs/${encodeURIComponent(taskId)}/detail`);
            if (!staleRef.current) setPageData(detailData);
        } catch (detailError) {
            try {
                const packageData = await readJsonWithLocalFallback(`/agent/v1/tasks/${encodeURIComponent(taskId)}/package`);
                if (!staleRef.current) setPageData(packageData);
            } catch (packageError) {
                if (!staleRef.current && !pageData) setError(packageError.message || detailError.message || String(packageError));
            }
        } finally {
            if (!staleRef.current) setLoading(false);
        }
    };

    useEffect(() => {
        const staleRef = {current: false};
        loadTaskDetail(staleRef);
        return () => { staleRef.current = true; };
    }, [taskId]);

    useEffect(() => {
        const taskStatus = String(pageData?.task?.status || '').toLowerCase();
        const taskStage = String(pageData?.task?.stage || '').toLowerCase();
        if (!['queued', 'running'].includes(taskStatus) && !['queued', 'resolving', 'downloading', 'saving', 'audio', 'stt', 'summary', 'export'].includes(taskStage)) return undefined;
        const staleRef = {current: false};
        const timer = setInterval(() => loadTaskDetail(staleRef, {silent: true}), 3000);
        return () => {
            staleRef.current = true;
            clearInterval(timer);
        };
    }, [pageData?.task?.status, pageData?.task?.stage, taskId]);

    const runAction = async (action) => {
        if (!action || actionBusy) return;
        setActionBusy(action.id);
        setActionError(null);
        try {
            if (action.id === 'resubmit' || action.method === 'NAVIGATE') {
                navigate(action.path || '/');
                return;
            }
            if (action.id === 'open_result') {
                const response = await apiFetch(`${API_BASE}/jobs/${encodeURIComponent(taskId)}`);
                const job = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(job?.detail || `HTTP ${response.status}`);
                if (job?.result) setLastResult(job.result);
                navigate('/editor');
                return;
            }
            const response = await apiFetch(`${API_BASE}${action.path}`, {method: action.method || 'POST'});
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
            if (action.id === 'delete') {
                navigate('/tasks');
                return;
            }
            if (action.id === 'regenerate_note' && data?.result) {
                setLastResult(data.result);
                navigate('/editor');
                return;
            }
            await loadTaskDetail();
        } catch (exc) {
            setActionError(exc.message || String(exc));
        } finally {
            setActionBusy(null);
        }
    };

    const title = pageData?.task?.title || pageData?.title || taskId;
    const decisions = useMemo(() => decisionEntries(pageData, lang), [pageData, lang]);
    const chapterCoverage = useMemo(() => chapterCoverageData(pageData), [pageData]);
    const recordedCount = decisions.filter((entry) => entry.source === 'recorded').length;
    const diagnosis = pageData?.diagnosis || pageData?.note?.diagnosis || {};
    const taskStatus = pageData?.task?.status || pageData?.note?.status || '-';
    const actions = visibleActions(pageData?.actions);

    if (loading) {
        return (
            <main className="ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 items-center justify-center bg-[#f8f7fb] p-8 transition-[margin] duration-200 ease-out dark:bg-[#101010]">
                <div className="flex items-center gap-2.5 text-sm font-semibold text-on-surface-variant">
                    <LoaderCircle className="size-4 animate-spin" strokeWidth={2.15}/>
                    {isZh ? '加载判断推进...' : 'Loading decision flow...'}
                </div>
            </main>
        );
    }

    if (error) {
        return (
            <main className="ml-[var(--sidebar-offset)] flex min-h-dvh flex-1 flex-col items-center justify-center gap-4 bg-[#f8f7fb] p-8 transition-[margin] duration-200 ease-out dark:bg-[#101010]">
                <div className="rounded-[16px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">{error}</div>
                <button type="button" onClick={() => navigate('/tasks')} className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-4 text-sm font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]">
                    <ArrowLeft className="size-4" strokeWidth={2.15}/>
                    {isZh ? '返回任务列表' : 'Back to Tasks'}
                </button>
            </main>
        );
    }

    return (
        <main className="ml-[var(--sidebar-offset)] min-h-dvh flex-1 overflow-y-auto bg-[#f8f7fb] px-6 py-5 text-[#111111] transition-[margin] duration-200 ease-out hide-scrollbar dark:bg-[#101010] dark:text-white/[0.92] lg:px-10">
            <div className="mx-auto max-w-7xl space-y-5">
                <header className="flex flex-col gap-3 border-b border-[#dedada] pb-4 dark:border-white/[0.10] lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <Link to="/tasks" className="inline-flex items-center gap-1.5 text-[13px] font-bold text-[#676970] transition hover:text-[#111111] dark:text-white/55 dark:hover:text-white">
                                <ArrowLeft className="size-3.5" strokeWidth={2.15}/>
                                {isZh ? '任务记录' : 'Tasks'}
                            </Link>
                            <span className="text-[#a2a3a8] dark:text-white/35">/</span>
                            <h1 className="font-headline text-[22px] font-extrabold leading-tight text-[#111111] dark:text-white">
                                {isZh ? '处理详情' : 'Task details'}
                            </h1>
                            <span className="rounded-full border border-[#dedada] bg-white px-2.5 py-1 text-[11px] font-extrabold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                {isZh ? 'Agent 工作流' : 'Agent workflow'}
                            </span>
                        </div>
                        <p className="mt-1 max-w-[72ch] truncate text-[13px] leading-5 text-[#676970] dark:text-white/60" title={title}>
                            {title}
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2 lg:justify-end">
                        <Link to="/editor" className="inline-flex h-9 items-center gap-2 rounded-[12px] bg-[#111111] px-4 text-[13px] font-extrabold text-white transition hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
                            <FileText className="size-4" strokeWidth={2.15}/>
                            {isZh ? '查看结果' : 'View result'}
                        </Link>
                        <Link to="/tasks" className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-4 text-[13px] font-extrabold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]">
                            <Clock3 className="size-4" strokeWidth={2.15}/>
                            {isZh ? '任务列表' : 'Task list'}
                        </Link>
                    </div>
                </header>

                <TaskProgressOverview pageData={pageData}/>

                <section className="rounded-[20px] border border-[#dedada] bg-white p-4 dark:border-white/[0.10] dark:bg-white/[0.055]">
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.4fr)] lg:items-center">
                        <div className="min-w-0">
                            <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">
                                {isZh ? '判断记录' : 'Decision records'}
                            </p>
                            <h2 className="mt-1 font-headline text-[20px] font-extrabold text-[#111111] dark:text-white">
                                {isZh ? '系统每一步为什么这样处理' : 'Why the system handled this task this way'}
                            </h2>
                            <p className="mt-2 max-w-[78ch] text-[13px] leading-5 text-[#676970] dark:text-white/60">
                                {isZh
                                    ? '这里展示可复查的判断结论、依据和影响。实时阶段和处理配置已经收敛到顶部。'
                                    : 'This shows reviewable decisions, evidence, and impact. Live stage and route context are consolidated above.'}
                            </p>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-[12px]">
                            <StatBlock label={isZh ? '判断数' : 'Decisions'} value={decisions.length || '-'}/>
                            <StatBlock label={isZh ? '真实记录' : 'Recorded'} value={recordedCount}/>
                            <StatBlock label={isZh ? '任务状态' : 'Status'} value={statusText(taskStatus, lang)}/>
                        </div>
                    </div>
                </section>

                <ChapterCoverageEvidence coverage={chapterCoverage} lang={lang}/>

                <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.55fr)]">
                    <section className="min-w-0 space-y-4">
                        <div>
                            <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">
                                {isZh ? '判断推进流' : 'Decision stream'}
                            </p>
                            <h2 className="font-headline text-[18px] font-extrabold text-[#111111] dark:text-white">
                                {isZh ? '关键判断、依据和影响' : 'Key decisions, evidence, and impact'}
                            </h2>
                        </div>
                        <div className="space-y-3">
                            {decisions.map((entry, index) => (
                                <DecisionEntry
                                    key={entry.id || `${entry.title}-${index}`}
                                    entry={entry}
                                    index={index}
                                    isLast={index === decisions.length - 1}
                                    lang={lang}
                                />
                            ))}
                            {!decisions.length && (
                                <div className="rounded-[18px] border border-[#dedada] bg-white p-6 text-[13px] font-semibold text-[#676970] dark:border-white/[0.10] dark:bg-white/[0.055] dark:text-white/58">
                                    {isZh ? '当前任务还没有可展示的判断记录。' : 'No decision records are available for this task yet.'}
                                </div>
                            )}
                        </div>
                    </section>

                    <aside className="space-y-5 xl:border-l xl:border-[#dedada] xl:pl-5 xl:dark:border-white/[0.10]">
                        <section>
                            <div className="mb-3 flex items-center gap-2">
                                <GitBranch className="size-4 text-[#676970] dark:text-white/55" strokeWidth={2.15}/>
                                <div>
                                    <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">
                                        {isZh ? '下一步' : 'Next step'}
                                    </p>
                                    <h2 className="font-headline text-[18px] font-extrabold text-[#111111] dark:text-white">
                                        {diagnosis.title || (isZh ? '复查结果' : 'Review result')}
                                    </h2>
                                </div>
                            </div>
                            <div className="space-y-2 text-[13px] leading-5 text-[#676970] dark:text-white/60">
                                <p className={`rounded-[14px] border p-3 font-semibold ${
                                    diagnosis.severity === 'error'
                                        ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200'
                                        : 'border-[#dedada] bg-white dark:border-white/[0.10] dark:bg-white/[0.055]'
                                }`}>
                                    {diagnosis.detail || diagnosis.next_action || (isZh ? '打开编辑器复查正文，必要时重生笔记。' : 'Open the editor to review the result, and regenerate the note if needed.')}
                                </p>
                                {diagnosis.next_action && diagnosis.next_action !== diagnosis.detail && (
                                    <p className="rounded-[14px] border border-[#dedada] bg-white p-3 font-semibold dark:border-white/[0.10] dark:bg-white/[0.055]">
                                        {diagnosis.next_action}
                                    </p>
                                )}
                                {actions.length > 0 && (
                                    <div className="flex flex-wrap gap-2 pt-1">
                                        {actions.map((action) => (
                                            <button
                                                key={action.id}
                                                type="button"
                                                disabled={!!actionBusy}
                                                onClick={() => runAction(action)}
                                                className={`inline-flex h-9 items-center rounded-[12px] border px-3 text-[12px] font-extrabold transition disabled:cursor-not-allowed disabled:opacity-55 ${actionToneClass(action.tone)}`}
                                            >
                                                {actionBusy === action.id ? (isZh ? '处理中...' : 'Working...') : action.label}
                                            </button>
                                        ))}
                                    </div>
                                )}
                                {actionError && (
                                    <p className="rounded-[14px] border border-red-200 bg-red-50 p-3 font-semibold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
                                        {actionError}
                                    </p>
                                )}
                            </div>
                        </section>
                    </aside>
                </div>
            </div>
        </main>
    );
};

export default AgentTrace;
