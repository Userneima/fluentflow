---
name: fluentflow-git-workflow
description: Use for FluentFlow git status checks, dirty worktree triage, staging, checkpoint commits, commit boundaries, change validation before commit, changelog/versioning decisions, or when the user asks whether to commit, save progress, checkpoint, split work, or manage git history.
---

# FluentFlow Git Workflow

## When To Use

Use this skill whenever a FluentFlow task touches git workflow, including:

- checking worktree state before edits
- deciding whether a change is a coherent commit
- staging files or hunks
- creating checkpoint commits
- explaining why a commit should not be made
- separating unrelated dirty changes
- version, changelog, release, or rollback decisions

Do not use it for read-only code questions unless the user asks about git,
commits, versioning, or worktree state.

## Required Reading

- `AGENTS.md`
- `docs/agent_task_brief.md`
- `docs/versioning_strategy.md` when committing, releasing, tagging, bumping
  versions, or discussing rollback.
- `docs/changelog.md` when the work changes user-visible behavior, maintainer
  workflow, data/API shape, deployment, auth/quota, or integration behavior.

## Start Gate

Before non-trivial edits or any git operation, run:

```bash
git status --short
```

Then classify the worktree:

- `clean`: proceed normally.
- `current-only`: dirty files all belong to the current work unit.
- `mixed`: unrelated dirty changes exist.
- `unclear`: ownership or purpose of dirty changes is not obvious.

For `mixed` or `unclear`, do not stage broad changes. Either keep the turn
read-only, ask for a boundary decision, move the task to a clean worktree, or
stage only files/hunks that are unmistakably part of the current work unit.

## Work Unit Boundary

Before staging or committing, identify:

- user-facing or maintainer-facing purpose
- in-scope files
- out-of-scope dirty files
- validation already run
- whether changelog, Agent/MCP parity, schema docs, or version docs are needed

One commit should represent one coherent product or maintainer outcome. Do not
create `misc`, `update`, or broad cleanup commits.

## Validation Before Commit

Always run:

```bash
git diff --check
```

Add focused checks based on touched surfaces:

- frontend source: `npm run build:frontend`
- frontend route/source assertions: relevant `pytest tests/test_frontend_routes.py ...`
- backend behavior: relevant pytest target
- staged commit: after staging, run `npm run change:check:staged`

If validation is skipped or already failing for unrelated reasons, say exactly
which check is missing or failing and do not present the commit as ready.

## Staging Rules

Stage intentionally:

- prefer explicit file paths
- inspect diffs before staging
- do not stage `.env`, databases, logs, runtime artifacts, media, exports, or
  private docs
- do not stage unrelated dirty files just because they are nearby
- when a file mixes unrelated changes, stage hunks only if the boundary is clear

Useful commands:

```bash
git diff -- <file>
git add <file>
git diff --cached --stat
git diff --cached --check
```

## Commit Rules

Create a normal checkpoint commit only when all are true:

- the work unit is coherent and independently reversible
- validation passed or known unrelated failures are clearly documented
- staged files match the work unit
- no unrelated dirty changes are included
- the user did not ask to avoid committing

Use concise English Conventional Commit style when practical, for example:

```text
fix: handle stale dashboard jobs
feat: add agent task workspace
docs: clarify release process
```

Do not push, tag, deploy, bump `VERSION`, or prepare a release unless the user
explicitly asks and the release process has been checked.

## Final Report

When git workflow was involved, report:

- whether a commit was created
- changed files or staged files
- validation commands and results
- why a commit was not created, if applicable
- remaining dirty worktree risk when unrelated changes remain

If a commit succeeds, include the Codex git directive required by the runtime.

## Do Not

- Do not run `git reset --hard` or `git checkout --` unless explicitly asked.
- Do not hide unrelated changes inside a checkpoint commit.
- Do not commit generated build output under `frontend/dist`.
- Do not use one conversation as one commit by default.
- Do not treat nearly exhausted time or context as a reason to commit.
