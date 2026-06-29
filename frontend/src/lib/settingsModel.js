export const SENSITIVE_SETTING_KEYS = ['deepseekApiKey', 'openaiApiKey', 'larkAppId', 'larkAppSecret', 'elevenLabsApiKey', 'azureSpeechKey', 'azureSpeechEndpoint', 'azureBlobContainerSasUrl'];
export const LEGACY_REMOVED_SETTING_KEYS = ['hotwordLibrary', 'hotwordLibraries', 'reviewMode', 'reviewUseAi'];
export const DEFAULT_DEEPSEEK_MODEL = 'deepseek-reasoner';
export const DEFAULT_OPENAI_MODEL = 'gpt-5.4-mini';
export const SUPPORTED_FRONTEND_NOTE_MODES = new Set(['auto', 'direct', 'high_fidelity', 'chapter_coverage']);
export const NOTE_MODE_OPTIONS = [
    {value: 'auto', labelEn: 'Auto', labelZh: '自动选择'},
    {value: 'direct', labelEn: 'Direct context', labelZh: '直接上下文'},
    {value: 'high_fidelity', labelEn: 'High-fidelity', labelZh: '高保真笔记'},
    {value: 'chapter_coverage', labelEn: 'Chapter coverage', labelZh: '完整覆盖笔记'},
];

export const LARK_EXPORT_ROUTE_OPENAPI = 'openapi';
export const LARK_EXPORT_ROUTE_LOCAL_CLI = 'local_cli';

export const normalizeLarkExportRoute = (value, legacyViaCli=false) => {
    const route = String(value || '').trim();
    if (route === LARK_EXPORT_ROUTE_LOCAL_CLI || route === 'lark_cli') return LARK_EXPORT_ROUTE_LOCAL_CLI;
    if (route === LARK_EXPORT_ROUTE_OPENAPI || route === 'lark_openapi') return LARK_EXPORT_ROUTE_OPENAPI;
    return legacyViaCli ? LARK_EXPORT_ROUTE_LOCAL_CLI : LARK_EXPORT_ROUTE_OPENAPI;
};

export const larkExportRouteFromSettings = (settings={}) => (
    normalizeLarkExportRoute(settings.larkExportRoute, !!settings.larkViaCli)
);

export const isLocalLarkExportRoute = (route) => normalizeLarkExportRoute(route) === LARK_EXPORT_ROUTE_LOCAL_CLI;

export const normalizeAiModel = (provider, model) => {
    const p = provider === 'openai' ? 'openai' : 'deepseek';
    const value = String(model || '').trim();
    if (p === 'openai') {
        return value && value.startsWith('gpt-') ? value : DEFAULT_OPENAI_MODEL;
    }
    return value && value !== 'deepseek-chat' ? value : DEFAULT_DEEPSEEK_MODEL;
};

export const sanitizeSettings = (settings={}) => {
    const next = {...settings};
    SENSITIVE_SETTING_KEYS.forEach((key) => delete next[key]);
    LEGACY_REMOVED_SETTING_KEYS.forEach((key) => delete next[key]);
    const provider = next.aiProvider === 'openai' ? 'openai' : 'deepseek';
    next.aiProvider = provider;
    next.aiModel = normalizeAiModel(provider, next.aiModel);
    if (!SUPPORTED_FRONTEND_NOTE_MODES.has(next.noteMode)) {
        next.noteMode = 'auto';
    }
    next.larkExportRoute = larkExportRouteFromSettings(next);
    next.larkViaCli = isLocalLarkExportRoute(next.larkExportRoute);
    return next;
};

export const sensitivePatchFromSettings = (settings={}) => ({
    deepseek_api_key: settings.deepseekApiKey || '',
    openai_api_key: settings.openaiApiKey || '',
    lark_app_id: settings.larkAppId || '',
    lark_app_secret: settings.larkAppSecret || '',
    elevenlabs_api_key: settings.elevenLabsApiKey || '',
    azure_speech_key: settings.azureSpeechKey || '',
    azure_speech_endpoint: settings.azureSpeechEndpoint || '',
    azure_blob_container_sas_url: settings.azureBlobContainerSasUrl || '',
});

export const noteModeLabel = (mode, lang) => {
    const found = NOTE_MODE_OPTIONS.find((item) => item.value === (mode || 'auto'));
    return found ? (lang === 'zh' ? found.labelZh : found.labelEn) : (mode || 'auto');
};

export const DEFAULT_STT_MODEL = 'medium';
export const DEFAULT_STT_PROVIDER = 'elevenlabs_scribe';

export const normalizeSttProvider = (provider) => {
    const value = String(provider || '').trim().toLowerCase().replace(/-/g, '_');
    if (value === 'local') return 'local';
    if (value === 'cloud' || value === 'cloud_stt' || value === 'elevenlabs' || value === 'elevenlabs_scribe' || value === 'scribe' || value === 'scribe_v2') return 'elevenlabs_scribe';
    if (value === 'azure_batch') return 'azure_batch';
    return DEFAULT_STT_PROVIDER;
};

export const isElevenLabsCloudProvider = (provider) => (
    normalizeSttProvider(provider) === 'elevenlabs_scribe'
);

export const isAzureCloudProvider = (provider) => (
    normalizeSttProvider(provider) === 'azure_batch'
);

export const isCloudSttProvider = (provider) => (
    normalizeSttProvider(provider) !== 'local'
);

const isElevenLabsConfigured = (status) => (
    !!status?.elevenlabs_api_key_configured
);

export const isAzureSpeechConfigured = (status) => (
    !!status?.azure_speech_endpoint_configured && !!status?.azure_speech_key_configured
);

export const isAzureBatchConfigured = (status) => (
    isAzureSpeechConfigured(status) && !!status?.azure_blob_container_sas_url_configured
);

export const isCloudSttConfigured = (provider, status) => (
    isElevenLabsCloudProvider(provider)
        ? isElevenLabsConfigured(status)
        : (isAzureCloudProvider(provider) ? isAzureBatchConfigured(status) : true)
);

export const DEFAULT_RUNTIME_CONFIG = {
    publicMode: false,
    allowedSttProviders: ['elevenlabs_scribe', 'local'],
    defaultSttProvider: DEFAULT_STT_PROVIDER,
    showMaintainerSettings: true,
    guestTrial: {enabled: false},
};

export const normalizeRuntimeConfig = (config={}) => {
    const allowed = Array.isArray(config.allowed_stt_providers)
        ? config.allowed_stt_providers.map(normalizeSttProvider)
        : DEFAULT_RUNTIME_CONFIG.allowedSttProviders;
    const uniqueAllowed = [...new Set(allowed.filter((item) => item === 'elevenlabs_scribe' || item === 'azure_batch' || item === 'local'))];
    const publicMode = !!config.public_mode;
    const localAwareAllowed = publicMode || uniqueAllowed.includes('local')
        ? uniqueAllowed
        : [...uniqueAllowed, 'local'];
    const fallbackAllowed = localAwareAllowed.length ? localAwareAllowed : DEFAULT_RUNTIME_CONFIG.allowedSttProviders;
    const defaultProvider = normalizeSttProvider(config.default_stt_provider || DEFAULT_STT_PROVIDER);
    return {
        publicMode,
        allowedSttProviders: fallbackAllowed,
        defaultSttProvider: fallbackAllowed.includes(defaultProvider) ? defaultProvider : fallbackAllowed[0],
        showMaintainerSettings: config.show_maintainer_settings !== false,
        limits: config.limits || {},
        guestTrial: config.guest_trial || config.limits?.guest_trial || DEFAULT_RUNTIME_CONFIG.guestTrial,
    };
};

export const effectiveSttProvider = (settings={}, runtimeConfig=DEFAULT_RUNTIME_CONFIG) => {
    const wanted = normalizeSttProvider(settings.sttProvider);
    return runtimeConfig.allowedSttProviders.includes(wanted) ? wanted : runtimeConfig.defaultSttProvider;
};

export const cloudSttMissingMessage = (lang) => (
    lang === 'zh'
        ? '云端转录暂不可用，请联系产品维护者检查后台配置。'
        : 'Cloud transcription is unavailable. Ask the product maintainer to check backend configuration.'
);

export const azureSpeechMissingMessage = cloudSttMissingMessage;

export const normalizeSttModel = (model) => (
    model === 'large-v3' || model === 'medium' ? model : DEFAULT_STT_MODEL
);
