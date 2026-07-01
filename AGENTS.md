# FluentFlow Agent Notes

FluentFlow is a maintained video/audio-to-transcript-and-note product.

## Project Shape

- Backend: `backend/main.py`, `backend/routers/`, `backend/core/`.
- Backend dependencies: `requirements.txt`; tests live under `tests/`.
- Frontend package/config: `package.json`, `vite.config.mjs`.
- Frontend source: `frontend/src/`.
- Built frontend app: `frontend/dist/` from Vite.
- Local runtime config template: `.env.example`; server deployment template: `deploy/fluentflow.env.example`.
- UI design system: `docs/ui_design_system.md`.
- Workflow design system: `docs/workflow_design_system.md`.
- Agent / MCP parity rule: `docs/agent_mcp_parity.md`.
- Execution task brief: `docs/agent_task_brief.md`.
- Versioning and release: `docs/versioning_strategy.md`, `docs/release_process.md`.
- Project skills: `.agents/skills/`.
- Changelog: `docs/changelog.md`.

## Common Commands

- Install dependencies: `./venv/bin/pip install -r requirements.txt` and `npm install`.
- Backend dev server: `./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload`.
- Frontend dev server: `npm run dev:frontend`.
- Frontend build: `npm run build:frontend`.
- Backend tests: `./venv/bin/python -m pytest`.

## Rules

- Edit frontend source under `frontend/src`; do not hand-edit `frontend/dist`.
- Before major UI or information-architecture changes, discuss the proposed direction with the user first. State what will move, hide, or be removed; what user workflow changes; and what existing settings/data remain intact. Wait for explicit confirmation before editing. Small visual fixes and bug fixes may still be implemented directly.
- Do not commit `.env`, SQLite databases, runtime artifacts, media files, transcripts, notes, logs, exports, or private docs.
- Do not push or deploy unless explicitly requested.
- Read `docs/agent_task_brief.md` before adding pages, changing user workflows,
  changing backend state/queue/auth/Agent API behavior, or doing broad multi-module work.
- Keep each execution turn to one coherent, verifiable work unit. If the request
  spans multiple workflows, modules, or risk areas, create a short staged plan
  first and execute one stage at a time.
- Repeated FluentFlow workflows should use the matching project skill in
  `.agents/skills/` when one applies.
- Before file edits, run `git status --short`. If dirty changes overlap the
  target files or make the commit boundary unclear, stop and ask/split first.
  If they are unrelated, continue carefully and report that they were left untouched.

## Validation Checklist

- Always run `git diff --check` before reporting completion.
- Frontend source changes: run `npm run build:frontend`.
- Backend logic, state, queue, auth, quota, API, or persistence changes: run relevant `pytest` coverage.
- User-facing workflow changes: run the Agent / MCP parity check in `docs/agent_mcp_parity.md`. Agent-actionable capabilities must update `/agent/v1`, MCP tools, task package fields, schemas, docs, or tests in the same work unit, unless the change is explicitly recorded as UI-only.
- Before creating a finished local commit, stage intentionally and run `npm run change:check:staged`.

## Agent Notes Maintenance

- Keep this file as a routing layer, not a manual.
- Add rules only for repeated mistakes, structural changes, validation changes, privacy boundaries, or long-lived workflow decisions.
- Before adding detail here, check whether it belongs in a focused doc instead.
- If this file grows beyond 90 lines, prefer pruning or moving details out before adding more.

## Versioning And Commit Discipline

- Follow `docs/versioning_strategy.md` for app versions, atomic commits, changelog entries, schema versions, release tags, and rollback decisions.
- One conversation is not one commit. Split work into separate commits by product purpose.
- At the end of each completed execution task, create a local checkpoint commit by default when the work unit is coherent, validated, clearly scoped, and independently reversible.
- Do not commit after every tiny edit. Commit after a coherent, validated work unit, or make temporary `wip:` commits only when the user explicitly asks to save progress.
- Do not commit when the user asks not to, when the work is still exploratory, when validation has not run, or when unrelated dirty changes make the commit boundary unclear. In those cases, split the work if possible; otherwise leave changes uncommitted and explain why.
- Do not create broad `misc`, `update`, or `fix things` commits. Each commit should explain one coherent user or maintainer outcome.
- Stage intentionally. When unrelated changes exist, inspect the diff and stage only the hunks/files for the current commit.
- Use English Conventional Commit style for new commit messages when practical, for example `fix: handle stale dashboard jobs` or `docs: clarify release process`.
- Do not bump `VERSION` for ordinary fixes. Bump the app version only when preparing a coherent release.
- User-visible behavior changes belong in `docs/changelog.md` under `Unreleased`; shipped release sections are prepared during release.
- Persistent data/API/result-shape changes must update the relevant schema or migration documentation and keep old data readable.
- Before preparing or tagging a release, run the release flow in `docs/release_process.md`; do not treat a checkpoint commit as a product version.

## Privacy Boundary

Public repo files must not contain credentials, tokens, private workflow notes, generated user content, local machine paths, production domains, or personal names unless that identity is explicitly intended as public project information. Keep private material in ignored local files such as `docs/private/`, `.env`, `data/`, `backend/data/`, `logs/`, `exports/`, and `reports/`.

Configuration templates such as `.env.example` may be committed only with blank values, dummy placeholders, or local-only examples such as `http://127.0.0.1:8000`.
