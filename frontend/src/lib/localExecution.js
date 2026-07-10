export const LOCAL_EXECUTION_HEADER = 'X-FluentFlow-Execution-Target';
export const LOCAL_EXECUTION_TARGET = 'local';

export const shouldUseLocalSingleUserClientId = () => {
    const { hostname } = window.location;
    return hostname === '127.0.0.1' || hostname === 'localhost';
};

const normalizeExecutionSttProvider = (provider) => {
    const value = String(provider || '').trim().toLowerCase().replace(/-/g, '_');
    if (value === 'local') return 'local';
    if (value === 'cloud' || value === 'cloud_stt' || value === 'elevenlabs' || value === 'elevenlabs_scribe' || value === 'scribe' || value === 'scribe_v2') return 'elevenlabs_scribe';
    return 'elevenlabs_scribe';
};

const isLocalLarkRoute = (route) => {
    const value = String(route || '').trim();
    return value === 'local_cli' || value === 'lark_cli';
};

export const shouldUseLocalExecution = (options={}) => (
    // On localhost single-user everything runs locally, so mark every request as
    // local execution regardless of STT provider — otherwise cloud-STT requests
    // are not exempted from account auth and get 401. The backend still verifies
    // the request originates from localhost, so public deployments are unaffected.
    !!options.localExecution
    || shouldUseLocalSingleUserClientId()
    || normalizeExecutionSttProvider(options.sttProvider) === 'local'
    || isLocalLarkRoute(options.larkExportRoute)
    || !!options.larkViaCli
);

export const localExecutionHeaders = (options={}) => (
    shouldUseLocalExecution(options)
        ? {[LOCAL_EXECUTION_HEADER]: LOCAL_EXECUTION_TARGET}
        : {}
);

export const isLocalHistoryResult = (result={}) => (
    !!result?.imported_from_local_history ||
    result?.source === 'imported_local_history' ||
    result?.source === 'browser_local_history' ||
    String(result?.task_id || '').startsWith('imported_')
);
