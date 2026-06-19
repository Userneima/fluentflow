# FluentFlow Project Rules

Default language: Chinese. Code, commands, variables, and commit messages use English.

---

# Agent Autonomy

- Do not hand off work to the user when it can be done directly by Claude Code in the shared local workspace.
- Prefer creating files, editing local documents, running commands, checking outputs, and preparing copy-ready artifacts yourself.
- Minimize user operations; ask the user to act only for credentials, secrets, account authorization, payment confirmation, CAPTCHA, or actions that cannot be performed safely from the local environment.
- When user action is unavoidable, reduce it to the smallest concrete step and provide the exact next command or field to fill.
- Do not ask the user to edit files with `nano`; use local file creation or other lower-friction alternatives instead.

---

# Context Budget Rules

Always exclude these paths from searches and broad reads unless the task explicitly needs them:

- `node_modules/`
- `dist/`
- `.git/`
- `package-lock.json`
- `.DS_Store`

Prefer targeted searches (Grep by symbol or selector) over reading large files whole.

---

# Change Boundaries

Match verification effort to change risk:

- CSS or copy changes: visual check may suffice
- Type, component structure, or import changes: lint + build
- Logic, state, flow, or persistence changes: full test suite when available
- Documentation changes: no verification needed

Do not run the full command set for every small edit, but do not skip verification when data or behavior is at stake.

---

# Problem Solving

When fixing a bug:

1. Identify the direct cause
2. Identify why it was able to happen
3. Make the smallest change that fixes it AND prevents the same class of problem
4. Apply the preventive measure immediately (add a test, tighten a type, add validation)

Do not stop at patching the visible symptom.

---

# Harness First

If the same problem reappears, do not just fix it again. Strengthen the guard layer first:

- add a test that catches the regression
- add a static check if the issue is mechanically detectable
- update project rules so future agents don't reintroduce the same mistake

Prefer harness improvements over broad refactors when the root cause is recurring mistakes, not structural decay.

---

# Feedback Capture

When the user explicitly points out an error, mismatch, confusing copy, or broken behavior, record the reusable rule in the relevant documentation layer within the same task. Do not treat user corrections as ephemeral chat context.
