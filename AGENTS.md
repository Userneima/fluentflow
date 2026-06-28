# FluentFlow Agent Notes

FluentFlow is a maintained video/audio-to-transcript-and-note product.

## Project Shape

- Backend: `backend/main.py`, `backend/routers/`, `backend/core/`.
- Frontend source: `frontend/src/`.
- Built frontend app: `frontend/dist/` from Vite.
- UI design system: `docs/ui_design_system.md`.
- Changelog: `docs/changelog.md`.

## Rules

- Edit frontend source under `frontend/src`; do not hand-edit `frontend/dist`.
- Before major UI or information-architecture changes, discuss the proposed direction with the user first. State what will move, hide, or be removed; what user workflow changes; and what existing settings/data remain intact. Wait for explicit confirmation before editing. Small visual fixes and bug fixes may still be implemented directly.
- After frontend changes, run `npm run build:frontend`.
- For backend logic, state, queue, auth, quota, or persistence changes, run relevant pytest coverage.
- Always run `git diff --check` before reporting completion.
- Do not commit `.env`, SQLite databases, runtime artifacts, media files, transcripts, notes, logs, exports, or private docs.
- Do not push or deploy unless explicitly requested.

## Privacy Boundary

Public repo files should avoid personal names, local machine paths, production domains, credentials, private workflow notes, and generated user content. Keep those in ignored local files such as `docs/private/`, `.env`, `data/`, `backend/data/`, `logs/`, `exports/`, and `reports/`.
