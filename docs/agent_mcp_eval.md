# Agent / MCP Eval

This document defines the first maintainable Agent/MCP eval layer for
FluentFlow. It checks whether an external agent can complete realistic product
flows through the stable MCP tools and Agent API shape, not only whether the MCP
server starts.

## Goal

The eval should answer:

- Can an agent submit work through the product-level tools?
- Can it wait, inspect the Agent Task Package, diagnose failure, regenerate a
  note, and export a result?
- Can the run produce reviewable metrics without storing private content,
  credentials, downloaded media, transcripts, logs, databases, or reports in
  the repository?

This is not a note-quality eval, STT quality eval, downloader smoke test, or
live YouTube reliability test.

## Eval Modes

| Mode | Default | Network | Purpose |
| --- | --- | --- | --- |
| Offline/mock | Yes | No | Exercise full Agent/MCP task choreography with deterministic fake task data. |
| Backend e2e | No | Local backend only | Exercise the MCP stdio server and existing Agent API with safe local inputs. |
| Live/network | No | External network | Future opt-in checks for real video platforms, credentials, and provider behavior. |

Offline/mock eval is the default because it is stable in CI and local agent
threads. It uses sample URLs and synthetic task packages, but never downloads
media or calls real video platforms.

Backend e2e is intentionally smaller at this stage. It should use safe local
inputs unless explicitly extended. Live/network eval must stay opt-in and must
not commit fetched media, transcripts, credentials, or generated logs.

## First Use Cases

| Case | Mode | Input | Expected tools/API | Verifiable output | Metrics |
| --- | --- | --- | --- | --- | --- |
| `video_link_success_note_export` | Offline/mock | Synthetic YouTube URL | `submit_video_link`, `wait_task`, `get_task_package`, `regenerate_note`, `export_result` | Task id exists, wait is done, package has video source and skipped/completed note state, regenerated package has completed note, export result has target/status summary. | Tool calls, elapsed seconds, task status, package summary, export summary, errors. |
| `video_link_failure_diagnosis` | Offline/mock | Synthetic unavailable video URL | `submit_video_link`, `wait_task`, `diagnose_task`, `get_task_package` | Failure is recorded as diagnosis/package summary instead of crashing the eval. | Tool calls, elapsed seconds, failure status, diagnosis code/note summary, errors. |
| `backend_transcript_package_diagnosis` | Backend e2e | Short synthetic transcript text | `submit_transcript`, `wait_task`, `get_task_package`, `diagnose_task` | Backend returns a task id and package/diagnosis summary through MCP. | Tool calls, elapsed seconds, task status, package summary, diagnosis summary, errors. |

The first two cases cover the full video-link agent workflow without external
network dependency. The backend case covers the real MCP stdio bridge and Agent
API with a safe local input.

## Running

From the repo root:

```bash
npm run agent:mcp:eval -- --mock
```

This prints JSON to stdout. It does not write reports by default.

Optional backend check, with a running backend:

```bash
npm run agent:mcp:eval -- --backend-e2e
```

Use the existing MCP checks for startup and smoke coverage:

```bash
npm run mcp:check
npm run mcp:check:e2e
```

## JSON Shape

The script emits one JSON object:

```json
{
  "ok": true,
  "mode": "mock",
  "summary": {"total": 2, "passed": 2, "failed": 0},
  "cases": [
    {
      "name": "video_link_success_note_export",
      "status": "passed",
      "elapsed_seconds": 0.01,
      "tool_calls": [
        {"name": "submit_video_link", "status": "ok", "elapsed_seconds": 0.0}
      ],
      "task_id": "eval-success",
      "diagnosis": {"code": "transcript_only_mode"},
      "package": {"task_status": "completed", "source_type": "video_link"},
      "error": null
    }
  ]
}
```

Summaries intentionally avoid full transcript text, note markdown, media paths,
or credentials. Future file output should default to ignored locations such as
`reports/`.

## Boundaries

- Do not use real user videos, private subtitles, API keys, downloaded media,
  logs, reports, SQLite databases, or generated exports as tracked fixtures.
- Do not treat offline/mock success as proof that YouTube, Bilibili, Douyin, STT
  providers, or Lark export are live-working.
- Do not expose low-level downloader or provider helpers as MCP tools just for
  eval convenience.
- When a workflow change modifies what agents can submit, inspect, retry,
  diagnose, or export, update `docs/agent_mcp_parity.md` checks in the same work
  unit.
