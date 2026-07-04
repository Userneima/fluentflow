# FluentFlow Architecture Optimization Plan

This plan captures the long-term cleanup path for FluentFlow after the Agent data-link work. The execution order follows product risk, not file size.

For the product-facing Agent execution roadmap, read `docs/agent_execution_plan.md` first. That plan defines the learning-material-first Agent path, while this document tracks supporting architecture cleanup.

## Scope

- In: execution scope, task state semantics, Agent task package, Result/Job schema, cloud proxy resilience, focused backend/frontend module extraction, and validation coverage.
- Out: visual redesign, deployment changes, database migrations, and broad rewrites that do not reduce current failure modes.

## Priority Order

### P0: Execution Scope As A First-Class Concept

- [x] Move backend local/cloud execution detection into a focused request-scope module.
- [x] Move frontend local execution header construction into a focused local-execution module.
- [x] Keep existing route behavior stable through guardrail tests.
- [x] Replace page-level header decisions with API-client-level local/cloud methods.

### P0: Unified Task State

- [x] Define the frontend task states: `idle`, `uploading`, `queued`, `running`, `completed`, `failed`, `cancelled`, and `cached_only`.
- [x] Replace ad hoc `__cacheOnly` handling with a formal cached-only state.
- [x] Normalize `currentJob`, `lastResult`, browser history, cached jobs, and backend jobs through one mapper.
- [x] Add behavior tests for opening backend-backed, local-backed, and cached-only tasks.

### P1: Agent Product Layer

- [x] Define and document the `Processing Plan` schema from `docs/agent_execution_plan.md`.
- [x] Generate a backend Processing Plan for course and lecture note tasks without changing the current automatic execution flow.
- [x] Persist the plan into job results and expose it through the Agent Task Package.
- [x] Fold `note_mode_plan_*` into the broader plan semantics while preserving old fields for compatibility.
- [ ] Add a minimal frontend display for the Agent plan and cloud STT / fallback tool trace in the existing processing settings and task detail/editor surfaces.
- [ ] Consolidate processing settings that the Agent now decides, moving unavoidable manual controls into plan explanation or advanced settings.

### P1: Agent Data Link And Result Schema

- [x] Add `/agent/v1/tasks/{task_id}/package` as the stable Agent Task Package outlet.
- [x] Add Agent submit, wait, diagnosis, note regeneration, and export endpoints.
- [x] Document the Result Payload and Agent Task Package schemas in `docs/result_schema.md`.
- [x] Add a frontend runtime normalizer or typedef for Result/Job payloads.

### P1: Cloud Proxy Resilience

- [x] Catch remote stream interruptions such as `httpx.RemoteProtocolError`.
- [x] Return a structured 502 payload for cloud workspace failures.
- [x] Show a user-facing cloud workspace unavailable message instead of browser-level network errors.

### P1/P2: Behavior-Oriented Tests

- [ ] Keep essential source-string guardrails where they cheaply prevent regressions.
- [x] Add API behavior tests for execution scope, Agent package, and task state transitions.
- [ ] Add Playwright coverage for opening local and cached-only tasks when the local dev setup is available.

### P2: Backend Module Extraction

- [x] Extract and wire `request_scope.py` into `server_helpers.py`.
- [x] Extract and wire `cloud_proxy.py` into `server_helpers.py` after proxy error handling is stable.
- [x] Extract `artifacts.py` around result artifact creation and downloads.
- [x] Extract `job_limits.py` around submission rate, daily upload/job quotas, and active job limits.
- [ ] Extract quota reservation/finalization from `server_helpers.py` after processing use cases are smaller.
- [ ] Delay `runtime_config.py` and `job_recovery.py` until the higher-risk seams are stable.

### P2: Processing Use Cases

- [ ] Extract `regenerate_summary` as a reusable use case for UI and Agent.
- [ ] Extract `export_lark` as a reusable use case for UI and Agent.
- [ ] Extract `summarize_transcript_file`.
- [ ] Extract `queue_media`.
- [ ] Extract `process_media` last because it has the largest blast radius.

### P2/P3: Frontend Shared Module Extraction

- [x] Extract `app/apiClient.js`.
- [x] Extract `lib/localExecution.js`.
- [x] Extract `lib/jobMappers.js`.
- [x] Extract `lib/settingsModel.js`.
- [x] Wire `AppProvider.jsx` as the app state provider while keeping `shared.jsx` as a compatibility export layer.
- [x] Extract `DropdownMenu.jsx`.
- [ ] Delay `i18n/messages.js` until the route copy churn settles.

### P3: Page Hooks

- [ ] Extract `useTaskSubmission` and `useQueueUpload` from `dashboard.jsx`.
- [ ] Extract `useTranscriptEditing` from `editor.jsx`.
- [ ] Extract `useMediaSource`, `useLarkExport`, and `useRetranscription` after task state is formalized.

## Current Execution Notes

- Start with P0 execution scope because it directly caused local/cloud task lookup and regeneration regressions.
- Keep each step small enough to validate with `pytest`, `npm run build:frontend`, and `git diff --check`.
- Do not use file length alone as a refactor trigger; refactor only where it creates a smaller interface for callers or concentrates repeated failure logic.
