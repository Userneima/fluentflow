# Task List Reconciliation Plan

Status: in progress (Stage 1 done)

## Purpose

Make the task **list** consistent across every source that feeds it. This is the
sibling of `docs/task_status_model_unification_plan.md`: that plan unified how a
*single task's status* is described; this plan unifies how the *set of tasks* is
assembled from cache, backend, in-memory state, and optimistic records so that a
record cannot duplicate, leak across accounts, or reappear after deletion.

This plan exists because the same class of bug keeps recurring. Of the last 60
commits, 42 were `fix:`, and the largest cluster fixes list-reconciliation
regressions (deleted records reappearing, stale probes, cross-owner leakage,
queued uploads not shown, agent records out of sync). Each was patched at one
call site; the next call site that forgot the same rule regressed again.

## Non-Goals

- Do not change task status *semantics*. That is owned by
  `docs/task_status_model_unification_plan.md` and its `task_snapshot` builder.
- Do not change backend job storage, the `/jobs` payload shape, or result
  schema. Old records must stay readable.
- Do not redesign any list UI. This is a state-ownership refactor, not a visual
  change.
- Do not add new list sources (e.g. server-sent events) as part of this plan.

## Stage 0 Audit Result

Status: completed on 2026-07-08

### Sources Of Truth Today

| Source | Form | Read/written by |
| --- | --- | --- |
| Backend job list | `GET /jobs?limit=100` (fetched **twice**: default headers + local-execution headers, then flattened) | `AppProvider.jsx`, `tasks.jsx`, `agent-tasks.jsx` each fetch independently |
| Account jobs cache | `localStorage: fluentflow_account_jobs_cache_<accountId>` | **6 files read/write directly** (see below) |
| In-memory history | `AppProvider` `history` state | `AppProvider.jsx` |
| Optimistic / queued records | `cacheJobRecord()` and `queueUpload.js` | `dashboard.jsx`, `media-text.jsx` |

Files that read or write the account cache directly today
(`readCachedAccountJobs` / `writeCachedAccountJobs` / `cacheJobRecord`):

- `frontend/src/app/AppProvider.jsx`
- `frontend/src/routes/tasks.jsx` (4 write sites)
- `frontend/src/routes/agent-tasks.jsx` (3 write sites)
- `frontend/src/routes/processing.jsx`
- `frontend/src/routes/dashboard.jsx`
- `frontend/src/routes/media-text.jsx`

Reconciliation helpers already exist in `frontend/src/lib/jobMappers.js`
(`mergeCachedJobs`, `readCachedAccountJobs`, `writeCachedAccountJobs`,
`cacheJobRecord`, `jobBelongsToAccountCache`, `sortJobsForHistoryView`) but they
are *called* from all of the above with different inputs and ordering, so there
is no single reconciliation path.

### Root Design Flaw

The cache is treated as a **writable source** by six call sites, and the
in-memory list exists as **two copies** (AppProvider `history` plus each route's
local list state). Every mutation — delete, retry, resubmit, queue-add, mark
failed — must be manually mirrored to all copies. Forgetting one copy at one
site is a regression. This is exactly the failure recorded in commit `fbc37ca`:
the delete handler purged the page-local cache but not the AppProvider history
or account cache, so `mergeCachedJobs` re-added the deleted job on next load.

### Harness Gap

- There is **no JavaScript test runner** (no vitest/jest). The pure
  reconciliation functions in `jobMappers.js` have **zero unit tests**.
- `tests/test_frontend_routes.py` contains ~527 string-existence assertions
  (`"..." in content`). These guard that source strings still exist; they cannot
  catch list-reconciliation *behavior* regressions. This is why every recurrence
  was found by the user in real use, not by CI.

### Legacy Residue

- `fluentflow_history` localStorage key is only ever `removeItem`-ed
  (`AppProvider.jsx:106`), never written. It is dead residue from an older
  history flow and should be removed once nothing depends on the cleanup.

## Target Design

Make `AppProvider` the single owner of the task list. Cache becomes a read-only
projection; routes consume derived views and call semantic mutations only.

1. **One pure reconcile function** in `frontend/src/lib/jobMappers.js`:

   ```
   reconcileTaskList({ fetched, cached, optimistic, tombstones, accountId })
     -> ordered canonical job list
   ```

   All merge rules live here: filter by account owner, drop tombstoned ids,
   dedupe by `task_id` keeping the freshest `updated_at`, let `uploading`/
   `queued` optimistic records win over a stale backend row, then
   `sortJobsForHistoryView`. Pure input/output, fully unit-testable offline.

2. **Cache is a projection, not a source.** `writeCachedAccountJobs` is called
   from exactly one place: an `AppProvider` effect mirroring the canonical
   `tasks` state. Routes stop writing the cache entirely.

3. **Tombstones** permanently fix the "deleted record reappears" class.
   `removeTask(id)` records the id in a short-lived deleted set; `reconcile`
   drops any fetched/cached job whose id is tombstoned, so a slow in-flight
   fetch cannot resurrect it. This is the general form of `fbc37ca`.

4. **Semantic mutations** on `AppProvider`, consumed by routes instead of direct
   cache access: `upsertTask(job)`, `removeTask(id)`, `markFailed(id, reason)`,
   `markQueued(record)`.

`history`, `stats`, and `currentJob` all become derived values of the single
`tasks` state.

## Regression Test Suite

Each historical regression becomes one `reconcileTaskList` unit test that must
stay green forever:

| Test | Locks regression | Commit |
| --- | --- | --- |
| Deleted id stays gone even when cached/fetched still contain it | delete reappears | `fbc37ca` |
| Account A cache never merges into account B list | cross-owner leakage | `e53885b` |
| Cold start (cache only, no fetch) still yields a list | records missing until fetch | `be500b5` |
| `uploading`/`queued` optimistic record shown and not overwritten by stale backend row | queued uploads not shown | `84584b9` |
| Same `task_id` keeps freshest `updated_at` | merge union freshness | `mergeCachedJobs` |
| Agent records and recent activity derive from the same source | out-of-sync lists | `b49dd85`, `85cc00b` |
| Resubmit/retry upserts instead of duplicating | duplicate records | `c1975cd` |

## Staged Execution

Do not execute multiple stages in one turn. After each stage, update this file's
status and record the validation that actually ran.

### Stage 1: Establish The Harness (zero behavior change)

Status: completed on 2026-07-08

Outcome:

- Added `vitest` dev dependency, `vitest.config.mjs` (node env, scoped to
  `frontend/src/lib/**/*.test.js`), and the `test:frontend` script.
- Added `reconcileTaskList` to `frontend/src/lib/jobMappers.js` as a pure
  function that reuses the existing `mergeCachedJobs` + `jobBelongsToAccountCache`
  owner filter + `sortJobsForHistoryView`, plus additive tombstone and optimistic
  inputs that no-op when empty. No call site consumes it yet, so behavior is
  unchanged.
- Encoded all regression-table cases (plus empty-input and no-mutation guards)
  as 11 passing tests in `frontend/src/lib/jobMappers.test.js`.

Validation (ran):

- `npm run test:frontend` — 11 passed
- `npm run build:frontend` — built
- `git diff --check` — clean

Stop condition:

- Met. The reconcile logic has real unit coverage before any refactor touches
  it. Stage 2 can now converge ownership behind these tests.

### Stage 2: Converge Ownership In AppProvider

- Make `AppProvider` hold a single canonical `tasks` state; derive `history`,
  `stats`, and `currentJob` from it.
- Move all cache writes into one projection effect on `tasks`.
- Add `tombstones` and route all list assembly through `reconcileTaskList`.

Validation:

- `npm run test:frontend`
- `npm run build:frontend`
- `git diff --check`

Stop condition:

- The cache is written from exactly one place and the list has one owner.

### Stage 3: Routes Stop Touching The Cache

- Convert `tasks.jsx`, `agent-tasks.jsx`, `dashboard.jsx`, `media-text.jsx`, and
  `processing.jsx` to consume derived views and call semantic mutations.
- Remove every direct `writeCachedAccountJobs` / `cacheJobRecord` call outside
  `AppProvider`.

Validation:

- `npm run test:frontend`
- `npm run build:frontend`
- `git diff --check`

Stop condition:

- No route mutates the cache directly; deletes/retries/resubmits go through
  AppProvider mutations.

### Stage 4: Remove Residue And Unify Polling

- Remove the dead `fluentflow_history` cleanup once nothing depends on it.
- Fold independent per-route `/jobs` polling into one AppProvider refresh.

Validation:

- `npm run test:frontend`
- `npm run build:frontend`
- `git diff --check`

Stop condition:

- One refresh path; no dead history key; list sources fully unified.

## Execution Rule

Pick exactly one stage per execution turn. Keep old cached records readable
throughout (compatibility fields in `jobMappers.js` must keep working). If a
stage reveals a source or mutation not captured in the Stage 0 audit, update the
audit before proceeding.
