# Agent Task Brief

This document is the entry mechanism for FluentFlow execution conversations. Use
it before non-trivial work so each thread has one clear boundary, one validation
standard, and one commit decision.

It does not replace `AGENTS.md`, `docs/versioning_strategy.md`,
`docs/agent_mcp_parity.md`, or `docs/ui_design_system.md`. It is the short
handoff layer that points each execution thread to the right checks.

## When To Use

Use this brief before work that changes product behavior, UI, backend logic,
data meaning, scripts, docs with maintainer impact, deployment, tests, or commit
history.

Trivial typo fixes or one-off read-only investigation can skip a written brief,
but the final response should still state what was checked.

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
| Commit allowed | Yes/no. If yes, define the commit boundary and validation required before commit. If dirty unrelated changes exist, stage only intended hunks/files. |
| Report format | Final report must cover: changed files, validation run, what was intentionally not done, and remaining risk. |

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
4. Is the commit boundary clear, even if this thread is not allowed to commit?
5. Are remaining risks or blocked follow-ups stated plainly?
