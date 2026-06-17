# Local And Cloud Sync Plan

## Status

Phase A is being implemented.

This document records how FluentFlow should make the local desktop shortcut, the public web app, and logged-in account history behave as one workspace.

## Goal

The user goal is multi-device continuity:

- Open `https://fluentflow.icu` on any device.
- Open the local macOS shortcut on the maintainer's Mac.
- Log in with the same account.
- See the same task history, balance, and completed results.

The cloud backend should be the source of truth for logged-in work.

## Current Problem

The product had two different data sources:

- Cloud web app: account-scoped jobs in the server job database.
- Local desktop shortcut: local backend and browser `localStorage`.

Setting `FLUENTFLOW_CLOUD_WORKSPACE_URL` makes future local API calls proxy to the cloud backend, but it does not migrate old local records. Existing local records may live in:

- Browser `localStorage` under `fluentflow_history`.
- Local SQLite job store under `data/fluentflow_jobs.sqlite`.

Therefore an empty "Recent Activity" after login can be correct technically but wrong for the product goal.

## Product Rule

Do not silently upload old local transcription content.

Transcripts and summaries are user content. Importing them to the cloud account is a data transfer, so the UI must ask for explicit confirmation.

## Phase A Scope

Phase A includes:

- Default the macOS desktop launcher to `FLUENTFLOW_CLOUD_WORKSPACE_URL=https://fluentflow.icu`.
- Keep local frontend assets served from `127.0.0.1`.
- Proxy account, job, upload, queue, admin, quota, and runtime API calls to the cloud backend.
- Add a local-only history candidate endpoint for the desktop workspace.
- Add an authenticated cloud import endpoint.
- Show a logged-in UI prompt when local records are detected.
- Import confirmed local records into the current account.
- Deduplicate imported records by original task id and source fingerprint.

Phase A does not include:

- Automatic import without confirmation.
- Importing original source audio/video files.
- Full bidirectional offline sync.
- Conflict resolution for independently edited versions of the same transcript.
- Payment or quota recharge changes.

## Data Flow

```text
Desktop shortcut
  -> local FastAPI on 127.0.0.1
  -> local frontend assets
  -> API proxy to https://fluentflow.icu
  -> cloud account session and cloud job database
```

For old local records:

```text
Browser localStorage / local SQLite
  -> local candidate detection
  -> user confirms import
  -> POST /account/import-history on cloud
  -> completed imported jobs under user:{account_id}
  -> Recent Activity reloads from cloud jobs
```

## Import Semantics

Imported records become completed account jobs with:

- A new deterministic `imported_*` task id.
- `client_id = user:{account_id}`.
- `source_type = imported_local_history` or the original source type when available.
- Preserved transcript text, segments, summary, duration, STT metadata, and edit metadata when available.
- `source_file_available = false`.
- `playback_audio_available = false`.
- Metadata containing the original task id and source fingerprint.

The original source media is intentionally not imported in Phase A.

## UX

After login, if local records exist but are not in the account history:

```text
发现本机历史
本机有 X 条旧记录尚未进入当前账号。确认后会上传转录文本和摘要，用于多端同步。
[导入当前账号]
```

After import:

```text
已导入 X 条本机历史到当前账号。
```

If import fails, show the error in the same prompt and keep the candidates available.

## Risk Boundaries

- Import is user-confirmed because transcript content may be sensitive.
- Imported jobs do not charge quota because they are historical records, not new processing work.
- Imported jobs do not restore source-file playback unless future migration explicitly uploads source media.
- Local candidate export must only work for local desktop cloud-workspace mode.
- Cloud import must require an authenticated account session.

## Validation

Required validation for this scope:

- Backend account import tests:
  - unauthenticated import is rejected.
  - logged-in import creates completed account jobs.
  - repeated import deduplicates.
- Frontend build succeeds.
- Launcher shell syntax check succeeds.

