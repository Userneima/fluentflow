# FluentFlow Agent Notes

FluentFlow is Wang Yuchao's video/audio-to-transcript-and-Feishu-note tool. It is a maintained product, not a throwaway demo.

## Project Shape

- Backend: `backend/main.py` (app factory) + `backend/routers/` (11 route modules) + `backend/core/` (focused modules).
  - Route modules import shared helpers from `backend.core.server_helpers` as `H`.
  - Re-exports in `main.py` exist for test backward compatibility.
- Frontend source: `frontend/src/`.
- Built frontend app: `frontend/dist/` from Vite.
- App entry: `frontend/src/app.jsx`. Routes/pages under `frontend/src/routes/`. App shell/provider/auth under `frontend/src/app/`. Reusable UI under `frontend/src/components/`. Shared logic under `frontend/src/lib/`.
- UI design system: `docs/ui_design_system.md`.
- Server deploy workflow: `docs/server_deploy_workflow.md`.
- Changelog: `docs/changelog.md`.

## Frontend Rules

- Edit source under `frontend/src`; do not hand-edit Vite output under `frontend/dist/`.
- After any frontend change, run `npm run build:frontend`.
- Vite owns hashed assets and cache busting. Do not add manual query-string versions.
- If a UI change should be visible, verify the marker exists in both source and built output, for example with `rg "marker" frontend/src frontend/dist/assets`.
- Before visual UI work, read `docs/ui_design_system.md` and use semantic Tailwind tokens instead of raw persistent surface colors.

## Validation

- Frontend: `npm run build:frontend`.
- Backend logic/state/flow/persistence changes: `./venv/bin/python -m pytest tests/ -x -q`.
- Backend syntax-only: `python3 -m py_compile backend/main.py backend/core/<file>.py`.
- Always run `git diff --check` before reporting completion.
- For subjective visual polish, build/static checks are enough unless behavior, routing, auth, upload, payment, or data state changed.

## Natural Language Skill Routing

The user should not need to remember skill names. Infer the workflow from their goal and use the matching installed skill when available:

- Broken behavior, repeated regressions, confusing errors, slow flows, or "check why this keeps failing": use `diagnosing-bugs`.
- Requests to prevent the same bug from coming back, protect critical behavior, or fix with tests first: use `tdd`.
- Messy code, module boundaries, large refactors, `app.jsx`-style splits, or maintainability concerns: use `codebase-design` or `improve-codebase-architecture`.
- Unclear product direction, feature scope, or "think this through before building": use `grilling` or `grill-with-docs`.
- Domain terms, workflow semantics, or decisions that future agents may misunderstand: use `domain-modeling`.
- Review requests for current work, branches, or pull requests: use `review`.

When these skills are not available in the current session, follow the same underlying discipline manually and say so briefly. Do not ask the user to name the skill unless they explicitly want that level of control.

## Codex Link Analysis

- When the user gives a Douyin/video link and asks Codex to transcribe or analyze it, use `scripts/codex_transcribe_link.py` first.
- The script submits the link to the local FluentFlow backend, waits for completion, and writes a Codex-readable JSON result under ignored local data storage.
- Prefer the script output transcript/segments over UI history when discussing the video, because it is the direct task result for the current request.

## Change Scope

- Keep edits minimal and local. Do not refactor unrelated pages while fixing one UI surface.
- Preserve user or previous-agent changes in the dirty worktree; do not reset or checkout files unless explicitly asked.
- After critical user-facing, data, deployment, auth, quota, or workflow changes, add a concise `Unreleased` note to `docs/changelog.md`.

## Deployment

- Do not push or deploy unless explicitly asked.
- If the user says `上传服务器`, `部署到服务器`, `上线`, `更新线上版本`, `发布到 fluentflow.icu`, or `把当前修改同步到服务器`, read `docs/server_deploy_workflow.md` first and follow it.
