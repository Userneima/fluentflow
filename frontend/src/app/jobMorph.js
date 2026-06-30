export { accountJobsCacheKey, readCachedAccountJobs, writeCachedAccountJobs, cacheJobRecord, mergeCachedJobs, sortJobsForHistoryView, hasTranscriptResult, historyStatusFromJob, jobVisibleInHistory, resultDisplayTitle, jobDisplayTitle, resultToHistoryEntry, jobToHistoryEntry, jobToCurrentJob, historyEntryToResult } from '../lib/jobMappers.js';
export {
    SENSITIVE_SETTING_KEYS,
    LEGACY_REMOVED_SETTING_KEYS,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    SUPPORTED_FRONTEND_NOTE_MODES,
    NOTE_MODE_OPTIONS,
    LARK_EXPORT_ROUTE_OPENAPI,
    LARK_EXPORT_ROUTE_LOCAL_CLI,
    normalizeLarkExportRoute,
    larkExportRouteFromSettings,
    isLocalLarkExportRoute,
    normalizeAiModel,
    sanitizeSettings,
    sensitivePatchFromSettings,
    noteModeLabel,
    DEFAULT_STT_MODEL,
    DEFAULT_STT_PROVIDER,
    normalizeSttProvider,
    isElevenLabsCloudProvider,
    isAzureCloudProvider,
    isCloudSttProvider,
    isAzureSpeechConfigured,
    isAzureBatchConfigured,
    isCloudSttConfigured,
    DEFAULT_RUNTIME_CONFIG,
    normalizeRuntimeConfig,
    effectiveSttProvider,
    cloudSttMissingMessage,
    azureSpeechMissingMessage,
    normalizeSttModel,
} from '../lib/settingsModel.js';

export const createTaskId = () => (
    window.crypto?.randomUUID?.() ||
    `task_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
);
