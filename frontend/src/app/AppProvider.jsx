import { useState, useEffect, useMemo, useRef, createContext, useContext } from 'react';
import { apiFetch, API_BASE } from './apiConfig.js';
import { useAuth } from './auth.jsx';
import { localExecutionHeaders } from '../lib/localExecution.js';
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
    reconcileTaskList,
    entryToJob,
    jobToHistoryEntry,
    jobToCurrentJob,
} from './jobMorph.js';
import { normalizeTaskState, TASK_STATE_RUNNING, TASK_STATE_QUEUED } from '../lib/taskState.js';

const AppCtx = createContext();

const taskKey = (job) => String(job?.task_id || job?.result?.task_id || '').trim();

export const AppProvider = ({children}) => {
    const {authMode, user, guestMode} = useAuth();
    // Single source of truth for the task list: canonical raw jobs. history,
    // stats, and the initial currentJob all derive from this. See
    // docs/task_list_reconciliation_plan.md.
    const [tasks, setTasks] = useState([]);
    const [larkExports, setLarkExports] = useState(() => {
        try { return JSON.parse(localStorage.getItem('fluentflow_lark_exports')||'[]'); } catch(_){ return []; }
    });
    const [currentJob, setCurrentJob] = useState(null);
    const [lastResult, setLastResult] = useState(null);
    const [lastSourceFile, setLastSourceFile] = useState(null);
    const [runtimeConfig, setRuntimeConfig] = useState(DEFAULT_RUNTIME_CONFIG);

    // Refs backing the single reconciliation path. accountCacheId + hydrated
    // gate cache writes so an in-progress account switch or guest state never
    // wipes a real account's cache. tombstones drop deleted ids even if a slow
    // in-flight fetch still returns them (the durable form of the "deleted
    // record reappears" bug).
    const accountCacheIdRef = useRef('local');
    const hydratedRef = useRef(false);
    const tombstonesRef = useRef(new Set());
    // Ids the user cancelled locally; reconcile pins them to cancelled until the
    // backend poll agrees (replaces the per-page locallyCancelled set).
    const cancelledRef = useRef(new Set());

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
        const accountReady = authMode !== 'accounts' || !!user?.id;
        accountCacheIdRef.current = accountCacheId;
        hydratedRef.current = false;
        tombstonesRef.current = new Set();
        cancelledRef.current = new Set();
        setCurrentJob(null);
        setLastResult(null);
        if (guestMode || !accountReady) {
            setTasks([]);
            return () => { cancelled = true; };
        }

        const cachedJobs = readCachedAccountJobs(accountCacheId);
        setTasks(reconcileTaskList({
            cached: cachedJobs,
            tombstones: tombstonesRef.current,
            cancelled: cancelledRef.current,
            accountId: accountCacheId,
        }));
        // Cache is now hydrated for this account; the projection effect may
        // safely mirror task changes back to the cache from here on.
        hydratedRef.current = true;

        Promise.allSettled([
            apiFetch(`${API_BASE}/jobs?limit=100`),
            apiFetch(`${API_BASE}/jobs?limit=100`, {headers: localExecutionHeaders({sttProvider: 'local'})}),
        ])
            .then(async (results) => {
                const groups = await Promise.all(results.map(async (result) => {
                    if (result.status !== 'fulfilled' || !result.value?.ok) return [];
                    const data = await result.value.json().catch(() => ({}));
                    return Array.isArray(data?.jobs) ? data.jobs : [];
                }));
                const fetchedJobs = groups.flat();
                if (cancelled || !fetchedJobs.length) return;
                const nextTasks = reconcileTaskList({
                    fetched: fetchedJobs,
                    cached: cachedJobs,
                    tombstones: tombstonesRef.current,
                    cancelled: cancelledRef.current,
                    accountId: accountCacheId,
                });
                setTasks(nextTasks);
                const running = nextTasks.find((job) => [TASK_STATE_RUNNING, TASK_STATE_QUEUED].includes(normalizeTaskState(job)));
                if (running) setCurrentJob(jobToCurrentJob(running));
            })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [authMode, user?.id, guestMode]);

    // Single cache write path: mirror the canonical task list to the account
    // cache. Routes must never write the cache directly (see plan Stage 3).
    useEffect(() => {
        if (!hydratedRef.current) return;
        writeCachedAccountJobs(accountCacheIdRef.current, tasks);
    }, [tasks]);

    const history = useMemo(
        () => tasks.filter(jobVisibleInHistory).map(jobToHistoryEntry),
        [tasks],
    );

    const persistLarkExports = (e) => { setLarkExports(e); localStorage.setItem('fluentflow_lark_exports', JSON.stringify(e)); };

    // Upsert a record into the canonical list. Callers still pass a history
    // entry for now; entryToJob rebuilds the raw job and reconcile dedupes by
    // task_id so a resubmit updates in place instead of duplicating.
    const addToHistory = (entry) => {
        const job = entryToJob(entry, {
            clientId: authMode === 'accounts' && user?.id ? `user:${user.id}` : null,
        });
        if (!job) return;
        setTasks((current) => reconcileTaskList({
            optimistic: [job],
            cached: current,
            tombstones: tombstonesRef.current,
            accountId: accountCacheIdRef.current,
        }));
    };

    const clearHistory = () => {
        tombstonesRef.current = new Set();
        setTasks([]);
        persistLarkExports([]);
        try {
            localStorage.removeItem('fluentflow_history');
            localStorage.removeItem(accountJobsCacheKey(accountCacheIdRef.current));
        } catch(_) {}
    };
    // Tombstone the id so an in-flight fetch or stale cache read cannot re-add a
    // backend-deleted job, then drop it from the canonical list. The projection
    // effect clears it from the cache.
    const removeFromHistory = (taskId) => {
        if (!taskId) return;
        const target = String(taskId);
        tombstonesRef.current.add(target);
        setTasks((current) => current.filter((job) => taskKey(job) !== target));
    };

    // Merge a freshly polled /jobs batch into the canonical list. Pages call
    // this from their poll timers instead of keeping a private jobs state and
    // writing the cache themselves (plan Stage 3b).
    const reconcileInto = (current, extra = {}) => reconcileTaskList({
        cached: current,
        tombstones: tombstonesRef.current,
        cancelled: cancelledRef.current,
        accountId: accountCacheIdRef.current,
        ...extra,
    });
    const ingestJobs = (fetchedJobs) => {
        if (!Array.isArray(fetchedJobs) || !fetchedJobs.length) return;
        setTasks((current) => reconcileInto(current, {fetched: fetchedJobs}));
    };
    // Pin/unpin a locally-cancelled task. revert is used when the backend cancel
    // call fails; the caller then re-fetches to restore the true state.
    const markCancelled = (taskId) => {
        if (!taskId) return;
        cancelledRef.current.add(String(taskId));
        setTasks((current) => reconcileInto(current));
    };
    const revertCancelled = (taskId) => {
        if (!taskId) return;
        cancelledRef.current.delete(String(taskId));
        setTasks((current) => reconcileInto(current));
    };
    // Undo a tombstone when a backend delete fails (non-404); the caller
    // re-fetches to bring the record back.
    const restoreTask = (taskId) => {
        if (!taskId) return;
        tombstonesRef.current.delete(String(taskId));
    };

    const addLarkExport = (entry) => persistLarkExports([entry, ...larkExports].slice(0, 50));
    const stats = {
        totalMinutes: Math.round(history.reduce((s,h) => s + (h.durationMin||0), 0)),
        notesGenerated: history.filter(h => h.status==='completed').length,
    };

    return <AppCtx.Provider value={{tasks,history,ingestJobs,markCancelled,revertCancelled,restoreTask,addToHistory,removeFromHistory,clearHistory,currentJob,setCurrentJob,lastResult,setLastResult,lastSourceFile,setLastSourceFile,stats,larkExports,addLarkExport,runtimeConfig}}>{children}</AppCtx.Provider>;
};
export const useApp = () => useContext(AppCtx);
