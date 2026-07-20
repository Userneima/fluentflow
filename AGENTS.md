# FluentFlow Agent Notes

FluentFlow is a maintained video/audio-to-transcript-and-note product. Keep
this file as a routing layer; put detailed plans, policies, and operating
procedures in focused docs.

## Start Here

- New execution conversations or cross-Agent handoffs: read
  `docs/cross_agent_context.md` and `docs/context_index.md` first.
- Broad or ambiguous work: read `docs/context_index.md` first.
- Cross-file, workflow, backend state/queue/auth/Agent API, deployment, or
  contract-changing work: read `docs/agent_task_brief.md`.
- Git staging, commits, mixed worktrees: read `docs/git_checkpoint_workflow.md`.
- Runtime data, deployment, backup, cleanup, recovery: read
  `docs/operations_runbook.md` and `deploy/README.md`.

## Project Map

- Backend: `backend/main.py`, `backend/routers/`, `backend/core/`.
- Frontend source: `frontend/src/`; do not hand-edit `frontend/dist/`.
- Tests: `tests/`; backend dependencies: `requirements.txt`.
- Frontend package/config: `package.json`, `vite.config.mjs`.
- Config templates: `.env.example`, `deploy/fluentflow.env.example`.
- Current product docs: `docs/current_version_plan.md`,
  `docs/product_overview.md`, `docs/changelog.md`.
- Design/workflow rules: `docs/ui_design_system.md`,
  `docs/workflow_design_system.md`, `docs/agent_mcp_parity.md`.
- Version/release docs: `docs/versioning_strategy.md`,
  `docs/release_process.md`.

## Commands

- Install: `./venv/bin/pip install -r requirements.txt` and `npm install`.
- Backend dev: `./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`.
- Frontend dev: `npm run dev:frontend`.
- Frontend build: `npm run build:frontend`.
- Backend tests: `./venv/bin/python -m pytest`.

## Rules

- Default language is Chinese; code, commands, variables, and commit messages
  use English.
- Before file edits, run `git status --short`. If dirty changes overlap the
  target files or ownership is unclear, stop and ask/split first.
- Keep each execution turn to one coherent, verifiable work unit. Stage broad
  requests; execute one stage at a time.
- Do not use `git stash`, `git reset`, or `git checkout` to hide or discard
  local changes unless explicitly asked.
- Do not commit `.env`, databases, runtime artifacts, media, transcripts,
  notes, logs, exports, private docs, or generated `frontend/dist`.
- Do not push, deploy, tag, release, or bump `VERSION` unless explicitly asked.
- Major UI or information-architecture changes require direction confirmation
  before editing. State what moves, hides, or changes in the user workflow.
- User-facing behavior changes belong in `docs/changelog.md` under
  `Unreleased`.
- Persistent data/API/result-shape changes must update the relevant schema or
  migration docs and keep old data readable.
- Agent-actionable workflow changes must preserve Agent/MCP parity per
  `docs/agent_mcp_parity.md`, unless explicitly recorded as UI-only.
- Browser verification should use the user's existing product window when
  available; do not launch a temporary browser profile unless approved.

## Validation

- Always run `git diff --check` before reporting completion.
- Match CI locally when relevant: `npm run lint:frontend` and
  `python3 -m pylint backend/ --errors-only --disable=import-error,no-member`.
- Frontend source changes: run `npm run build:frontend` and
  `npm run lint:frontend`.
- Backend logic/state/queue/auth/quota/API/persistence changes: run focused
  `pytest` coverage and `pylint backend/ --errors-only`.
- Before a finished local commit: stage intentionally and run
  `npm run change:check:staged`.

## Privacy Boundary

Public repo files must not contain secrets, tokens, private workflow notes,
generated user content, local machine paths, production domains, or personal
names unless intended as public product information. Keep private material in
ignored paths such as `docs/private/`, `.env`, `data/`, `backend/data/`,
`logs/`, `exports/`, and `reports/`.
