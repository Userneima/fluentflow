---
name: fluentflow-product-task-brief
description: Use when a FluentFlow request needs to be turned into a narrow execution work unit, task brief, handoff, implementation boundary, validation plan, commit boundary, or main-conversation/execution-conversation split. Trigger even if the user does not mention skill names.
---

# FluentFlow Product Task Brief

## When To Use

Use this before non-trivial FluentFlow execution work, especially when a request
needs scope, risk, validation, ownership, or commit boundaries before editing.

Skip only for trivial read-only questions or obvious typo fixes.

## Required Reading

- `AGENTS.md`
- `docs/agent_task_brief.md`
- `docs/current_change_inventory.md` if it exists
- `docs/versioning_strategy.md` when commit, release, changelog, or dirty-worktree boundaries matter

## Steps

1. Restate the real user or maintainer goal, not just the literal operation.
2. Define one work unit: in scope, out of scope, risk level, expected files, and
   success criteria.
3. Check dirty worktree state before editing; report unrelated changes and keep
   them out of the work unit.
4. Decide whether UI confirmation, Agent/MCP parity, changelog, tests, build, or
   commit permission are required.
5. If direction or success criteria are ambiguous, confirm with the main
   conversation before landing persistent changes.
6. Keep the final report aligned to the brief: changed files, validation,
   intentionally skipped work, and remaining risk.

## Validation

- Always include `git diff --check` for changes.
- Use `npm run change:check:staged` only after staging and only when a commit is
  allowed.
- Add pytest, frontend build, browser screenshot, release, or MCP checks only
  when the work unit touches those surfaces.

## Do Not

- Do not expand one task brief into unrelated cleanup or extra features.
- Do not mix unrelated dirty changes into the current work unit.
- Do not commit unless the user or project rules allow it and validation has
  run.
- Do not use the changelog for plans that have not landed.
