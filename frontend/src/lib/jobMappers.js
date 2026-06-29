import { displayTitleForUser } from './format.js';
import {
    normalizeJobPayload,
    normalizeResultPayload,
} from './resultSchema.js';
import {
    normalizeTaskState,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_QUEUED,
    TASK_STATE_RUNNING,
} from './taskState.js';

export const accountJobsCacheKey = (accountId) => `fluentflow_account_jobs_cache_${accountId || 'local'}`;

const compactTextForCache = (value, maxChars=240) => (
    value ? String(value).slice(0, maxChars) : ''
);

const minimizeJobForCache = (job) => {
    if (!job || typeof job !== 'object') return null;
    const {__cacheOnly, ...persistedJob} = job;
    const result = job.result && typeof job.result === 'object' ? job.result : null;
    return {
        ...persistedJob,
        result: result ? {
            ...result,
            transcript_text_preview: result.transcript_text_preview || compactTextForCache(result.transcript_text),
            transcript_text: compactTextForCache(result.transcript_text),
            summary_markdown: compactTextForCache(result.summary_markdown),
            segments: [],
            cleaned_segments: null,
            raw_segments: null,
            translated_segments_zh: null,
            raw_transcript_text: null,
            cleaned_transcript_text: null,
        } : result,
    };
};

export const readCachedAccountJobs = (accountId) => {
    try {
        const parsed = JSON.parse(localStorage.getItem(accountJobsCacheKey(accountId)) || '{}');
        const jobs = Array.isArray(parsed?.jobs) ? parsed.jobs : [];
        return jobs.filter((job) => job && typeof job === 'object');
    } catch(_) {
        return [];
    }
};

export const writeCachedAccountJobs = (accountId, jobs) => {
    try {
        const compactJobs = (Array.isArray(jobs) ? jobs : [])
            .map(minimizeJobForCache)
            .filter(Boolean)
            .slice(0, 100);
        localStorage.setItem(accountJobsCacheKey(accountId), JSON.stringify({
            updatedAt: Date.now(),
            jobs: compactJobs,
        }));
    } catch(_) {}
};

export const mergeCachedJobs = (...groups) => {
    const seen = new Set();
    const merged = [];
    groups.flat().forEach((job) => {
        if (!job || typeof job !== 'object') return;
        const key = String(job.task_id || job.result?.task_id || '').trim();
        if (!key || seen.has(key)) return;
        seen.add(key);
        merged.push(job);
    });
    return merged;
};

export const hasTranscriptResult = (result={}) => {
    const normalized = normalizeResultPayload(result);
    return !!(
        String(normalized.transcript_text || '').trim()
        || String(normalized.transcript_text_preview || '').trim()
        || (Array.isArray(normalized.raw_segments) && normalized.raw_segments.length > 0)
        || (Array.isArray(normalized.display_segments) && normalized.display_segments.length > 0)
    );
};

export const historyStatusFromJob = (job={}) => {
    const normalizedJob = normalizeJobPayload(job);
    const result = normalizedJob.result || {};
    const taskState = normalizedJob.task_state || normalizeTaskState(normalizedJob);
    if (hasTranscriptResult(result)) return TASK_STATE_COMPLETED;
    if (taskState === TASK_STATE_QUEUED || taskState === TASK_STATE_RUNNING) return 'processing';
    return taskState === TASK_STATE_COMPLETED ? TASK_STATE_COMPLETED : (normalizedJob.status || taskState || TASK_STATE_FAILED);
};

export const jobVisibleInHistory = (job={}) => !!(job?.task_id || job?.result);

export const resultDisplayTitle = (result={}, fallback={}) => {
    const normalized = normalizeResultPayload(result);
    return displayTitleForUser(
        normalized.display_title || fallback.displayTitle || normalized.raw_title || fallback.rawTitle || normalized.filename || fallback.name,
        normalized.filename || fallback.rawFilename || fallback.name,
    );
};

export const jobDisplayTitle = (job={}, lang='zh') => {
    const normalizedJob = normalizeJobPayload(job);
    const result = normalizedJob.result || {};
    const metadata = normalizedJob.metadata || {};
    const videoSource = metadata.video_source || {};
    const title = displayTitleForUser(
        metadata.display_title
            || videoSource.display_title
            || result.display_title
            || metadata.raw_title
            || videoSource.raw_title
            || videoSource.title
            || result.raw_title
            || normalizedJob.source_filename
            || result.filename,
        normalizedJob.source_filename || result.filename,
    );
    return title || (lang === 'zh' ? '未命名任务' : 'Untitled task');
};

export const resultToHistoryEntry = (sourceResult, fallback={}) => {
    const result = normalizeResultPayload(sourceResult);
    const durSec = result.audio_duration_seconds || 0;
    const hasTranscript = hasTranscriptResult(result);
    const displayTitle = resultDisplayTitle(result, fallback);
    const rawTitle = result.raw_title || fallback.rawTitle || result.filename || fallback.name || 'Untitled';
    const rawFilename = result.filename || fallback.rawFilename || fallback.name || '';
    const segments = result.raw_segments || [];
    return {
        id: fallback.id || Date.now(),
        taskId: result.task_id || fallback.taskId,
        name: displayTitle || rawTitle,
        displayTitle: displayTitle || rawTitle,
        rawTitle,
        rawFilename,
        timestamp: fallback.timestamp || Date.now(),
        durationMin: Math.round(durSec/60*10)/10,
        status: hasTranscript ? 'completed' : (fallback.status || (result.status === 'completed' ? 'completed' : (result.status || 'failed'))),
        transcriptText: result.transcript_text||result.transcript_text_preview||'',
        segments,
        displaySegments: result.display_segments || [],
        summary: result.summary_markdown||'',
        summarySkipped: !!result.summary_skipped,
        summaryStatus: result.summary_status||null,
        summaryError: result.summary_error||null,
        larkUrl: result.lark_response?.url || null,
        larkError: result.lark_error||null,
        audioDurationSec: durSec,
        sttElapsedSec: result.stt_elapsed_seconds||0,
        sttRealtimeFactor: result.stt_realtime_factor||null,
        sttProvider: result.stt_provider||null,
        sttProviderLabel: result.stt_provider_label||null,
        sttModel: result.stt_model||null,
        sttSpeed: result.stt_speed||null,
        sttLanguage: result.stt_language||null,
        detectedLanguage: result.detected_language||null,
        sourceLanguage: result.source_language||null,
        subtitleMode: result.subtitle_mode||null,
        bilingualSegments: Array.isArray(result.bilingual_segments) ? result.bilingual_segments : [],
        translatedSegmentsZh: Array.isArray(result.translated_segments_zh) ? result.translated_segments_zh : [],
        translationStatus: result.translation_status||null,
        translationError: result.translation_error||null,
        sourceFingerprint: result.source_fingerprint||null,
        originalTaskId: result.original_task_id||fallback.originalTaskId||null,
        rawTranscriptText: result.raw_transcript_text||null,
        cleanedTranscriptText: result.cleaned_transcript_text||null,
        cleanedSegments: result.cleaned_segments||null,
        rawSegments: result.raw_segments||null,
        transcriptCleanup: result.transcript_cleanup||null,
        transcriptEdited: !!result.transcript_edited,
        transcriptEditedAt: result.transcript_edited_at||null,
        editedTranscriptPath: result.edited_transcript_path||null,
        editedTranscriptSavedAt: result.edited_transcript_saved_at||null,
        transcriptEditRecords: result.transcript_edit_records||[],
        transcriptEditRecordsPath: result.transcript_edit_records_path||null,
        artifacts: result.artifacts||null,
        playbackAudioAvailable: !!result.playback_audio_available,
        playbackAudioStorage: result.playback_audio_storage||null,
        requestedNoteMode: result.requested_note_mode||fallback.requestedNoteMode||null,
        resolvedNoteMode: result.resolved_note_mode||null,
        noteModeChunkCount: result.note_mode_chunk_count||null,
        noteModeSegmentCount: result.note_mode_segment_count||null,
        noteModeEvidenceCount: result.note_mode_evidence_count||null,
        noteModeChapterCount: result.note_mode_chapter_count||null,
        noteModeImportantEvidenceCount: result.note_mode_important_evidence_count||null,
        noteModeCoveredImportantEvidenceCount: result.note_mode_covered_important_evidence_count||null,
        noteModeCoverageMissingCount: result.note_mode_coverage_missing_count||null,
        noteModePlanReason: result.note_mode_plan_reason||null,
        noteModePlanConfidence: result.note_mode_plan_confidence||null,
        noteModePlanWarnings: Array.isArray(result.note_mode_plan_warnings) ? result.note_mode_plan_warnings : [],
        noteModePlanProvider: result.note_mode_plan_provider||null,
        noteModePlanModel: result.note_mode_plan_model||null,
        noteModePlanFallback: result.note_mode_plan_fallback ?? null,
        noteModePlanError: result.note_mode_plan_error||null,
        noteModePlanSelectedMode: result.note_mode_plan_selected_mode||null,
        processingPlan: result.processing_plan||null,
        toolTrace: result.tool_trace||null,
        promptPreset: result.prompt_preset||fallback.promptPreset||null,
        promptPresetLabel: result.prompt_preset_label||fallback.promptPresetLabel||null,
        source: result.source||fallback.source||null,
        sourceFileAvailable: !!result.source_file_available,
    };
};

export const jobToHistoryEntry = (sourceJob) => {
    const job = normalizeJobPayload(sourceJob);
    const result = job.result || {};
    const entry = resultToHistoryEntry(result, {
        taskId: job.task_id,
        name: jobDisplayTitle(job),
        displayTitle: jobDisplayTitle(job),
        rawTitle: job.metadata?.raw_title || job.metadata?.video_source?.raw_title || job.source_filename,
        rawFilename: job.source_filename,
        timestamp: Date.parse(job.updated_at || job.created_at || '') || Date.now(),
        status: historyStatusFromJob(job),
        source: job.source_type,
    });
    return {
        ...entry,
        status: historyStatusFromJob(job),
        taskState: job.task_state,
        summaryStatus: result.summary_status || job.summary_status || entry.summaryStatus,
        summaryError: result.summary_error || job.error_reason || entry.summaryError,
    };
};

export const jobToCurrentJob = (sourceJob) => {
    const job = normalizeJobPayload(sourceJob);
    return {
        taskId: job.task_id,
        fileName: jobDisplayTitle(job),
        stage: job.stage || 'upload',
        taskState: job.task_state,
        progress: job.progress ?? 0,
        startedAt: Date.parse(job.created_at || '') || Date.now(),
        sourceType: job.source_type || null,
        fileSizeMb: job.source_file_size_mb || null,
        resume: true,
        sttProvider: job.metadata?.stt_provider || job.result?.stt_provider || null,
        sttProgress: job.metadata?.stt_progress,
        transcribedSeconds: job.metadata?.transcribed_seconds,
        durationSeconds: job.metadata?.duration_seconds,
        sttElapsedSeconds: job.metadata?.stt_elapsed_seconds,
        sttStatus: job.metadata?.stt_status,
        azureBatchAudioSizeMb: job.metadata?.elevenlabs_audio_size_mb ?? job.metadata?.azure_batch_audio_size_mb,
    };
};

export const historyEntryToResult = (h) => h ? normalizeResultPayload({
    task_id: h.taskId,
    source: h.source||null,
    transcript_text: h.transcriptText,
    segments: h.segments,
    summary_markdown: h.summary,
    summary_skipped: !!h.summarySkipped,
    summary_status: h.summaryStatus||null,
    summary_error: h.summaryError||null,
    filename: h.rawFilename || h.name,
    raw_title: h.rawTitle || h.rawFilename || h.name,
    display_title: h.displayTitle || displayTitleForUser(h.name, h.rawFilename),
    audio_duration_seconds: h.audioDurationSec,
    stt_elapsed_seconds: h.sttElapsedSec||0,
    stt_realtime_factor: h.sttRealtimeFactor||null,
    stt_provider: h.sttProvider||null,
    stt_provider_label: h.sttProviderLabel||null,
    stt_model: h.sttModel||null,
    stt_speed: h.sttSpeed||null,
    stt_language: h.sttLanguage||null,
    detected_language: h.detectedLanguage||null,
    source_language: h.sourceLanguage||null,
    subtitle_mode: h.subtitleMode||null,
    display_segments: h.displaySegments||[],
    bilingual_segments: h.bilingualSegments||[],
    translated_segments_zh: h.translatedSegmentsZh||[],
    translation_status: h.translationStatus||null,
    translation_error: h.translationError||null,
    source_fingerprint: h.sourceFingerprint||null,
    raw_transcript_text: h.rawTranscriptText||null,
    cleaned_transcript_text: h.cleanedTranscriptText||null,
    cleaned_segments: h.cleanedSegments||null,
    raw_segments: h.rawSegments||null,
    transcript_cleanup: h.transcriptCleanup||null,
    transcript_edited: !!h.transcriptEdited,
    transcript_edited_at: h.transcriptEditedAt||null,
    edited_transcript_path: h.editedTranscriptPath||null,
    edited_transcript_saved_at: h.editedTranscriptSavedAt||null,
    transcript_edit_records: h.transcriptEditRecords||[],
    transcript_edit_records_path: h.transcriptEditRecordsPath||null,
    artifacts: h.artifacts||null,
    playback_audio_available: !!h.playbackAudioAvailable,
    playback_audio_storage: h.playbackAudioStorage||null,
    requested_note_mode: h.requestedNoteMode||null,
    resolved_note_mode: h.resolvedNoteMode||null,
    note_mode_chunk_count: h.noteModeChunkCount||null,
    note_mode_segment_count: h.noteModeSegmentCount||null,
    note_mode_evidence_count: h.noteModeEvidenceCount||null,
    note_mode_chapter_count: h.noteModeChapterCount||null,
    note_mode_important_evidence_count: h.noteModeImportantEvidenceCount||null,
    note_mode_covered_important_evidence_count: h.noteModeCoveredImportantEvidenceCount||null,
    note_mode_coverage_missing_count: h.noteModeCoverageMissingCount||null,
    note_mode_plan_reason: h.noteModePlanReason||null,
    note_mode_plan_confidence: h.noteModePlanConfidence||null,
    note_mode_plan_warnings: h.noteModePlanWarnings||[],
    note_mode_plan_provider: h.noteModePlanProvider||null,
    note_mode_plan_model: h.noteModePlanModel||null,
    note_mode_plan_fallback: h.noteModePlanFallback ?? null,
    note_mode_plan_error: h.noteModePlanError||null,
    note_mode_plan_selected_mode: h.noteModePlanSelectedMode||null,
    processing_plan: h.processingPlan||null,
    tool_trace: h.toolTrace||null,
    prompt_preset: h.promptPreset||null,
    prompt_preset_label: h.promptPresetLabel||null,
    source_file_available: !!h.sourceFileAvailable,
    imported_from_local_history: h.source === 'imported_local_history' || h.source === 'browser_local_history' || String(h.taskId || '').startsWith('imported_'),
}) : null;
