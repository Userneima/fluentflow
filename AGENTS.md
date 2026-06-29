# FluentFlow Agent Notes

FluentFlow is a maintained video/audio-to-transcript-and-note product.

## Project Shape

- Backend: `backend/main.py`, `backend/routers/`, `backend/core/`.
- Frontend source: `frontend/src/`.
- Built frontend app: `frontend/dist/` from Vite.
- UI design system: `docs/ui_design_system.md`.
- Agent / MCP parity rule: `docs/agent_mcp_parity.md`.
- Changelog: `docs/changelog.md`.

## Rules

- Edit frontend source under `frontend/src`; do not hand-edit `frontend/dist`.
- Before major UI or information-architecture changes, discuss the proposed direction with the user first. State what will move, hide, or be removed; what user workflow changes; and what existing settings/data remain intact. Wait for explicit confirmation before editing. Small visual fixes and bug fixes may still be implemented directly.
- After frontend changes, run `npm run build:frontend`.
- For backend logic, state, queue, auth, quota, or persistence changes, run relevant pytest coverage.
- When adding or changing a user-facing workflow, run the Agent / MCP parity check in `docs/agent_mcp_parity.md`. Agent-actionable capabilities must update `/agent/v1`, MCP tools, task package fields, schemas, docs, or tests in the same work unit, unless the change is explicitly recorded as UI-only.
- Always run `git diff --check` before reporting completion.
- Do not commit `.env`, SQLite databases, runtime artifacts, media files, transcripts, notes, logs, exports, or private docs.
- Do not push or deploy unless explicitly requested.

## Versioning And Commit Discipline

- Follow `docs/versioning_strategy.md` for app versions, atomic commits, changelog entries, schema versions, release tags, and rollback decisions.
- One conversation is not one commit. Split work into separate commits by product purpose.
- Do not commit after every tiny edit by default. Commit after a coherent, validated work unit, or make temporary `wip:` commits only when the user explicitly asks to save progress.
- Codex may create a normal checkpoint commit without an extra prompt when the work unit is complete, validated, clearly scoped, and independently reversible.
- Do not commit when the user asks not to, when the work is still exploratory, when validation has not run, or when unrelated dirty changes make the commit boundary unclear. In those cases, leave changes uncommitted and explain why.
- Do not create broad `misc`, `update`, or `fix things` commits. Each commit should explain one coherent user or maintainer outcome.
- Stage intentionally. When unrelated changes exist, inspect the diff and stage only the hunks/files for the current commit.
- Use English Conventional Commit style for new commit messages when practical, for example `fix: handle stale dashboard jobs` or `docs: clarify release process`.
- Do not bump `VERSION` for ordinary fixes. Bump the app version only when preparing a coherent release.
- User-visible behavior changes belong in `docs/changelog.md` under `Unreleased`; shipped release sections are prepared during release.
- Persistent data/API/result-shape changes must update the relevant schema or migration documentation and keep old data readable.
- Before creating a finished local commit, run `npm run change:check:staged` after staging the intended files. Treat warnings as review prompts; fix failures before committing.
- Before preparing or tagging a release, run the release flow in `docs/release_process.md`; do not treat a checkpoint commit as a product version.

## Privacy Boundary

Public repo files should avoid personal names, local machine paths, production domains, credentials, private workflow notes, and generated user content. Keep those in ignored local files such as `docs/private/`, `.env`, `data/`, `backend/data/`, `logs/`, `exports/`, and `reports/`.
