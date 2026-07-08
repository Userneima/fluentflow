# FluentFlow Context Index

Use this file as the first stop when orienting inside FluentFlow. It tells you
which documents are current, which are supporting references, and which paths
are local runtime data rather than source.

## Current Truth Sources

| Need | Read |
| --- | --- |
| Product goal, boundary, and non-goals | `docs/current_version_plan.md` |
| Product positioning and target users | `docs/product_overview.md` |
| Architecture and API surface | `docs/architecture.md` |
| Runtime, deployment, backup, cleanup, and recovery | `docs/operations_runbook.md` |
| Result/job schema meaning | `docs/result_schema.md` |
| Agent API and MCP parity | `docs/agent_mcp_parity.md`, `docs/mcp_integration.md` |
| Git, work-unit, and commit boundaries | `docs/agent_task_brief.md`, `docs/git_checkpoint_workflow.md`, `docs/versioning_strategy.md` |
| User-facing change history | `docs/changelog.md` |

## Task Routing

| Task touches | Read before editing |
| --- | --- |
| Frontend UI or page responsibility | `docs/ui_design_system.md`, `docs/workflow_design_system.md` |
| Homepage review or redesign | `.agents/skills/fluentflow-homepage-design/SKILL.md` |
| Agent-actionable workflow changes | `docs/agent_mcp_parity.md` |
| Deployment, env vars, storage, backup, or rollback | `docs/operations_runbook.md`, `deploy/README.md` |
| Release preparation | `docs/release_process.md`, `docs/versioning_strategy.md` |
| Broad or risky execution work | `docs/agent_task_brief.md` |

## Historical Or Supporting Docs

Documents under `docs/archive/` are preserved for context only. Do not treat
them as current execution plans unless a current truth source links to a
specific archived decision.

Focused plan and design documents such as `docs/task_status_model_unification_plan.md`,
`docs/task_list_reconciliation_plan.md`, `docs/long_transcript_coverage_notes_plan.md`,
and `docs/note_mode_evaluation_plan.md` are supporting references. Read them only
when the current task touches that domain.

## Runtime Data Boundary

These paths are local data, generated output, or private material. They are not
source-of-truth code and must not be committed:

- `.env`, `.env.before-*`
- `data/`, `backend/data/`
- `视频文件/`, `backend/视频文件/`
- `logs/`, `exports/`, `reports/`
- `frontend/dist/`, `build/`
- `docs/private/`

Do not delete `data/` or `backend/data/` just because they are ignored. They may
contain task history, source media, artifacts, edited transcripts, eval data, or
backup files. Use `docs/operations_runbook.md` and the cleanup scripts before
removing durable runtime data.

Default runtime data now belongs under the OS application data directory, such
as `~/Library/Application Support/FluentFlow` on macOS. After a successful
`scripts/migrate_runtime_storage.py --apply` run and verification, keep the
legacy repo-local data for 14 days as a rollback window before deleting it.

## Current Code Shape Notes

- Backend entrypoint: `backend/main.py`; routers live in `backend/routers/`;
  core processing helpers live in `backend/core/`.
- Frontend source lives in `frontend/src/`; do not hand-edit `frontend/dist/`.
- Some extraction/refactor docs are intentionally historical. Inspect actual
  imports before assuming a helper is the active implementation.
