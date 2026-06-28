export const LOCAL_EXECUTION_HEADER = 'X-FluentFlow-Execution-Target';
export const LOCAL_EXECUTION_TARGET = 'local';

export const shouldUseLocalSingleUserClientId = () => {
    const { hostname } = window.location;
    return hostname === '127.0.0.1' || hostname === 'localhost';
};

const normalizeExecutionSttProvider = (provider) => (
    provider === 'local' || provider === 'elevenlabs_scribe' || provider === 'azure_batch' || provider === 'azure_fast'
        ? (provider === 'azure_fast' ? 'azure_batch' : provider)
        : 'elevenlabs_scribe'
);

const isLocalLarkRoute = (route) => {
    const value = String(route || '').trim();
    return value === 'local_cli' || value === 'lark_cli';
};

export const shouldUseLocalExecution = (options={}) => (
    !!options.localExecution
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
