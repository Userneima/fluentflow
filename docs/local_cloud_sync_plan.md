# Local And Cloud Workspace Notes

## Current Rule

The backend job store is the source of truth for task history.

Browser local history is only a recent-display cache. It must not be treated as a second durable history database, and it must not trigger a legacy "discover local history and import into account" flow.

## Removed Legacy Flow

The one-time local-history import route was a transition plan and is no longer part of the product:

- No UI prompt for "发现本机历史 / 导入当前账号".
- No local candidate export endpoint.
- No authenticated account import endpoint.
- No new `imported_*` jobs should be created from browser local history.

Old browser cache entries can still be displayed locally when the editor already has the full cached result, but they should not be uploaded or converted into account jobs through the removed flow.

## Current Data Flow

```text
Desktop shortcut
  -> local FastAPI on 127.0.0.1
  -> local frontend assets
  -> optional cloud workspace proxy for account/jobs/upload APIs
  -> backend job database for durable task history
```

## Product Boundary

- New work should create normal backend jobs as early as possible, including video-link tasks after metadata is fetched.
- History cleanup, deletion, retry, download, and editor opening should operate on backend jobs.
- Browser cache can help reopen recent local-only results, but it is not a migration source.
- If a future migration is needed, design it as a new explicit migration feature instead of reviving the removed import endpoints.

## Validation

Required guardrails:

- Frontend source must not call the removed local-history import routes.
- Backend must return 404 for the removed routes.
- Cloud workspace proxy local-only route lists must not include removed import routes.
