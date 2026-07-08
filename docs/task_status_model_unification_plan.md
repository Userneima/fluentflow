# Task Status Model Unification Plan

Status: in progress

## Purpose

Make every FluentFlow surface describe the same task in the same way. A user
should be able to open the home page, history records, task detail, or editor
and understand where the task is, why it stopped, and what can be done next.

This plan exists because the work is larger than one execution turn. Each stage
below should be handled as one coherent, verifiable work unit.

Scope boundary: this plan owns how a *single task's status* is described.
How the *list of tasks* is reconciled across cache, backend, in-memory state,
and optimistic records is a separate concern owned by
`docs/task_list_reconciliation_plan.md`.

## Non-Goals

- Do not redesign the task detail UI before the backend status shape is stable.
- Do not add new export targets, platforms, billing logic, or AI planning
  behavior as part of this plan.
- Do not rewrite historical storage unless a stage explicitly requires a
  compatibility adapter.

## Target Task Snapshot

Long-term task-facing surfaces should read one normalized snapshot with these
meanings:

| Field | Meaning |
| --- | --- |
| `overall_status` | queued, running, completed, failed, cancelled. |
| `current_step` | The current user-understandable processing step. |
| `step_statuses` | Per-step pending/running/completed/failed/cancelled state. |
| `progress` | One backend-owned progress value, not page-specific guesses. |
| `failure_reason` | User-readable failure explanation. |
| `next_action` | The recommended recovery action. |
| `artifacts` | Available transcript, subtitle, note, media, and export outputs. |
| `route` | Local/cloud route and whether account-backed AI services are needed. |

## Stage 1 Audit Result

Status: completed on 2026-06-30

### Current Status Sources

| Layer | Current source | What it owns today | Long-term role |
| --- | --- | --- | --- |
| Job row | `backend/core/job_store.py` `jobs` table | `status`, `stage`, `progress`, `summary_status`, `error_reason`, `metadata`, `result` | Keep as persistence input, not the final UI contract. |
| Queue steps | `backend/core/job_store.py` `job_steps` table | Durable queued/running/completed/failed/cancelled step records for selected async work | Feed recorded step state into the snapshot when available. |
| Detail projection | `backend/core/task_detail.py` | Builds timeline, diagnosis, actions, artifacts, and data quality for `/jobs/{task_id}/detail` | Best starting point for the unified snapshot builder. |
| Error diagnosis | `backend/core/error_diagnostics.py` | Converts raw errors into user-readable title/detail/next action | Remain the source of `failure_reason` and `next_action`. |
| Result payload | `backend/core/result_schema.py` and `docs/result_schema.md` | Transcript, note, subtitle, artifacts, note mode, processing plan | Feed transcript/note/artifact availability into the snapshot. |
| Processing routes | `backend/routers/processing.py`, `backend/routers/video_sources.py`, `backend/core/server_helpers.py` | Write many job stages and progress values during upload, link fetch, STT, notes, export, recovery | Continue writing raw execution facts; do not make UI pages infer from each route. |
| Frontend state | `frontend/src/lib/taskState.js`, `frontend/src/lib/jobMappers.js`, app providers, route pages | Normalizes status locally, caches jobs, derives history entries and current job cards | Become compatibility/cache adapters around backend snapshot fields. |
| Processing detail UI | `frontend/src/routes/agent-trace.jsx`, `frontend/src/routes/processing.jsx` | Mixes backend detail, current job state, result diagnosis, and fallback package data | Should prefer the unified snapshot and use fallbacks only for old/cached data. |

### Compatibility Fields To Keep Reading

- Job-level: `status`, `task_state`, `stage`, `progress`, `summary_status`,
  `error_reason`, `metadata.video_source_progress`, `metadata.queue_options`.
- Result-level: `summary_status`, `summary_error`, `summary_skipped`,
  `transcript_text`, `transcript_text_preview`, `raw_segments`,
  `display_segments`, `artifacts`, `lark_response`, `lark_error`,
  `processing_plan`, legacy note mode fields.
- Frontend-only: `cached_only`, `__cacheOnly`, `queueUpload`, `currentJob`,
  browser history entries converted through `historyEntryToResult`.

### Normalized Field Mapping

| Target field | Primary source | Compatibility / fallback rule |
| --- | --- | --- |
| `overall_status` | Job `status` normalized to `queued`, `running`, `completed`, `failed`, `cancelled` | Frontend `task_state` remains a read fallback for cached jobs; do not introduce `canceled`. |
| `current_step` | Active timeline step from `task_detail.STAGE_TO_STEP` | If no known stage exists, use the first pending/running/failed timeline item. |
| `step_statuses` | Timeline from `build_task_detail()` plus `job_steps` | Result evidence may mark transcript, note, artifact, and export steps complete even if no recorded step exists. |
| `progress` | Job `progress` | For unmeasured work, expose `null` or stage-only status instead of fake precision. |
| `failure_reason` | `diagnosis.detail` / `diagnose_error()` | Fall back to `job.error_reason`, step `error_reason`, `result.summary_error`, or `result.lark_error`. |
| `next_action` | `diagnosis.next_action` | Fall back to action derived from failed step, source type, account/quota/export hints. |
| `artifacts` | `result.artifacts` projected by task detail | Keep `result.artifacts` readable for editor/download compatibility. |
| `route` | `result.stt_provider`, `result.stt_model`, `metadata.queue_options`, `processing_plan.execution` | Must state both transcription route and whether AI notes/export require account-backed services. |

### Backend Builder Boundary For Stage 2

Stage 2 should not create a second competing read model. It should extract or
wrap the existing `backend/core/task_detail.py` projection into one normalized
task snapshot that can be returned by job list and detail surfaces.

Recommended shape:

```json
{
  "task_snapshot_version": "1",
  "task_id": "...",
  "overall_status": "running",
  "current_step": "transcription",
  "progress": 42,
  "steps": [
    {"id": "source_fetch", "title": "素材获取与校验", "status": "completed"}
  ],
  "failure_reason": null,
  "next_action": null,
  "artifacts": [],
  "route": {
    "transcription": "local",
    "stt_provider": "local",
    "stt_model": "medium",
    "ai_note_requires_account": true
  },
  "actions": [],
  "data_quality": {}
}
```

The existing `/jobs/{task_id}` payload should remain readable. New surfaces can
prefer `task_snapshot`, while old fields stay during migration.

## Staged Execution

### Stage 1: Status Source Audit

Status: completed on 2026-06-30

Outcome:

- Mapped where task status is currently created, transformed, cached, and
  rendered.
- Identified old fields that must remain readable.
- Decided the normalized snapshot shape and compatibility strategy.

Likely files/surfaces:

- `backend/core/`
- `backend/routers/`
- `frontend/src/app/`
- `frontend/src/routes/`
- `docs/result_schema.md`
- `docs/workflow_design_system.md`

Validation:

- Docs-only.
- `git diff --check`

Stop condition:

- Concrete field mapping exists above. Stage 2 can start from
  `backend/core/task_detail.py`.

### Stage 2: Backend Snapshot Builder

Status: completed on 2026-06-30

Outcome:

- Added one backend-owned task snapshot builder in `backend/core/task_detail.py`.
- Kept old job/result data readable and returned `task_snapshot` additively.
- Covered completed, running, failed, cancelled, transcript-only, and partially
  completed tasks through snapshot tests.

Validation:

- `./venv/bin/python -m pytest tests/test_task_detail.py -q`
- `git diff --check`

Stop condition:

- `/jobs`, `/jobs/{task_id}`, and `/jobs/{task_id}/detail` can return the
  normalized snapshot without frontend guessing.

### Stage 3: Frontend Consumers

Status: completed on 2026-06-30

Outcome:

- Home recent activity, history records, processing detail, and current task
  entrances prefer `task_snapshot` when backend data provides it.
- Shared frontend mappers now normalize task state, current job cards, history
  entries, failure reasons, next actions, and live step detail from the backend
  snapshot before falling back to legacy fields.
- Processing detail initial state can carry `task_snapshot` from navigation
  state, reducing stale `queued` or locally guessed status on first paint.

Validation:

- `npm run build:frontend`
- `git diff --check`

Stop condition:

- Major surfaces can consume the same backend snapshot fields. Stage 4 remains
  responsible for the visual timeline redesign.

### Stage 4: Processing Detail Surface

Status: completed on 2026-06-30

Outcome:

- Preserved the top task progress overview as the primary processing-detail
  surface.
- Removed the standalone large step timeline from the main content because it
  duplicated the overview and brought back a previously rejected generic
  pipeline block.
- `task_snapshot.steps` remains a data source for state, failure, and recovery
  logic, but the page should not render it as a full always-visible generic
  step list by default.
- The page shows readable reason, next action, available artifacts, and decision
  evidence without making raw technical fields the primary view.
- Raised dark-mode text contrast in the processing detail surface so labels and
  secondary explanations remain readable.

Validation:

- `npm run build:frontend`
- `git diff --check`
- `npm run change:check`
- Browser screenshot check was attempted, but local Chrome DevTools was not
  available in this environment.

Stop condition:

- Users can tell where the task is stuck and what to do next without reading
  internal logs.

## Execution Rule

Do not execute multiple stages in one turn unless the user explicitly asks for a
larger batch and the work still has one validation path. After each stage,
update this file's stage status and record the validation that actually ran.
