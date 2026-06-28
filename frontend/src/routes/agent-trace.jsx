import {useEffect, useMemo, useState} from 'react';
import {Link, useParams, useNavigate} from 'react-router-dom';
import {API_BASE, apiFetch, noteModeLabel, useI18n} from '../app/shared.jsx';
import SvgIcon from '../components/SvgIcon.jsx';

const languageLabel = (value, lang) => {
    const normalized = String(value || '').toLowerCase();
    if (!normalized || normalized === 'auto') return lang === 'zh' ? '未记录' : 'Not recorded';
    if (normalized.startsWith('en')) return lang === 'zh' ? '英文' : 'English';
    if (normalized.startsWith('zh') || normalized.startsWith('cmn')) return lang === 'zh' ? '中文' : 'Chinese';
    return value;
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

const confidenceLabel = (value, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        high: isZh ? '高' : 'High',
        medium: isZh ? '中' : 'Medium',
        low: isZh ? '低' : 'Low',
    };
    return labels[value] || value || (isZh ? '未记录' : 'Not recorded');
};

const routeLabel = (plan, lang) => {
    const tool = plan?.execution?.transcription_tool || '';
    const scope = plan?.execution?.scope || '';
    if (tool === 'transcript_parser') return lang === 'zh' ? '读取字幕文件' : 'Read transcript file';
    if (tool === 'local_whisper') return lang === 'zh' ? '本地 faster-whisper' : 'Local faster-whisper';
    if (tool === 'cloud_stt') return lang === 'zh' ? '云端转录' : 'Cloud STT';
    if (scope === 'cloud') return lang === 'zh' ? '云端执行' : 'Cloud execution';
    if (scope === 'local') return lang === 'zh' ? '本机执行' : 'Local execution';
    return lang === 'zh' ? '按任务来源决定' : 'From task source';
};

const sourceTypeLabel = (value, lang) => {
    const isZh = lang === 'zh';
    const labels = {
        video_link: isZh ? '视频链接' : 'Video link',
        transcript_file: isZh ? '字幕文件' : 'Transcript file',
        video: isZh ? '视频文件' : 'Video file',
        audio: isZh ? '音频文件' : 'Audio file',
    };
    return labels[value] || value || (isZh ? '未知来源' : 'Unknown source');
};

const formatDuration = (seconds, lang) => {
    const value = Number(seconds) || 0;
    if (!value) return lang === 'zh' ? '未记录' : 'Not recorded';
    const mins = Math.round(value / 60);
    if (mins < 1) return lang === 'zh' ? `${Math.round(value)} 秒` : `${Math.round(value)} sec`;
    if (mins < 60) return lang === 'zh' ? `${mins} 分钟` : `${mins} min`;
    const hours = Math.floor(mins / 60);
    const rest = mins % 60;
    return lang === 'zh' ? `${hours} 小时 ${rest} 分钟` : `${hours}h ${rest}m`;
};

const compactList = (items, fallback, limit = 3) => {
    const values = (Array.isArray(items) ? items : []).map((item) => String(item || '').trim()).filter(Boolean);
    if (!values.length) return fallback;
    return values.slice(0, limit).join('；');
};

const noteStatusText = (note, lang) => {
    const status = note?.status || note?.diagnosis?.status || 'unavailable';
    const isZh = lang === 'zh';
    const labels = {
        completed: isZh ? '笔记已生成' : 'Note generated',
        pending: isZh ? '笔记生成中' : 'Note pending',
        skipped: isZh ? '仅转录，未生成笔记' : 'Transcript only',
        failed: isZh ? '笔记生成失败' : 'Note failed',
        unavailable: isZh ? '没有可用笔记' : 'No note available',
    };
    return labels[status] || status;
};

const stageLabel = (step, lang) => {
    if (step?.label) return step.label;
    const id = String(step?.id || '');
    const isZh = lang === 'zh';
    const labels = {
        resolve_link: isZh ? '解析链接' : 'Resolve link',
        download_video: isZh ? '下载视频' : 'Download video',
        save_source: isZh ? '保存来源' : 'Save source',
        parse_subtitles: isZh ? '读取字幕' : 'Read subtitles',
        extract_audio: isZh ? '提取音频' : 'Extract audio',
        local_stt: isZh ? '本地转录' : 'Local STT',
        cloud_stt: isZh ? '云端转录' : 'Cloud STT',
        diarize_speakers: isZh ? '区分讲话人' : 'Diarize speakers',
        cleanup_transcript: isZh ? '清理转录' : 'Clean transcript',
        rebuild_paragraphs: isZh ? '整理段落' : 'Rebuild paragraphs',
        generate_note: isZh ? '生成笔记' : 'Generate note',
        save_artifacts: isZh ? '保存产物' : 'Save artifacts',
        export_lark: isZh ? '导出飞书' : 'Export to Feishu',
        regenerate_note: isZh ? '重生笔记' : 'Regenerate note',
    };
    return labels[id] || id || (isZh ? '处理步骤' : 'Processing step');
};

const statusTone = (status) => {
    if (status === 'failed') return 'border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-400/10 dark:text-red-200';
    if (status === 'pending') return 'border-[#dedada] bg-white text-[#85868c] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/50';
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-200';
};

const evidenceWeightText = (policy, lang) => {
    const transcriptWeight = policy?.transcript_content;
    const filenameWeight = policy?.filename;
    if (lang === 'zh') {
        if (transcriptWeight === 'primary') return '以转录正文为主，文件名只作弱信号。';
        if (transcriptWeight === 'pending') return '转录尚未完成，当前主要依赖来源、时长和文件名弱信号。';
        if (filenameWeight === 'weak') return '文件名只作弱信号。';
        return '依据来自当前任务包。';
    }
    if (transcriptWeight === 'primary') return 'Transcript content is primary; filename is only a weak signal.';
    if (transcriptWeight === 'pending') return 'Transcript is pending, so this uses source, duration, and weak filename signals.';
    if (filenameWeight === 'weak') return 'Filename is only a weak signal.';
    return 'Evidence comes from this task package.';
};

function buildJudgmentCards(packageData, lang) {
    const isZh = lang === 'zh';
    const plan = packageData?.processing_plan || {};
    const material = plan.material || {};
    const noteStrategy = plan.note_strategy || {};
    const transcript = packageData?.transcript || {};
    const note = packageData?.note || {};
    const source = packageData?.source || {};
    const stats = note.stats || {};
    const evidenceFallback = isZh ? '当前任务包没有记录更细的判断依据。' : 'This task package does not include more detailed evidence.';
    const evidenceText = compactList(material.evidence, evidenceFallback);
    const noteMode = noteStrategy.resolved_mode || note.resolved_mode || noteStrategy.selected_mode || note.requested_mode;
    const chunkCount = stats.chunk_count || noteStrategy.chunk_count;
    const evidenceCount = stats.evidence_count;
    const covered = stats.covered_important_evidence_count;
    const important = stats.important_evidence_count;
    const coverage = important ? `${covered || 0}/${important}` : null;
    const preview = String(transcript.preview || '').trim();

    const cards = [
        {
            key: 'material',
            icon: 'psychology',
            title: isZh ? '材料判断' : 'Material judgment',
            evidenceLabel: isZh ? '依据' : 'Evidence',
            impactLabel: isZh ? '对结果的影响' : 'Impact on result',
            conclusion: materialTypeLabel(material.type, lang),
            meta: isZh ? `置信度：${confidenceLabel(material.confidence, lang)}` : `Confidence: ${confidenceLabel(material.confidence, lang)}`,
            evidence: evidenceText,
            impact: material.type?.includes('lecture')
                ? (isZh ? '因此按讲座笔记处理，优先保留主题推进、论证和关键例子。' : 'Therefore it is treated as lecture notes, preserving topic flow, arguments, and examples.')
                : (isZh ? '因此按课程笔记处理，优先保留结构、知识点和复习线索。' : 'Therefore it is treated as course notes, preserving structure, concepts, and review cues.'),
        },
        {
            key: 'route',
            icon: 'cloud_done',
            title: isZh ? '转录路线' : 'Transcription route',
            evidenceLabel: isZh ? '依据' : 'Evidence',
            impactLabel: isZh ? '对结果的影响' : 'Impact on result',
            conclusion: routeLabel(plan, lang),
            meta: sourceTypeLabel(material.source_type || source.type, lang),
            evidence: [
                plan.execution?.transcription_tool ? `${isZh ? '工具' : 'Tool'}：${plan.execution.transcription_tool}` : '',
                source.duration_seconds || material.duration_seconds ? `${isZh ? '时长' : 'Duration'}：${formatDuration(source.duration_seconds || material.duration_seconds, lang)}` : '',
                languageLabel(transcript.source_language || transcript.detected_language || material.language, lang),
            ].filter(Boolean).join(' · ') || evidenceFallback,
            impact: plan.execution?.scope === 'cloud'
                ? (isZh ? '云端路线适合对准确率要求更高的材料，前端不暴露个人密钥。' : 'Cloud route fits accuracy-sensitive material; personal keys are not exposed in the UI.')
                : (isZh ? '本机路线适合私人材料、开发调试或云端不可用时兜底。' : 'Local route fits private material, development, or cloud fallback.'),
        },
        {
            key: 'note',
            icon: 'subject',
            title: isZh ? '笔记策略' : 'Note strategy',
            evidenceLabel: isZh ? '依据' : 'Evidence',
            impactLabel: isZh ? '对结果的影响' : 'Impact on result',
            conclusion: noteModeLabel(noteMode || 'auto', lang),
            meta: [
                chunkCount ? `${isZh ? '分块' : 'Chunks'}：${chunkCount}` : '',
                evidenceCount ? `${isZh ? '证据' : 'Evidence'}：${evidenceCount}` : '',
                coverage ? `${isZh ? '重点覆盖' : 'Coverage'}：${coverage}` : '',
            ].filter(Boolean).join(' · ') || (isZh ? '未记录生成统计' : 'No generation stats recorded'),
            evidence: noteStrategy.reason || note.diagnosis?.detail || (isZh ? '按转录长度、材料类型和当前模板选择笔记结构。' : 'Chosen from transcript length, material type, and active template.'),
            impact: noteMode === 'high_fidelity' || noteMode === 'chapter_coverage'
                ? (isZh ? '会牺牲一些速度，换取更完整的结构和重点覆盖。' : 'Trades speed for stronger structure and coverage.')
                : (isZh ? '处理速度更快，适合长度适中或结构清楚的材料。' : 'Faster processing for shorter or clearly structured material.'),
        },
        {
            key: 'review',
            icon: note.status === 'failed' ? 'error' : 'verified',
            title: isZh ? '复查点' : 'Review points',
            evidenceLabel: isZh ? '依据' : 'Evidence',
            impactLabel: isZh ? '下一步' : 'Next step',
            conclusion: noteStatusText(note, lang),
            meta: [
                transcript.raw_segment_count ? `${isZh ? '原文段' : 'Raw segments'}：${transcript.raw_segment_count}` : '',
                transcript.display_segment_count ? `${isZh ? '展示段' : 'Display segments'}：${transcript.display_segment_count}` : '',
                note.markdown_chars ? `${isZh ? '笔记字数' : 'Note chars'}：${Number(note.markdown_chars).toLocaleString()}` : '',
            ].filter(Boolean).join(' · ') || (isZh ? '没有记录复查统计' : 'No review stats recorded'),
            evidence: note.diagnosis?.detail || evidenceWeightText(material.evidence_policy, lang),
            impact: note.diagnosis?.next_action || (isZh ? '下一步在编辑器复查正文、下载字幕，必要时重生笔记。' : 'Next, review the note in Editor, download subtitles, or regenerate when needed.'),
        },
    ];

    if (preview) {
        cards.push({
            key: 'preview',
            icon: 'closed_caption',
            title: isZh ? '转录信号' : 'Transcript signal',
            evidenceLabel: isZh ? '依据' : 'Evidence',
            impactLabel: isZh ? '对判断的影响' : 'Impact on judgment',
            conclusion: isZh ? '正文已可用于判断' : 'Transcript is available for judgment',
            meta: languageLabel(transcript.source_language || transcript.detected_language || material.language, lang),
            evidence: preview.length > 180 ? `${preview.slice(0, 180)}...` : preview,
            impact: evidenceWeightText(material.evidence_policy, lang),
        });
    }

    return cards;
}

function buildExecutionSteps(packageData, lang) {
    const traceSteps = Array.isArray(packageData?.tool_trace?.steps) ? packageData.tool_trace.steps : [];
    if (traceSteps.length) {
        return traceSteps.map((step) => ({
            id: step.id || step.label,
            title: stageLabel(step, lang),
            status: step.status || 'done',
            detail: step.error_reason || step.reason || step.tool || null,
            duration: step.duration_seconds,
        }));
    }
    const planSteps = Array.isArray(packageData?.processing_plan?.steps) ? packageData.processing_plan.steps : [];
    return planSteps.map((step) => ({
        id: step.id || step.label,
        title: step.label || step.id,
        status: 'done',
        detail: step.reason || step.tool || null,
        duration: null,
    }));
}

const JudgmentCard = ({card}) => (
    <article className="min-w-0 rounded-[18px] border border-[#dedada] bg-white p-4 dark:border-white/[0.10] dark:bg-white/[0.055]">
        <div className="flex items-start gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-[13px] bg-[#f0f0f0] text-[#111111] dark:bg-white/[0.10] dark:text-white">
                <SvgIcon name={card.icon} className="text-[18px]"/>
            </div>
            <div className="min-w-0 flex-1">
                <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">{card.title}</p>
                <h2 className="mt-1 truncate font-headline text-[18px] font-extrabold leading-tight text-[#111111] dark:text-white" title={card.conclusion}>
                    {card.conclusion}
                </h2>
                {card.meta && <p className="mt-1 text-[12px] font-bold text-[#676970] dark:text-white/55">{card.meta}</p>}
            </div>
        </div>
        <div className="mt-4 space-y-3 text-[13px] leading-5">
            <div>
                <p className="mb-1 text-[11px] font-extrabold text-[#85868c] dark:text-white/40">{card.evidenceLabel}</p>
                <p className="text-[#2f3035] dark:text-white/78">{card.evidence}</p>
            </div>
            <div>
                <p className="mb-1 text-[11px] font-extrabold text-[#85868c] dark:text-white/40">{card.impactLabel}</p>
                <p className="text-[#2f3035] dark:text-white/78">{card.impact}</p>
            </div>
        </div>
    </article>
);

const AgentTrace = () => {
    const {taskId} = useParams();
    const navigate = useNavigate();
    const {lang} = useI18n();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [packageData, setPackageData] = useState(null);
    const isZh = lang === 'zh';

    useEffect(() => {
        let stale = false;
        const load = async () => {
            setLoading(true);
            setError(null);
            try {
                const r = await apiFetch(`${API_BASE}/agent/v1/tasks/${encodeURIComponent(taskId)}/package`);
                const data = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
                if (!stale) setPackageData(data);
            } catch (err) {
                if (!stale) setError(err.message || String(err));
            } finally {
                if (!stale) setLoading(false);
            }
        };
        load();
        return () => { stale = true; };
    }, [taskId]);

    const title = packageData?.title || taskId;
    const judgmentCards = useMemo(() => buildJudgmentCards(packageData, lang), [packageData, lang]);
    const executionSteps = useMemo(() => buildExecutionSteps(packageData, lang), [packageData, lang]);
    const plan = packageData?.processing_plan || {};
    const note = packageData?.note || {};
    const riskNotes = Array.isArray(plan.risk_notes) ? plan.risk_notes.filter(Boolean) : [];

    if (loading) {
        return (
            <main className="flex min-h-dvh flex-1 items-center justify-center bg-[#f8f7fb] p-8 dark:bg-[#101010]">
                <div className="flex items-center gap-2.5 text-sm font-semibold text-on-surface-variant">
                    <SvgIcon name="sync" className="animate-spin text-base"/>
                    {isZh ? '加载任务解释...' : 'Loading task explanation...'}
                </div>
            </main>
        );
    }

    if (error) {
        return (
            <main className="flex min-h-dvh flex-1 flex-col items-center justify-center gap-4 bg-[#f8f7fb] p-8 dark:bg-[#101010]">
                <div className="rounded-[16px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">{error}</div>
                <button type="button" onClick={() => navigate('/tasks')} className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-4 text-sm font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]">
                    {isZh ? '返回任务列表' : 'Back to Tasks'}
                </button>
            </main>
        );
    }

    return (
        <main className="min-h-dvh flex-1 overflow-y-auto bg-[#f8f7fb] px-6 py-5 text-[#111111] hide-scrollbar dark:bg-[#101010] dark:text-white/[0.92] lg:px-10">
            <div className="mx-auto max-w-7xl space-y-5">
                <header className="flex flex-col gap-3 border-b border-[#dedada] pb-4 dark:border-white/[0.10] lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <Link to="/tasks" className="text-[13px] font-bold text-[#676970] transition hover:text-[#111111] dark:text-white/55 dark:hover:text-white">
                                {isZh ? '后台任务' : 'Tasks'}
                            </Link>
                            <span className="text-[#a2a3a8] dark:text-white/35">/</span>
                            <h1 className="font-headline text-[22px] font-extrabold leading-tight text-[#111111] dark:text-white">
                                {isZh ? '素材处理解释' : 'Material explanation'}
                            </h1>
                            <span className="rounded-full border border-[#dedada] bg-white px-2.5 py-1 text-[11px] font-extrabold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                {isZh ? '证据摘要' : 'Evidence summary'}
                            </span>
                        </div>
                        <p className="mt-1 max-w-[72ch] truncate text-[13px] leading-5 text-[#676970] dark:text-white/60" title={title}>
                            {title}
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2 lg:justify-end">
                        <Link to="/editor" className="inline-flex h-9 items-center gap-2 rounded-[12px] bg-[#111111] px-4 text-[13px] font-extrabold text-white transition hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
                            <SvgIcon name="open_in_new" className="text-base"/>
                            {isZh ? '查看笔记' : 'View note'}
                        </Link>
                        <Link to="/tasks" className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-4 text-[13px] font-extrabold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]">
                            <SvgIcon name="monitoring" className="text-base"/>
                            {isZh ? '任务记录' : 'Task record'}
                        </Link>
                    </div>
                </header>

                <section className="rounded-[20px] border border-[#dedada] bg-white p-4 dark:border-white/[0.10] dark:bg-white/[0.055]">
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.34fr)] lg:items-center">
                        <div className="min-w-0">
                            <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">
                                {isZh ? '本页展示什么' : 'What this page shows'}
                            </p>
                            <h2 className="mt-1 font-headline text-[20px] font-extrabold text-[#111111] dark:text-white">
                                {isZh ? '这条素材为什么被这样处理' : 'Why this material was processed this way'}
                            </h2>
                            <p className="mt-2 max-w-[78ch] text-[13px] leading-5 text-[#676970] dark:text-white/60">
                                {isZh
                                    ? '这里把处理解释整理成可复查的判断结论、依据和影响。通用执行步骤放在下方，作为处理记录。'
                                    : 'This turns the processing explanation into reviewable conclusions, evidence, and impact. Generic steps stay below as execution record.'}
                            </p>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[12px]">
                            <div className="rounded-[14px] border border-[#dedada] bg-[#fbfbfb] p-3 dark:border-white/[0.10] dark:bg-white/[0.04]">
                                <p className="font-bold text-[#85868c] dark:text-white/45">{isZh ? '计划阶段' : 'Plan stage'}</p>
                                <p className="mt-1 truncate font-extrabold text-[#111111] dark:text-white">{plan.planning_stage || '-'}</p>
                            </div>
                            <div className="rounded-[14px] border border-[#dedada] bg-[#fbfbfb] p-3 dark:border-white/[0.10] dark:bg-white/[0.04]">
                                <p className="font-bold text-[#85868c] dark:text-white/45">{isZh ? '笔记状态' : 'Note status'}</p>
                                <p className="mt-1 truncate font-extrabold text-[#111111] dark:text-white">{noteStatusText(note, lang)}</p>
                            </div>
                        </div>
                    </div>
                </section>

                <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1.36fr)_minmax(320px,0.64fr)]">
                    <section className="min-w-0 space-y-4">
                        <div className="flex items-end justify-between gap-3">
                            <div>
                                <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">{isZh ? '判断结论' : 'Judgments'}</p>
                                <h2 className="font-headline text-[18px] font-extrabold text-[#111111] dark:text-white">
                                    {isZh ? '针对当前素材的分析' : 'Analysis for this material'}
                                </h2>
                            </div>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                            {judgmentCards.map((card) => <JudgmentCard key={card.key} card={card}/>)}
                        </div>
                    </section>

                    <aside className="space-y-5 xl:border-l xl:border-[#dedada] xl:pl-5 xl:dark:border-white/[0.10]">
                        <section>
                            <div className="mb-3">
                                <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">{isZh ? '执行记录' : 'Execution record'}</p>
                                <h2 className="font-headline text-[18px] font-extrabold text-[#111111] dark:text-white">
                                    {isZh ? '真实经过的步骤' : 'Steps actually recorded'}
                                </h2>
                            </div>
                            <div className="space-y-2">
                                {executionSteps.map((step, index) => (
                                    <div key={`${step.id}-${index}`} className="rounded-[14px] border border-[#dedada] bg-white p-3 dark:border-white/[0.10] dark:bg-white/[0.055]">
                                        <div className="flex items-center justify-between gap-3">
                                            <p className="min-w-0 truncate text-[13px] font-extrabold text-[#111111] dark:text-white" title={step.title}>{step.title}</p>
                                            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-extrabold ${statusTone(step.status)}`}>
                                                {step.status === 'failed' ? (isZh ? '失败' : 'Failed') : step.status === 'pending' ? (isZh ? '等待' : 'Pending') : (isZh ? '完成' : 'Done')}
                                            </span>
                                        </div>
                                        {(step.detail || step.duration != null) && (
                                            <p className="mt-1 text-[12px] leading-5 text-[#676970] dark:text-white/58">
                                                {[step.detail, step.duration != null ? `${Math.round(step.duration)}s` : ''].filter(Boolean).join(' · ')}
                                            </p>
                                        )}
                                    </div>
                                ))}
                                {!executionSteps.length && (
                                    <p className="rounded-[14px] border border-[#dedada] bg-white p-3 text-[13px] font-semibold text-[#676970] dark:border-white/[0.10] dark:bg-white/[0.055] dark:text-white/58">
                                        {isZh ? '当前任务包没有记录执行步骤。' : 'This task package has no execution steps recorded.'}
                                    </p>
                                )}
                            </div>
                        </section>

                        <section className="border-t border-[#dedada] pt-5 dark:border-white/[0.10]">
                            <div className="mb-3">
                                <p className="text-[12px] font-extrabold text-[#85868c] dark:text-white/45">{isZh ? '限制和下一步' : 'Limits and next step'}</p>
                                <h2 className="font-headline text-[18px] font-extrabold text-[#111111] dark:text-white">
                                    {note.diagnosis?.title || (isZh ? '复查结果' : 'Review result')}
                                </h2>
                            </div>
                            <div className="space-y-2 text-[13px] leading-5 text-[#676970] dark:text-white/60">
                                {riskNotes.length > 0 ? riskNotes.map((item) => (
                                    <p key={item} className="rounded-[14px] border border-orange-300/40 bg-orange-50 p-3 font-semibold text-orange-900 dark:border-orange-300/20 dark:bg-orange-300/10 dark:text-orange-100">
                                        {item}
                                    </p>
                                )) : (
                                    <p className="rounded-[14px] border border-[#dedada] bg-white p-3 font-semibold dark:border-white/[0.10] dark:bg-white/[0.055]">
                                        {note.diagnosis?.next_action || (isZh ? '打开编辑器复查正文，必要时重生笔记。' : 'Open the editor to review the note, and regenerate if needed.')}
                                    </p>
                                )}
                                {riskNotes.length > 0 && note.diagnosis?.next_action && (
                                    <p className="rounded-[14px] border border-[#dedada] bg-white p-3 font-semibold dark:border-white/[0.10] dark:bg-white/[0.055]">
                                        {note.diagnosis.next_action}
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
