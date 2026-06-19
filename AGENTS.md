# FluentFlow Agent Notes

FluentFlow is Wang Yuchao's video/audio-to-transcript-and-Feishu-note tool. It is a maintained product, not a throwaway demo.

## Project Shape

- Backend: `backend/main.py` plus focused modules under `backend/core/`.
- Frontend source: `frontend/src/`.
- Built frontend app: `frontend/dist/` from Vite.
- UI design system: `docs/ui_design_system.md`.
- Server deploy workflow: `docs/server_deploy_workflow.md`.
- Changelog: `docs/changelog.md`.

## Frontend Rules

- Edit source under `frontend/src`; do not hand-edit Vite output under `frontend/dist/`.
- After any frontend change, run `npm run build:frontend`.
- Vite owns hashed assets and cache busting. Do not add manual query-string versions.
- If a UI change should be visible, verify the marker exists in both source and built output, for example with `rg "marker" frontend/src frontend/dist/assets`.
- Keep route/page work out of the monolithic `frontend/src/app.jsx` when practical. New or actively changed pages should live under `frontend/src/routes/` and be imported as modules.
- Before visual UI work, read `docs/ui_design_system.md` and use semantic Tailwind tokens instead of raw persistent surface colors.

## Validation

- Frontend: `npm run build:frontend`.
- Python syntax for backend touches: `python3 -m py_compile backend/main.py backend/core/<file>.py`.
- Always run `git diff --check` before reporting completion.
- For subjective visual polish, build/static checks are enough unless behavior, routing, auth, upload, payment, or data state changed.

## Change Scope

- Keep edits minimal and local. Do not refactor unrelated pages while fixing one UI surface.
- Preserve user or previous-agent changes in the dirty worktree; do not reset or checkout files unless explicitly asked.
- After critical user-facing, data, deployment, auth, quota, or workflow changes, add a concise `Unreleased` note to `docs/changelog.md`.

## Deployment

- Do not push or deploy unless explicitly asked.
- If the user says `上传服务器`, `部署到服务器`, `上线`, `更新线上版本`, `发布到 fluentflow.icu`, or `把当前修改同步到服务器`, read `docs/server_deploy_workflow.md` first and follow it.
