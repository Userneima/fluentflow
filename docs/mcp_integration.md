# FluentFlow MCP Integration

FluentFlow exposes a local MCP server for external agents such as Claude Code, Codex, and other MCP clients.

The MCP server wraps the stable Agent API under `/agent/v1`. It does not call backend internals or read storage directly.

## Status

- Available server: `scripts/fluentflow_mcp_server.py`
- Transport: stdio
- Backend dependency: a running FluentFlow backend, usually `http://127.0.0.1:8000`
- Python dependency: none beyond the existing FluentFlow runtime

## Configuration

Create an API key from the FluentFlow Agent access panel, then use this shape in an MCP client that supports stdio servers:

```json
{
  "mcpServers": {
    "fluentflow": {
      "command": "python3",
      "args": [
        "<path-to-fluentflow>/scripts/fluentflow_mcp_server.py"
      ],
      "env": {
        "FLUENTFLOW_API_BASE": "http://127.0.0.1:8000",
        "FLUENTFLOW_CLIENT_ID": "local-client",
        "FLUENTFLOW_ACCESS_TOKEN": "<your-fluentflow-api-key>"
      }
    }
  }
}
```

API keys work for both local and cloud deployments. Local development can still run without a key when access control is disabled, but MCP clients should use `FLUENTFLOW_ACCESS_TOKEN` so the local and cloud setup paths stay the same. Do not hard-code production keys in repo files.

API keys are shown once when created. The server stores only a hash, and the key list only shows a prefix plus status.

## Checks

From the repo root:

```bash
npm run mcp:check
npm run mcp:check:e2e
```

`mcp:check` verifies stdio initialization and the tool list.

`mcp:check:e2e` additionally requires the backend to be running. It submits a short transcript through MCP, waits for completion, reads the task package, and checks the diagnosis tool.

## Tools

| Tool | Purpose |
| --- | --- |
| `submit_video_link` | Submit a video URL or copied share text to FluentFlow. |
| `submit_transcript` | Submit transcript text directly and optionally generate a note. |
| `get_task` | Read lightweight task status. |
| `wait_task` | Wait for completion or return the current running state. |
| `get_task_package` | Read the stable Agent Task Package. |
| `diagnose_task` | Explain task or note generation failure state. |
| `retry_task` | Retry a failed task from retained source media when the task package exposes that action. |
| `regenerate_note` | Regenerate a note from the stored transcript. |
| `export_result` | Export the task note to a supported target such as Lark. |

## Usage Flow

1. Start the FluentFlow backend.
2. Configure the MCP client with the stdio server above.
3. Call `submit_video_link` or `submit_transcript`.
4. Call `wait_task` until the task is done.
5. Call `get_task_package` for transcript, note, artifacts, diagnosis, processing plan, and next actions.
6. Use `retry_task`, `regenerate_note`, `diagnose_task`, or `export_result` when the package indicates those actions are available.

## Design Boundary

MCP tools should remain product-level actions. Do not expose low-level helpers such as provider-specific download calls, SQLite reads, or internal parser functions unless they become stable product capabilities.
