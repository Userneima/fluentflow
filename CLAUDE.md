# FluentFlow Project Rules

Default language: Chinese. Code, commands, variables, and commit messages use English.

FluentFlow is a maintained video/audio-to-transcript-and-note product.

## Project Shape

- Backend: `backend/main.py`, `backend/routers/`, `backend/core/`.
- Frontend source: `frontend/src/`; built output: `frontend/dist/`.
- UI design system: `docs/ui_design_system.md`.
- Changelog: `docs/changelog.md`.

## Validation

- Frontend: `npm run build:frontend`.
- Backend logic/state/flow/persistence changes: `./venv/bin/python -m pytest tests/ -x -q`.
- Backend syntax-only: `python3 -m py_compile <file>.py`.
- Always run `git diff --check`.

## Scope

- Keep changes minimal and local.
- Preserve existing worktree changes; do not reset or checkout files unless explicitly requested.
- Do not push or deploy unless explicitly requested.

## Privacy

Do not commit secrets, local runtime state, generated media/transcripts/notes, personal workflow notes, local machine paths, or production-only deployment details. Keep private material in ignored local paths.
