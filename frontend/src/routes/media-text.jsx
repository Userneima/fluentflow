import {useEffect, useRef, useState} from 'react';
import {Link, useNavigate, useSearchParams} from 'react-router-dom';
import {
    DEFAULT_PROMPT_PRESET,
    presetDisplayLabel,
    resolveSystemPromptFromSettings,
} from '../lib/promptPresets.js';
import {
    azureSpeechMissingMessage,
    createTaskId,
    effectiveSttProvider,
    fileNameStem,
    fmtElapsed,
    fmtFileSize,
    friendlyTaskError,
    hasTranscriptResult,
    historyEntryToResult,
    isCloudSttConfigured,
    isCloudSttProvider,
    jobProgressLabel,
    jobToCurrentJob,
    larkExportRouteFromSettings,
    normalizeSttModel,
    resultToHistoryEntry,
    setGuestTrialTaskId,
    setGuestTrialToken,
    timeAgo,
    totalFileSizeMb,
    useApi,
    useApp,
    useAuth,
    useI18n,
    useSettings,
} from '../app/shared.jsx';
import SvgIcon from '../components/SvgIcon.jsx';

const mediaExts = /\.(mp4|mov|avi|mkv|wmv|flv|webm|m4v|mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;
const transcriptExts = /\.(srt|vtt|txt|md)$/i;
const audioExts = /\.(mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;

const platformItems = [
    {label: '抖音', tone: 'bg-[#111111] text-white', icon: 'douyin'},
    {label: 'Bilibili', tone: 'bg-[#00aeec] text-white', icon: 'bilibili'},
    {label: 'YouTube', tone: 'bg-[#ff0033] text-white', icon: 'youtube'},
    {label: '本地文件', tone: 'bg-[#efeeee] text-[#111111]', icon: 'local-file'},
];

const MediaText = () => {
    const {t, lang} = useI18n();
    const {guestMode, guestTrial} = useAuth();
    const {
        history,
        addToHistory,
        currentJob,
        setCurrentJob,
        setLastResult,
        setLastSourceFile,
        addLarkExport,
        runtimeConfig,
    } = useApp();
    const {
        processVideoSSE,
        enqueueProcessFiles,
        processGuestTrialFile,
        createVideoSourceJob,
        subscribeJobEvents,
        subscribeGuestTrialJobEvents,
        summarizeTranscriptFile,
        cancelGuestTrialJob,
        cancelJob,
        getJob,
        getCredentialsStatus,
        checkHealth,
    } = useApi();
    const {loadSettings} = useSettings();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const mode = searchParams.get('mode') === 'subtitle' ? 'subtitle' : 'media';
    const [sourceMode, setSourceMode] = useState('link');
    const [videoLinkInput, setVideoLinkInput] = useState('');
    const [uploadError, setUploadError] = useState(null);
    const [processingResult, setProcessingResult] = useState(null);
    const [submitting, setSubmitting] = useState(false);
    const fileInputRef = useRef(null);
    const subtitleInputRef = useRef(null);
    const abortRef = useRef(null);

    useEffect(() => { checkHealth(); }, []);
    useEffect(() => {
        if (mode === 'subtitle') setSourceMode('upload');
    }, [mode]);

    const buildAiOptions = (settings) => ({
        aiProvider: settings.aiProvider || 'deepseek',
        aiModel: settings.aiModel || null,
        systemPrompt: resolveSystemPromptFromSettings(settings) || null,
        noteMode: settings.noteMode || 'auto',
        promptPreset: settings.promptPreset || DEFAULT_PROMPT_PRESET,
        promptPresetLabel: presetDisplayLabel(settings.promptPreset || DEFAULT_PROMPT_PRESET, settings, lang),
        speakerDiarization: !!settings.speakerDiarization,
        sttProvider: effectiveSttProvider(settings, runtimeConfig),
    });

    const ensureCloudReady = async (sttProvider) => {
        if (guestMode) return true;
        if (!isCloudSttProvider(sttProvider)) return true;
        try {
            const status = await getCredentialsStatus();
            const configured = isCloudSttConfigured(sttProvider, status);
            if (configured) return true;
        } catch (_) {}
        setUploadError(azureSpeechMissingMessage(lang));
        return false;
    };

    const applyProgressEvent = (ev) => {
        setCurrentJob((prev) => prev ? {
            ...prev,
            stage: ev.stage,
            progress: ev.progress,
            sttProgress: ev.stt_progress ?? prev.sttProgress,
            transcribedSeconds: ev.transcribed_seconds ?? prev.transcribedSeconds,
            durationSeconds: ev.duration_seconds ?? prev.durationSeconds,
            sttElapsedSeconds: ev.stt_elapsed_seconds ?? prev.sttElapsedSeconds,
            sttStatus: ev.stt_status ?? prev.sttStatus,
            sttProvider: ev.stt_provider ?? prev.sttProvider,
            azureBatchAudioSizeMb: ev.elevenlabs_audio_size_mb ?? ev.azure_batch_audio_size_mb ?? prev.azureBatchAudioSizeMb,
        } : null);
        if (ev.stage === 'transcript_ready' && ev.result) {
            setLastResult(ev.result);
            setProcessingResult(ev.result);
        }
    };

    const settleResult = (result, {taskId, fileName, source = 'media'} = {}) => {
        const displayName = result?.title || result?.filename || fileName;
        setLastResult(result);
        setProcessingResult(result);
        setCurrentJob({taskId, fileName: displayName || fileName, stage: 'done', progress: 100});
        addToHistory(resultToHistoryEntry(result, {
            taskId,
            name: displayName || fileName,
            rawFilename: fileName,
            requestedNoteMode: loadSettings().noteMode || 'auto',
            source,
        }));
        const larkUrl = result?.lark_response?.url || null;
        if (larkUrl) addLarkExport({url: larkUrl, title: result.lark_doc_title || fileNameStem(displayName || fileName), timestamp: Date.now()});
        setTimeout(() => setCurrentJob((prev) => prev?.taskId === taskId ? null : prev), 3000);
    };

    const startMediaFiles = async (files) => {
        const selectedFiles = Array.from(files || []);
        if (selectedFiles.length === 0) return;
        if (!selectedFiles.every((file) => mediaExts.test(file.name))) {
            setUploadError(t('dash.fileError'));
            return;
        }
        if (guestMode && selectedFiles.length > 1) {
            setUploadError(lang === 'zh' ? '访客试用一次只能上传 1 个音视频文件。' : 'Guest trial accepts one audio/video file at a time.');
            return;
        }

        setUploadError(null);
        setProcessingResult(null);
        setLastResult(null);
        const settings = loadSettings();
        const sttModel = normalizeSttModel(settings.sttModel);
        const sttProvider = effectiveSttProvider(settings, runtimeConfig);
        if (!(await ensureCloudReady(sttProvider))) return;

        if (!guestMode && selectedFiles.length > 1) {
            setSubmitting(true);
            setLastSourceFile(null);
            setCurrentJob({
                taskId: null,
                fileName: lang === 'zh' ? `${selectedFiles.length} 个文件` : `${selectedFiles.length} files`,
                stage: 'upload',
                progress: 2,
                startedAt: Date.now(),
                sourceType: 'queue_upload',
                fileSizeMb: totalFileSizeMb(selectedFiles),
                queueTotal: selectedFiles.length,
                queueUpload: true,
            });
            try {
                await enqueueProcessFiles(selectedFiles, {
                    exportToLark: settings.exportToLark || false,
                    larkExportRoute: larkExportRouteFromSettings(settings),
                    larkViaCli: !!settings.larkViaCli,
                    ...buildAiOptions(settings),
                    skipSummary: !!settings.skipAiSummary,
                    sttProvider,
                    sttModel,
                    sttSpeed: settings.sttSpeed || 'balanced',
                    sttLanguage: 'auto',
                });
                navigate('/tasks', {state: {queueSubmittedAt: Date.now()}});
            } catch (err) {
                setUploadError(friendlyTaskError(err.message || 'Queue failed.', lang));
                setCurrentJob(null);
            } finally {
                setSubmitting(false);
            }
            return;
        }

        const file = selectedFiles[0];
        const taskId = createTaskId();
        const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
        setLastSourceFile(file);
        const ac = new AbortController();
        abortRef.current = ac;
        setSubmitting(true);
        setCurrentJob({
            taskId,
            fileName: file.name,
            stage: 'upload',
            progress: 2,
            startedAt: Date.now(),
            sourceType: audioExts.test(file.name) ? 'audio' : 'video',
            fileSizeMb,
            guestTrial: guestMode,
            sttProvider,
            sttModel,
            sttSpeed: settings.sttSpeed || 'balanced',
            sttLanguage: 'auto',
            skipSummary: guestMode ? false : !!settings.skipAiSummary,
            exportToLark: guestMode ? false : !!settings.exportToLark,
            noteMode: settings.noteMode || 'auto',
        });

        try {
            if (guestMode) {
                const guestConfig = guestTrial || runtimeConfig.guestTrial || {};
                const fileLimit = Number(guestConfig.file_limit_mb || 150);
                if (fileSizeMb > fileLimit) {
                    setUploadError(lang === 'zh' ? `访客试用支持 ${fileLimit} MB 以内的单个音视频文件。` : `Guest trial supports one file up to ${fileLimit} MB.`);
                    setCurrentJob(null);
                    return;
                }
                const data = await processGuestTrialFile(file, {
                    ...buildAiOptions(settings),
                    sttProvider,
                    sttModel,
                    sttLanguage: 'auto',
                    noteMode: settings.noteMode || 'auto',
                }, ac.signal);
                setGuestTrialToken(data.guest_token);
                setGuestTrialTaskId(data.task_id);
                setCurrentJob((prev) => prev ? {...prev, taskId: data.task_id, guestToken: data.guest_token, resume: true} : prev);
                const result = await subscribeGuestTrialJobEvents(data.task_id, data.guest_token, applyProgressEvent, ac.signal);
                settleResult(result, {taskId: data.task_id, fileName: file.name});
                navigate('/editor');
                return;
            }

            let openedTranscript = false;
            const result = await processVideoSSE(file, {
                taskId,
                sourceLastModifiedMs: file.lastModified || null,
                exportToLark: settings.exportToLark || false,
                larkExportRoute: larkExportRouteFromSettings(settings),
                larkViaCli: !!settings.larkViaCli,
                title: file.name.replace(/\.[^/.]+$/, ''),
                ...buildAiOptions(settings),
                skipSummary: !!settings.skipAiSummary,
                sttProvider,
                sttModel,
                sttSpeed: settings.sttSpeed || 'balanced',
                sttLanguage: 'auto',
            }, (ev) => {
                applyProgressEvent(ev);
                if (ev.stage === 'transcript_ready' && ev.result && !openedTranscript) {
                    openedTranscript = true;
                    setLastResult(ev.result);
                    setProcessingResult(ev.result);
                    navigate('/editor');
                }
            }, ac.signal);
            settleResult(result, {taskId, fileName: file.name});
        } catch (err) {
            if (err.name !== 'AbortError') {
                setUploadError(err.message || 'Processing failed.');
                addToHistory({id: Date.now(), taskId, name: file.name, timestamp: Date.now(), durationMin: 0, status: 'failed'});
            }
            setCurrentJob(null);
        } finally {
            if (abortRef.current === ac) abortRef.current = null;
            setSubmitting(false);
        }
    };

    const handleVideoLinkSubmit = async () => {
        if (guestMode) {
            setUploadError(lang === 'zh' ? '访客试用暂不支持链接抓取，请直接上传一个音视频文件。' : 'Guest trial does not support link fetching. Upload a media file instead.');
            return;
        }
        const input = videoLinkInput.trim();
        if (!input) {
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
        const ac = new AbortController();
        abortRef.current = ac;
        setSubmitting(true);
        try {
            const data = await createVideoSourceJob(input, {
                exportToLark: settings.exportToLark || false,
                larkExportRoute: larkExportRouteFromSettings(settings),
                larkViaCli: !!settings.larkViaCli,
                ...buildAiOptions(settings),
                skipSummary: !!settings.skipAiSummary,
                sttProvider,
                sttModel,
                sttSpeed: settings.sttSpeed || 'balanced',
                sttLanguage: 'auto',
            }, ac.signal);
            const job = data?.job || {};
            if (job.task_id) {
                setCurrentJob({
                    ...jobToCurrentJob({...job, progress: job.progress ?? 2, created_at: job.created_at || new Date().toISOString()}),
                    sourceType: 'video_link',
                    resume: true,
                    skipSummary: !!settings.skipAiSummary,
                    exportToLark: !!settings.exportToLark,
                    noteMode: settings.noteMode || 'auto',
                    sttProvider,
                    sttModel,
                    sttSpeed: settings.sttSpeed || 'balanced',
                    sttLanguage: 'auto',
                });
                setVideoLinkInput('');
                subscribeJobEvents(job.task_id, applyProgressEvent, ac.signal, {sttProvider})
                    .then((result) => {
                        settleResult(result, {taskId: job.task_id, fileName: job.source_filename || input.slice(0, 80), source: 'video_link'});
                        navigate('/editor');
                    })
                    .catch((err) => {
                        if (err.name !== 'AbortError') setUploadError(err.message || 'Video link task failed.');
                    })
                    .finally(() => {
                        if (abortRef.current === ac) abortRef.current = null;
                        setSubmitting(false);
                    });
                return;
            }
        } catch (err) {
            setUploadError(err.message || 'Video link fetch failed.');
        }
        if (abortRef.current === ac) abortRef.current = null;
        setSubmitting(false);
    };

    const handleSubtitleSelect = async (eventOrFiles) => {
        const file = Array.isArray(eventOrFiles)
            ? eventOrFiles[0]
            : eventOrFiles?.target?.files?.[0];
        if (subtitleInputRef.current) subtitleInputRef.current.value = '';
        if (!file) return;
        if (guestMode) {
            setUploadError(lang === 'zh' ? '访客试用暂不支持字幕导入，请上传一个音视频文件。' : 'Guest trial does not support transcript imports. Upload media instead.');
            return;
        }
        if (!transcriptExts.test(file.name)) {
            setUploadError(t('dash.subtitleFileError'));
            return;
        }
        setUploadError(null);
        setProcessingResult(null);
        setLastResult(null);
        setLastSourceFile(null);

        const ac = new AbortController();
        abortRef.current = ac;
        const taskId = createTaskId();
        const settings = loadSettings();
        const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
        setSubmitting(true);
        setCurrentJob({
            taskId,
            fileName: file.name,
            stage: 'summary',
            progress: 20,
            startedAt: Date.now(),
            sourceType: 'transcript_file',
            fileSizeMb,
            skipSummary: false,
            exportToLark: false,
            noteMode: settings.noteMode || 'auto',
        });
        try {
            const result = await summarizeTranscriptFile(file, {taskId, ...buildAiOptions(settings), skipSummary: false}, ac.signal);
            settleResult(result, {taskId, fileName: file.name, source: 'transcript_file'});
            navigate('/editor');
        } catch (err) {
            if (err.name !== 'AbortError') {
                setUploadError(err.message || 'Summary generation failed.');
                addToHistory({id: Date.now(), taskId, name: file.name, timestamp: Date.now(), durationMin: 0, status: 'failed'});
            }
            setCurrentJob(null);
        } finally {
            if (abortRef.current === ac) abortRef.current = null;
            setSubmitting(false);
        }
    };

    const handleMediaInput = async (eventOrFiles) => {
        const files = Array.isArray(eventOrFiles)
            ? eventOrFiles
            : Array.from(eventOrFiles?.target?.files || []);
        if (fileInputRef.current) fileInputRef.current.value = '';
        await startMediaFiles(files);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        const files = Array.from(e.dataTransfer.files || []);
        if (files.length === 0) return;
        if (mode === 'subtitle' || (files.length === 1 && transcriptExts.test(files[0].name))) {
            handleSubtitleSelect(files);
        } else {
            startMediaFiles(files);
        }
    };

    const handleCancel = async () => {
        if (abortRef.current) {
            abortRef.current.abort();
            abortRef.current = null;
        }
        if (currentJob?.guestTrial && currentJob.taskId) {
            try { await cancelGuestTrialJob(currentJob.taskId, currentJob.guestToken); } catch (_) {}
        }
        if (currentJob?.taskId && !currentJob?.guestTrial) {
            try { await cancelJob(currentJob.taskId, {sttProvider: currentJob.sttProvider}); } catch (_) {}
        }
        setCurrentJob(null);
        setSubmitting(false);
    };

    const activeProgress = Math.max(0, Math.min(100, Number(currentJob?.progress) || 0));
    const activeStageLabel = currentJob?.stage ? t(`status.${currentJob.stage}`) : '';
    const recent = history.slice(0, 6);

    const openRecentTask = async (item) => {
        if (!item.taskId) {
            if (item.status === 'completed') {
                setLastResult(historyEntryToResult(item));
                navigate('/editor');
            } else {
                navigate('/tasks');
            }
            return;
        }
        try {
            const job = await getJob(item.taskId);
            if (job?.result && hasTranscriptResult(job.result)) {
                setLastResult(job.result);
                navigate('/editor');
                return;
            }
        } catch (_) {}
        if (item.status === 'completed') {
            setLastResult(historyEntryToResult(item));
            navigate('/editor');
        } else {
            navigate('/tasks');
        }
    };

    return (
        <main className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <section className="mx-auto h-dvh max-w-[1280px] overflow-y-auto px-8 py-9 hide-scrollbar">
                <input ref={fileInputRef} type="file" multiple accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus" onChange={handleMediaInput} className="hidden"/>
                <input ref={subtitleInputRef} type="file" accept=".srt,.vtt,.txt,.md,text/plain,text/markdown" onChange={handleSubtitleSelect} className="hidden"/>

                <div className="mb-7 flex flex-wrap items-center justify-center gap-3">
                    <span className="text-sm font-bold text-[#8a8a8a] dark:text-white/40">{lang === 'zh' ? '目前支持：' : 'Supported:'}</span>
                    {platformItems.map((item) => (
                        <span key={item.label} className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm font-bold text-[#666] dark:text-white/55">
                            <span className={`flex size-7 items-center justify-center rounded-[8px] ${item.tone}`}>
                                <SvgIcon name={item.icon} className="size-4"/>
                            </span>
                            {item.label}
                        </span>
                    ))}
                </div>

                <section
                    className="relative overflow-hidden rounded-[24px] border border-[#dedada] bg-white p-8 shadow-[0_26px_70px_-46px_rgba(17,17,17,.5)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none"
                    onDrop={handleDrop}
                    onDragOver={(e) => e.preventDefault()}
                >
                    <div className="pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-[radial-gradient(circle_at_20%_30%,rgba(151,231,211,.38),transparent_0_24%,transparent_48%)]"/>
                    <div className="relative z-10">
                        <div className="mb-7 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                            <div className="inline-flex rounded-[18px] border border-[#dedada] bg-[#f4f3f3] p-1 dark:border-white/[0.12] dark:bg-white/[0.08]">
                                {['media', 'subtitle'].map((item) => (
                                    <button
                                        key={item}
                                        type="button"
                                        onClick={() => setSearchParams({mode: item})}
                                        className={`h-10 rounded-[14px] px-4 text-sm font-extrabold transition ${mode === item ? 'bg-white text-[#111111] shadow-sm dark:bg-white/[0.16] dark:text-white' : 'text-[#777] hover:text-[#111111] dark:text-white/55 dark:hover:text-white'}`}
                                    >
                                        {item === 'media' ? (lang === 'zh' ? '视频生成笔记' : 'Media notes') : (lang === 'zh' ? '字幕生成笔记' : 'Subtitle notes')}
                                    </button>
                                ))}
                            </div>
                            <Link to="/tasks" className="inline-flex h-11 items-center justify-center rounded-[16px] bg-[#efeeee] px-4 text-sm font-extrabold text-[#111111] hover:bg-[#e8e5e5] dark:bg-white/[0.12] dark:text-white dark:hover:bg-white/[0.18]">
                                {t('dash.viewTasks')}
                            </Link>
                        </div>

                        {mode === 'media' && (
                            <div className="space-y-5">
                                <div className="inline-flex rounded-[18px] border border-[#dedada] bg-[#f4f3f3] p-1 dark:border-white/[0.12] dark:bg-white/[0.08]">
                                    {['link', 'upload'].map((item) => (
                                        <button
                                            key={item}
                                            type="button"
                                            onClick={() => setSourceMode(item)}
                                            className={`h-10 rounded-[14px] px-4 text-sm font-extrabold transition ${sourceMode === item ? 'bg-white text-[#111111] shadow-sm dark:bg-white/[0.16] dark:text-white' : 'text-[#777] hover:text-[#111111] dark:text-white/55 dark:hover:text-white'}`}
                                        >
                                            {item === 'link' ? (lang === 'zh' ? '链接' : 'Link') : (lang === 'zh' ? '本地上传' : 'Upload')}
                                        </button>
                                    ))}
                                </div>

                                {sourceMode === 'link' ? (
                                    <div>
                                        <label className="mb-2 block text-sm font-extrabold text-[#111111] dark:text-white">{lang === 'zh' ? '视频或播客链接' : 'Video or podcast link'}</label>
                                        <textarea
                                            value={videoLinkInput}
                                            onChange={(e) => setVideoLinkInput(e.target.value)}
                                            className="min-h-[116px] w-full resize-none rounded-[18px] border border-[#dedada] bg-[#fbfbfb] px-5 py-4 text-[15px] font-semibold text-[#111111] outline-none placeholder:text-[#aaa] focus:border-[#111111] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/[0.4]"
                                            placeholder={lang === 'zh' ? '粘贴抖音、Bilibili、YouTube 或视频直链' : 'Paste a Douyin, Bilibili, YouTube, or direct video link'}
                                        />
                                    </div>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={() => fileInputRef.current?.click()}
                                        className="flex min-h-[180px] w-full flex-col items-center justify-center rounded-[20px] border border-dashed border-[#cfcaca] bg-[#fbfbfb] px-6 text-center transition hover:border-[#111111] hover:bg-white dark:border-white/[0.16] dark:bg-white/[0.04] dark:hover:border-white/[0.4] dark:hover:bg-white/[0.08]"
                                    >
                                        <SvgIcon name="upload-file" className="mb-3 size-8 text-[#111111] dark:text-white"/>
                                        <span className="text-lg font-extrabold">{lang === 'zh' ? '拖放或选择音视频文件' : 'Drop or choose media files'}</span>
                                        <span className="mt-2 text-sm font-semibold text-[#777] dark:text-white/55">MP4 / MOV / MP3 / WAV / M4A</span>
                                    </button>
                                )}
                            </div>
                        )}

                        {mode === 'subtitle' && (
                            <button
                                type="button"
                                onClick={() => subtitleInputRef.current?.click()}
                                className="flex min-h-[220px] w-full flex-col items-center justify-center rounded-[20px] border border-dashed border-[#cfcaca] bg-[#fbfbfb] px-6 text-center transition hover:border-[#111111] hover:bg-white dark:border-white/[0.16] dark:bg-white/[0.04] dark:hover:border-white/[0.4] dark:hover:bg-white/[0.08]"
                            >
                                <SvgIcon name="subtitles" className="mb-3 size-8 text-[#111111] dark:text-white"/>
                                <span className="text-lg font-extrabold">{lang === 'zh' ? '拖放或选择字幕 / 文本文件' : 'Drop or choose subtitle files'}</span>
                                <span className="mt-2 text-sm font-semibold text-[#777] dark:text-white/55">SRT / VTT / TXT / MD</span>
                            </button>
                        )}

                        <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-center md:justify-end">
                            {mode === 'media' && sourceMode === 'upload' && (
                                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={submitting} className="inline-flex h-12 items-center justify-center gap-2 rounded-[16px] border border-[#dedada] bg-white px-5 text-sm font-extrabold text-[#111111] hover:bg-[#f4f3f3] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.12]">
                                    <SvgIcon name="upload-file" className="size-4"/>
                                    {lang === 'zh' ? '选择文件' : 'Choose files'}
                                </button>
                            )}
                            {mode === 'subtitle' && (
                                <button type="button" onClick={() => subtitleInputRef.current?.click()} disabled={submitting} className="inline-flex h-12 items-center justify-center gap-2 rounded-[16px] border border-[#dedada] bg-white px-5 text-sm font-extrabold text-[#111111] hover:bg-[#f4f3f3] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.12]">
                                    <SvgIcon name="subtitles" className="size-4"/>
                                    {lang === 'zh' ? '选择字幕文件' : 'Choose subtitle file'}
                                </button>
                            )}
                            {mode === 'media' && sourceMode === 'link' && (
                                <button type="button" onClick={handleVideoLinkSubmit} disabled={submitting} className="inline-flex h-12 items-center justify-center gap-2 rounded-[16px] bg-[#111111] px-7 text-sm font-extrabold text-white hover:bg-[#2a2a2a] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-[#111111] dark:hover:bg-[#e8e8e8]">
                                    {submitting ? <SvgIcon name="sync" className="size-4 animate-spin"/> : <SvgIcon name="arrow-right" className="size-4"/>}
                                    {lang === 'zh' ? '开始生成笔记' : 'Start'}
                                </button>
                            )}
                        </div>

                        {uploadError && <div className="mt-5 rounded-[16px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300">{uploadError}</div>}
                        {processingResult && <div className="mt-5 rounded-[16px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300">{t('dash.done')} <button type="button" onClick={() => navigate('/editor')} className="underline hover:no-underline">{t('dash.viewEditor')}</button></div>}
                    </div>
                </section>

                {currentJob && currentJob.stage !== 'done' && (
                    <section className="mt-6 rounded-[22px] border border-[#dedada] bg-white p-5 dark:border-white/[0.12] dark:bg-white/[0.06]">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div className="min-w-0">
                                <p className="text-xs font-extrabold text-[#777] dark:text-white/55">{lang === 'zh' ? '当前任务' : 'Active task'}</p>
                                <h2 className="mt-1 truncate text-xl font-extrabold">{currentJob.fileName}</h2>
                                <p className="mt-1 text-sm font-semibold text-[#666] dark:text-white/55">{activeStageLabel} · {jobProgressLabel(currentJob, t)}</p>
                            </div>
                            <button type="button" onClick={handleCancel} className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] border border-red-200 bg-red-50 px-3 text-xs font-extrabold text-red-600 hover:bg-red-100 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300 dark:hover:bg-red-400/20">
                                <SvgIcon name="cancel" className="size-4"/>
                                {t('dash.cancel')}
                            </button>
                        </div>
                        <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12]">
                            <div className="h-full rounded-full bg-[#111111] transition-all duration-700 dark:bg-white" style={{width: `${activeProgress}%`}}/>
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                            <div className="rounded-[16px] bg-[#f4f3f3] p-3 dark:bg-white/[0.08]">
                                <p className="text-[11px] font-bold text-[#777] dark:text-white/55">{t('dash.fileSize')}</p>
                                <p className="mt-1 text-sm font-extrabold">{fmtFileSize(currentJob.fileSizeMb)}</p>
                            </div>
                            <div className="rounded-[16px] bg-[#f4f3f3] p-3 dark:bg-white/[0.08]">
                                <p className="text-[11px] font-bold text-[#777] dark:text-white/55">STT</p>
                                <p className="mt-1 truncate text-sm font-extrabold">{currentJob.sttModel || '-'}</p>
                            </div>
                        </div>
                    </section>
                )}

                <section className="mt-7 rounded-[24px] border border-[#dedada] bg-white p-6 shadow-[0_18px_44px_-38px_rgba(17,17,17,.45)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                    <div className="mb-5 flex items-center justify-between gap-4">
                        <div>
                            <h2 className="text-[22px] font-extrabold">{lang === 'zh' ? '最近任务' : 'Recent tasks'}</h2>
                            <p className="mt-1 text-sm font-semibold text-[#777] dark:text-white/55">{lang === 'zh' ? '视频和字幕任务都会显示在这里。' : 'Media and subtitle tasks appear here.'}</p>
                        </div>
                        <Link to="/tasks" className="rounded-full bg-[#efeeee] px-4 py-2 text-xs font-extrabold text-[#111111] hover:bg-[#e8e5e5] dark:bg-white/[0.12] dark:text-white dark:hover:bg-white/[0.18]">{t('dash.viewAll')}</Link>
                    </div>
                    {recent.length === 0 ? (
                        <div className="rounded-[18px] border border-dashed border-[#dedada] bg-[#fbfbfb] px-4 py-12 text-center text-sm font-semibold text-[#999] dark:border-white/[0.12] dark:bg-white/[0.04] dark:text-white/40">
                            {lang === 'zh' ? '还没有视频或字幕任务。' : 'No media or subtitle tasks yet.'}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                            {recent.map((item) => (
                                <button key={item.id} type="button" onClick={() => openRecentTask(item)} className="min-w-0 rounded-[18px] bg-[#f4f3f3] p-4 text-left transition hover:bg-[#efeeee] dark:bg-white/[0.08] dark:hover:bg-white/[0.12]">
                                    <div className="mb-2 flex items-center justify-between gap-2">
                                        <h3 className="truncate text-sm font-extrabold">{item.name}</h3>
                                        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-[#666] dark:bg-white/[0.16] dark:text-white/70">{t(item.status === 'completed' ? 'dash.statusCompleted' : item.status === 'processing' ? 'dash.statusProcessing' : 'dash.statusFailed')}</span>
                                    </div>
                                    <p className="text-xs font-semibold text-[#777] dark:text-white/55">{timeAgo(item.timestamp, t)}{item.durationMin > 0 && ` · ${item.durationMin} ${t('dash.minUnit')}`}</p>
                                </button>
                            ))}
                        </div>
                    )}
                </section>
            </section>
        </main>
    );
};

export default MediaText;
