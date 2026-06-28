import {useState,useEffect,useRef,useCallback,useMemo} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {
    BUILTIN_EXTRA_PROMPT_KEYS,
    DEFAULT_PROMPT_PRESET,
    allPresetSelectKeys,
    getBuiltinExtraPromptBody,
    getDefaultPromptBody,
    isBuiltinPromptPresetHidden,
    normalizeUserPresets,
    presetDisplayLabel,
    resolveSystemPromptFromSettings,
} from '../lib/promptPresets.js';
import SvgIcon from '../components/SvgIcon.jsx';
import {
    API_BASE,
    azureSpeechMissingMessage,
    compactDisplayFilename,
    createTaskId,
    effectiveSttProvider,
    autoSizeTextarea,
    buildTranscriptEditRecords,
    composeTranscriptText,
    dlSummaryMd,
    dlSummaryPdf,
    dlSummaryTxt,
    dlSummaryWord,
    dlBilingualTranscriptSrt,
    dlBilingualTranscriptVtt,
    dlTranscriptSrt,
    dlTranscriptTxt,
    dlTranscriptVtt,
    fmtElapsed,
    fmtFileSize,
    fmtSttRelative,
    fmtTime,
    friendlyTaskError,
    apiFetch,
    DropdownMenu,
    fileNameStem,
    getGuestTrialTaskId,
    getGuestTrialToken,
    historyEntryToResult,
    isAzureBatchConfigured,
    isAzureCloudProvider,
    isAzureSpeechConfigured,
    isLocalHistoryResult,
    isLocalLarkExportRoute,
    isSttProgressUnmeasured,
    jobToCurrentJob,
    jobToHistoryEntry,
    larkExportRouteFromSettings,
    localExecutionHeaders,
    noteModeLabel,
    pickDisplayTranscriptSegments,
    normalizeSttModel,
    normalizeSttProvider,
    pickTranscriptBaselineSegments,
    pickTranscriptSegments,
    resultToHistoryEntry,
    resultDisplayTitle,
    shouldUseLocalSingleUserClientId,
    simpleMd,
    timeAgo,
    useApi,
    useApp,
    useAuth,
    useI18n,
    useSettings,
} from '../app/shared.jsx';
import PromptTemplateDialog from '../components/PromptTemplateDialog.jsx';

const jobOptionsForResult = (result) => (
    normalizeSttProvider(result?.stt_provider) === 'local'
    || result?.playback_audio_storage === 'local'
    || result?.source_file_storage === 'local'
        ? {sttProvider: 'local'}
        : {}
);

const noteModeReasonText = (result, lang) => {
    const plannedReason = String(result?.note_mode_plan_reason || '').trim();
    if (plannedReason) {
        return plannedReason;
    }
    const requested = String(result?.requested_note_mode || '').trim();
    const resolved = String(result?.resolved_note_mode || requested || '').trim();
    if (!resolved) return '';
    const wasAuto = !requested || requested === 'auto';
    if (resolved === 'chapter_coverage') {
        return wasAuto
            ? (lang === 'zh' ? '材料较长或信息密度高，系统改用章节覆盖流程，先抽证据再按章节生成。' : 'The material is long or dense, so FluentFlow used chapter coverage: evidence first, then chapter writing.')
            : (lang === 'zh' ? '来自本次处理设置：先抽取证据、规划章节，再检查重要遗漏。' : 'Chosen in this run: extract evidence, plan chapters, then check important omissions.');
    }
    if (resolved === 'high_fidelity') {
        return wasAuto
            ? (lang === 'zh' ? '材料偏长，系统改用分块整理，重点是减少遗漏。' : 'The material is long, so the system used chunked coverage to reduce omissions.')
            : (lang === 'zh' ? '来自本次处理设置，优先完整覆盖，速度会慢一些。' : 'Chosen in this run. It prioritizes coverage and may take longer.');
    }
    if (resolved === 'direct') {
        return wasAuto
            ? (lang === 'zh' ? '材料长度适中，系统直接生成，速度更快。' : 'The material is short enough for direct generation, which is faster.')
            : (lang === 'zh' ? '来自本次处理设置，适合较短或结构清楚的材料。' : 'Chosen in this run. It fits shorter or clearly structured material.');
    }
    return lang === 'zh' ? '按本次处理设置生成。' : 'Generated from this run’s settings.';
};

const promptPresetReasonText = (result, lang) => {
    const preset = String(result?.prompt_preset || '').trim();
    const label = String(result?.prompt_preset_label || '').trim();
    if (!preset && !label) return '';
    if (preset === 'default') {
        return lang === 'zh' ? '使用默认课程笔记结构，保证输出格式稳定。' : 'Uses the default course-note structure for stable output.';
    }
    return lang === 'zh'
        ? '来自处理设置，用来决定笔记结构、重点和限制。'
        : 'Comes from Processing settings and controls note structure, focus, and constraints.';
};

const subtitleReasonText = (result, hasBilingualTranscript, lang) => {
    const sourceLanguage = String(result?.source_language || result?.detected_language || '').toLowerCase();
    if (hasBilingualTranscript || result?.subtitle_mode === 'bilingual_zh') {
        return lang === 'zh'
            ? '英文原文已保留，并附加中文对照，方便校对和做笔记。'
            : 'The English source is preserved with Chinese alongside it for review and note-taking.';
    }
    if (sourceLanguage.startsWith('en')) {
        return lang === 'zh'
            ? '当前只有英文原文字幕，需要中文时可生成中英对照。'
            : 'Only the English source subtitles are present. Add bilingual subtitles when Chinese is needed.';
    }
    return '';
};

const summaryFailureNextStep = (result, lang) => {
    if (!(result?.summary_status === 'failed' || result?.summary_error)) return '';
    const error = friendlyTaskError(result?.summary_error, lang);
    return lang === 'zh'
        ? `原因：${error} 下一步：点击“重新生成”；如果还失败，先更换提示词或缩短材料。`
        : `Reason: ${error} Next: click Regenerate; if it still fails, change the prompt or shorten the material.`;
};

const Editor = () => {
    const {t, lang} = useI18n();
    const {guestMode} = useAuth();
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
    const {processVideoSSE, fetchJobSourceFile, fetchJobArtifactFile, fetchGuestTrialArtifactFile, uploadJobPlaybackAudio, recordEvent, getJob, getGuestTrialJob, saveTranscriptEdit, translateJobSegments, getCredentialsStatus} = useApi();
    const {loadSettings, saveSettings} = useSettings();
    const [exporting, setExporting] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const [translatingTranscript, setTranslatingTranscript] = useState(false);
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
    let initPk = initSettings.promptPreset || DEFAULT_PROMPT_PRESET;
    if (isBuiltinPromptPresetHidden(initPk, initSettings)) initPk = 'default';
    const [promptKey, setPromptKey] = useState(initPk);
    const [customText, setCustomText] = useState(initSettings.customPromptText || '');
    const [defaultPromptEdit, setDefaultPromptEdit] = useState(() => getDefaultPromptBody(initSettings));
    const [autoTranscriptNotesEdit, setAutoTranscriptNotesEdit] = useState(() => getBuiltinExtraPromptBody('autoTranscriptNotes', initSettings));
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
        const pkRaw = s.promptPreset || DEFAULT_PROMPT_PRESET;
        const pk = isBuiltinPromptPresetHidden(pkRaw, s) ? 'default' : pkRaw;
        setPromptKey(pk);
        setDefaultPromptEdit(getDefaultPromptBody(s));
        setAutoTranscriptNotesEdit(getBuiltinExtraPromptBody('autoTranscriptNotes', s));
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
    const isGuestResult = !!(guestMode && result?.task_id && result.task_id === getGuestTrialTaskId());
    const resultSegmentCount = pickTranscriptSegments(result).length;
    const resultTextLength = (result?.transcript_text || '').length;
    const resultKey = result
        ? `${result.task_id || result.filename || 'current_result'}:${result.transcript_edited ? 'edited' : `${resultSegmentCount}:${resultTextLength}`}`
        : 'empty_result';
    const mediaSourceKey = result
        ? [
            result.task_id || result.filename || 'current_result',
            result.artifacts?.playback_audio?.filename || (result.playback_audio_available ? 'playback-audio' : 'no-playback-audio'),
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
    const [transcriptView, setTranscriptView] = useState('bilingual');
    const [editRecordsOpen, setEditRecordsOpen] = useState(false);
    const mediaRef = useRef(null);
    const mediaInputRef = useRef(null);
    const transcriptScrollRef = useRef(null);
    const segmentRefs = useRef({});
    const resultJobOptions = useMemo(() => jobOptionsForResult(result), [
        result?.stt_provider,
        result?.playback_audio_storage,
        result?.source_file_storage,
    ]);

    useEffect(() => {
        if (!result?.task_id || transcriptUnsaved) return;
        if (isLocalHistoryResult(result)) return;
        const currentSegments = pickTranscriptSegments(result);
        const currentText = result.transcript_text || '';
        const needsHydration = currentSegments.length === 0 || currentText.length <= 260;
        if (!needsHydration || hydratedTaskIdsRef.current.has(result.task_id)) return;
        hydratedTaskIdsRef.current.add(result.task_id);
        let cancelled = false;
        const jobRequest = isGuestResult
            ? getGuestTrialJob(result.task_id, getGuestTrialToken())
            : getJob(result.task_id, resultJobOptions);
        jobRequest
            .then((job) => {
                const full = job?.result;
                if (cancelled || !full) return;
                const fullSegments = pickTranscriptSegments(full);
                const fullText = full.transcript_text || '';
                const currentDisplayCount = pickDisplayTranscriptSegments(result, currentSegments).length;
                const fullDisplayCount = pickDisplayTranscriptSegments(full, fullSegments).length;
                if (fullSegments.length > currentSegments.length || fullText.length > currentText.length || fullDisplayCount > currentDisplayCount) {
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
    }, [resultKey, transcriptUnsaved, isGuestResult, resultJobOptions]);

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
        const playbackArtifact = result.artifacts?.playback_audio;
        if (result.task_id && playbackArtifact) {
            setMediaLoading(true);
            const fetchArtifact = isGuestResult ? fetchGuestTrialArtifactFile : fetchJobArtifactFile;
            const artifactOptions = resultJobOptions;
            fetchArtifact(result.task_id, 'playback_audio', playbackArtifact.filename || `${result.filename || 'source'}_audio.mp3`, artifactOptions)
                .then((file) => { if (!cancelled) loadMediaFile(file); })
                .catch((err) => {
                    if (!cancelled && result.source_file_available && !isGuestResult) {
                        fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)
                            .then((file) => { if (!cancelled) loadMediaFile(file); })
                            .catch((sourceErr) => {
                                if (!cancelled) {
                                    setMediaError(sourceErr.message || err.message || 'Audio file unavailable');
                                    setMediaLoading(false);
                                }
                            });
                        return;
                    }
                    if (!cancelled) {
                        setMediaError(err.message || 'Audio file unavailable');
                        setMediaLoading(false);
                    }
                });
            return () => { cancelled = true; };
        }
        if (result.task_id && result.source_file_available && !isGuestResult) {
            setMediaLoading(true);
            fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions)
                .then((file) => { if (!cancelled) loadMediaFile(file); })
                .catch((err) => {
                    if (!cancelled) {
                        setMediaError(err.message || 'Source file unavailable');
                        setMediaLoading(false);
                    }
                });
        }
        return () => { cancelled = true; };
    }, [mediaSourceKey, isGuestResult, resultJobOptions]);

    const segments = editedSegments;
    const transcript = editedTranscript || result?.transcript_text || '';
    const editRecords = useMemo(
        () => buildTranscriptEditRecords(baselineSegments, segments, result),
        [baselineSegments, segments, result?.transcript_edit_records]
    );
    const summary = result?.summary_markdown || '';
    const displayTranscriptSegments = pickDisplayTranscriptSegments(result, segments);
    const bilingualTranscriptSegments = displayTranscriptSegments
        .filter((seg) => String(seg.text_zh || '').trim());
    const hasBilingualTranscript = bilingualTranscriptSegments.length > 0;
    const visibleTranscriptView = hasBilingualTranscript && transcriptView !== 'raw' ? 'bilingual' : 'raw';
    const visibleTranscriptSegments = visibleTranscriptView === 'bilingual' ? bilingualTranscriptSegments : segments;
    const canUseStoredSource = !!result?.source_file_available && !!result?.task_id;
    const canUsePlaybackAudio = !!result?.artifacts?.playback_audio && !!result?.task_id;
    const canRetranscribeStoredMedia = !!lastSourceFile || canUseStoredSource || canUsePlaybackAudio;
    const retranscribeBlockedByJob = !!currentJob && !['summary', 'export', 'done'].includes(currentJob.stage);
    const retranscribeSourceLabel = canRetranscribeStoredMedia
        ? ((lastSourceFile || canUseStoredSource)
            ? (lang === 'zh' ? '原文件' : 'Source file')
            : (lang === 'zh' ? '已保存音频' : 'Saved audio'))
        : (lang === 'zh' ? '当前结果' : 'Current result');
    const retranscribeSourceName = lastSourceFile?.name
        || (canUseStoredSource ? result?.filename : result?.artifacts?.playback_audio?.filename)
        || result?.filename
        || t('edit.title');
    const durSec = result?.audio_duration_seconds || 0;
    const sttElapsedSec = result?.stt_elapsed_seconds || 0;
    const sttRealtimeFactor = result?.stt_realtime_factor || (durSec > 0 && sttElapsedSec > 0 ? sttElapsedSec / durSec : null);
    const sttProfile = result?.stt_model ? [isAzureCloudProvider(result.stt_provider) ? 'Azure' : 'local', result.stt_model, result.stt_speed, result.stt_language].filter(Boolean).join(' / ') : '';
    const activeTaskId = result?.task_id || fallbackTaskIdRef.current;
    const resolvedNoteMode = result?.resolved_note_mode || result?.requested_note_mode || null;
    const noteModeText = resolvedNoteMode ? noteModeLabel(resolvedNoteMode, lang) : null;
    const promptPresetMeta = result?.prompt_preset || null;
    const promptPresetMetaLabel = result?.prompt_preset_label
        || (promptPresetMeta ? presetDisplayLabel(promptPresetMeta, loadSettings(), lang) : null);
    const sourceLanguageMeta = result?.source_language || result?.detected_language || null;
    const normalizedSourceLanguage = String(sourceLanguageMeta || '').toLowerCase();
    const sourceLanguageLabel = normalizedSourceLanguage.startsWith('en')
        ? (lang === 'zh' ? '英文' : 'English')
        : normalizedSourceLanguage.startsWith('zh')
            ? (lang === 'zh' ? '中文' : 'Chinese')
            : (sourceLanguageMeta || (lang === 'zh' ? '未记录' : 'Not recorded'));
    const subtitleModeLabel = result?.subtitle_mode === 'bilingual_zh'
        ? (lang === 'zh' ? '中英双语' : 'Bilingual EN/ZH')
        : (lang === 'zh' ? '原文字幕' : 'Source subtitles');
    const summaryBasisLabel = normalizedSourceLanguage.startsWith('en')
        ? (lang === 'zh' ? '英文原文生成中文摘要' : 'Chinese note from English source')
        : (lang === 'zh' ? '原文生成摘要' : 'Source transcript');
    const summaryGenerationMeta = [
        {
            label: lang === 'zh' ? '生成模式' : 'Note mode',
            value: noteModeText || (lang === 'zh' ? '未记录' : 'Not recorded'),
        },
        {
            label: lang === 'zh' ? '提示词模板' : 'Prompt template',
            value: promptPresetMetaLabel || (lang === 'zh' ? '未记录' : 'Not recorded'),
        },
        {
            label: lang === 'zh' ? '原音频语言' : 'Source language',
            value: sourceLanguageLabel,
        },
        {
            label: lang === 'zh' ? '字幕模式' : 'Subtitle mode',
            value: subtitleModeLabel,
        },
        {
            label: lang === 'zh' ? '摘要依据' : 'Summary basis',
            value: summaryBasisLabel,
        },
        result?.note_mode_chunk_count ? {
            label: lang === 'zh' ? '分块数' : 'Chunks',
            value: String(result.note_mode_chunk_count),
        } : null,
        result?.note_mode_chapter_count ? {
            label: lang === 'zh' ? '章节数' : 'Chapters',
            value: String(result.note_mode_chapter_count),
        } : null,
        result?.note_mode_evidence_count ? {
            label: lang === 'zh' ? '证据数' : 'Evidence',
            value: String(result.note_mode_evidence_count),
        } : null,
        result?.note_mode_important_evidence_count ? {
            label: lang === 'zh' ? '重要证据覆盖' : 'Important coverage',
            value: `${result.note_mode_covered_important_evidence_count ?? 0}/${result.note_mode_important_evidence_count}`,
        } : null,
    ].filter(Boolean);
    const summaryReasonItems = [
        {
            label: lang === 'zh' ? '模式原因' : 'Mode reason',
            value: noteModeReasonText(result, lang),
        },
        {
            label: lang === 'zh' ? '提示词原因' : 'Prompt reason',
            value: promptPresetReasonText(result, lang),
        },
        {
            label: lang === 'zh' ? '字幕原因' : 'Subtitle reason',
            value: subtitleReasonText(result, hasBilingualTranscript, lang),
        },
    ].filter((item) => item.value);
    const transcriptReason = subtitleReasonText(result, hasBilingualTranscript, lang);
    const summaryFailureHint = summaryFailureNextStep(result, lang);
    const resultTitle = resultDisplayTitle(result, {name: t('edit.title')});
    const resultDownloadName = result?.display_title || resultTitle || result?.filename;
    const rawEditorTitle = resultTitle || result?.filename || t('edit.title');
    const editorTitle = compactDisplayFilename(rawEditorTitle, 42);
    const playbackDuration = mediaDuration || durSec || 0;
    const activeSegmentIndex = visibleTranscriptSegments.length > 0
        ? (() => {
            const found = visibleTranscriptSegments.findIndex((seg, index) => {
            const start = Number(seg.start) || 0;
            const nextStart = Number(visibleTranscriptSegments[index + 1]?.start);
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
        if (isGuestResult) {
            setTranscriptSaveStatus('idle');
            return;
        }
        const seq = ++transcriptSaveSeqRef.current;
        setTranscriptSaveStatus('saving');
        const timer = setTimeout(() => {
            saveTranscriptEdit(result.task_id, {
                transcript_text: transcript,
                segments,
                edit_records: editRecords,
            }, resultJobOptions)
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
    }, [result?.task_id, transcriptUnsaved, transcript, segments, editRecords, isGuestResult, resultJobOptions]);

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
        if (newKey === 'autoTranscriptNotes') setAutoTranscriptNotesEdit(getBuiltinExtraPromptBody('autoTranscriptNotes', { ...s, promptPreset: newKey }));
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
        if (key === 'autoTranscriptNotes') setAutoTranscriptNotesEdit(val);
        else if (key === 'meeting') setMeetingEdit(val);
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
        if(isGuestResult) {
            showToast(lang === 'zh' ? '访客试用暂不支持导出到飞书，请先下载结果文件。' : 'Guest trial does not export to Lark. Download the result files instead.', false);
            return;
        }
        setExporting(true);
        try {
            const settings = loadSettings();
            const fd = new FormData();
            fd.append('markdown', result.summary_markdown||'');
            fd.append('title', fileNameStem(resultDownloadName));
            fd.append('task_id', activeTaskId);
            if(result.source) fd.append('source_type', result.source);
            if(result.filename) fd.append('source_filename', result.filename);
            if(durSec > 0) fd.append('source_duration_seconds', String(durSec));
            const larkExportRoute = larkExportRouteFromSettings(settings);
            fd.append('lark_export_route', larkExportRoute);
            fd.append('lark_via_cli', isLocalLarkExportRoute(larkExportRoute) ? 'true' : 'false');
            const headers = shouldUseLocalSingleUserClientId()
                ? localExecutionHeaders({localExecution: true, larkExportRoute})
                : localExecutionHeaders({larkExportRoute});
            const r = await apiFetch(`${API_BASE}/export-lark`, {method:'POST', headers, body:fd});
            const data = await r.json().catch(()=>({}));
            if(!r.ok) {
                const d = data.detail;
                const msg = Array.isArray(d) ? d.map(x=>x.msg||x).join('; ') : (d || 'Export failed');
                throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
            }
            const exportUrl = data.url || null;
            if(!exportUrl && !data.dry_run) throw new Error(data.msg || 'No document URL returned');
            setLarkUrl(exportUrl);
            const dispTitle = data.doc_title || fileNameStem(resultDownloadName) || "Export";
            if(exportUrl) addLarkExport({url:exportUrl, title: dispTitle, timestamp:Date.now()});
            showToast(t('edit.exportDone'));
        } catch(err) { showToast(t('edit.exportFail')+': '+err.message, false); }
        finally { setExporting(false); }
    };

    const handleRegenerate = async () => {
        if(!transcript || regenerating) return;
        if(isGuestResult) {
            showToast(lang === 'zh' ? '访客试用暂不支持重新生成，请重新上传一个文件试用。' : 'Guest trial cannot regenerate. Upload a new file to try again.', false);
            return;
        }
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
            fd.append('prompt_preset', settings.promptPreset || DEFAULT_PROMPT_PRESET);
            fd.append('prompt_preset_label', presetDisplayLabel(settings.promptPreset || DEFAULT_PROMPT_PRESET, settings, lang));
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
		                summary_status: data.summary_status || 'completed',
		                summary_error: null,
			                requested_note_mode: data.requested_note_mode||settings.noteMode||'auto',
			                resolved_note_mode: data.resolved_note_mode||null,
			                note_mode_chunk_count: data.note_mode_chunk_count||null,
			                note_mode_segment_count: data.note_mode_segment_count||null,
			                note_mode_evidence_count: data.note_mode_evidence_count||null,
			                note_mode_chapter_count: data.note_mode_chapter_count||null,
			                note_mode_important_evidence_count: data.note_mode_important_evidence_count||null,
			                note_mode_covered_important_evidence_count: data.note_mode_covered_important_evidence_count||null,
			                note_mode_coverage_missing_count: data.note_mode_coverage_missing_count||null,
			                prompt_preset: data.prompt_preset || settings.promptPreset || DEFAULT_PROMPT_PRESET,
			                prompt_preset_label: data.prompt_preset_label || presetDisplayLabel(settings.promptPreset || DEFAULT_PROMPT_PRESET, settings, lang),
			            });
            showToast(t('edit.regenDone'));
        } catch(err) { showToast(err.message, false); }
        finally { setRegenerating(false); }
    };

    const handleTranslateTranscript = async () => {
        if(!result?.task_id || segments.length === 0 || translatingTranscript) return;
        if(isGuestResult) {
            showToast(lang === 'zh' ? '访客试用暂不支持生成中英对照。' : 'Guest trial cannot generate bilingual subtitles.', false);
            return;
        }
        setTranslatingTranscript(true);
        try {
            if(transcriptUnsaved) {
                const saveData = await saveTranscriptEdit(result.task_id, {
                    transcript_text: transcript,
                    segments,
                    edit_records: editRecords,
                }, resultJobOptions);
                setTranscriptUnsaved(false);
                setTranscriptDirty(true);
                setTranscriptSaveStatus('saved');
                if(saveData?.result) {
                    setLastResult((prev) => (
                        prev?.task_id === result.task_id ? {...prev, ...saveData.result} : prev
                    ));
                }
            }
            const settings = loadSettings();
            const translationOptions = Object.keys(resultJobOptions).length
                ? resultJobOptions
                : {sttProvider: effectiveSttProvider(settings, runtimeConfig)};
            const data = await translateJobSegments(result.task_id, {
                segments,
                aiProvider: settings.aiProvider || 'deepseek',
                aiModel: settings.aiModel || null,
            }, translationOptions);
            if(data?.result) {
                setLastResult((prev) => (
                    prev?.task_id === result.task_id
                        ? {...prev, ...data.result}
                        : {...result, ...data.result}
                ));
            }
            setTranscriptView('bilingual');
            showToast(lang === 'zh' ? '中英对照已生成' : 'Bilingual subtitles added');
        } catch(err) {
            showToast((lang === 'zh' ? '生成中英对照失败：' : 'Bilingual generation failed: ') + (err?.message || ''), false);
        } finally {
            setTranslatingTranscript(false);
        }
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
        const retranscribeErrorMessage = (err) => {
            if (err?.status === 401 || err?.payload?.account_required) {
                if (isAzureCloudProvider(sttProvider)) {
                    return lang === 'zh'
                        ? '当前选择的是云端转录，需要先登录或重新登录账号。想用本机转录，请到「处理设置」把转录路线切到「本地转录」。'
                        : 'Cloud transcription requires an active account login. To use this Mac instead, switch the transcription route to Local in Processing settings.';
                }
                return lang === 'zh'
                    ? '本地重新转录请求被账号校验拦住了。请刷新页面或重新登录后再试。'
                    : 'The local retranscription request was blocked by account verification. Refresh or sign in again, then retry.';
            }
            return err?.message || (lang === 'zh' ? '重新转录失败' : 'Retranscription failed');
        };
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
            sttLanguage: 'auto',
            skipSummary: !!settings.skipAiSummary,
            exportToLark: !!settings.exportToLark,
            noteMode: settings.noteMode||'auto',
        });
        try {
            const resultData = await processVideoSSE(file, {
                taskId,
                sourceLastModifiedMs: file.lastModified||null,
                exportToLark: settings.exportToLark||false,
                larkExportRoute: larkExportRouteFromSettings(settings),
                larkViaCli: !!settings.larkViaCli,
                title: file.name.replace(/\.[^/.]+$/,""),
                ...buildAiOptions(settings),
                skipSummary: !!settings.skipAiSummary,
                sttProvider,
                sttModel,
                sttSpeed: settings.sttSpeed||'balanced',
                sttLanguage: 'auto',
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
            showToast(retranscribeErrorMessage(err), false);
        } finally {
            setRetranscribing(false);
        }
    };

    const handleRetranscribe = () => {
        setRetranscribeConfirmOpen(true);
    };

    const confirmRetranscribe = async () => {
        setRetranscribeConfirmOpen(false);
        if(isGuestResult) {
            showToast(lang === 'zh' ? '访客试用暂不支持重新转录，请回到首页重新上传。' : 'Guest trial cannot retranscribe here. Start a new upload from Dashboard.', false);
            return;
        }
        const fetchPlaybackAudioForRetranscribe = async () => {
            const artifact = result?.artifacts?.playback_audio;
            if (!result?.task_id || !artifact) throw new Error(t('edit.retranscribeUnavailableTitle'));
            return await fetchJobArtifactFile(
                result.task_id,
                'playback_audio',
                artifact.filename || `${result.filename || 'source'}_audio.mp3`,
                resultJobOptions,
            );
        };
        if(lastSourceFile) runRetranscribe(lastSourceFile);
        else if(result?.task_id && result?.source_file_available) {
            try {
                const sourceFile = await fetchJobSourceFile(result.task_id, result.filename || 'source', resultJobOptions);
                runRetranscribe(sourceFile);
            } catch (err) {
                if (result?.artifacts?.playback_audio) {
                    try {
                        const audioFile = await fetchPlaybackAudioForRetranscribe();
                        runRetranscribe(audioFile);
                    } catch (playbackErr) {
                        showToast(playbackErr.message || err.message || t('edit.retranscribeUnavailableTitle'), false);
                        retranscribeInputRef.current?.click();
                    }
                } else {
                    showToast(err.message || t('edit.retranscribeUnavailableTitle'), false);
                    retranscribeInputRef.current?.click();
                }
            }
        } else if(result?.task_id && result?.artifacts?.playback_audio) {
            try {
                const audioFile = await fetchPlaybackAudioForRetranscribe();
                runRetranscribe(audioFile);
            } catch (err) {
                showToast(err.message || t('edit.retranscribeUnavailableTitle'), false);
                retranscribeInputRef.current?.click();
            }
        } else retranscribeInputRef.current?.click();
    };

    const handleMediaFileSelected = async (file) => {
        if (!file) return;
        setLastSourceFile(file);
        loadMediaFile(file);
        if (!result?.task_id || isGuestResult) return;
        try {
            const data = await uploadJobPlaybackAudio(result.task_id, file);
            if (data?.result) {
                setLastResult(data.result);
                addToHistory(resultToHistoryEntry(data.result, {
                    taskId: data.result.task_id || result.task_id,
                    name: data.result.filename || file.name,
                }));
            }
            showToast(lang === 'zh' ? '原音频已保存，下次打开不用重选。' : 'Source audio saved for next time.');
        } catch (err) {
            showToast(
                lang === 'zh'
                    ? `当前可播放，但保存失败，刷新后可能还要重选。${err?.message ? ` ${err.message}` : ''}`
                    : `Playback works for now, but saving failed. You may need to choose it again after refresh.${err?.message ? ` ${err.message}` : ''}`,
                false,
            );
        }
    };

    if(!result && guestMode) return <GuestEditorPreview lang={lang} />;

    if(!result) return (
        <div className="ml-[var(--sidebar-offset)] min-h-dvh bg-[#f8f7fb] pb-8 text-[#111111] dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="flex h-[calc(100vh-2rem)] items-center justify-center px-8">
                <div className="w-full max-w-xl rounded-[28px] border border-[#e4e0e0] bg-white px-8 py-10 text-center shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                    <SvgIcon name="edit_note" className="mb-4 text-6xl text-[#8a8a8a] dark:text-white/40"/>
                    <h2 className="mb-2 font-headline text-2xl font-extrabold text-[#111111] dark:text-white">{t('edit.noResult')}</h2>
                    <p className="mb-6 text-sm font-semibold leading-relaxed text-[#666] dark:text-white/60">{t('edit.noResultDesc')}</p>
                    <Link to="/" className="inline-flex items-center gap-2 rounded-[14px] bg-[#111111] px-6 py-3 text-sm font-bold text-white transition-colors hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/85">
                        <SvgIcon name="upload_file" className="text-lg"/>{t('dash.selectFile')}
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
    <div className="ml-[var(--sidebar-offset)] min-h-dvh bg-[#f8f7fb] pb-8 text-[#111111] dark:bg-[#101010] dark:text-white/[0.92]">
        {toast && (
            <div className={`fixed right-8 top-6 z-50 rounded-[16px] px-5 py-3 text-sm font-bold shadow-[0_18px_44px_-26px_rgba(17,17,17,.55)] ${toast.ok?'bg-[#111111] text-white dark:bg-white dark:text-[#111111]':'bg-red-600 text-white'}`}>
                {toast.msg}
                                            </div>
        )}
        {larkUrl && (
            <div className="fixed left-1/2 top-6 z-50 flex max-w-lg -translate-x-1/2 items-center gap-4 rounded-[20px] border border-[#d9eadf] bg-white px-6 py-4 shadow-[0_18px_44px_-26px_rgba(17,17,17,.55)] dark:border-emerald-400/20 dark:bg-[#151515]">
                <SvgIcon name="check_circle" className="text-2xl text-emerald-600 dark:text-emerald-300"/>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-[#111111] dark:text-white">{t('edit.exportDone')}</p>
                    <a href={larkUrl} target="_blank" rel="noopener noreferrer" className="text-primary text-sm hover:underline truncate block">{larkUrl}</a>
                                                </div>
                <button onClick={()=>setLarkUrl(null)} className="flex-shrink-0 text-[#777] hover:text-[#111111] dark:text-white/50 dark:hover:text-white">
                    <SvgIcon name="close" className="text-sm"/>
                </button>
                                                </div>
        )}
        {retranscribeConfirmOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-6 backdrop-blur-sm">
                <div className="w-full max-w-lg overflow-hidden rounded-[24px] border border-[#e4e0e0] bg-white shadow-[0_24px_70px_-35px_rgba(17,17,17,.65)] dark:border-white/[0.12] dark:bg-[#151515]">
                    <div className="flex items-start gap-4 border-b border-[#e4e0e0] px-6 py-5 dark:border-white/[0.12]">
                        <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-[14px] bg-[#eef2ff] text-primary dark:bg-white/[0.08] dark:text-white">
                            <SvgIcon name="record_voice_over" className=""/>
                        </div>
                        <div className="min-w-0">
                            <h2 className="font-headline text-xl font-extrabold text-[#111111] dark:text-white">
                                {canRetranscribeStoredMedia ? t('edit.retranscribeConfirmTitle') : t('edit.retranscribeUnavailableTitle')}
                            </h2>
                            <p className="mt-2 text-sm font-medium leading-relaxed text-[#666] dark:text-white/60">
                                {canRetranscribeStoredMedia ? t('edit.retranscribeConfirmDesc') : t('edit.retranscribeUnavailableDesc')}
                            </p>
                            <div className="mt-4 rounded-[16px] border border-[#e4e0e0] bg-[#f8f7fb] p-3 dark:border-white/[0.12] dark:bg-white/[0.06]">
                                <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-[#777] dark:text-white/45">{retranscribeSourceLabel}</p>
                                <p className="truncate text-sm font-bold text-[#111111] dark:text-white">{retranscribeSourceName}</p>
                            </div>
                        </div>
                    </div>
                    <div className="flex flex-col-reverse gap-3 px-6 py-4 sm:flex-row sm:justify-end">
                        <button
                            type="button"
                            onClick={()=>setRetranscribeConfirmOpen(false)}
                            className="rounded-[13px] bg-[#efeeee] px-4 py-2 text-sm font-bold text-[#111111] transition hover:bg-[#e4e0e0] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]"
                        >
                            {t('edit.cancel')}
                        </button>
                        <button
                            type="button"
                            onClick={confirmRetranscribe}
                            className="inline-flex items-center justify-center gap-2 rounded-[13px] bg-[#111111] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/85"
                        >
                            <SvgIcon name={canRetranscribeStoredMedia ? 'sync' : 'upload_file'} className="text-base"/>
                            {canRetranscribeStoredMedia ? t('edit.retranscribeConfirmAction') : t('edit.retranscribeChooseAction')}
                        </button>
                    </div>
                </div>
            </div>
        )}
        {editRecordsOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-6 backdrop-blur-sm">
                <div className="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-[24px] border border-[#e4e0e0] bg-white shadow-[0_24px_70px_-35px_rgba(17,17,17,.65)] dark:border-white/[0.12] dark:bg-[#151515]">
                    <div className="flex items-start justify-between gap-4 border-b border-[#e4e0e0] px-6 py-5 dark:border-white/[0.12]">
                        <div className="min-w-0">
                            <h2 className="flex items-center gap-2 font-headline text-xl font-extrabold text-[#111111] dark:text-white">
                                <SvgIcon name="edit_note" className="text-primary"/>
                                {t('edit.editRecordsTitle')}
                                <span className="rounded-full bg-[#eef2ff] px-2 py-0.5 text-xs font-bold text-primary dark:bg-white/[0.08] dark:text-white">{editRecords.length}</span>
                            </h2>
                            <p className="mt-2 text-sm font-medium leading-relaxed text-[#666] dark:text-white/60">{t('edit.editRecordsDesc')}</p>
                        </div>
                        <button
                            type="button"
                            onClick={()=>setEditRecordsOpen(false)}
                            className="flex h-9 w-9 items-center justify-center rounded-[13px] bg-[#efeeee] text-[#666] transition hover:bg-[#e4e0e0] hover:text-[#111111] dark:bg-white/[0.08] dark:text-white/60 dark:hover:bg-white/[0.12] dark:hover:text-white"
                        >
                            <SvgIcon name="close" className="text-lg"/>
                        </button>
                    </div>
                    <div className="flex-1 space-y-4 overflow-y-auto p-5">
                        {editRecords.length === 0 ? (
                            <div className="rounded-[18px] bg-[#f8f7fb] px-5 py-8 text-center text-sm font-medium text-[#666] dark:bg-white/[0.06] dark:text-white/60">
                                {t('edit.editRecordsEmpty')}
                            </div>
                        ) : editRecords.map((record, idx) => (
                            <article key={`${record.index}-${record.start}-${idx}`} className="overflow-hidden rounded-[18px] border border-[#e4e0e0] bg-white dark:border-white/[0.12] dark:bg-white/[0.04]">
                                <div className="flex items-center gap-3 bg-[#f8f7fb] px-4 py-3 dark:bg-white/[0.04]">
                                    <button
                                        type="button"
                                        onClick={()=>{ setEditRecordsOpen(false); seekToSegment(record); }}
                                        className="font-mono text-xs font-bold text-primary hover:underline"
                                    >
                                        {fmtTime(record.start || 0)}
                                    </button>
                                    <span className="text-xs font-semibold text-[#777] dark:text-white/45">#{record.index + 1}</span>
                                </div>
                                <div className="space-y-3 p-4">
                                    <div className="grid gap-3 md:grid-cols-2">
                                        <div className="rounded-[14px] border border-red-500/10 bg-red-50/70 p-3 dark:bg-red-500/10">
                                            <p className="mb-1 text-[10px] font-bold text-red-600 dark:text-red-300">{t('edit.before')}</p>
                                            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#111111] dark:text-white">{record.before}</p>
                                        </div>
                                        <div className="rounded-[14px] border border-green-500/10 bg-green-50/80 p-3 dark:bg-green-500/10">
                                            <p className="mb-1 text-[10px] font-bold text-green-700 dark:text-green-300">{t('edit.after')}</p>
                                            <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#111111] dark:text-white">{record.after}</p>
                                        </div>
                                    </div>
                                    <div className="grid gap-3 text-xs text-[#666] dark:text-white/60 md:grid-cols-2">
                                        <div className="rounded-[14px] bg-[#f8f7fb] p-3 dark:bg-white/[0.06]">
                                            <p className="mb-1 font-bold text-[#111111] dark:text-white">{t('edit.previousSentence')}</p>
                                            <p className="whitespace-pre-wrap leading-relaxed">{record.previous_before || record.previous_after || '-'}</p>
                                        </div>
                                        <div className="rounded-[14px] bg-[#f8f7fb] p-3 dark:bg-white/[0.06]">
                                            <p className="mb-1 font-bold text-[#111111] dark:text-white">{t('edit.nextSentence')}</p>
                                            <p className="whitespace-pre-wrap leading-relaxed">{record.next_before || record.next_after || '-'}</p>
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
                if(file) handleMediaFileSelected(file);
            }}
        />
        <main className="h-dvh overflow-hidden px-8 pb-4 pt-6">
            <div className="max-w-7xl mx-auto h-full min-h-0 flex flex-col gap-4">
                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                                            <div className="min-w-0 pr-2">
                        <h1
                            className="max-w-[30ch] font-headline text-[clamp(1.55rem,1.8vw,2rem)] font-extrabold leading-tight text-[#111111] dark:text-white"
                            title={rawEditorTitle}
                            aria-label={rawEditorTitle}
                        >
                            {editorTitle}
                        </h1>
	                        <p className="mt-1 max-w-[68ch] text-sm font-semibold leading-snug text-[#666] dark:text-white/60">
	                            {durSec > 0 && <>{t('edit.duration')}: {fmtTime(durSec)} &bull; </>}
		                            {sttElapsedSec > 0 && <>{t('edit.sttElapsed')}: {fmtElapsed(sttElapsedSec)} {sttRealtimeFactor ? `(${fmtSttRelative(sttRealtimeFactor, lang)})` : ''} &bull; </>}
		                            {sttProfile && <>STT: {sttProfile} &bull; </>}
		                            {noteModeText && <>{t('work.summaryMode')}: {noteModeText} &bull; </>}
		                            {segments.length > 0 && <>{segments.length} {t('edit.segments')} &bull; </>}
                            <span className="text-[10px] font-bold uppercase tracking-wider text-[#111111] dark:text-white">{t('edit.confidence')}</span>
                        </p>
                                            </div>
                    <div className="grid grid-cols-4 gap-3 w-[360px] flex-shrink-0">
	                        <button onClick={()=>setPromptOpen(true)} className="flex h-[82px] min-w-0 flex-col items-center justify-center gap-1.5 rounded-[18px] border border-[#e4e0e0] bg-white px-2 py-2 text-xs font-bold text-[#111111] transition hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.1]">
	                            <SvgIcon name="tune" className="text-lg"/>
	                            <span className="leading-tight text-center whitespace-normal break-keep">{t('prompt.collapsed')}</span>
	                        </button>
	                        <button onClick={handleRegenerate} disabled={isGuestResult||regenerating||!transcript} className="flex h-[82px] min-w-0 flex-col items-center justify-center gap-1.5 rounded-[18px] border border-[#e4e0e0] bg-white px-2 py-2 text-xs font-bold text-[#111111] transition hover:bg-[#efeeee] disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.1]">
                            <SvgIcon name={regenerating ? 'sync' : 'refresh'} className={`text-lg ${regenerating?'animate-spin':''}`}/>
                            <span className="leading-tight text-center whitespace-normal break-keep">{t('edit.regenerate')}</span>
                        </button>
	                        <button onClick={handleRetranscribe} disabled={isGuestResult||retranscribing||retranscribeBlockedByJob} className="flex h-[82px] min-w-0 flex-col items-center justify-center gap-1.5 rounded-[18px] border border-[#d6dcff] bg-[#eef2ff] px-2 py-2 text-xs font-bold text-primary transition hover:bg-[#e7edff] active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:cursor-not-allowed disabled:border-[#e4e0e0] disabled:bg-white disabled:text-[#8a8a8a] disabled:opacity-100 disabled:hover:bg-white dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:disabled:bg-white/[0.04] dark:disabled:text-white/35">
                            <SvgIcon name={retranscribing ? 'sync' : 'record_voice_over'} className={`text-lg ${retranscribing?'animate-spin':''}`}/>
                            <span className="leading-tight text-center whitespace-normal break-keep">{retranscribing ? t('edit.retranscribing') : t('edit.retranscribe')}</span>
                        </button>
                        <button onClick={handleExportLark} disabled={isGuestResult||exporting||!summary} className="flex h-[82px] min-w-0 flex-col items-center justify-center gap-1.5 rounded-[18px] bg-[#111111] px-2 py-2 text-xs font-bold text-white transition hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/85">
                            <SvgIcon name={exporting ? 'sync' : 'cloud_upload'} className={`text-lg ${exporting?'animate-spin':''}`}/>
                            <span className="leading-tight text-center whitespace-normal break-keep">{t('edit.export')}</span>
                        </button>
                                        </div>
                                    </div>

                <PromptTemplateDialog
                    open={promptOpen}
                    onClose={()=>setPromptOpen(false)}
                    t={t}
                    lang={lang}
                    settings={loadSettings()}
                    promptKey={promptKey}
                    presetLabel={presetLabel}
                    handlePromptKeyChange={handlePromptKeyChange}
                    handleDeleteUserPreset={handleDeleteUserPreset}
                    resetBuiltinExtra={resetBuiltinExtra}
                    defaultPromptEdit={defaultPromptEdit}
                    handleDefaultPromptChange={handleDefaultPromptChange}
                    userPresetEdit={userPresetEdit}
                    handleUserPresetChange={handleUserPresetChange}
                    customText={customText}
                    handleCustomTextChange={handleCustomTextChange}
                    presetNameInput={presetNameInput}
                    setPresetNameInput={setPresetNameInput}
                    saveCustomAsPresetFromEditor={saveCustomAsPresetFromEditor}
                    autoTranscriptNotesEdit={autoTranscriptNotesEdit}
                    meetingEdit={meetingEdit}
                    researchEdit={researchEdit}
                    quickBulletsEdit={quickBulletsEdit}
                    handleBuiltinExtraChange={handleBuiltinExtraChange}
                />

                        <div className="flex min-h-0 flex-1 gap-4 overflow-hidden">
                            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[24px] border border-[#e4e0e0] bg-white shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                <div className="border-b border-[#e4e0e0] p-4 dark:border-white/[0.12] sm:p-5">
                                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2">
                                                <SvgIcon name="subject" className="text-[20px] text-[#111111] dark:text-white"/>
                                                <h2 className="truncate font-headline text-lg font-extrabold text-[#111111] dark:text-white">
                                                    {t('edit.transcript')}
                                                </h2>
                                            </div>
                                            {(transcriptDirty || segments.length === 0 || transcriptSaveStatus !== 'idle') && (
                                                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 pl-7 text-[11px] font-semibold leading-tight text-[#666] dark:text-white/60">
                                                    {transcriptDirty && (
                                                        <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-300">
                                                            <span className="h-1.5 w-1.5 rounded-full bg-amber-500"></span>
                                                            {t('edit.editedTranscript')}
                                                        </span>
                                                    )}
                                                    {segments.length === 0 && (
                                                        <span className="inline-flex items-center gap-1 text-on-surface-variant">
                                                            <span className="h-1.5 w-1.5 rounded-full bg-outline"></span>
                                                            {lang==='zh'?'纯文本模式':'Plain text'}
                                                        </span>
                                                    )}
                                                    {transcriptSaveStatus !== 'idle' && (
                                                        <span className={`inline-flex items-center gap-1 ${
                                                            transcriptSaveStatus === 'failed'
                                                                ? 'text-error'
                                                                : transcriptSaveStatus === 'saving'
                                                                    ? 'text-primary'
                                                                    : 'text-emerald-700 dark:text-emerald-300'
                                                        }`}>
                                                            <SvgIcon
                                                                name={transcriptSaveStatus === 'saving'
                                                                    ? 'sync'
                                                                    : transcriptSaveStatus === 'failed'
                                                                        ? 'error'
                                                                        : 'check_circle'}
                                                                className={`text-[13px] ${
                                                                transcriptSaveStatus === 'saving' ? 'animate-spin' : ''
                                                            }`}
                                                            />
                                                            {transcriptSaveStatus === 'saving'
                                                                ? t('edit.transcriptSaving')
                                                                : transcriptSaveStatus === 'failed'
                                                                    ? t('edit.transcriptSaveFailed')
                                                                    : t('edit.transcriptSaved')}
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                            {transcriptReason && (
                                                <p className="mt-1 max-w-[56ch] pl-7 text-[11px] font-semibold leading-relaxed text-[#666] dark:text-white/60">
                                                    {transcriptReason}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
                                            {hasBilingualTranscript && segments.length > 0 && (
                                                <div className="inline-flex h-9 overflow-hidden rounded-[13px] border border-[#e4e0e0] bg-[#f8f7fb] p-0.5 dark:border-white/[0.12] dark:bg-white/[0.06]">
                                                    <button
                                                        type="button"
                                                        onClick={()=>setTranscriptView('bilingual')}
                                                        className={`inline-flex items-center justify-center px-2.5 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
                                                            visibleTranscriptView === 'bilingual'
                                                                ? 'bg-[#111111] text-white dark:bg-white dark:text-[#111111]'
                                                                : 'text-[#666] hover:bg-white hover:text-[#111111] dark:text-white/60 dark:hover:bg-white/[0.08] dark:hover:text-white'
                                                        }`}
                                                    >
                                                        {lang === 'zh' ? '中英对照' : 'Bilingual'}
                                                    </button>
                                                    <button
                                                        type="button"
                                                        onClick={()=>setTranscriptView('raw')}
                                                        className={`inline-flex items-center justify-center px-2.5 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 ${
                                                            visibleTranscriptView === 'raw'
                                                                ? 'bg-[#111111] text-white dark:bg-white dark:text-[#111111]'
                                                                : 'text-[#666] hover:bg-white hover:text-[#111111] dark:text-white/60 dark:hover:bg-white/[0.08] dark:hover:text-white'
                                                        }`}
                                                    >
                                                        {lang === 'zh' ? '原始字幕' : 'Original'}
                                                    </button>
                                                </div>
                                            )}
                                            <button
                                                type="button"
                                                onClick={handleTranslateTranscript}
                                                disabled={isGuestResult || translatingTranscript || !result?.task_id || segments.length === 0}
                                                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-[13px] border border-[#d6dcff] bg-[#eef2ff] px-3 text-xs font-bold text-primary transition hover:bg-[#e7edff] active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 disabled:cursor-not-allowed disabled:border-[#e4e0e0] disabled:bg-[#f8f7fb] disabled:text-[#8a8a8a] dark:border-white/[0.12] dark:bg-white/[0.08] dark:text-white dark:disabled:bg-white/[0.04] dark:disabled:text-white/35"
                                            >
                                                <SvgIcon name={translatingTranscript ? 'sync' : 'translate'} className={`text-[17px] ${translatingTranscript ? 'animate-spin' : ''}`}/>
                                                <span>
                                                    {translatingTranscript
                                                        ? (lang === 'zh' ? '生成中' : 'Translating')
                                                        : hasBilingualTranscript
                                                            ? (lang === 'zh' ? '更新中英对照' : 'Refresh Bilingual')
                                                            : (lang === 'zh' ? '生成中英对照' : 'Add Bilingual')}
                                                </span>
                                            </button>
                                            <button
                                                type="button"
                                                onClick={()=>setEditRecordsOpen(true)}
                                                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-[13px] border border-[#e4e0e0] bg-white px-3 text-xs font-bold text-[#666] transition hover:bg-[#efeeee] hover:text-[#111111] active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/65 dark:hover:bg-white/[0.1] dark:hover:text-white"
                                            >
                                                <SvgIcon name="edit_note" className="text-[17px]"/>
                                                <span>{t('edit.editRecords')}</span>
                                                <span className="tabular-nums text-primary">{editRecords.length}</span>
                                            </button>
                                            <DropdownMenu
                                                trigger={
                                                    <button className="inline-flex h-9 items-center justify-center gap-1.5 rounded-[13px] bg-[#111111] px-3 text-xs font-bold text-white transition hover:bg-[#2a2a2a] active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/85">
                                                        <SvgIcon name="download" className="text-[17px]"/>
                                                        {lang === 'zh' ? '导出' : t('dl.transcript')}
                                                    </button>
                                                }
                                                items={[
                                                    {icon:'description', label:t('dl.txt'), badge:'TXT', onClick:()=>{dlTranscriptTxt(transcript,resultDownloadName); recordDownload('transcript_downloaded','txt'); showToast(t('dl.success'));}},
                                                    {icon:'subtitles', label:t('dl.srt'), badge:'SRT', disabled:segments.length===0, onClick:()=>{dlTranscriptSrt(segments,resultDownloadName); recordDownload('transcript_downloaded','srt'); showToast(t('dl.success'));}},
                                                    {icon:'closed_caption', label:t('dl.vtt'), badge:'VTT', disabled:segments.length===0, onClick:()=>{dlTranscriptVtt(segments,resultDownloadName); recordDownload('transcript_downloaded','vtt'); showToast(t('dl.success'));}},
                                                    {icon:'translate', label:t('dl.bilingualSrt'), badge:'双语 SRT', disabled:!hasBilingualTranscript, onClick:()=>{dlBilingualTranscriptSrt(bilingualTranscriptSegments,null,resultDownloadName); recordDownload('transcript_downloaded','bilingual_srt'); showToast(t('dl.success'));}},
                                                    {icon:'translate', label:t('dl.bilingualVtt'), badge:'双语 VTT', disabled:!hasBilingualTranscript, onClick:()=>{dlBilingualTranscriptVtt(bilingualTranscriptSegments,null,resultDownloadName); recordDownload('transcript_downloaded','bilingual_vtt'); showToast(t('dl.success'));}},
                                                ]}
                                            />
                                        </div>
                                    </div>
                                </div>
                        <div ref={transcriptScrollRef} className="hide-scrollbar min-h-0 flex-1 space-y-2 overflow-y-auto p-5">
                            {visibleTranscriptView === 'bilingual' && bilingualTranscriptSegments.length > 0 ? bilingualTranscriptSegments.map((seg,i) => (
                                <div
                                    key={`bilingual-${i}`}
                                    ref={(node)=>{ if(node) segmentRefs.current[i]=node; }}
                                    className={`flex gap-4 rounded-[16px] px-3 py-3 transition-colors ${i===activeSegmentIndex && mediaUrl ? 'bg-[#eef2ff] dark:bg-white/[0.1]' : 'hover:bg-[#f8f7fb] dark:hover:bg-white/[0.06]'}`}
                                >
                                    <button
                                        type="button"
                                        onClick={()=>seekToSegment(seg)}
                                        className={`w-24 flex-shrink-0 pt-1 text-left font-mono text-xs tabular-nums transition ${i===activeSegmentIndex && mediaUrl ? 'font-bold text-primary' : 'text-[#777] hover:text-primary dark:text-white/45'}`}
                                    >
                                        <span className="block">{fmtTime(seg.start)}</span>
                                        <span className="mt-0.5 block text-[10px] opacity-70">{fmtTime(seg.end)}</span>
                                    </button>
                                    <div className="min-w-0 flex-1">
                                        <p className="whitespace-pre-wrap text-sm font-medium leading-relaxed text-[#111111] dark:text-white">
                                            {seg.text}
                                        </p>
                                        <p className="mt-2 border-l-2 border-primary/25 pl-3 text-sm font-medium leading-relaxed text-[#666] dark:text-white/65">
                                            {seg.text_zh}
                                        </p>
                                    </div>
                                </div>
                            )) : segments.length > 0 ? segments.map((seg,i) => (
                                <div
                                    key={i}
                                    ref={(node)=>{ if(node) segmentRefs.current[i]=node; }}
                                    className={`group flex gap-4 rounded-[16px] px-2 py-2 transition-colors ${i===activeSegmentIndex && mediaUrl ? 'bg-[#eef2ff] dark:bg-white/[0.1]' : 'hover:bg-[#f8f7fb] dark:hover:bg-white/[0.06]'}`}
                                >
                                    <button
                                        type="button"
                                        onClick={()=>seekToSegment(seg)}
                                        className={`w-14 flex-shrink-0 pt-2 text-left font-mono text-xs transition ${i===activeSegmentIndex && mediaUrl ? 'font-bold text-primary' : 'text-[#8a8a8a] hover:text-primary dark:text-white/40'}`}
                                    >
                                        {fmtTime(seg.start)}
                                    </button>
                                    <div className="flex-1 min-w-0">
                                        <textarea
                                            data-transcript-segment="true"
                                            value={seg.text || ''}
                                            ref={autoSizeTextarea}
                                            onChange={(e)=>{ autoSizeTextarea(e.target); handleSegmentTextChange(i, e.target.value); }}
                                            onFocus={()=>setFollowPlayback(false)}
                                            rows={1}
                                            className="min-h-[2rem] w-full resize-none overflow-hidden border-none bg-transparent p-0 text-sm font-medium leading-relaxed text-[#111111] focus:ring-0 dark:text-white"
                                        />
                                    </div>
                                        </div>
	                            )) : (
                                    <div className="min-h-full flex flex-col gap-3">
                                        <div className="flex items-start gap-3 rounded-[16px] border border-[#d6dcff] bg-[#eef2ff] px-3.5 py-3 dark:border-white/[0.12] dark:bg-white/[0.08]">
                                            <SvgIcon name="info" className="text-primary text-base mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10"/>
                                            <p className="text-xs leading-relaxed text-on-surface-variant">
                                                {lang==='zh'
                                                    ? '当前结果没有时间戳分段，只能按纯文本编辑。常见原因是旧历史记录、纯文本导入，或任务结果没有成功写入后端。重新转录原音频后会恢复左侧时间戳分段。'
                                                    : 'This result has no timestamped segments, so it is shown as plain text. This usually comes from old history, plain-text import, or a result that was not saved to the backend. Retranscribing the source audio restores timestamped segments.'}
                                            </p>
                                        </div>
	                                <textarea
	                                    value={transcript}
	                                    onChange={(e)=>handlePlainTranscriptChange(e.target.value)}
	                                    onFocus={()=>setFollowPlayback(false)}
	                                    className="min-h-[320px] w-full flex-1 resize-none whitespace-pre-wrap border-none bg-transparent p-0 text-sm font-medium leading-relaxed text-[#111111] focus:ring-0 dark:text-white"
	                                />
                                    </div>
	                            )}
                                </div>
                                <div className="border-t border-[#e4e0e0] bg-[#fbfbfb]/90 p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
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
                                                <button type="button" onClick={togglePlayback} className="flex h-9 w-9 items-center justify-center rounded-[13px] bg-[#111111] text-white transition hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/85">
                                                    <SvgIcon name={mediaPlaying ? 'pause' : 'play_arrow'} className="text-lg"/>
                                                </button>
                                                <button type="button" onClick={()=>setFollowPlayback(v=>!v)} className={`rounded-[12px] px-2.5 py-1.5 text-xs font-bold transition ${followPlayback?'bg-[#eef2ff] text-primary dark:bg-white/[0.1] dark:text-white':'bg-[#efeeee] text-[#666] dark:bg-white/[0.08] dark:text-white/60'}`}>
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
                                            <p className="text-xs font-semibold text-[#666] dark:text-white/60">{mediaLoading ? t('edit.sourceLoading') : (mediaError || t('edit.audioUnavailable'))}</p>
                                            <button type="button" onClick={()=>mediaInputRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-[13px] bg-[#efeeee] px-3 py-2 text-xs font-bold text-[#111111] transition hover:bg-[#e4e0e0] dark:bg-white/[0.08] dark:text-white dark:hover:bg-white/[0.12]">
                                                <SvgIcon name="audio_file" className="text-sm"/>{t('edit.chooseAudio')}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </section>

                            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[24px] border border-[#e4e0e0] bg-white shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                <div className="flex items-center justify-between border-b border-[#e4e0e0] bg-[#fbfbfb] p-5 dark:border-white/[0.12] dark:bg-white/[0.04]">
                                    <h2 className="flex items-center gap-2 font-headline text-lg font-extrabold text-[#111111] dark:text-white">
                                        <SvgIcon name="psychology" className="text-[#111111] dark:text-white"/>
                                {t('edit.aiSummary')}
                                    </h2>
                            <div className="flex items-center gap-2">
                            <span className="rounded-full border border-[#e4e0e0] bg-white px-2.5 py-1 text-[10px] font-bold text-[#666] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                {t('prompt.activeHint')}{presetLabel(promptKey)}
                            </span>
                                <DropdownMenu
                                    trigger={
                                        <button disabled={!summary || !!downloading} className="flex items-center gap-1 rounded-[13px] border border-[#e4e0e0] bg-white px-2.5 py-1.5 text-xs font-bold text-[#111111] transition hover:bg-[#efeeee] disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.1]">
                                            <SvgIcon name={downloading ? 'sync' : 'download'} className={`text-sm ${downloading?'animate-spin':''}`}/>
                                            {downloading ? t('dl.generating') : t('dl.summary')}
                                    </button>
                                    }
                                    items={[
                                        {icon:'description', label:t('dl.txt'), badge:'TXT', disabled:!summary, onClick:()=>{dlSummaryTxt(summary,resultDownloadName); recordDownload('summary_downloaded','txt'); showToast(t('dl.success'));}},
                                        {icon:'markdown', label:t('dl.md'), badge:'MD', disabled:!summary, onClick:()=>{dlSummaryMd(summary,resultDownloadName); recordDownload('summary_downloaded','md'); showToast(t('dl.success'));}},
                                        {divider:true},
                                        {icon:'picture_as_pdf', label:t('dl.pdf'), badge:'PDF', disabled:!summary, onClick:async()=>{
                                            setDownloading('pdf');
                                            try{ await dlSummaryPdf(summaryRef,resultDownloadName); recordDownload('summary_downloaded','pdf'); showToast(t('dl.success')); }catch(e){showToast(e.message,false);}
                                            finally{setDownloading(null);}
                                        }},
                                        {icon:'article', label:t('dl.word'), badge:'DOC', disabled:!summary, onClick:()=>{dlSummaryWord(summary,resultDownloadName); recordDownload('summary_downloaded','doc'); showToast(t('dl.success'));}},
                                    ]}
                                />
                            </div>
                                </div>
                                <div className="hide-scrollbar min-h-0 flex-1 overflow-y-auto p-8 text-[#111111] dark:text-white">
	                            {summary ? (
	                                <div ref={summaryRef} dangerouslySetInnerHTML={{__html: simpleMd(summary)}}></div>
	                            ) : result.summary_skipped ? (
	                                <p className="text-sm italic text-[#666] dark:text-white/60">{t('edit.summarySkipped')}</p>
	                            ) : result.summary_status === 'failed' || result.summary_error ? (
	                                <div className="space-y-2 text-sm text-[#666] dark:text-white/60">
	                                    <p className="italic">{t('edit.summaryFailed')}</p>
	                                    {summaryFailureHint && (
	                                        <p className="rounded-[14px] border border-error/20 bg-error-container px-3 py-2 text-xs font-semibold leading-relaxed text-on-error-container">
	                                            {summaryFailureHint}
	                                        </p>
	                                    )}
	                                </div>
	                            ) : (
	                                <p className="text-sm italic text-[#666] dark:text-white/60">{t('edit.summaryPending')}</p>
	                            )}
                                </div>
                                <div className="border-t border-[#e4e0e0] bg-[#fbfbfb] px-4 py-3 dark:border-white/[0.12] dark:bg-white/[0.04]">
                                    <div className="flex flex-col gap-2">
                                        <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
                                        <div className="flex items-center gap-2">
                                            <SvgIcon name="verified" className="text-sm text-[#111111] dark:text-white"/>
                                            <span className="text-[10px] font-bold uppercase tracking-widest text-[#666] dark:text-white/60">{t('edit.confidence')}</span>
                                        </div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {summaryGenerationMeta.map((item) => (
                                                <span key={item.label} className="inline-flex min-h-7 items-center gap-1 rounded-[11px] border border-[#e4e0e0] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#666] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                                    <span className="text-[#8a8a8a] dark:text-white/40">{item.label}</span>
                                                    <span className="max-w-[16rem] truncate text-[#111111] dark:text-white" title={item.value}>{item.value}</span>
                                                </span>
                                            ))}
                                        </div>
                                        </div>
                                        {summaryReasonItems.length > 0 && (
                                            <div className="grid gap-1.5 md:grid-cols-3">
                                                {summaryReasonItems.map((item) => (
                                                    <p key={item.label} className="rounded-[11px] border border-[#e4e0e0] bg-white px-2.5 py-1.5 text-[11px] font-semibold leading-relaxed text-[#666] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/60">
                                                        <span className="mr-1 text-[#8a8a8a] dark:text-white/40">{item.label}</span>
                                                        <span>{item.value}</span>
                                                    </p>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                </main>
            </div>
        );
};

/* ═══════════════ Admin ═══════════════ */

export default Editor;
