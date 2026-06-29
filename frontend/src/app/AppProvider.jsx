import { useState, useEffect, createContext, useContext } from 'react';
import { apiFetch, API_BASE } from './apiConfig.js';
import { useAuth } from './auth.jsx';
import {
    sanitizeSettings,
    sensitivePatchFromSettings,
    SENSITIVE_SETTING_KEYS,
    accountJobsCacheKey,
    jobVisibleInHistory,
    normalizeRuntimeConfig,
    DEFAULT_RUNTIME_CONFIG,
    readCachedAccountJobs,
    writeCachedAccountJobs,
    jobToHistoryEntry,
    jobToCurrentJob,
} from './jobMorph.js';
import { normalizeTaskState, TASK_STATE_RUNNING, TASK_STATE_QUEUED } from '../lib/taskState.js';

const AppCtx = createContext();

export const AppProvider = ({children}) => {
    const {authMode, user, guestMode} = useAuth();
    const [history, setHistory] = useState([]);
    const [larkExports, setLarkExports] = useState(() => {
        try { return JSON.parse(localStorage.getItem('fluentflow_lark_exports')||'[]'); } catch(_){ return []; }
    });
    const [currentJob, setCurrentJob] = useState(null);
    const [lastResult, setLastResult] = useState(null);
    const [lastSourceFile, setLastSourceFile] = useState(null);
    const [runtimeConfig, setRuntimeConfig] = useState(DEFAULT_RUNTIME_CONFIG);
    useEffect(() => {
        let cancelled = false;
        apiFetch(`${API_BASE}/runtime-config`)
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
                if (data && !cancelled) setRuntimeConfig(normalizeRuntimeConfig(data));
            })
            .catch(() => {});
        try {
            const rawSettings = JSON.parse(localStorage.getItem("fluentflow_settings")||"{}");
            const hasLegacySecrets = SENSITIVE_SETTING_KEYS.some((key) => rawSettings[key]);
            if (hasLegacySecrets) {
                apiFetch(`${API_BASE}/credentials`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(sensitivePatchFromSettings(rawSettings)),
                }).finally(() => {
                    localStorage.setItem("fluentflow_settings", JSON.stringify(sanitizeSettings(rawSettings)));
                });
            }
        } catch(_) {}
        const accountCacheId = authMode === 'accounts' ? user?.id : 'local';
        if (guestMode || (authMode === 'accounts' && !user?.id)) {
            setHistory([]);
            return;
        }
        const cachedJobs = readCachedAccountJobs(accountCacheId);
        if (cachedJobs.length) {
            const cachedEntries = cachedJobs
                .filter(jobVisibleInHistory)
                .map(jobToHistoryEntry);
            setHistory(cachedEntries);
            const cachedRunning = cachedJobs.find((job) => normalizeTaskState(job) === TASK_STATE_RUNNING || normalizeTaskState(job) === TASK_STATE_QUEUED);
            if (cachedRunning) setCurrentJob(jobToCurrentJob(cachedRunning));
        }
        apiFetch(`${API_BASE}/jobs?limit=100`)
            .then((r) => r.ok ? r.json() : null)
            .then((data) => {
                if (!Array.isArray(data?.jobs)) return;
                writeCachedAccountJobs(accountCacheId, data.jobs);
                const entries = data.jobs
                    .filter(jobVisibleInHistory)
                    .map(jobToHistoryEntry);
                if (cancelled) return;
                setHistory(entries);
                const running = data.jobs.find((job) => normalizeTaskState(job) === TASK_STATE_RUNNING);
                if (running) setCurrentJob(jobToCurrentJob(running));
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [authMode, user?.id, guestMode]);

    const persistLarkExports = (e) => { setLarkExports(e); localStorage.setItem('fluentflow_lark_exports', JSON.stringify(e)); };
    const addToHistory = (entry) => setHistory((current) => [
        entry,
        ...current.filter((item) => !(entry.taskId && item.taskId === entry.taskId)),
    ].slice(0, 100));
    const clearHistory = () => {
        setHistory([]);
        persistLarkExports([]);
        try {
            localStorage.removeItem('fluentflow_history');
            localStorage.removeItem(accountJobsCacheKey(authMode === 'accounts' ? user?.id : 'local'));
        } catch(_) {}
    };

    const addLarkExport = (entry) => persistLarkExports([entry, ...larkExports].slice(0, 50));
    const stats = {
        totalMinutes: Math.round(history.reduce((s,h) => s + (h.durationMin||0), 0)),
        notesGenerated: history.filter(h => h.status==='completed').length,
    };

    return <AppCtx.Provider value={{history,addToHistory,clearHistory,currentJob,setCurrentJob,lastResult,setLastResult,lastSourceFile,setLastSourceFile,stats,larkExports,addLarkExport,runtimeConfig}}>{children}</AppCtx.Provider>;
};
export const useApp = () => useContext(AppCtx);
