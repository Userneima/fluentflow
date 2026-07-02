---
name: fluentflow-frontend-change
description: Use for FluentFlow frontend, React, Vite, UI, visual design, page layout, navigation, copy that changes workflow meaning, route behavior, information architecture, dark mode, responsive behavior, or browser verification tasks. Trigger from task type, not from skill name.
---

# FluentFlow Frontend Change

## When To Use

Use for any FluentFlow frontend source, UI, route, layout, navigation,
information architecture, styling, copy with workflow meaning, or browser
verification task.

## Required Reading

- `AGENTS.md`
- `docs/agent_task_brief.md`
- `docs/ui_design_system.md`
- `docs/agent_mcp_parity.md` when the UI change affects workflow behavior
- `docs/changelog.md` when the change is user-visible or maintainer-visible

## Steps

1. Identify the page's user goal and whether the change is visual-only,
   workflow-changing, or information-architecture-changing.
2. For major UI, navigation, page responsibility, or information architecture
   changes, state what moves, hides, or changes workflow meaning and wait for
   main-conversation confirmation before editing.
3. Edit frontend source under `frontend/src` only. Do not hand-edit
   `frontend/dist`.
4. Follow existing components and `docs/ui_design_system.md`: operational
   typography for tools, stable dimensions, semantic colors, no card nesting,
   no decorative visual churn.
5. If the UI exposes a new or changed workflow, run the Agent/MCP parity review
   and update contracts/docs/tests in the same work unit or explicitly record
   why the change is UI-only.
6. Keep changelog entries focused on landed behavior, not design plans.

## Validation

- Run `npm run build:frontend` after frontend source changes.
- Run relevant pytest coverage when routes, API assumptions, or frontend route
  fallbacks are affected.
- Run `git diff --check`.
- Use browser screenshot verification when changing important visual layout,
  responsive behavior, dark mode, or interactions that build output cannot
  prove.
- For browser verification, prefer the user's already-open Edge/Chrome product
  window. Do not start a fresh browser profile such as a temporary Edge
  `--user-data-dir` unless the user explicitly approves it first; a fresh
  profile loses cookies/login state and can look like a newly installed browser.
  If the existing window cannot be automated, give the local URL and ask the
  user to inspect it in that window.

## Do Not

- Do not modify `frontend/dist` by hand.
- Do not redesign adjacent pages or shared components unless the brief includes
  them.
- Do not make major UI or information-architecture changes without prior
  confirmation.
- Do not hide workflow changes as "copy only" when they affect user decisions
  or Agent/MCP parity.
