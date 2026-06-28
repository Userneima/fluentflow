import {useEffect, useMemo, useState} from 'react';
import {Link, useParams, useNavigate} from 'react-router-dom';
import {useApi, useI18n, useAuth} from '../app/shared.jsx';
import SvgIcon from '../components/SvgIcon.jsx';

const THOUGHT_GENERATORS = {

    resolve_link(result, job) {
        const source = result?.source || job?.source_type || '';
        if (source === 'douyin') return '这是一个抖音分享链接，我先解析出里面的视频地址再下载。';
        return '这是一个分享链接，我先解析出真实视频地址再下载。';
    },

    download_video(result, job) {
        const dur = result?.audio_duration_seconds || job?.source_duration_seconds;
        if (dur && dur >= 1800) return `视频下载完毕，长度 ${Math.round(dur / 60)} 分钟。这是个长内容，后续笔记需要分段处理才能不丢重点。`;
        if (dur) return `视频下载完毕，长度 ${Math.round(dur / 60)} 分钟。`;
        return '视频下载完毕。';
    },

    save_source(result, job) {
        const name = result?.display_title || result?.filename || job?.source_filename || '';
        const dur = result?.audio_duration_seconds || job?.source_duration_seconds;
        if (name && dur && dur >= 1800) return `收到「${name}」，约 ${Math.round(dur / 60)} 分钟。内容不短，我得选一个靠谱的转录方案。`;
        if (name) return `收到「${name}」。`;
        return '文件已收到，开始处理。';
    },

    parse_subtitles(result, job) {
        const name = result?.display_title || result?.filename || job?.source_filename || '';
        if (name) return `收到「${name}」，这是一个字幕文件，不需要转写，我直接整理后生成笔记。`;
        return '这是一个字幕文件，跳过转写，我直接整理格式后生成笔记。';
    },

    extract_audio(result, job) {
        return '从视频里提取音频，准备送去转写。';
    },

    local_stt(result, job) {
        const model = result?.stt_model || '';
        const lang = result?.detected_language || result?.source_language || '';
        const rf = result?.stt_realtime_factor;
        if (model && rf != null) {
            return `用 faster-whisper ${model} 在本地跑完转写了，速度是你设备上的实际表现。${lang ? `检测到语言是 ${String(lang).toLowerCase().startsWith('en') ? '英文' : lang.startsWith('zh') ? '中文' : lang}。` : ''}`;
        }
        return '本地转录完成。';
    },

    cloud_stt(result, job) {
        const provider = result?.stt_provider || '';
        const lang = result?.source_language || result?.detected_language || '';
        const parts = [];
        if (provider === 'elevenlabs_scribe') {
            parts.push('这次走 ElevenLabs 云端转写——准确率比本地高不少，适合需要认真对待的长内容。');
        } else if (provider === 'azure_batch') {
            parts.push('这次走 Azure 云端转写。');
        } else {
            parts.push('云端转写完成。');
        }
        if (lang) {
            parts.push(`识别到 ${String(lang).toLowerCase().startsWith('en') ? '英文' : lang.startsWith('zh') ? '中文' : lang}。`);
        }
        return parts.join(' ');
    },

    diarize_speakers(result, job) {
        const count = result?.speaker_diarization?.speaker_count;
        if (count) return `检测到 ${count} 位说话人，已经做了区分——转录里能看到谁说了什么。`;
        return '已尝试区分说话人。';
    },

    cleanup_transcript(result, job) {
        const info = result?.transcript_cleanup || {};
        const removed = info.removed_segment_count;
        const issues = info.issues;
        const parts = [];
        if (removed) {
            parts.push(`转录里发现了 ${removed} 段重复内容，已经清洗掉——避免这些重复文字干扰笔记生成。`);
        } else if (issues) {
            parts.push('转录里有一些重复痕迹，已经洗掉了。');
        }
        if (!parts.length) parts.push('转录整理完成。');
        return parts.join(' ');
    },

    rebuild_paragraphs(result, job) {
        return '转录是带时间码的碎片句，不适合直接喂给模型。我把碎片按段落重组成正文，模型才能按逻辑而不是按时间戳理解内容。';
    },

    generate_note(result, job) {
        const mode = result?.resolved_note_mode || result?.note_mode_plan_selected_mode || result?.requested_note_mode || 'auto';
        const chunkCount = result?.note_mode_chunk_count;
        const provider = result?.ai_provider || '';
        const length = (result?.transcript_text || '').length;
        const parts = [];
        if (mode === 'high_fidelity') {
            if (chunkCount) parts.push(`转录有 ${length.toLocaleString()} 字，直接丢给模型会被选择性概括——我把内容拆成 ${chunkCount} 段，每段先提取论点和证据，再合成完整笔记。`);
            else parts.push(`转录有 ${length.toLocaleString()} 字，密度比较高，我决定走分段提取再合成的路线——宁愿慢一点，不丢重点。`);
        } else if (mode === 'direct') {
            parts.push(`转录 ${length.toLocaleString()} 字，内容长度适中，直接生成笔记不会漏。`);
        } else {
            parts.push('根据转录长度和内容结构选择笔记策略，生成笔记。');
        }
        if (provider) parts.push(`笔记由 ${provider} 生成。`);
        return parts.join(' ');
    },

    save_artifacts(result, job) {
        return '笔记和产出物已经保存，你可以随时下载或导出。';
    },

    export_lark(result, job) {
        const docUrl = result?.lark_response?.url || '';
        if (docUrl) return `笔记已自动导出到飞书文档，可以在飞书里继续编辑和复习。`;
        return '已尝试导出飞书。';
    },

    regenerate_note(result, job) {
        return '你让我重新生成笔记，我重新评估了材料特征，再生成一次。';
    },
};


function buildThoughts(toolTrace, result, jobMetadata) {
    if (!toolTrace?.steps) return [];
    const resultObj = result || {};
    const jobObj = jobMetadata || {};
    return toolTrace.steps.map((step) => {
        const generator = THOUGHT_GENERATORS[step.id];
        const thought = generator ? generator(resultObj, jobObj) : `${step.label}完成。`;
        return {
            id: step.id,
            stage: step.id,
            thought,
            status: step.status,
            error: step.error_reason || null,
            duration_seconds: step.duration_seconds || null,
            metadata: step.metadata || null,
        };
    });
}

const STAGE_ICONS = {
    resolve_link: 'douyin',
    download_video: 'video',
    save_source: 'local-file',
    parse_subtitles: 'subtitles',
    extract_audio: 'wave',
    local_stt: 'wave',
    cloud_stt: 'sync',
    diarize_speakers: 'queue',
    cleanup_transcript: 'tune',
    rebuild_paragraphs: 'subject',
    generate_note: 'grid',
    save_artifacts: 'upload-file',
    export_lark: 'arrow-right',
    regenerate_note: 'sync',
};

const STAGE_COLORS = {
    resolve_link: '#6366f1',
    download_video: '#6366f1',
    save_source: '#6366f1',
    parse_subtitles: '#6366f1',
    extract_audio: '#8b5cf6',
    local_stt: '#8b5cf6',
    cloud_stt: '#8b5cf6',
    diarize_speakers: '#8b5cf6',
    cleanup_transcript: '#f59e0b',
    rebuild_paragraphs: '#f59e0b',
    generate_note: '#10b981',
    save_artifacts: '#6b7280',
    export_lark: '#3b82f6',
    regenerate_note: '#10b981',
};

const AgentTrace = () => {
    const {taskId} = useParams();
    const navigate = useNavigate();
    const {t, lang} = useI18n();
    const {guestMode} = useAuth();
    const {request: apiRequest} = useApi();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [packageData, setPackageData] = useState(null);

    useEffect(() => {
        let stale = false;
        const load = async () => {
            setLoading(true);
            setError(null);
            try {
                const r = await apiRequest(`/agent/v1/tasks/${encodeURIComponent(taskId)}/package`);
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

    const thoughts = useMemo(() => {
        const result = packageData?.transcript ? {
            transcript_text: packageData.transcript.text,
            transcript_text_preview: packageData.transcript.preview,
            source_language: packageData.transcript.source_language,
            detected_language: packageData.transcript.detected_language,
            stt_provider: (packageData.processing_plan?.execution?.scope === 'cloud' ? 'elevenlabs_scribe' : 'local'),
            ...packageData.processing_plan?.material,
            ...packageData.note,
        } : {};
        return buildThoughts(packageData?.tool_trace, result, {});
    }, [packageData]);

    const isZh = lang === 'zh';
    const title = packageData?.title || taskId;

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-2.5 text-sm text-on-surface-variant">
                    <span className="material-symbols-outlined animate-spin text-base">sync</span>
                    {isZh ? '加载中...' : 'Loading...'}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
                <div className="text-sm text-red-500">{error}</div>
                <button type="button" onClick={() => navigate('/tasks')} className="inline-flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] bg-[#f4f3f3] px-4 text-sm font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]">
                    {isZh ? '返回任务列表' : 'Back to Tasks'}
                </button>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#dedada] dark:border-white/[0.08]">
                <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <Link to="/tasks" className="text-sm text-on-surface-variant hover:text-on-surface transition-colors">
                            {isZh ? '任务' : 'Tasks'}
                        </Link>
                        <span className="text-sm text-on-surface-variant">/</span>
                        <Link to="/editor" className="text-sm text-on-surface-variant hover:text-on-surface transition-colors">
                            {isZh ? '编辑器' : 'Editor'}
                        </Link>
                        <span className="text-sm text-on-surface-variant">/</span>
                        <h1 className="text-sm font-bold text-on-surface truncate max-w-[300px]" title={title}>
                            {isZh ? '处理过程' : 'Processing'}
                        </h1>
                    </div>
                    <p className="text-xs text-on-surface-variant truncate max-w-[400px]">{title}</p>
                </div>
                <Link
                    to="/editor"
                    className="inline-flex h-9 items-center gap-2 rounded-[12px] bg-[#111111] px-4 text-xs font-bold text-white transition-colors hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]"
                >
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                    {isZh ? '查看笔记' : 'View Note'}
                </Link>
            </div>

            {/* Timeline */}
            <div className="flex-1 overflow-auto px-6 py-6">
                <div className="max-w-[640px] mx-auto">
                    <div className="relative ml-4">
                        {/* vertical line */}
                        <div className="absolute left-0 top-0 bottom-0 w-px bg-[#dedada] dark:bg-white/[0.08]" style={{transform: 'translateX(7px)'}} />

                        <div className="flex flex-col gap-5">
                            {thoughts.map((item, index) => {
                                const icon = STAGE_ICONS[item.stage] || 'check-circle';
                                const color = STAGE_COLORS[item.stage] || '#6b7280';
                                const isError = item.status === 'failed';
                                const isPending = item.status === 'pending';

                                return (
                                    <div key={`${item.id}-${index}`} className="relative pl-8">
                                        {/* dot */}
                                        <div
                                            className={`absolute left-0 top-1 flex items-center justify-center w-[15px] h-[15px] rounded-full border-2 transition-colors ${isError ? 'bg-red-50 border-red-300 dark:bg-red-500/10 dark:border-red-500/30' : isPending ? 'bg-surface border-[#dedada] dark:bg-[#1a1a1a] dark:border-white/[0.12]' : 'bg-white border-[#aaa] dark:bg-[#1a1a1a] dark:border-white/[0.25]'}`}
                                            style={{transform: 'translateX(-3px)', borderColor: !isError && !isPending ? color : undefined}}
                                        >
                                            {isError ? (
                                                <span className="material-symbols-outlined text-[10px] text-red-500">close</span>
                                            ) : isPending ? (
                                                <span className="material-symbols-outlined text-[10px] text-on-surface-variant">schedule</span>
                                            ) : (
                                                <div className="w-[7px] h-[7px] rounded-full" style={{backgroundColor: color}} />
                                            )}
                                        </div>

                                        {/* thought text */}
                                        <p className={`text-sm leading-relaxed ${isError ? 'text-red-600 dark:text-red-400' : isPending ? 'text-on-surface-variant opacity-60' : 'text-on-surface'}`}>
                                            {item.thought}
                                        </p>

                                        {/* error detail */}
                                        {item.error && (
                                            <p className="mt-1 text-xs text-red-500">{item.error}</p>
                                        )}

                                        {/* duration badge */}
                                        {item.duration_seconds != null && !isPending && (
                                            <span className="inline-block mt-1.5 text-xs text-on-surface-variant opacity-60">
                                                {item.duration_seconds < 60
                                                    ? `${Math.round(item.duration_seconds)}s`
                                                    : `${Math.round(item.duration_seconds / 60)}min ${Math.round(item.duration_seconds % 60)}s`}
                                            </span>
                                        )}
                                    </div>
                                );
                            })}

                            {/* final status */}
                            {thoughts.length > 0 && packageData?.tool_trace?.status === 'completed' && (
                                <div className="relative pl-8">
                                    <div className="absolute left-0 top-1 flex items-center justify-center w-[15px] h-[15px]" style={{transform: 'translateX(-3px)', color: '#10b981'}}>
                                        <span className="material-symbols-outlined text-[15px]">check_circle</span>
                                    </div>
                                    <p className="text-sm text-on-surface-variant">
                                        {isZh ? '处理完成，所有步骤都已执行。' : 'Processing complete. All steps finished.'}
                                    </p>
                                </div>
                            )}

                            {thoughts.length > 0 && packageData?.tool_trace?.status === 'partial' && (
                                <div className="relative pl-8">
                                    <div className="absolute left-0 top-1 flex items-center justify-center w-[15px] h-[15px]" style={{transform: 'translateX(-3px)', color: '#f59e0b'}}>
                                        <span className="material-symbols-outlined text-[15px]">warning</span>
                                    </div>
                                    <p className="text-sm text-on-surface-variant">
                                        {isZh ? '处理部分完成，有些步骤失败了。' : 'Partial completion — some steps failed.'}
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* back link */}
                    <div className="mt-6 pt-4 border-t border-[#dedada] dark:border-white/[0.08] text-center">
                        <Link to="/editor" className="text-xs text-on-surface-variant hover:text-on-surface transition-colors">
                            {isZh ? '→ 打开编辑器查看笔记和转录' : '→ Open editor to view note and transcript'}
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AgentTrace;
