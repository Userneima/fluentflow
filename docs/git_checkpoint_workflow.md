# Git Checkpoint Workflow

This document is the operational Git workflow for FluentFlow execution tasks.
It keeps `AGENTS.md` lightweight while making checkpoint behavior consistent
across Codex, Claude, and human maintainers.

## Purpose

Use Git to make completed work traceable, reviewable, and reversible.

A checkpoint commit is not "whatever changed during the chat." It is one
coherent, validated work unit that can be understood and reverted without
dragging unrelated work with it.

## Start Gate

Before file edits or git operations, run:

```bash
git status --short
```

Classify the worktree:

| State | Meaning | Action |
| --- | --- | --- |
| `clean` | No local changes | Proceed normally. |
| `current-only` | Dirty files all belong to the current work unit | Continue, validate, then commit the work unit. |
| `mixed` | Dirty files include unrelated work | Continue only if the current boundary is clear; stage only the intended files or hunks. |
| `unclear` | You cannot tell which changes belong to which task | Stop and ask/split before editing or committing. |

Never treat a mixed worktree as a reason to use `git add .`.

## Work Unit Boundary

Before staging, state the boundary in plain terms:

- User or maintainer outcome.
- In-scope files.
- Out-of-scope dirty files.
- Validation already run.
- Whether changelog, Agent/MCP parity, schema docs, or release docs are needed.

One commit should represent one outcome:

- Good: `fix: redirect legacy history route to records`
- Good: `docs: document checkpoint workflow`
- Bad: `update app`
- Bad: `fix ui and docs and backend`

## Validation

Always run:

```bash
git diff --check
```

Then run the focused checks for touched surfaces:

- Frontend source: `npm run build:frontend`
- Frontend route/source contracts: relevant `pytest tests/test_frontend_routes.py ...`
- Backend logic/state/auth/API/persistence: relevant `pytest`
- User-facing workflow changes: Agent/MCP parity review from `docs/agent_mcp_parity.md`
- Staged commit: `npm run change:check:staged`

Do not present a checkpoint as finished when required validation was skipped or
failed. If a failure is unrelated, say why and keep the commit boundary clear.

## Staging

Stage intentionally:

```bash
git add path/to/file
git add -p path/to/file
git diff --cached --stat
git diff --cached --check
```

Rules:

- Stage only files or hunks that belong to the current work unit.
- Do not stage `.env`, databases, logs, runtime artifacts, media, exports,
  private docs, or generated frontend build output.
- If one file contains unrelated hunks, use `git add -p` or leave it
  unstaged and explain why.
- If the boundary is unclear, do not commit.

## Commit

At the end of each completed execution task, create a local checkpoint commit
by default when all are true:

- The work unit is coherent and independently reversible.
- Validation passed, or unrelated failures are explicitly documented.
- Staged files match the work unit.
- No unrelated dirty changes are included.
- The user did not ask to avoid committing.

Use concise English Conventional Commit style:

```text
fix: handle stale dashboard jobs
feat: add agent task workspace
docs: document checkpoint workflow
```

Do not create a commit when:

- The work is still exploratory.
- Required validation has not run.
- Dirty changes overlap and ownership is unclear.
- The user asked not to commit.
- The commit would mix unrelated product purposes.

`wip:` commits require explicit user request. `git push`, tags, releases,
deployment, and version bumps also require explicit user intent.

## Final Report

When reporting completion, include:

- Commit hash and message, if created.
- Validation commands and result.
- Files intentionally left unstaged or unrelated dirty work that remains.
- Why a default checkpoint was not created, if not created.

Use the runtime git directives only after the corresponding action actually
succeeds.
