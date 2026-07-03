import {useEffect, useRef, useState} from 'react';
import {Link, useNavigate, useSearchParams} from 'react-router-dom';
import {XCircle} from 'lucide-react';
import {
    DEFAULT_PROMPT_PRESET,
    presetDisplayLabel,
    resolveSystemPromptFromSettings,
} from '../lib/promptPresets.js';
import {
    cacheJobRecord,
    cloudSttMissingMessage,
    createTaskId,
    effectiveSttProvider,
    fileNameStem,
    fmtFileSize,
    friendlyTaskError,
    hasTranscriptResult,
    historyEntryToResult,
    isCloudSttConfigured,
    isCloudSttProvider,
    jobToCurrentJob,
    jobToHistoryEntry,
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
    videoLinkDisplayTitle,
} from '../app/shared.jsx';
import {
    queueUploadItemsFromFiles,
    queueUploadItemsFromQueuedResponse,
} from '../lib/queueUpload.js';
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
    const {authMode, guestMode, guestTrial, user} = useAuth();
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
        subscribeGuestTrialJobEvents,
        summarizeTranscriptFile,
        cancelGuestTrialJob,
        cancelJob,
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
    const cacheAccountId = authMode === 'accounts' ? user?.id : 'local';

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
        setUploadError(cloudSttMissingMessage(lang));
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

    const persistFailedVideoLinkJob = (job, rawMessage, input) => {
        const taskId = job?.task_id;
        const errorText = friendlyTaskError(rawMessage || job?.error_reason || 'Video link task failed.', lang);
        if (!taskId) return errorText;
        const now = new Date().toISOString();
        const displayTitle = job?.metadata?.display_title || job?.source_filename || videoLinkDisplayTitle(input, lang);
        const failedJob = cacheJobRecord(cacheAccountId, {
            ...job,
            task_id: taskId,
            status: 'failed',
            task_state: 'failed',
            stage: 'failed',
            progress: 100,
            source_type: job?.source_type || 'video_link',
            source_filename: job?.source_filename || displayTitle || input.slice(0, 80),
            error_reason: errorText,
            metadata: {
                ...(job?.metadata || {}),
                display_title: displayTitle,
                raw_input: input,
            },
            created_at: job?.created_at || now,
            updated_at: now,
        });
        if (failedJob) addToHistory(jobToHistoryEntry(failedJob));
        setCurrentJob((prev) => prev?.taskId === taskId ? null : prev);
        return errorText;
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
            const provisionalQueueItems = queueUploadItemsFromFiles(selectedFiles);
            setCurrentJob({
                taskId: null,
                fileName: lang === 'zh' ? `${selectedFiles.length} 个文件` : `${selectedFiles.length} files`,
                stage: 'upload',
                progress: 2,
                startedAt: Date.now(),
                sourceType: 'queue_upload',
                fileSizeMb: totalFileSizeMb(selectedFiles),
                queueTotal: selectedFiles.length,
                queueItems: provisionalQueueItems,
                queueUpload: true,
            });
            navigate('/agent');
            try {
                const data = await enqueueProcessFiles(selectedFiles, {
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
                const queueItems = queueUploadItemsFromQueuedResponse(data?.queued, provisionalQueueItems);
                setCurrentJob({
                    taskId: null,
                    fileName: lang === 'zh' ? `${selectedFiles.length} 个文件` : `${selectedFiles.length} files`,
                    stage: 'queued',
                    progress: 100,
                    startedAt: Date.now(),
                    sourceType: 'queue_upload',
                    fileSizeMb: totalFileSizeMb(selectedFiles),
                    queueTotal: selectedFiles.length,
                    queueItems,
                    queueUpload: true,
                    queueSubmitted: true,
                });
                navigate('/agent', {replace: true, state: {queueSubmittedAt: Date.now()}});
            } catch (err) {
                setCurrentJob(null);
                navigate('/agent', {
                    replace: true,
                    state: {queueSubmitError: friendlyTaskError(err.message || 'Queue failed.', lang)},
                });
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
                abortRef.current = null;
                setSubmitting(false);
                navigate('/agent', {state: {job}});
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
        const confirmText = lang === 'zh'
            ? '取消当前正在上传或处理的任务？任务会中止，完整结果不会生成；如果任务已经进入队列，可到处理记录查看已取消记录。这不是删除历史记录。'
            : 'Cancel the current upload or processing task? The task will stop and a complete result will not be created. If it already entered the queue, you can check the cancelled record in Processing records. This does not delete history.';
        if (!window.confirm(confirmText)) return;
        if (abortRef.current) {
            abortRef.current.abort();
            abortRef.current = null;
        }
        if (currentJob?.guestTrial && currentJob.taskId) {
            try { await cancelGuestTrialJob(currentJob.taskId, currentJob.guestToken); } catch (err) { setUploadError(friendlyTaskError(err.message || String(err), lang)); }
        }
        if (currentJob?.taskId && !currentJob?.guestTrial) {
            try { await cancelJob(currentJob.taskId, {sttProvider: currentJob.sttProvider}); } catch (err) { setUploadError(friendlyTaskError(err.message || String(err), lang)); }
        }
        setCurrentJob(null);
        setSubmitting(false);
    };

    const recent = history.slice(0, 6);

    const openRecentTask = async (item) => {
        const cachedResult = historyEntryToResult(item);
        const openCachedEditor = () => {
            if (item.status !== 'completed' || !hasTranscriptResult(cachedResult)) return false;
            setLastResult(cachedResult);
            navigate('/editor');
            return true;
        };
        if (openCachedEditor()) return;
        if (!item.taskId) return;
        navigate('/agent', {state: {job: item}});
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
                    className="relative overflow-hidden rounded-[24px] border border-[#dedada] bg-white p-8 shadow-[0_26px_70px_-46px_rgba(17,17,17,.5)] dark:border-white/[0.12] dark:bg-[#1d1f22] dark:shadow-none"
                    onDrop={handleDrop}
                    onDragOver={(e) => e.preventDefault()}
                >
                    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(0,174,236,.14),transparent_32%),radial-gradient(circle_at_82%_10%,rgba(255,0,51,.08),transparent_28%),radial-gradient(circle_at_44%_105%,rgba(151,231,211,.12),transparent_34%)] dark:bg-[radial-gradient(circle_at_18%_14%,rgba(0,174,236,.18),transparent_34%),radial-gradient(circle_at_82%_10%,rgba(255,0,51,.12),transparent_30%),radial-gradient(circle_at_42%_108%,rgba(151,231,211,.12),transparent_36%)]"/>
                    <div className="pointer-events-none absolute inset-0 bg-white/72 dark:bg-[#1d1f22]/78"/>
                    <div className="relative z-10">
                        <div className="mb-7 flex items-center justify-between gap-3">
                            <div className="inline-flex min-w-0 shrink rounded-[18px] border border-[#dedada] bg-[#f4f3f3] p-1 dark:border-white/[0.12] dark:bg-white/[0.08]">
                                {['media', 'subtitle'].map((item) => (
                                    <button
                                        key={item}
                                        type="button"
                                        onClick={() => setSearchParams({mode: item})}
                                        className={`h-10 min-w-0 whitespace-nowrap rounded-[14px] px-3 text-[13px] font-extrabold transition sm:px-4 sm:text-sm ${mode === item ? 'bg-white text-[#111111] shadow-sm dark:bg-white/[0.16] dark:text-white' : 'text-[#777] hover:text-[#111111] dark:text-white/55 dark:hover:text-white'}`}
                                    >
                                        {item === 'media' ? (lang === 'zh' ? '视频生成笔记' : 'Media notes') : (lang === 'zh' ? '字幕生成笔记' : 'Subtitle notes')}
                                    </button>
                                ))}
                            </div>
                            <Link to="/agent" className="inline-flex h-11 shrink-0 items-center justify-center whitespace-nowrap rounded-[16px] bg-[#efeeee] px-4 text-sm font-extrabold text-[#111111] hover:bg-[#e8e5e5] dark:bg-white/[0.12] dark:text-white dark:hover:bg-white/[0.18]">
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

                {currentJob && currentJob.stage !== 'done' && currentJob.sourceType !== 'video_link' && (
                    <section className="mt-6 rounded-[22px] border border-[#dedada] bg-white p-5 dark:border-white/[0.12] dark:bg-white/[0.06]">
                        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div className="min-w-0">
                                <p className="text-xs font-extrabold text-[#777] dark:text-white/55">{lang === 'zh' ? '当前任务' : 'Active task'}</p>
                                <h2 className="mt-1 truncate text-xl font-extrabold">{currentJob.fileName}</h2>
                                <p className="mt-1 text-sm font-semibold text-[#666] dark:text-white/55">{t(`status.${currentJob.stage}`)}</p>
                            </div>
                            <button type="button" onClick={handleCancel} className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] border border-red-200 bg-red-50 px-3 text-xs font-extrabold text-red-600 hover:bg-red-100 dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-300 dark:hover:bg-red-400/20">
                                <XCircle className="size-4" strokeWidth={2.15}/>
                                {t('dash.cancel')}
                            </button>
                        </div>
                        <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12]">
                            <div className="h-full rounded-full bg-[#111111] transition-all duration-700 dark:bg-white" style={{width: `${Math.max(0, Math.min(100, Number(currentJob?.progress) || 0))}%`}}/>
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
                            <h2 className="text-[22px] font-extrabold">{t('dash.recent')}</h2>
                            <p className="mt-1 text-sm font-semibold text-[#777] dark:text-white/55">{lang === 'zh' ? '最近完成和处理中任务会显示在这里。' : 'Recent completed and active tasks appear here.'}</p>
                        </div>
                        <Link to="/agent" className="rounded-full bg-[#efeeee] px-4 py-2 text-xs font-extrabold text-[#111111] hover:bg-[#e8e5e5] dark:bg-white/[0.12] dark:text-white dark:hover:bg-white/[0.18]">{t('dash.viewAll')}</Link>
                    </div>
                    {recent.length === 0 ? (
                        <div className="rounded-[18px] border border-dashed border-[#dedada] bg-[#fbfbfb] px-4 py-12 text-center text-sm font-semibold text-[#999] dark:border-white/[0.12] dark:bg-white/[0.04] dark:text-white/40">
                            {t('dash.noActivity')}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                            {recent.map((item) => (
                                <button key={item.id} type="button" onClick={() => openRecentTask(item)} className="min-w-0 rounded-[18px] bg-[#f4f3f3] p-4 text-left transition hover:bg-[#efeeee] dark:bg-white/[0.08] dark:hover:bg-white/[0.12]">
                                    <div className="mb-2 flex items-center justify-between gap-2">
                                        <h3 className="min-w-0 flex-1 truncate text-sm font-extrabold">{item.name}</h3>
                                        <span className="inline-flex shrink-0 whitespace-nowrap rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-[#666] dark:bg-white/[0.16] dark:text-white/70">{t(item.status === 'completed' ? 'dash.statusCompleted' : item.status === 'processing' ? 'dash.statusProcessing' : 'dash.statusFailed')}</span>
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
