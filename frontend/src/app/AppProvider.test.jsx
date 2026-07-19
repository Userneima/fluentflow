// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, act, waitFor } from '@testing-library/react';
import { AppProvider, useApp } from './AppProvider.jsx';

// AppProvider is the single owner of the task list. These tests exercise the
// ref-threaded wiring (ingest / tombstone / cancelled pin) that the pure
// reconcileTaskList unit tests cannot reach. See
// docs/task_list_reconciliation_plan.md.

vi.mock('./auth.jsx', () => ({
    useAuth: () => ({ authMode: 'local', user: null, guestMode: false }),
}));
vi.mock('./apiConfig.js', () => ({
    API_BASE: '',
    apiFetch: vi.fn(async (url) => ({
        ok: true,
        json: async () => (String(url).includes('/jobs') ? { jobs: [] } : {}),
    })),
}));

let ctx;
const Capture = () => { ctx = useApp(); return null; };

const makeJob = (task_id, extra = {}) => ({
    task_id,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    task_state: 'completed',
    result: { task_id, transcript_text: 'hello', display_title: task_id, filename: `${task_id}.mp4` },
    ...extra,
});

const ids = () => ctx.history.map((h) => h.taskId).sort();

const mount = async () => {
    await act(async () => { render(<AppProvider><Capture /></AppProvider>); });
    // flush the mount-effect /jobs fetch (resolves empty)
    await act(async () => { await new Promise((r) => setTimeout(r, 0)); });
    await waitFor(() => expect(ctx).toBeTruthy());
};

describe('AppProvider task list wiring', () => {
    beforeEach(() => { localStorage.clear(); ctx = undefined; });

    it('derives history from ingested jobs', async () => {
        await mount();
        await act(async () => { ctx.ingestJobs([makeJob('a'), makeJob('b')]); });
        expect(ids()).toEqual(['a', 'b']);
    });

    // The recurring "deleted record reappears" bug, at the wiring level: a slow
    // in-flight poll returning the deleted id must not resurrect it.
    it('keeps a deleted job gone even if a later poll returns it', async () => {
        await mount();
        await act(async () => { ctx.ingestJobs([makeJob('a'), makeJob('b')]); });
        await act(async () => { ctx.removeFromHistory('a'); });
        expect(ids()).toEqual(['b']);
        await act(async () => { ctx.ingestJobs([makeJob('a')]); });
        expect(ids()).toEqual(['b']);
    });

    // restoreTask (used on a failed backend delete) un-tombstones so a re-fetch
    // brings the record back.
    it('restores a tombstoned job on the next poll after restoreTask', async () => {
        await mount();
        await act(async () => { ctx.ingestJobs([makeJob('a')]); });
        await act(async () => { ctx.removeFromHistory('a'); });
        expect(ids()).toEqual([]);
        await act(async () => { ctx.restoreTask('a'); });
        await act(async () => { ctx.ingestJobs([makeJob('a')]); });
        expect(ids()).toEqual(['a']);
    });

    it('pins a cancelled job even when a poll reports it running, and reverts', async () => {
        await mount();
        await act(async () => { ctx.ingestJobs([makeJob('b', { task_state: 'running', result: { task_id: 'b' } })]); });
        await act(async () => { ctx.markCancelled('b'); });
        await act(async () => {
            ctx.ingestJobs([makeJob('b', { task_state: 'running', updated_at: '2026-07-05T00:00:00Z', result: { task_id: 'b' } })]);
        });
        expect(ctx.history.find((h) => h.taskId === 'b').status).toBe('cancelled');
        await act(async () => { ctx.revertCancelled('b'); });
        await act(async () => {
            ctx.ingestJobs([makeJob('b', { task_state: 'running', updated_at: '2026-07-06T00:00:00Z', result: { task_id: 'b' } })]);
        });
        expect(ctx.history.find((h) => h.taskId === 'b').status).toBe('processing');
    });

    it('keeps an upload abort controller available across route changes', async () => {
        await mount();
        const controller = {abort: vi.fn()};
        await act(async () => { ctx.setPendingUploadAbort(controller); });

        expect(ctx.abortPendingUpload()).toBe(true);
        expect(controller.abort).toHaveBeenCalledOnce();
        expect(ctx.abortPendingUpload()).toBe(false);
    });
});
