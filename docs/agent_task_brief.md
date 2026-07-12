# Agent Task Brief

This document is the entry mechanism for FluentFlow execution conversations. Use
it before cross-file, workflow, backend state, deployment, or contract-changing
work so each thread has one clear boundary, one validation standard, and one
commit decision.

It does not replace `AGENTS.md`, `docs/versioning_strategy.md`,
`docs/git_checkpoint_workflow.md`, `docs/agent_mcp_parity.md`,
`docs/ui_design_system.md`, or `docs/workflow_design_system.md`. It is the
short handoff layer that points each execution thread to the right checks.

During the foundation-stabilization phase, read
`docs/foundation_stabilization_plan.md` first. It defines the current scope
freeze, the four spines and their owner files, the parallel-work rules (one
owner per shared file, especially `backend/core/server_helpers.py`), and the
pre-unfreeze acceptance checklist. Do not start new-feature work while that
freeze is in effect.

## When To Use

Use this brief before work that adds pages, changes user workflows, changes
backend state/queue/auth/Agent API behavior, affects deployment or contracts, or
spans multiple modules.

Trivial typo fixes or one-off read-only investigation can skip a written brief,
but the final response should still state what was checked.

## Work Unit Size

One execution turn should finish one coherent, verifiable work unit. A work unit
can touch several files, but it should have one user or maintainer outcome and
one clear validation path.

Split the request into stages before editing when it includes any of these:

- More than one product workflow, for example history records plus editor plus
  export.
- More than one risk area, for example UI plus queue semantics plus auth.
- Backend, frontend, docs, and tests all moving for different reasons.
- A change that cannot be verified with a small, relevant check.
- Work whose success criteria are still fuzzy.

Use this staged-plan shape:

```md
Stage 1: outcome, files/surfaces, validation, stop condition
Stage 2: outcome, files/surfaces, validation, stop condition
```

Execute the current stage only. After it passes validation, report what remains
instead of silently continuing into the next stage.

## Task Brief Template

Copy or answer these fields in the main conversation handoff before execution.
If a field is unknown, mark it as unknown and resolve it before editing.

| Field | Required content |
| --- | --- |
| User goal | What real user or maintainer problem this work solves. |
| In scope | Allowed modules, files, file types, or product surfaces. |
| Out of scope | Files, workflows, product domains, or cleanup explicitly not allowed. |
| Risk level | Choose one: low-risk docs/style; normal business behavior; core flow/data/auth/deployment. |
| Validation commands | Pick only relevant checks: `git diff --check`, pytest targets, `npm run build:frontend`, lint, `npm run change:check:staged`, browser screenshot, Agent/MCP parity review, release checks. |
| UI confirmation needed | Yes when changing major UI, information architecture, page responsibility, navigation, or visible workflow meaning. State who confirms before editing. |
| Agent/MCP parity needed | Yes when adding or changing a user-facing workflow that an external agent may need to submit, wait for, inspect, retry, export, or diagnose. Use `docs/agent_mcp_parity.md`. |
| Changelog needed | Yes for user-visible behavior, maintainer-visible workflow, deployment, schema, auth/quota, integration, rollback, or migration impact. Record under `Unreleased`. |
| Commit expected | Yes by default for completed execution work. Use `docs/git_checkpoint_workflow.md` for staging, validation, mixed worktrees, and commit rules. |
| Report format | Final report must cover: changed files, validation run, what was intentionally not done, and remaining risk. |

## Clean Worktree Start Gate

Before those file edits, run:

```bash
git status --short
```

Then choose one path:

| State | Required action |
| --- | --- |
| Clean worktree | Proceed with the task brief. |
| Dirty, all changes belong to this work unit | Continue, validate when complete, and create a checkpoint commit unless the user asked not to commit. |
| Dirty, unrelated changes exist and do not overlap target files | Continue carefully, leave them untouched, and report them in the final summary. |
| Dirty changes overlap target files or ownership is unclear | Stop and report the ambiguity before editing. |

This gate protects the commit boundary. Use `docs/git_checkpoint_workflow.md`
for staging, committing, and mixed worktree handling.

## Main And Execution Conversation Split

Main conversation responsibilities:

- Make product judgment and decide whether the task is worth doing.
- Split work into narrow execution units with clear success criteria.
- Confirm high-risk direction before editing starts.
- Review final behavior and decide whether more work is needed.

Execution conversation responsibilities:

- Complete exactly one assigned work unit.
- Read the relevant project rules before changing files.
- Report unrelated dirty changes before editing and avoid mixing them into the
  work unit.
- Keep changes within the declared scope.
- Run the declared validation or explain why a check is not applicable.
- Do not create broad cleanup, extra features, or unrelated fixes while inside
  the work unit.

Low-risk documentation, copy, style, or isolated tests can be handled
asynchronously when the task brief is clear.

Core business logic, data semantics, authentication, quotas, deployment,
release/version boundaries, persistent storage, and major UI information
architecture require main-conversation confirmation before editing.

## Parallel Thread Rules

- Read-heavy investigation can run in parallel.
- Independent low-risk docs or tests can run in parallel if they touch separate
  files.
- Do not parallelize writes to the same file, shared helper, schema, changelog,
  route, product domain, or release boundary.
- Shared files such as `docs/changelog.md`, provider helpers, task mappers,
  Agent API contracts, result schema, and navigation should have one designated
  execution owner at a time.
- If an execution thread discovers unrelated dirty changes, it must say so and
  leave them out of its diff unless the main conversation explicitly folds them
  into the work unit.

## Completion Check

Before reporting completion, verify the result against the user goal and the
brief:

1. Did the work solve the stated problem without expanding scope?
2. Were validation commands run, or was each skipped check justified?
3. Did Agent/MCP parity, changelog, and UI confirmation get handled when needed?
4. Was `docs/git_checkpoint_workflow.md` followed for checkpoint decisions?
5. Are remaining risks or blocked follow-ups stated plainly?

Completed execution tasks should end with a local checkpoint commit by default
when the Git checkpoint workflow allows it. If the default commit is not
created, the final report must say exactly why.
