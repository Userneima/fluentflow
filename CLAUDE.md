# FluentFlow Project Rules

Default language: Chinese. Code, commands, variables, and commit messages use English.

FluentFlow is a maintained video/audio-to-transcript-and-Feishu-note product, not a throwaway demo.

---

## Project Shape

- Backend: `backend/main.py` (app factory) + `backend/routers/` (11 route modules) + `backend/core/` (focused modules).
  - Route modules import shared helpers from `backend.core.server_helpers` as `H`.
  - Re-exports in `main.py` exist for test backward compatibility.
- Frontend source: `frontend/src/`, built output: `frontend/dist/` (Vite).
  - App entry: `frontend/src/app.jsx`
  - Routes/pages: `frontend/src/routes/`
  - App shell/provider/auth: `frontend/src/app/`
  - Reusable UI: `frontend/src/components/`
  - Shared logic: `frontend/src/lib/`
- UI design system: `docs/ui_design_system.md`
- Server deploy workflow: `docs/server_deploy_workflow.md`
- Changelog: `docs/changelog.md`

---

## Agent Autonomy

- Do not hand off work to the user when it can be done directly by Claude Code.
- Minimize user operations; ask the user to act only for credentials, secrets, account authorization, payment confirmation, CAPTCHA, or actions that cannot be performed safely from the local environment.

---

## Context Budget

Always exclude from searches unless the task explicitly needs them:

- `node_modules/`, `dist/`, `.git/`, `package-lock.json`, `.DS_Store`

Prefer targeted searches (Grep by symbol or selector) over reading large files whole.

---

## Validation

- Frontend: `npm run build:frontend`
- Backend logic/state/flow/persistence changes: `./venv/bin/python -m pytest tests/ -x -q`
- Backend syntax-only: `python3 -m py_compile <file>.py`
- Visual-only (CSS/copy): build check is enough unless behavior, routing, auth, or data state changed.
- After critical user-facing, data, deployment, auth, quota, or workflow changes, add an `Unreleased` note to `docs/changelog.md`.

---

## Frontend Rules

- Edit source under `frontend/src`; do not hand-edit Vite output under `frontend/dist/`.
- After any frontend change, run `npm run build:frontend`.
- Vite owns hashed assets and cache busting — do not add manual query-string versions.
- Before visual UI work, read `docs/ui_design_system.md` and use semantic Tailwind tokens.

---

## Change Scope

- Keep edits minimal and local. Do not refactor unrelated code.
- Preserve existing changes in the worktree; do not reset or checkout files unless explicitly asked.
- Match verification effort to change risk (see Validation section).

---

## Problem Solving

1. Identify the direct cause
2. Identify why it was able to happen
3. Make the smallest change that fixes it AND prevents the same class of problem
4. Add a test, type constraint, or validation as a guard

If the same problem reappears, strengthen the guard layer first — do not just fix the symptom.

---

## Deployment

- Do not push or deploy unless explicitly asked.
- If the user says `上传服务器`, `部署到服务器`, `上线`, `更新线上版本`, `发布到 fluentflow.icu`, or `把当前修改同步到服务器`, read `docs/server_deploy_workflow.md` first and follow it.
