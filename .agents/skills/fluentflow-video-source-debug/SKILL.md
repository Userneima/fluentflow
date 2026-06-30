---
name: fluentflow-video-source-debug
description: Use when debugging FluentFlow video link ingestion, YouTube, Bilibili, Douyin, yt-dlp, subtitles, captions, audio extraction, download fallback, video metadata, local/cloud task handoff, or failures where a video source does not reach transcription or note generation. Trigger from symptoms and platform names.
---

# FluentFlow Video Source Debug

## When To Use

Use when a video URL, share text, subtitle source, downloaded media, extracted
audio, or platform metadata fails before or during the transcription/note
pipeline.

## Required Reading

- `AGENTS.md`
- `docs/agent_task_brief.md`
- `docs/agent_mcp_parity.md`
- `docs/mcp_integration.md` when Agent/MCP submission, package fields, or tool
  output could be affected
- `docs/changelog.md` when behavior or maintainer workflow changes
- Relevant tests before editing, found with `rg "youtube|bilibili|douyin|yt-dlp|subtitle|video link|video_link" tests backend frontend scripts`

## Steps

1. Map the failing chain before changing code: URL parsing, platform detection,
   metadata, subtitle discovery, media download, audio extraction, task
   creation, transcription handoff, note generation, task package, and UI state.
2. Reproduce or inspect the narrow failing path with existing tests, logs,
   fixtures, or a small local command. Do not start by patching symptoms.
3. State the current hypothesis and the exact boundary of the fix.
4. Make the smallest change that repairs the broken handoff or preserves the
   right failure state.
5. If the behavior changes what external agents can submit, inspect, diagnose,
   retry, or export, apply `docs/agent_mcp_parity.md` and update Agent API/MCP
   contracts or document why no parity change is needed.
6. Keep user-facing failure messages honest: explain what failed and the next
   realistic action without pretending all platforms are equally reliable.

## Validation

- Run the smallest relevant pytest target first; broaden if the fix touches
  shared task, source, or result semantics.
- Run `npm run build:frontend` only if frontend source changed.
- Run MCP checks only when Agent/MCP contracts or server behavior changed.
- Run `git diff --check`.
- For platform behavior that depends on live network or credentials, say what
  was not smoke-tested and why.

## Do Not

- Do not implement Agent/MCP eval automation here.
- Do not rewrite the downloader pipeline, task model, or UI unless the brief
  explicitly includes it.
- Do not add brittle heuristics and present them as semantic intelligence.
- Do not commit downloaded media, transcripts, logs, databases, API keys, or
  runtime artifacts.
- Do not expose low-level provider helpers as MCP tools unless they become
  stable product actions.
