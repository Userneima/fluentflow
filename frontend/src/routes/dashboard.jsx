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
import {
    azureSpeechMissingMessage,
    clearGuestTrialSession,
    compactDisplayFilename,
    createTaskId,
    DEFAULT_STT_MODEL,
    effectiveSttProvider,
    fileNameStem,
    fmtElapsed,
    fmtFileSize,
    fmtSttRelative,
    getGuestTrialTaskId,
    getGuestTrialToken,
    friendlyTaskError,
    hasTranscriptResult,
    isAzureBatchConfigured,
    isAzureCloudProvider,
    isAzureSpeechConfigured,
    isLocalHistoryResult,
    isSttProgressUnmeasured,
    historyEntryToResult,
    jobDisplayTitle,
    jobToCurrentJob,
    jobToHistoryEntry,
    larkExportRouteFromSettings,
    noteModeLabel,
    normalizeSttModel,
    normalizeSttProvider,
    pickTranscriptSegments,
    jobProgressLabel,
    resultToHistoryEntry,
    resultDisplayTitle,
    setGuestTrialTaskId,
    setGuestTrialToken,
    sttProgressFraction,
    sttStatusLabel,
    timeAgo,
    totalFileSizeMb,
    useApi,
    useApp,
    useAuth,
    useI18n,
    useSettings,
} from '../app/shared.jsx';

const Dashboard = () => {
    const {t, lang} = useI18n();
    const {guestMode, guestTrial} = useAuth();
    const {history, addToHistory, currentJob, setCurrentJob, setLastResult, setLastSourceFile, stats, addLarkExport, runtimeConfig} = useApp();
            const [uploadError, setUploadError] = useState(null);
            const [processingResult, setProcessingResult] = useState(null);
            const fileInputRef = useRef(null);
            const subtitleInputRef = useRef(null);
    const {processVideoSSE, enqueueProcessFiles, processGuestTrialFile, getGuestTrialJob, subscribeGuestTrialJobEvents, cancelGuestTrialJob, createVideoSourceJob, subscribeJobEvents, summarizeTranscriptFile, recordEvent, checkHealth, getJob, getCredentialsStatus} = useApi();
    const {loadSettings} = useSettings();
            const navigate = useNavigate();
    const abortRef = useRef(null);
    const currentTaskRef = useRef(null);
    const settledJobRef = useRef(new Set());
    const [now, setNow] = useState(Date.now());
    const [videoLinkInput, setVideoLinkInput] = useState('');
    const [videoLinkSubmitting, setVideoLinkSubmitting] = useState(false);
    const [queueSubmitting, setQueueSubmitting] = useState(false);

    useEffect(() => { checkHealth(); }, []);
    useEffect(() => {
        if(!currentJob || currentJob.stage === 'done') return;
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [currentJob?.taskId, currentJob?.stage]);

    const handleCancel = async () => {
        const task = currentTaskRef.current;
        if(task){
            recordEvent({
                event_name: "task_cancelled",
                task_id: task.taskId,
                source_type: task.sourceType,
                source_filename: task.fileName,
                source_file_size_mb: task.fileSizeMb,
                stage: currentJob?.stage || "cancelled",
                success: false,
                metadata: {trigger: "user_cancel"},
            });
        }
        if(abortRef.current){ abortRef.current.abort(); abortRef.current=null; }
        if(currentJob?.guestTrial && currentJob.taskId) {
            try { await cancelGuestTrialJob(currentJob.taskId, currentJob.guestToken || getGuestTrialToken()); } catch(_) {}
        }
        currentTaskRef.current = null;
        setCurrentJob(null);
    };

    const buildAiOptions = (settings) => ({
        aiProvider: settings.aiProvider||'deepseek',
        aiModel: settings.aiModel||null,
        systemPrompt: resolveSystemPromptFromSettings(settings)||null,
        noteMode: settings.noteMode||'auto',
        promptPreset: settings.promptPreset||DEFAULT_PROMPT_PRESET,
        promptPresetLabel: presetDisplayLabel(settings.promptPreset||DEFAULT_PROMPT_PRESET, settings, lang),
        speakerDiarization: !!settings.speakerDiarization,
        sttProvider: effectiveSttProvider(settings, runtimeConfig),
    });

    const openHistoryEntry = async (h) => {
        if(!h.taskId) {
            if(h.status==='completed'){ setLastResult(historyEntryToResult(h)); navigate('/editor'); }
            return;
        }
        try {
            const job = await getJob(h.taskId);
            if(job?.result) {
                if(hasTranscriptResult(job.result)) {
                    setLastResult(job.result);
                    navigate('/editor');
                    return;
                }
            }
        } catch(_) {}
        if(h.status==='completed'){ setLastResult(historyEntryToResult(h)); navigate('/editor'); }
        else navigate('/tasks');
    };

    const settleCompletedJob = (job, fallbackJob = currentJob) => {
        const result = job?.result;
        const taskId = job?.task_id || result?.task_id || fallbackJob?.taskId;
        if(!result || !taskId) return false;
        if(settledJobRef.current.has(taskId)) return true;
        settledJobRef.current.add(taskId);
        if(abortRef.current){
            abortRef.current.abort();
            abortRef.current = null;
        }
        currentTaskRef.current = null;
        const fileName = result.filename || job?.source_filename || fallbackJob?.fileName;
        const displayName = resultDisplayTitle(result, {name: fileName, rawFilename: fileName});
        setCurrentJob({taskId, fileName: displayName || fileName, stage:'done', progress:100});
        setLastResult(result);
        setProcessingResult(result);
        const larkUrl = result.lark_response?.url || null;
        if(!fallbackJob?.guestTrial) {
            addToHistory(resultToHistoryEntry(result, {taskId, name: displayName || fileName, rawFilename: fileName}));
        }
        if(larkUrl) addLarkExport({url:larkUrl, title: result.lark_doc_title || fileNameStem(displayName || fileName), timestamp:Date.now()});
        setTimeout(() => {
            setCurrentJob((prev) => prev?.taskId === taskId ? null : prev);
        }, 3000);
        return true;
    };

    const applyProgressEvent = (ev) => {
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
        if(ev.stage === 'transcript_ready' && ev.result) {
            setLastResult(ev.result);
            setProcessingResult(ev.result);
        }
    };

    useEffect(() => {
        if(!currentJob?.taskId || currentJob.stage === 'done') return;
        let stale = false;
        const syncCurrentJob = async () => {
            try {
                const job = currentJob.guestTrial
                    ? await getGuestTrialJob(currentJob.taskId, currentJob.guestToken || getGuestTrialToken())
                    : await getJob(currentJob.taskId, {sttProvider: currentJob.sttProvider});
                if(stale) return;
                if(job?.result && (job.status === 'completed' || hasTranscriptResult(job.result))) {
                    settleCompletedJob(job, currentJob);
                    return;
                }
                if(job?.status === 'queued' || job?.status === 'running') {
                    const syncedJob = jobToCurrentJob(job);
                    setCurrentJob((prev) => prev?.taskId === (job.task_id || currentJob.taskId) ? {
                        ...prev,
                        ...syncedJob,
                        resume: prev.resume,
                        guestTrial: prev.guestTrial,
                        guestToken: prev.guestToken,
                        queue: prev.queue,
                        skipSummary: prev.skipSummary,
                        exportToLark: prev.exportToLark,
                        noteMode: prev.noteMode,
                        sttProvider: syncedJob.sttProvider || prev.sttProvider,
                        sttModel: prev.sttModel,
                        sttSpeed: prev.sttSpeed,
                        sttLanguage: prev.sttLanguage,
                    } : prev);
                    return;
                }
                if(job?.status === 'failed') {
                    if(abortRef.current){
                        abortRef.current.abort();
                        abortRef.current = null;
                    }
                    currentTaskRef.current = null;
                    setUploadError(job.error_reason || 'Task failed.');
                    if(!currentJob.guestTrial) {
                        addToHistory({
                            id: Date.now(),
                            taskId: job.task_id || currentJob.taskId,
                            name: jobDisplayTitle(job) || currentJob.fileName,
                            rawFilename: job.source_filename || currentJob.fileName,
                            timestamp: Date.now(),
                            durationMin: 0,
                            status: 'failed',
                        });
                    }
                    setCurrentJob(null);
                }
            } catch(_) {}
        };
        syncCurrentJob();
        const timer = setInterval(syncCurrentJob, 5000);
        return () => {
            stale = true;
            clearInterval(timer);
        };
    }, [currentJob?.taskId, currentJob?.stage]);

    useEffect(() => {
        if(!currentJob?.resume || !currentJob.taskId || currentJob.stage === 'done' || abortRef.current) return;
        const ac = new AbortController();
        abortRef.current = ac;
        currentTaskRef.current = {
            taskId: currentJob.taskId,
            fileName: currentJob.fileName,
            sourceType: currentJob.sourceType,
            fileSizeMb: currentJob.fileSizeMb,
        };
        let stale = false;
        const subscribe = currentJob.guestTrial
            ? subscribeGuestTrialJobEvents(currentJob.taskId, currentJob.guestToken || getGuestTrialToken(), applyProgressEvent, ac.signal)
            : subscribeJobEvents(currentJob.taskId, applyProgressEvent, ac.signal, {sttProvider: currentJob.sttProvider});
        subscribe.then((result) => {
            if(stale) return;
            settleCompletedJob({task_id: currentJob.taskId, source_filename: currentJob.fileName, result}, currentJob);
        }).catch((err) => {
            if(!stale && err.name !== 'AbortError') setUploadError(err.message || 'Failed to resume task.');
        }).finally(() => {
            if(abortRef.current === ac) abortRef.current = null;
        });
        return () => {
            stale = true;
            ac.abort();
            if(abortRef.current === ac) abortRef.current = null;
        };
    }, [currentJob?.taskId, currentJob?.resume]);

    useEffect(() => {
        if(!guestMode || currentJob) return;
        const token = getGuestTrialToken();
        const taskId = getGuestTrialTaskId();
        if(!token || !taskId) return;
        let stale = false;
        getGuestTrialJob(taskId, token).then((job) => {
            if(stale || !job) return;
            if(job.status === 'completed' && job.result) {
                setLastResult(job.result);
                setProcessingResult(job.result);
                return;
            }
            if(['queued', 'running'].includes(job.status)) {
                setCurrentJob({
                    ...jobToCurrentJob(job),
                    guestTrial: true,
                    guestToken: token,
                    resume: true,
                    queue: job.metadata?.guest_trial_queue || null,
                    skipSummary: false,
                    exportToLark: false,
                    noteMode: loadSettings().noteMode || 'auto',
                });
            }
        }).catch(() => {
            clearGuestTrialSession();
        });
        return () => { stale = true; };
    }, [guestMode]);

    const mediaExts = /\.(mp4|mov|avi|mkv|wmv|flv|webm|m4v|mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;
    const transcriptExts = /\.(srt|vtt|txt|md)$/i;
    const audioExts = /\.(mp3|wav|flac|aac|ogg|m4a|wma|opus)$/i;

    const ensureCloudReady = async (sttProvider) => {
        if (guestMode) return true;
        if (!isAzureCloudProvider(sttProvider)) return true;
        try {
            const status = await getCredentialsStatus();
            const configured = sttProvider === 'azure_batch'
                ? isAzureBatchConfigured(status)
                : isAzureSpeechConfigured(status);
            if (configured) return true;
        } catch (_) {}
        setUploadError(azureSpeechMissingMessage(lang));
        return false;
    };

    const estimateText = (queue) => {
        const wait = queue?.estimated_wait;
        if(!wait) return null;
        if((wait.min_minutes || 0) <= 0 && (wait.max_minutes || 0) <= 0) {
            return lang === 'zh' ? '即将开始处理' : 'Starting soon';
        }
        return lang === 'zh'
            ? `预计等待约 ${wait.min_minutes}-${wait.max_minutes} 分钟`
            : `Estimated wait ${wait.min_minutes}-${wait.max_minutes} min`;
    };

    const startMediaFiles = async (files) => {
        const selectedFiles = Array.from(files || []);
        if(selectedFiles.length === 0) return;
        if(!selectedFiles.every((file) => mediaExts.test(file.name))){
            setUploadError(t('dash.fileError')); return;
        }
        if(guestMode && selectedFiles.length > 1) {
            setUploadError(lang === 'zh' ? '访客试用一次只能上传 1 个音视频文件。' : 'Guest trial accepts one audio/video file at a time.');
            return;
        }
                setUploadError(null);

        const settings = loadSettings();
        const sttModel = normalizeSttModel(settings.sttModel);
        const sttProvider = effectiveSttProvider(settings, runtimeConfig);
        if (!(await ensureCloudReady(sttProvider))) return;

        if(guestMode) {
            setProcessingResult(null);
            setLastResult(null);
            const file = selectedFiles[0];
            const guestConfig = guestTrial || runtimeConfig.guestTrial || {};
            const fileLimit = Number(guestConfig.file_limit_mb || 150);
            const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
            if(fileSizeMb > fileLimit) {
                setUploadError(lang === 'zh'
                    ? `访客试用支持 ${fileLimit} MB 以内的单个音视频文件。`
                    : `Guest trial supports one file up to ${fileLimit} MB.`);
                return;
            }
            setLastSourceFile(file);
            const ac = new AbortController();
            abortRef.current = ac;
            setCurrentJob({
                taskId: null,
                fileName:file.name,
                stage:'upload',
                progress:2,
                startedAt: Date.now(),
                sourceType: audioExts.test(file.name) ? "audio" : "video",
                fileSizeMb,
                guestTrial: true,
                sttProvider,
                sttModel,
                sttSpeed: settings.sttSpeed||'balanced',
                sttLanguage: 'auto',
                skipSummary: false,
                exportToLark: false,
                noteMode: settings.noteMode||'auto',
            });
            try {
                const data = await processGuestTrialFile(file, {
                    ...buildAiOptions(settings),
                    sttProvider,
                    sttModel,
                    sttLanguage: 'auto',
                    noteMode: settings.noteMode||'auto',
                }, ac.signal);
                const token = data.guest_token;
                const taskId = data.task_id;
                setGuestTrialToken(token);
                setGuestTrialTaskId(taskId);
                currentTaskRef.current = {
                    taskId,
                    fileName: file.name,
                    sourceType: audioExts.test(file.name) ? "audio" : "video",
                    fileSizeMb,
                };
                setCurrentJob({
                    ...jobToCurrentJob(data.job || {task_id: taskId, source_filename: file.name, status:'queued', stage:'queued', progress:0}),
                    guestTrial: true,
                    guestToken: token,
                    queue: data.queue,
                    resume: true,
                    skipSummary: false,
                    exportToLark: false,
                    noteMode: settings.noteMode||'auto',
                    sttProvider,
                    sttModel,
                    sttLanguage: 'auto',
                });
                const result = await subscribeGuestTrialJobEvents(taskId, token, applyProgressEvent, ac.signal);
                abortRef.current = null;
                currentTaskRef.current = null;
                settleCompletedJob({task_id: taskId, source_filename: file.name, result}, {taskId, fileName:file.name, guestTrial:true});
                navigate('/editor');
            } catch(err) {
                abortRef.current = null;
                currentTaskRef.current = null;
                setCurrentJob(null);
                if(err.name !== 'AbortError') setUploadError(err.message || "Guest trial failed.");
            }
            return;
        }

        const hasActiveJob = !!currentJob && currentJob.stage !== 'done';
        if(hasActiveJob) {
            setLastSourceFile(null);
            setQueueSubmitting(true);
            try {
                await enqueueProcessFiles(selectedFiles, {
                    exportToLark: settings.exportToLark||false,
                    larkExportRoute: larkExportRouteFromSettings(settings),
                    larkViaCli: !!settings.larkViaCli,
                    ...buildAiOptions(settings),
                    skipSummary: !!settings.skipAiSummary,
                    sttProvider,
                    sttModel,
                    sttSpeed: settings.sttSpeed||'balanced',
                    sttLanguage: 'auto',
                });
                navigate('/tasks', {state:{queueSubmittedAt: Date.now()}});
            } catch(err) {
                setUploadError(friendlyTaskError(err.message || "Queue failed.", lang));
            } finally {
                setQueueSubmitting(false);
            }
            return;
        }

        setProcessingResult(null);
        setLastResult(null);

        if(selectedFiles.length > 1) {
            setLastSourceFile(null);
            const queuedFileCount = selectedFiles.length;
            setCurrentJob({
                taskId: null,
                fileName: lang === 'zh' ? `${queuedFileCount} 个文件` : `${queuedFileCount} files`,
                stage:'upload',
                progress:2,
                startedAt: Date.now(),
                sourceType:'queue_upload',
                fileSizeMb: totalFileSizeMb(selectedFiles),
                queueTotal: queuedFileCount,
                queueUpload: true,
            });
            navigate('/tasks');
            try {
                await enqueueProcessFiles(selectedFiles, {
                    exportToLark: settings.exportToLark||false,
                    larkExportRoute: larkExportRouteFromSettings(settings),
                    larkViaCli: !!settings.larkViaCli,
                    ...buildAiOptions(settings),
                    skipSummary: !!settings.skipAiSummary,
                    sttProvider,
                    sttModel,
                    sttSpeed: settings.sttSpeed||'balanced',
                    sttLanguage: 'auto',
                });
                setCurrentJob(null);
                navigate('/tasks', {replace:true, state:{queueSubmittedAt: Date.now()}});
            } catch(err) {
                setCurrentJob(null);
                navigate('/tasks', {
                    replace:true,
                    state:{queueSubmitError: friendlyTaskError(err.message || "Queue failed.", lang)},
                });
            }
            return;
        }

        const file = selectedFiles[0];
                setLastSourceFile(file);

        const ac = new AbortController();
        const taskId = createTaskId();
        const sourceType = audioExts.test(file.name) ? "audio" : "video";
        const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
        abortRef.current = ac;
        currentTaskRef.current = {
            taskId,
            fileName: file.name,
            sourceType,
            fileSizeMb,
        };
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
            let openedTranscript = false;
            const result = await processVideoSSE(file, {
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
                applyProgressEvent(ev);
                if(ev.stage === 'transcript_ready' && ev.result && !openedTranscript) {
                    openedTranscript = true;
                    setLastResult(ev.result);
                    setProcessingResult(ev.result);
                    navigate('/editor');
                }
            }, ac.signal);

            abortRef.current = null;
            currentTaskRef.current = null;
            setCurrentJob({fileName:file.name, stage:'done', progress:100});
            setLastResult(result);
                    setProcessingResult(result);

            const larkUrl = result.lark_response?.url || null;
            addToHistory(resultToHistoryEntry(result, {taskId, name:file.name, requestedNoteMode: settings.noteMode||'auto'}));
            if(larkUrl) addLarkExport({url:larkUrl, title: result.lark_doc_title || fileNameStem(file.name), timestamp:Date.now()});
            setTimeout(() => setCurrentJob(null), 3000);
        } catch(err) {
            abortRef.current = null;
            currentTaskRef.current = null;
            setCurrentJob(null);
            if(err.name !== 'AbortError'){
                setUploadError(err.message || "Processing failed.");
                addToHistory({id:Date.now(), taskId, name:file.name, timestamp:Date.now(), durationMin:0, status:'failed'});
            }
                }
            };

            const handleVideoLinkSubmit = async () => {
                if(guestMode) {
                    setUploadError(lang === 'zh' ? '访客试用暂不支持链接抓取，请直接上传一个音视频文件。' : 'Guest trial does not support link fetching. Upload one audio/video file instead.');
                    return;
                }
                const input = videoLinkInput.trim();
                if(!input){
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
                setVideoLinkSubmitting(true);
                try {
                    const data = await createVideoSourceJob(input, {
                        exportToLark: settings.exportToLark||false,
                        larkExportRoute: larkExportRouteFromSettings(settings),
                        larkViaCli: !!settings.larkViaCli,
                        ...buildAiOptions(settings),
                        skipSummary: !!settings.skipAiSummary,
                        sttProvider,
                        sttModel,
                        sttSpeed: settings.sttSpeed||'balanced',
                        sttLanguage: 'auto',
                    });
                    const job = data?.job || {};
                    if(job.task_id) {
                        const current = jobToCurrentJob({
                            ...job,
                            progress: job.progress ?? 2,
                            created_at: job.created_at || new Date().toISOString(),
                        });
                        currentTaskRef.current = {
                            taskId: job.task_id,
                            fileName: job.source_filename || input.slice(0, 80),
                            sourceType: 'video_link',
                            fileSizeMb: null,
                        };
                        setCurrentJob({
                            ...current,
                            sourceType: 'video_link',
                            resume: true,
                            skipSummary: !!settings.skipAiSummary,
                            exportToLark: !!settings.exportToLark,
                            noteMode: settings.noteMode||'auto',
                            sttProvider,
                            sttModel,
                            sttSpeed: settings.sttSpeed||'balanced',
                            sttLanguage: 'auto',
                        });
                    }
                    setVideoLinkInput('');
                } catch(err) {
                    setUploadError(err.message || "Video link fetch failed.");
                } finally {
                    setVideoLinkSubmitting(false);
                }
            };

            const handleFileSelect = async (e) => {
                const files = Array.from(e.target.files || []);
                if(fileInputRef.current) fileInputRef.current.value = '';
                await startMediaFiles(files);
            };

            const handleSubtitleSelect = async (e) => {
                const file = e.target.files?.[0];
                if(!file) return;
                if(subtitleInputRef.current) subtitleInputRef.current.value = '';
                if(guestMode) {
                    setUploadError(lang === 'zh' ? '访客试用暂不支持字幕导入，请上传一个音视频文件。' : 'Guest trial does not support transcript imports. Upload one audio/video file instead.');
                    return;
                }
                if(!transcriptExts.test(file.name)){
                    setUploadError(t('dash.subtitleFileError')); return;
                }
                setUploadError(null);
                setProcessingResult(null);
                setLastResult(null);
                setLastSourceFile(null);

                const ac = new AbortController();
                const taskId = createTaskId();
                const settings = loadSettings();
                const fileSizeMb = Math.round(file.size / 1024 / 1024 * 1000) / 1000;
                abortRef.current = ac;
                currentTaskRef.current = {
                    taskId,
                    fileName: file.name,
                    sourceType: "transcript_file",
                    fileSizeMb,
                };
	                setCurrentJob({
	                    taskId,
	                    fileName:file.name,
	                    stage:'summary',
	                    progress:20,
	                    startedAt: Date.now(),
	                    sourceType: "transcript_file",
	                    fileSizeMb,
	                    skipSummary: false,
	                    exportToLark: false,
	                    noteMode: settings.noteMode||'auto',
	                });
	                try {
	                    const result = await summarizeTranscriptFile(file, {taskId, ...buildAiOptions(settings), skipSummary: false}, ac.signal);
                    abortRef.current = null;
                    currentTaskRef.current = null;
                    setCurrentJob({fileName:file.name, stage:'done', progress:100});
                    setLastResult(result);
                    setProcessingResult(result);
                    addToHistory(resultToHistoryEntry(result, {taskId, name:file.name, requestedNoteMode: settings.noteMode||'auto', source:'transcript_file'}));
                    navigate('/editor');
                    setTimeout(() => setCurrentJob(null), 3000);
                } catch(err) {
                    abortRef.current = null;
                    currentTaskRef.current = null;
                    setCurrentJob(null);
                    if(err.name !== 'AbortError'){
                        setUploadError(err.message || "Summary generation failed.");
                        addToHistory({id:Date.now(), taskId, name:file.name, timestamp:Date.now(), durationMin:0, status:'failed'});
                    }
                }
            };

            const handleDrop = (e) => {
                e.preventDefault();
                const files = Array.from(e.dataTransfer.files || []);
                if(files.length === 0) return;
                const file = files[0];
        if(uploading && files.length === 1 && file && transcriptExts.test(file.name)){
            setUploadError(lang === 'zh' ? '当前有转录任务时，只能继续添加音视频到后台队列。字幕/文本导入请等当前任务结束后再用。' : 'While a transcription is active, only audio/video files can be added to the background queue. Import transcript files after the active task finishes.');
            return;
        }
        if(files.length === 1 && file && transcriptExts.test(file.name) && subtitleInputRef.current){
            const dt = new DataTransfer(); dt.items.add(file);
            subtitleInputRef.current.files = dt.files;
            handleSubtitleSelect({target:subtitleInputRef.current});
        } else {
            startMediaFiles(files);
        }
    };

    const uploading = !!currentJob && currentJob.stage !== 'done';
    const elapsedSec = uploading ? Math.max(0, Math.floor((now - (currentJob.startedAt||now)) / 1000)) : 0;
    const activeProgress = Math.max(0, Math.min(100, Number(currentJob?.progress)||0));
    const activeStageLabel = currentJob ? (t(`status.${currentJob.stage}`)||t('dash.uploading')) : '';
    const jobStages = currentJob?.sourceType === 'transcript_file'
        ? [{key:'summary', label:'proc.aiSumm'}, {key:'export', label:'proc.larkExport'}]
        : currentJob?.sourceType === 'video_link'
            ? [
                {key:'resolving', label:'status.resolving'},
                {key:'downloading', label:'status.downloading'},
                {key:'saving', label:'status.saving'},
                {key:'queued', label:'status.queued'},
                {key:'audio', label:'proc.audioExtract'},
                {key:'stt', label:'proc.transcription'},
                {key:'summary', label:'proc.aiSumm'},
                {key:'export', label:'proc.larkExport'},
            ]
            : [{key:'audio', label:'proc.audioExtract'}, {key:'stt', label:'proc.transcription'}, {key:'summary', label:'proc.aiSumm'}, {key:'export', label:'proc.larkExport'}];
    const stageRank = {upload:0, resolving:1, downloading:2, saving:3, queued:4, audio:5, stt:6, transcript_ready:7, summary:7, export:8, done:9};
    const currentRank = stageRank[currentJob?.stage] ?? 0;
    const sttProfile = currentJob?.sourceType === 'transcript_file'
        ? '-'
        : [
            isAzureCloudProvider(currentJob?.sttProvider) ? 'Azure' : 'local',
            currentJob?.sttModel||DEFAULT_STT_MODEL,
            currentJob?.sttSpeed||'balanced',
            currentJob?.sttLanguage||'auto',
        ].join(' / ');
    const sttProgressPct = Math.round(sttProgressFraction(currentJob) * 100);
    const sttProgressUnknown = isSttProgressUnmeasured(currentJob);
    const hasSttTiming = currentJob?.stage === 'stt' && currentJob?.durationSeconds > 0 && !sttProgressUnknown;
    const sttElapsedForHint = Math.max(elapsedSec, Number(currentJob?.sttElapsedSeconds) || 0);
    const sttWaitedLong = sttProgressUnknown && !isAzureCloudProvider(currentJob?.sttProvider) && sttElapsedForHint >= 60;
    const selectedSttProvider = currentJob?.sttProvider || effectiveSttProvider(loadSettings(), runtimeConfig);
    const taskInfoCards = [
        ...(currentJob?.guestTrial && currentJob?.queue
            ? [
                {label: lang === 'zh' ? '前方任务' : 'Ahead', value: `${currentJob.queue.people_ahead ?? 0}`},
                {label: lang === 'zh' ? '等待预估' : 'Wait', value: estimateText(currentJob.queue) || '-'},
            ]
            : []),
        {label:t('dash.elapsed'), value:fmtElapsed(elapsedSec)},
        {label:t('dash.fileSize'), value:fmtFileSize(currentJob?.fileSizeMb)},
        ...(isAzureCloudProvider(currentJob?.sttProvider) && currentJob?.azureBatchAudioSizeMb != null
            ? [{label:t('dash.azureUploadAudio'), value:fmtFileSize(currentJob.azureBatchAudioSizeMb)}]
            : []),
        {label:t('dash.modelProfile'), value:sttProfile},
        {label:t('dash.summaryMode'), value:currentJob?.skipSummary?t('dash.summaryOff'):`${t('dash.summaryOn')} / ${noteModeLabel(currentJob?.noteMode, lang)}`},
    ];

            return (
            <div className="ml-64 min-h-screen relative pb-8">
                <section className="p-12 max-w-7xl mx-auto space-y-12 h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
                        <div>
                    <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface mb-2">{t('dash.welcome')}</h2>
                    <p className="text-on-surface-variant font-body">{t('dash.subtitle')}</p>
                        </div>
                        <div className="flex gap-4">
	                    <div className="bg-surface-container-lowest editorial-shadow p-6 rounded-sm flex items-center gap-4 min-w-[220px] border border-outline-variant/20 dark:border-white/5">
	                                <div className="w-12 h-12 rounded-sm bg-primary/10 flex items-center justify-center text-primary dark:bg-blue-400/10 dark:text-blue-300">
	                            <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>timer</span>
	                                </div>
                                <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-outline">{t('dash.totalMin')}</p>
                            <p className="text-2xl font-headline font-bold text-on-surface">{stats.totalMinutes.toLocaleString()} {t('dash.minUnit')}</p>
                                </div>
                            </div>
	                    <div className="bg-surface-container-lowest editorial-shadow p-6 rounded-sm flex items-center gap-4 min-w-[220px] border border-outline-variant/20 dark:border-white/5">
	                                <div className="w-12 h-12 rounded-sm bg-tertiary/10 flex items-center justify-center text-tertiary dark:bg-blue-400/10 dark:text-blue-300">
	                            <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>description</span>
	                                </div>
                                <div>
                            <p className="text-[10px] font-bold uppercase tracking-widest text-outline">{t('dash.noteGen')}</p>
                            <p className="text-2xl font-headline font-bold text-on-surface">{stats.notesGenerated} {t('dash.docUnit')}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-6">
                        {!guestMode && (
                        <form
                            onSubmit={(e)=>{e.preventDefault(); handleVideoLinkSubmit();}}
                            className="flex items-stretch gap-2"
                        >
                            <input
                                type="text"
                                value={videoLinkInput}
                                onChange={(e)=>setVideoLinkInput(e.target.value)}
                                disabled={videoLinkSubmitting}
                                className="h-12 min-w-0 flex-1 appearance-none rounded-sm border border-outline-variant/35 bg-surface-container-lowest/70 px-4 text-sm font-semibold text-on-surface shadow-none outline-none ring-0 placeholder:text-on-surface-variant/60 transition-colors focus:border-primary/45 focus:bg-surface-container-lowest focus:outline-none focus:ring-0 disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.035] dark:placeholder:text-slate-500 dark:focus:border-blue-300/40"
                                placeholder={t('dash.linkPlaceholder')}
                                aria-label={t('dash.linkPlaceholder')}
                            />
                            <button
                                type="submit"
                                disabled={videoLinkSubmitting}
                                className="flex h-12 flex-shrink-0 items-center justify-center gap-2 rounded-sm border border-primary/20 bg-primary/10 px-5 text-sm font-extrabold text-primary transition-colors duration-200 hover:bg-primary/15 active:translate-y-px disabled:opacity-50 dark:border-blue-300/20 dark:bg-blue-400/10 dark:text-blue-200 dark:hover:bg-blue-400/15"
                            >
                                <span className={`material-symbols-outlined text-[18px] ${videoLinkSubmitting ? 'animate-spin' : ''}`}>{videoLinkSubmitting ? 'sync' : 'arrow_forward'}</span>
                                {videoLinkSubmitting ? t('dash.linkSubmitting') : t('dash.linkSubmit')}
                            </button>
                        </form>
                        )}

                    <div className="grid grid-cols-12 gap-8">
                        <div className="col-span-12 lg:col-span-9 group">
                    <div className={`relative h-[480px] rounded-sm overflow-hidden bg-slate-900 shadow-2xl transition-transform duration-500 ${uploading?'':'hover:scale-[1.01]'}`} onDrop={handleDrop} onDragOver={e=>e.preventDefault()}>
                                <input ref={fileInputRef} type="file" multiple accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus" onChange={handleFileSelect} className="hidden"/>
                                <input ref={subtitleInputRef} type="file" accept=".srt,.vtt,.txt,.md,text/plain,text/markdown" onChange={handleSubtitleSelect} className="hidden"/>
                                <div className="absolute inset-0 opacity-40" aria-hidden="true">
                            <div className="w-full h-full bg-gradient-to-br from-slate-800 via-indigo-950/90 to-blue-900/70" style={{backgroundImage:'linear-gradient(135deg,#1e293b 0%,#312e81 35%,#1e3a5f 70%,#0f172a 100%)'}} />
                                </div>
                                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/40 to-transparent"></div>
	                                <div className="relative h-full flex flex-col justify-end items-center p-10 space-y-6">
	                                    {!uploading && (
	                                    <div className="w-full max-w-[720px] mx-auto">
                                <span className="bg-white/[0.08] text-blue-100 border border-white/[0.12] px-3 py-1 rounded-sm text-[10px] font-bold tracking-widest uppercase mb-4 inline-block">{t('dash.proTag')}</span>
                                <h3 className="font-headline text-3xl font-bold text-white leading-tight">{guestMode ? (lang==='zh'?'访客试用：上传一个短视频生成字幕与笔记':'Guest trial: upload one short file for subtitles and notes') : t('dash.heroTitle')}</h3>
                                <p className="text-slate-300 mt-4 text-sm leading-relaxed">
                                    {guestMode
                                        ? (lang==='zh'?'支持 15 分钟以内、150MB 以内的单个音视频文件。真实转录，完成后可下载结果。':'One audio/video file up to 15 minutes and 150 MB. Real processing with downloadable results.')
                                        : t('dash.heroDesc')}
                                </p>
                                    </div>
                                    )}
                                    {uploading && currentJob && (
                                    <div className="w-full max-w-[760px] mx-auto space-y-6">
                                        <div className="flex items-start justify-between gap-6">
                                            <div className="min-w-0">
                                                <span className="bg-blue-400/15 text-blue-100 border border-blue-300/30 px-3 py-1 rounded-sm text-[10px] font-bold tracking-widest uppercase mb-4 inline-block">{t('dash.activeTask')}</span>
                                                <h3 className="font-headline text-3xl font-bold text-white leading-tight truncate">{currentJob.fileName}</h3>
                                                <p className="text-slate-300 mt-3 text-sm">
                                                    {currentJob.guestTrial && currentJob.stage === 'queued'
                                                        ? (lang==='zh'?'文件已进入访客试用队列，开始处理后会自动更新进度。':'Your file is in the guest trial queue. Progress updates automatically when processing starts.')
                                                        : currentJob.sourceType === 'video_link'
                                                            ? t('dash.linkQueued')
                                                        : t('dash.waitingForTranscript')}
                                                </p>
                                            </div>
                                            <div className="flex flex-col items-end gap-2 flex-shrink-0">
                                                {!guestMode && (
                                                    <button onClick={()=>fileInputRef.current?.click()} disabled={queueSubmitting} className="text-blue-100 hover:text-white border border-blue-300/40 hover:bg-blue-500/20 px-3 py-2 rounded-sm text-xs font-bold flex items-center gap-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                                                        <span className={`material-symbols-outlined text-sm ${queueSubmitting?'animate-spin':''}`}>{queueSubmitting?'sync':'playlist_add'}</span>
                                                        {queueSubmitting ? (lang==='zh'?'添加中…':'Adding…') : (lang==='zh'?'添加到队列':'Add to queue')}
                                                    </button>
                                                )}
                                                {currentJob.resume && !currentJob.guestTrial ? (
                                                    <Link to="/tasks" className="text-blue-100 hover:text-white border border-blue-300/40 hover:bg-blue-500/20 px-3 py-2 rounded-sm text-xs font-bold flex items-center gap-2 transition-colors">
                                                        <span className="material-symbols-outlined text-sm">monitoring</span>{t('dash.viewTasks')}
                                                    </Link>
                                                ) : (
                                                    <button onClick={handleCancel} className="text-red-300 hover:text-white border border-red-300/40 hover:bg-red-500/20 px-3 py-2 rounded-sm text-xs font-bold flex items-center gap-2 transition-colors">
                                                        <span className="material-symbols-outlined text-sm">cancel</span>{t('dash.cancel')}
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="flex items-end justify-between gap-4 mb-2">
                                                <div>
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{t('dash.currentStage')}</p>
                                                    <p className="text-lg font-bold text-white">{activeStageLabel}</p>
                                                </div>
                                                <p className="font-headline text-3xl font-extrabold text-white">{jobProgressLabel(currentJob, t)}</p>
                                            </div>
                                            <div className={`w-full h-3 bg-slate-700/80 rounded-full overflow-hidden ${sttProgressUnknown ? 'progress-indeterminate' : ''}`}>
                                                {!sttProgressUnknown && <div className="h-full bg-gradient-to-r from-blue-400 to-cyan-300 transition-all duration-700" style={{width:`${activeProgress}%`}}></div>}
                                            </div>
                                            {currentJob.stage === 'stt' && (
                                                <div className="flex flex-wrap items-center justify-between gap-2 mt-3 text-xs text-slate-300">
	                                                    <span>
	                                                        {hasSttTiming
	                                                            ? `${t('dash.transcribedTo')}: ${fmtElapsed(currentJob.transcribedSeconds||0)} / ${fmtElapsed(currentJob.durationSeconds||0)}`
	                                                            : sttStatusLabel(currentJob.sttStatus, t)}
	                                                    </span>
	                                                    <span className="font-bold text-cyan-200">{sttProgressUnknown ? t('dash.sttMeasuring') : `STT ${sttProgressPct}%`}</span>
	                                                    {sttWaitedLong && (
	                                                        <span className="basis-full text-[11px] text-amber-200 leading-snug">{t('dash.sttNoProgressHint')}</span>
	                                                    )}
	                                                </div>
	                                            )}
                                        </div>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                            {taskInfoCards.map((item) => (
	                                                <div key={item.label} className="bg-white/[0.08] border border-white/10 rounded-sm p-3 min-w-0">
                                                    <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">{item.label}</p>
                                                    <p className="text-sm font-bold text-white truncate">{item.value}</p>
                                                </div>
                                            ))}
                                        </div>
                                        <div className="bg-white/[0.07] border border-white/10 rounded-sm p-4">
                                            <div className="flex items-center justify-between mb-4">
                                                <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{t('dash.pipeline')}</p>
                                                <p className="text-xs text-slate-300">{currentJob.exportToLark?t('dash.exportOn'):t('dash.exportOff')}</p>
                                            </div>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                                {jobStages.map((stage) => {
                                                    const rank = stageRank[stage.key] ?? 0;
                                                    const isActive = currentJob.stage === stage.key || (currentJob.stage === 'transcript_ready' && stage.key === 'summary');
                                                    const isDone = currentRank > rank;
                                                    return (
                                                        <div key={stage.key} className={`flex items-center gap-2 text-xs font-bold ${isDone?'text-blue-100':isActive?'text-white':'text-slate-500'}`}>
                                                            <span className={`material-symbols-outlined text-base ${isDone?'text-cyan-300':isActive?'text-blue-300 animate-spin':'text-slate-600'}`}>{isDone?'check_circle':isActive?'sync':'radio_button_unchecked'}</span>
                                                            <span className="truncate">{t(stage.label)}</span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    </div>
                                    )}
	                                    {!uploading && (
			                                    <div className="w-full max-w-[720px] mx-auto space-y-5">
			                                        <div className="grid grid-cols-1 sm:grid-cols-[auto_auto] gap-3 w-full max-w-[560px]">
			                                            <button onClick={()=>fileInputRef.current?.click()} disabled={uploading} className="min-h-[56px] bg-white/[0.92] text-slate-950 font-bold px-5 py-4 rounded-sm flex items-center gap-3 hover:bg-blue-50 transition-colors shadow-[0_16px_46px_-30px_rgba(255,255,255,0.8)] active:translate-y-px disabled:opacity-50 justify-center dark:bg-white/90 dark:hover:bg-white">
			                                                <span className="material-symbols-outlined">upload_file</span>
			                                                <span>{uploading ? t('dash.processing') : (guestMode ? (lang==='zh'?'开始访客试用':'Start guest trial') : t('dash.selectFile'))}</span>
			                                            </button>
	                                                    {!guestMode && (
			                                                <button onClick={()=>subtitleInputRef.current?.click()} disabled={uploading} className="min-h-[56px] bg-white/[0.07] text-white border border-white/15 font-bold px-5 py-4 rounded-sm flex items-center gap-3 hover:bg-white/[0.12] transition-colors active:translate-y-px disabled:opacity-50 justify-center">
			                                                    <span className="material-symbols-outlined">subtitles</span>
			                                                    <span className="flex flex-col items-start text-left leading-tight">
                                                                    <span>{t('dash.selectSubtitle')}</span>
                                                                    <span className="mt-1 text-[11px] font-semibold text-slate-300">SRT / VTT / TXT / MD</span>
                                                                </span>
			                                                </button>
	                                                    )}
			                                        </div>
		                                <div className="text-slate-400 text-sm font-bold max-w-xl">{t('dash.dragHint')}</div>
	                                {isAzureCloudProvider(selectedSttProvider) && (
		                                    <div className="text-cyan-100/85 text-xs leading-relaxed max-w-xl bg-white/[0.08] border border-white/10 rounded-sm px-3 py-2">
	                                        {t('dash.azureUploadHint')}
	                                    </div>
	                                )}
	                                    </div>
                                    )}
                            {uploadError && <div className="bg-red-500/15 border border-red-400/30 text-red-200 px-4 py-2 rounded-sm text-sm">{uploadError}</div>}
	                                    {processingResult && (
	                                        <div className="bg-green-500/15 border border-green-400/30 text-green-200 px-4 py-2 rounded-sm text-sm">
	                                    {processingResult.source==='transcript_file' ? t('dash.subtitleDone') : t('dash.done')} <button onClick={()=>navigate("/editor")} className="underline hover:no-underline">{t('dash.viewEditor')}</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="col-span-12 lg:col-span-3 flex flex-col gap-5">
                            <div className="flex items-center justify-between px-2">
                        <h4 className="font-headline text-xl font-bold text-on-surface">{t('dash.recent')}</h4>
                        <Link to="/tasks" className="text-xs font-bold text-primary hover:underline">{t('dash.viewAll')}</Link>
                            </div>
                            <div className="space-y-3">
                        {history.length === 0 && (
                            <div className="text-center py-12 text-on-surface-variant text-sm">{t('dash.noActivity')}</div>
                        )}
                        {history.slice(0,3).map(h => {
                            const historyDone = h.status === 'completed';
                            const historyProcessing = h.status === 'processing';
                            return (
		                            <div key={h.id} className="bg-surface-container-low p-4 rounded-sm flex gap-3 items-start hover:bg-surface-container transition-all cursor-pointer" onClick={() => openHistoryEntry(h)}>
                                <div className={`w-10 h-10 rounded-sm flex items-center justify-center flex-shrink-0 ${historyDone?'bg-blue-50':historyProcessing?'bg-primary/10':'bg-red-50'}`}>
                                    <span className={`material-symbols-outlined ${historyDone?'text-primary':historyProcessing?'text-primary':'text-red-500'}`}>{historyDone?'check_circle':historyProcessing?'sync':'error'}</span>
                                        </div>
                                <div className="flex-1 min-w-0">
                                            <div className="flex justify-between items-start mb-1">
                                        <h5 className="font-bold text-on-surface text-sm truncate pr-2">{h.name}</h5>
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-sm uppercase tracking-tighter flex-shrink-0 ${historyDone?'text-primary bg-primary-fixed':historyProcessing?'text-primary bg-primary/10':'text-red-600 bg-red-50'}`}>
                                            {t(historyDone?'dash.statusCompleted':historyProcessing?'dash.statusProcessing':'dash.statusFailed')}
                                                </span>
                                            </div>
                                    <p className="text-xs text-on-surface-variant">
	                                        {timeAgo(h.timestamp, t)}
	                                        {h.durationMin > 0 && ` • ${h.durationMin} ${t('dash.minUnit')}`}
	                                        {h.sttElapsedSec > 0 && ` • ${t('edit.sttElapsed')} ${fmtElapsed(h.sttElapsedSec)}`}
	                                        {h.sttElapsedSec > 0 && h.audioDurationSec > 0 && ` (${fmtSttRelative(h.sttElapsedSec / h.audioDurationSec, lang)})`}
	                                        {h.sttModel && ` • STT ${[h.sttModel,h.sttSpeed,h.sttLanguage].filter(Boolean).join('/')}`}
	                                        {h.larkUrl && <> • <a href={h.larkUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline" onClick={e=>e.stopPropagation()}>Lark</a></>}
                                    </p>
                                        </div>
                                    </div>
                            );
                        })}
                            </div>
                        </div>
                    </div>
                    </div>
                </section>
            </div>
            );
        };

/* Background Tasks route lives in frontend/src/routes/tasks.jsx */

/* ═══════════════ Processing ═══════════════ */

export default Dashboard;
