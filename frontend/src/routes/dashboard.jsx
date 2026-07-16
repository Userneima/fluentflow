import {useState,useEffect,useRef} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {
    DEFAULT_PROMPT_PRESET,
    presetDisplayLabel,
    resolveSystemPromptFromSettings,
} from '../lib/promptPresets.js';
import {
    cloudSttMissingMessage,
    clearGuestTrialSession,
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
    isCloudSttConfigured,
    isCloudSttProvider,
    isSttProgressUnmeasured,
    historyEntryToResult,
    jobToCurrentJob,
    jobToHistoryEntry,
    larkExportRouteFromSettings,
    noteModeLabel,
    normalizeSttModel,
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
import {
    queueUploadItemsFromFiles,
    queueUploadItemsFromQueuedResponse,
} from '../lib/queueUpload.js';
import SvgIcon from '../components/SvgIcon.jsx';

const Dashboard = () => {
    const {t, lang} = useI18n();
    const {guestMode, guestTrial} = useAuth();
    const {history, addToHistory, currentJob, setCurrentJob, setLastResult, setLastSourceFile, addLarkExport, runtimeConfig} = useApp();
            const [uploadError, setUploadError] = useState(null);
            const [processingResult, setProcessingResult] = useState(null);
            const fileInputRef = useRef(null);
            const subtitleInputRef = useRef(null);
    const {processVideoSSE, enqueueProcessFiles, processGuestTrialFile, getGuestTrialJob, subscribeGuestTrialJobEvents, cancelGuestTrialJob, subscribeJobEvents, summarizeTranscriptFile, recordEvent, checkHealth, getJob, cancelJob, getCredentialsStatus} = useApi();
    const {loadSettings} = useSettings();
            const navigate = useNavigate();
    const abortRef = useRef(null);
    const currentTaskRef = useRef(null);
    const settledJobRef = useRef(new Set());
    const [now, setNow] = useState(Date.now());
    const [queueSubmitting, setQueueSubmitting] = useState(false);
    const [dragActive, setDragActive] = useState(false);

    useEffect(() => { checkHealth(); }, []);
    useEffect(() => {
        if(!currentJob || currentJob.stage === 'done') return;
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, [currentJob?.taskId, currentJob?.stage]);

    const handleCancel = async () => {
        const confirmText = lang === 'zh'
            ? '取消当前正在处理的任务？转录进度不会保留。'
            : 'Cancel this active task? Transcription progress will not be kept.';
        if (!window.confirm(confirmText)) return;

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
        if(currentJob?.taskId && !currentJob?.guestTrial) {
            try {
                await cancelJob(currentJob.taskId, {sttProvider: currentJob.sttProvider});
            } catch(_) {}
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
        generateVisuals: !!settings.autoIllustrate,
        sttProvider: effectiveSttProvider(settings, runtimeConfig),
        cookiesFromBrowser: settings.videoCookiesBrowser || '',
    });

    const openHistoryEntry = async (h) => {
        const cachedResult = historyEntryToResult(h);
        const openCachedEditor = () => {
            if (h.status !== 'completed' || !hasTranscriptResult(cachedResult)) return false;
            setLastResult(cachedResult);
            navigate('/editor');
            return true;
        };
        if (openCachedEditor()) return;
        if(!h.taskId) return;
        navigate('/agent', {state: {job: h}});
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
            cloudAudioSizeMb: ev.elevenlabs_audio_size_mb ?? prev.cloudAudioSizeMb,
        } : null);
        if(ev.stage === 'transcript_ready' && ev.result) {
            setLastResult(ev.result);
            setProcessingResult(ev.result);
        }
    };

    const persistFailedTaskJob = (job, rawMessage, fallback={}) => {
        const taskId = job?.task_id || fallback.taskId;
        const errorText = friendlyTaskError(rawMessage || job?.error_reason || 'Task failed.', lang);
        if (!taskId || fallback.guestTrial) return errorText;
        const now = new Date().toISOString();
        const failedJob = {
            ...job,
            task_id: taskId,
            status: 'failed',
            task_state: 'failed',
            stage: 'failed',
            progress: 100,
            source_type: job?.source_type || fallback.sourceType || 'video',
            source_filename: job?.source_filename || fallback.fileName || 'Untitled task',
            source_file_size_mb: job?.source_file_size_mb ?? fallback.fileSizeMb ?? null,
            error_reason: errorText,
            metadata: {
                ...(job?.metadata || {}),
                display_title: job?.metadata?.display_title || fallback.fileName || job?.source_filename,
                stt_provider: job?.metadata?.stt_provider || fallback.sttProvider || null,
            },
            created_at: job?.created_at || (fallback.startedAt ? new Date(fallback.startedAt).toISOString() : now),
            updated_at: now,
        };
        // AppProvider.addToHistory upserts into the single task list and its
        // projection effect persists the cache (see task_list_reconciliation_plan).
        addToHistory(jobToHistoryEntry(failedJob));
        setCurrentJob((prev) => prev?.taskId === taskId ? null : prev);
        return errorText;
    };

    useEffect(() => {
        if(!currentJob?.taskId || currentJob.stage === 'done') return;
        let stale = false;
        let timer = null;
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
                    const errorText = persistFailedTaskJob(job, job.error_reason, currentJob);
                    setUploadError(currentJob.guestTrial ? errorText : (lang === 'zh' ? `${errorText} 已保存在处理记录里。` : `${errorText} Saved in processing records.`));
                }
            } catch(err) {
                if(!stale && err?.status === 404) {
                    stale = true;
                    if(timer) clearInterval(timer);
                    if(abortRef.current){
                        abortRef.current.abort();
                        abortRef.current = null;
                    }
                    currentTaskRef.current = null;
                    setCurrentJob((prev) => prev?.taskId === currentJob.taskId ? null : prev);
                }
            }
        };
        syncCurrentJob();
        timer = setInterval(syncCurrentJob, 5000);
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
            if(!stale && err.name !== 'AbortError') {
                if(err?.status === 404) {
                    setCurrentJob((prev) => prev?.taskId === currentJob.taskId ? null : prev);
                    return;
                }
                currentTaskRef.current = null;
                const errorText = persistFailedTaskJob({
                    task_id: currentJob.taskId,
                    source_filename: currentJob.fileName,
                    source_type: currentJob.sourceType,
                    source_file_size_mb: currentJob.fileSizeMb,
                    metadata: {stt_provider: currentJob.sttProvider},
                }, err.message || 'Failed to resume task.', currentJob);
                setUploadError(currentJob.guestTrial ? errorText : (lang === 'zh' ? `${errorText} 已保存在处理记录里。` : `${errorText} Saved in processing records.`));
            }
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
        if (!isCloudSttProvider(sttProvider)) return true;
        try {
            const status = await getCredentialsStatus();
            const configured = isCloudSttConfigured(sttProvider, status);
            if (configured) return true;
        } catch (_) {}
        setUploadError(cloudSttMissingMessage(lang));
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
                navigate('/agent', {state:{queueSubmittedAt: Date.now()}});
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
            const provisionalQueueItems = queueUploadItemsFromFiles(selectedFiles);
            setCurrentJob({
                taskId: null,
                fileName: lang === 'zh' ? `${queuedFileCount} 个文件` : `${queuedFileCount} files`,
                stage:'upload',
                progress:2,
                startedAt: Date.now(),
                sourceType:'queue_upload',
                fileSizeMb: totalFileSizeMb(selectedFiles),
                queueTotal: queuedFileCount,
                queueItems: provisionalQueueItems,
                queueUpload: true,
            });
            navigate('/agent');
            try {
                const data = await enqueueProcessFiles(selectedFiles, {
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
                const queueItems = queueUploadItemsFromQueuedResponse(data?.queued, provisionalQueueItems);
                setCurrentJob({
                    taskId: null,
                    fileName: lang === 'zh' ? `${queuedFileCount} 个文件` : `${queuedFileCount} files`,
                    stage:'queued',
                    progress:100,
                    startedAt: Date.now(),
                    sourceType:'queue_upload',
                    fileSizeMb: totalFileSizeMb(selectedFiles),
                    queueTotal: queuedFileCount,
                    queueItems,
                    queueUpload: true,
                    queueSubmitted: true,
                });
                navigate('/agent', {replace:true, state:{queueSubmittedAt: Date.now()}});
            } catch(err) {
                setCurrentJob(null);
                navigate('/agent', {
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
                setDragActive(false);
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
    const sttProfile = currentJob?.sourceType === 'transcript_file'
        ? '-'
        : [
            isCloudSttProvider(currentJob?.sttProvider) ? 'cloud' : 'local',
            currentJob?.sttModel||DEFAULT_STT_MODEL,
            currentJob?.sttSpeed||'balanced',
            currentJob?.sttLanguage||'auto',
        ].join(' / ');
    const sttProgressPct = Math.round(sttProgressFraction(currentJob) * 100);
    const sttProgressUnknown = isSttProgressUnmeasured(currentJob);
    const hasSttTiming = currentJob?.stage === 'stt' && currentJob?.durationSeconds > 0 && !sttProgressUnknown;
    const sttElapsedForHint = Math.max(elapsedSec, Number(currentJob?.sttElapsedSeconds) || 0);
    const sttWaitedLong = sttProgressUnknown && !isCloudSttProvider(currentJob?.sttProvider) && sttElapsedForHint >= 60;
    const linkPlatforms = [
        '抖音',
        'Bilibili',
        'YouTube',
        'TikTok',
        '小红书',
        '快手',
        lang === 'zh' ? '视频直链' : 'Direct video',
    ];
    const taskInfoCards = [
        ...(currentJob?.guestTrial && currentJob?.queue
            ? [
                {label: lang === 'zh' ? '前方任务' : 'Ahead', value: `${currentJob.queue.people_ahead ?? 0}`},
                {label: lang === 'zh' ? '等待预估' : 'Wait', value: estimateText(currentJob.queue) || '-'},
            ]
            : []),
        {label:t('dash.elapsed'), value:fmtElapsed(elapsedSec)},
        {label:t('dash.fileSize'), value:fmtFileSize(currentJob?.fileSizeMb)},
        ...(isCloudSttProvider(currentJob?.sttProvider) && currentJob?.cloudAudioSizeMb != null
            ? [{label:t('dash.cloudUploadAudio'), value:fmtFileSize(currentJob.cloudAudioSizeMb)}]
            : []),
        {label:t('dash.modelProfile'), value:sttProfile},
        {label:t('dash.summaryMode'), value:currentJob?.skipSummary?t('dash.summaryOff'):`${t('dash.summaryOn')} / ${noteModeLabel(currentJob?.noteMode, lang)}`},
    ];

            return (
            <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
                <section className="mx-auto h-dvh max-w-[1500px] overflow-y-auto px-8 py-10 hide-scrollbar">
                    <input ref={fileInputRef} type="file" multiple accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.flac,.aac,.ogg,.m4a,.wma,.opus" onChange={handleFileSelect} className="hidden"/>
                    <input ref={subtitleInputRef} type="file" accept=".srt,.vtt,.txt,.md,text/plain,text/markdown" onChange={handleSubtitleSelect} className="hidden"/>

                    <header className="mb-10 text-center">
                        <div className="flex items-center justify-center gap-2 text-[1.25rem] font-semibold leading-tight tracking-normal text-[#050505] sm:text-[1.5rem] lg:text-[1.7rem] dark:text-white">
                            <SvgIcon name="hand" className="h-6 w-6 shrink-0 -rotate-12 sm:h-7 sm:w-7 lg:h-8 lg:w-8" style={{strokeWidth: 2.4}}/>
                            <span>{lang === 'zh' ? '你好' : 'Hi'}</span>
                        </div>
                        <h1 className="mt-2.5 text-[1.5rem] font-semibold leading-[1.1] tracking-normal text-[#050505] sm:mt-3 sm:text-[2rem] lg:text-[2.45rem] dark:text-white">
                            {lang === 'zh' ? '今天想记录些什么呢？' : 'What do you want to record today?'}
                        </h1>
                    </header>

                    <div className="grid gap-5">
                        <Link
                            to="/media-text?mode=media"
                            onDrop={handleDrop}
                            onDragOver={(e) => e.preventDefault()}
                            onDragEnter={(e) => { e.preventDefault(); setDragActive(true); }}
                            onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
                            className={`group relative block min-h-[19rem] overflow-hidden rounded-[24px] border bg-white p-7 text-[#111111] shadow-[0_26px_70px_-46px_rgba(17,17,17,.5)] transition hover:-translate-y-0.5 dark:bg-[#1d1f22] dark:text-white dark:shadow-[0_24px_80px_rgba(0,0,0,0.32)] ${dragActive ? 'border-[#00aeec] ring-2 ring-[#00aeec]/45' : 'border-[#dedada] dark:border-white/[0.12]'}`}
                        >
                            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_14%,rgba(0,174,236,.14),transparent_32%),radial-gradient(circle_at_82%_10%,rgba(255,0,51,.08),transparent_28%),radial-gradient(circle_at_44%_105%,rgba(151,231,211,.12),transparent_34%)] dark:bg-[radial-gradient(circle_at_18%_14%,rgba(0,174,236,.18),transparent_34%),radial-gradient(circle_at_82%_10%,rgba(255,0,51,.12),transparent_30%),radial-gradient(circle_at_42%_108%,rgba(151,231,211,.12),transparent_36%)]"/>
                            <div className="pointer-events-none absolute inset-0 bg-white/72 dark:bg-[#1d1f22]/78"/>
                            <div className="relative flex h-full flex-col gap-6 md:flex-row md:items-stretch md:justify-between">
                                <div className="flex min-w-0 flex-1 flex-col justify-between">
                                    <div>
                                        <span className="inline-flex rounded-[0.3rem] bg-[#eef1f5] px-2.5 py-1 text-[0.74rem] font-bold tracking-wide text-[#39424f] dark:bg-white/[0.12] dark:text-white/90">MEDIA</span>
                                        <h3 className="mt-3 text-[1.7rem] font-semibold leading-[1.05] tracking-[-0.01em]">{lang === 'zh' ? '音视频转写' : 'Media transcription'}</h3>
                                        <p className="mt-2.5 max-w-[26rem] text-[0.9rem] leading-6 text-[#666] dark:text-white/85">
                                            {lang === 'zh' ? '把视频拖到这里直接转写，或点击上传文件、粘贴平台链接，自动生成转录与 AI 笔记。' : 'Drop a video here to transcribe it, or click to upload a file or paste a platform link — transcripts and AI notes, automatically.'}
                                        </p>
                                    </div>
                                    <div className="mt-5 flex flex-wrap gap-1.5">
                                        {linkPlatforms.slice(0, 4).map((platform) => (
                                            <span key={platform} className="rounded-[0.3rem] border border-[#dedada] bg-[#f4f3f3] px-2.5 py-1 text-[0.74rem] font-medium text-[#555] dark:border-white/[0.18] dark:bg-white/[0.08] dark:text-white/85">{platform}</span>
                                        ))}
                                    </div>
                                </div>
                                <div className="flex shrink-0 flex-col items-center justify-center gap-3 rounded-[18px] border border-dashed border-[#cfcaca] bg-white/50 px-10 py-9 text-center md:w-[320px] dark:border-white/[0.18] dark:bg-white/[0.04]">
                                    <svg viewBox="0 0 24 24" className="h-10 w-10 text-[#333] dark:text-white/90" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 15V4M12 4l-4 4M12 4l4 4"/><path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"/></svg>
                                    <span className="text-[0.9rem] font-bold text-[#333] dark:text-white/90">{dragActive ? (lang === 'zh' ? '松手开始转写' : 'Drop to transcribe') : (lang === 'zh' ? '拖入视频 / 点击选择' : 'Drop a video / click to pick')}</span>
                                </div>
                            </div>
                        </Link>
                    </div>

                    {(uploadError || processingResult) && (
                        <div className="mt-5 space-y-3">
                            {uploadError && <div className="rounded-[16px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300">{uploadError}</div>}
                            {processingResult && (
                                <div className="rounded-[16px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300">
                                    {processingResult.source==='transcript_file' ? t('dash.subtitleDone') : t('dash.done')} <button onClick={()=>navigate("/editor")} className="underline hover:no-underline">{t('dash.viewEditor')}</button>
                                </div>
                            )}
                        </div>
                    )}

                    {uploading && currentJob && (
                        <section className="mt-6 rounded-[24px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                                <div className="min-w-0">
                                    <span className="inline-flex rounded-full bg-[#efeeee] px-3 py-1 text-[12px] font-bold text-[#111111] dark:bg-white/[0.12] dark:text-white">{t('dash.activeTask')}</span>
                                    <h3 className="mt-3 truncate font-headline text-[24px] font-extrabold leading-tight text-[#111111] dark:text-white">{currentJob.fileName}</h3>
                                    <p className="mt-2 text-[14px] font-medium leading-6 text-[#666] dark:text-white/55">
                                        {currentJob.guestTrial && currentJob.stage === 'queued'
                                            ? (lang==='zh'?'文件已进入访客试用队列，开始处理后会自动更新进度。':'Your file is in the guest trial queue. Progress updates automatically when processing starts.')
                                            : currentJob.sourceType === 'video_link'
                                                ? t('dash.linkQueued')
                                                : t('dash.waitingForTranscript')}
                                    </p>
                                </div>
                                <div className="flex shrink-0 flex-wrap gap-2">
                                    {!guestMode && (
                                        <button onClick={()=>fileInputRef.current?.click()} disabled={queueSubmitting} className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 text-xs font-bold text-[#111111] hover:bg-[#efeeee] disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.09]">
                                            <SvgIcon name={queueSubmitting ? 'sync' : 'playlist-add'} className={`h-4 w-4 ${queueSubmitting ? 'animate-spin' : ''}`}/>
                                            {queueSubmitting ? (lang==='zh'?'添加中…':'Adding…') : (lang==='zh'?'添加到队列':'Add to queue')}
                                        </button>
                                    )}
                                    {currentJob.resume && !currentJob.guestTrial ? (
                                        <Link to="/agent" className="inline-flex h-10 items-center gap-2 rounded-[14px] bg-[#111111] px-3 text-xs font-bold text-white hover:bg-[#2a2a2a] dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
                                            <SvgIcon name="monitoring" className="h-4 w-4"/>{t('dash.viewTasks')}
                                        </Link>
                                    ) : (
                                        <button onClick={handleCancel} className="inline-flex h-10 items-center gap-2 rounded-[14px] border border-red-200 bg-red-50 px-3 text-xs font-bold text-red-600 hover:bg-red-100 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20">
                                            <SvgIcon name="close" className="h-4 w-4"/>{t('dash.cancelTask')}
                                        </button>
                                    )}
                                </div>
                            </div>
                            <div className="mt-5">
                                <div className="mb-2 flex items-end justify-between gap-4">
                                    <div>
                                        <p className="text-[12px] font-bold text-[#777] dark:text-white/55">{t('dash.currentStage')}</p>
                                        <p className="text-[18px] font-extrabold text-[#111111] dark:text-white">{activeStageLabel}</p>
                                    </div>
                                    <p className="font-headline text-[28px] font-extrabold tabular-nums text-[#111111] dark:text-white">{jobProgressLabel(currentJob, t)}</p>
                                </div>
                                <div className={`h-2.5 w-full overflow-hidden rounded-full bg-[#efeeee] dark:bg-white/[0.12] ${sttProgressUnknown ? 'progress-indeterminate' : ''}`}>
                                    {!sttProgressUnknown && <div className="h-full rounded-full bg-[#111111] transition-all duration-700 dark:bg-white" style={{width:`${activeProgress}%`}}></div>}
                                </div>
                                {currentJob.stage === 'stt' && (
                                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-[#666] dark:text-white/55">
                                        <span>
                                            {hasSttTiming
                                                ? `${t('dash.transcribedTo')}: ${fmtElapsed(currentJob.transcribedSeconds||0)} / ${fmtElapsed(currentJob.durationSeconds||0)}`
                                                : sttStatusLabel(currentJob.sttStatus, t)}
                                        </span>
                                        <span className="font-extrabold text-[#111111] dark:text-white">{sttProgressUnknown ? t('dash.sttMeasuring') : `STT ${sttProgressPct}%`}</span>
                                        {sttWaitedLong && <span className="basis-full text-[11px] leading-snug text-amber-700 dark:text-amber-300">{t('dash.sttNoProgressHint')}</span>}
                                    </div>
                                )}
                            </div>
                            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                                {taskInfoCards.map((item) => (
                                    <div key={item.label} className="min-w-0 rounded-[18px] bg-[#f4f3f3] p-3 dark:bg-white/[0.08]">
                                        <p className="mb-1 text-[11px] font-bold text-[#777] dark:text-white/55">{item.label}</p>
                                        <p className="truncate text-sm font-extrabold text-[#111111] dark:text-white">{item.value}</p>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    <section className="mt-8">
                        <div className="mb-4 flex items-center justify-between">
                            <div>
                                <h3 className="font-headline text-[24px] font-extrabold text-[#111111] dark:text-white">{t('dash.recent')}</h3>
                                <p className="mt-1 text-sm font-medium text-[#777] dark:text-white/55">{lang === 'zh' ? '最近完成和处理中任务会显示在这里。' : 'Recent completed and active tasks appear here.'}</p>
                            </div>
                            <Link to="/agent" className="rounded-full bg-[#efeeee] px-4 py-2 text-xs font-extrabold text-[#111111] hover:bg-[#e8e5e5] dark:bg-white/[0.12] dark:text-white dark:hover:bg-white/[0.18]">{t('dash.viewAll')}</Link>
                        </div>
                        <div className="rounded-[24px] border border-[#e4e0e0] bg-white p-4 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                            {history.length === 0 ? (
                                <div className="rounded-[18px] bg-[#f4f3f3] px-4 py-12 text-center text-sm font-semibold text-[#777] dark:bg-white/[0.08] dark:text-white/55">{t('dash.noActivity')}</div>
                            ) : (
                                <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                                    {history.slice(0,6).map(h => {
                                        const historyDone = h.status === 'completed';
                                        const historyProcessing = h.status === 'processing';
                                        return (
                                            <div key={h.id} className="flex cursor-pointer items-start gap-3 rounded-[18px] bg-[#f4f3f3] p-3 transition hover:bg-[#efeeee] dark:bg-white/[0.08] dark:hover:bg-white/[0.12]" onClick={() => openHistoryEntry(h)}>
                                                <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] ${historyDone?'bg-white dark:bg-white/[0.16]':historyProcessing?'bg-white dark:bg-white/[0.16]':'bg-red-50 dark:bg-red-500/10'}`}>
                                                    <SvgIcon name={historyDone ? 'check-circle' : historyProcessing ? 'sync' : 'error'} className={`h-5 w-5 ${historyProcessing ? 'animate-spin' : ''} ${historyDone?'text-[#111111] dark:text-white':historyProcessing?'text-[#111111] dark:text-white':'text-red-500 dark:text-red-300'}`}/>
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <div className="mb-1 flex items-start justify-between gap-2">
                                                        <h5 className="min-w-0 flex-1 truncate pr-2 text-sm font-extrabold text-[#111111] dark:text-white">{h.name}</h5>
                                                        <span className={`inline-flex shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-bold ${historyDone?'bg-white text-[#111111] dark:bg-white/[0.16] dark:text-white':historyProcessing?'bg-white text-[#111111] dark:bg-white/[0.16] dark:text-white':'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300'}`}>
                                                            {t(historyDone?'dash.statusCompleted':historyProcessing?'dash.statusProcessing':'dash.statusFailed')}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs font-medium leading-5 text-[#777] dark:text-white/55">
                                                        {timeAgo(h.timestamp, t)}
                                                        {h.durationMin > 0 && ` • ${h.durationMin} ${t('dash.minUnit')}`}
                                                        {h.sttElapsedSec > 0 && ` • ${t('edit.sttElapsed')} ${fmtElapsed(h.sttElapsedSec)}`}
                                                        {h.sttElapsedSec > 0 && h.audioDurationSec > 0 && ` (${fmtSttRelative(h.sttElapsedSec / h.audioDurationSec, lang)})`}
                                                        {h.sttModel && ` • STT ${[h.sttModel,h.sttSpeed,h.sttLanguage].filter(Boolean).join('/')}`}
                                                        {h.larkUrl && <> • <a href={h.larkUrl} target="_blank" rel="noopener noreferrer" className="font-bold text-[#111111] hover:underline dark:text-white" onClick={e=>e.stopPropagation()}>Lark</a></>}
                                                    </p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </section>
                </section>
            </div>
            );
        };

/* Legacy history route lives in frontend/src/routes/tasks.jsx; primary record UI is /agent. */

/* ═══════════════ Processing ═══════════════ */

export default Dashboard;
