# Agent / MCP Parity Rule

FluentFlow has three product entrances:

- UI: for people operating the product directly.
- Agent API (`/agent/v1`): for scripts and stable programmatic workflows.
- MCP: for external agents such as Claude Code, Codex, and other MCP clients.

The product should not add important workflow capabilities only to the UI while leaving Agent API or MCP behind.

Current MCP server setup lives in `docs/mcp_integration.md`.

## Core Rule

When adding or changing a user-facing workflow, always check whether the capability is agent-actionable.

A capability is agent-actionable if an external agent may reasonably need to:

- submit it
- wait for it
- inspect its result
- retry, regenerate, or repair it
- export it
- diagnose its failure
- compose it with another workflow

If yes, update the Agent API and MCP layer in the same work unit, or explicitly record why it is intentionally UI-only.

## Definition Of Done

For every meaningful workflow change, check these before reporting completion:

- UI behavior is implemented or intentionally unchanged.
- Backend capability is implemented or intentionally unchanged.
- Agent API impact is assessed.
- MCP tool impact is assessed.
- Agent Task Package fields are added or updated when agents need the data.
- Result schema, API docs, or MCP docs are updated when the contract changes.
- Tests cover any changed Agent API / MCP contract.
- `docs/changelog.md` records user-visible or maintainer-visible behavior changes.

## Prefer Package Fields Before New Tools

Do not add a new MCP tool just because a new field exists.

Prefer updating the task package when the agent only needs to inspect data. Add or extend a tool only when the agent needs to perform a distinct action.

Examples:

| Product change | Preferred Agent / MCP response |
| --- | --- |
| Add source subtitle availability | Add `source.video_source.subtitles` or equivalent package field |
| Add Bilibili downloader metadata | Add source metadata fields and tests |
| Add a new export destination | Add or extend an export tool |
| Add a new note mode | Extend `regenerate_note` parameters and package note metadata |
| Add failure recovery guidance | Add diagnosis and `next_actions`; add a tool only if the action is executable |

## MCP Tool Design

MCP tools should wrap stable Agent API capabilities, not internal implementation details.

The first-class MCP actions should map to stable product actions:

- submit a task
- wait for a task
- get a task package
- regenerate a note
- export a result
- diagnose or explain a task
- download or locate an artifact

Avoid exposing low-level helpers such as "call this provider", "read this SQLite row", or "run this internal parser" as MCP tools unless they are intentionally productized.

## Review Questions

Use this checklist during implementation:

1. Can an external agent complete the same workflow without opening the UI?
2. If the workflow is long-running, can the agent submit, wait, resume, and inspect failure state?
3. Does `GET /agent/v1/tasks/{task_id}/package` contain enough source, transcript, note, artifact, plan, trace, diagnosis, and next-action data?
4. Does an existing MCP tool need a new parameter or output field?
5. Is a new MCP tool truly needed, or is a task package field enough?
6. Are old clients still compatible if fields are added?
7. Is the intentionally UI-only decision documented when Agent/MCP support is skipped?

## Intentional UI-Only Changes

Some changes do not need Agent API or MCP work. Examples:

- purely visual layout changes
- copy changes that do not alter workflow meaning
- local hover, focus, or responsive styling fixes
- analytics-only UI instrumentation that does not affect task behavior

When in doubt, treat workflow state, exported data, retry actions, and failure explanations as agent-actionable.
