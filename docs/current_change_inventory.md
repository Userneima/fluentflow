# Current Change Inventory

Last updated: 2026-06-28

This document is the integration map for the current dirty worktree. It groups
changes by product intent, not by which agent made them. Use it before staging,
committing, deploying, or asking another agent to continue work.

## Working Rule

Do not advance the app version for each agent conversation. Advance the app
version only when a coherent release is being prepared.

Each group below should become its own reviewed commit or be explicitly held
back. Do not merge all dirty files as one "misc fixes" commit.

## Group A: Release And Version Management

Status: ready to commit after final review.

Purpose:

- Make the running app traceable by version, commit, schema versions, and
  deployed frontend assets.
- Add a repeatable release gate and release-preparation command.
- Record successful deployments with a release manifest.

Files:

- `VERSION`
- `.github/workflows/ci.yml`
- `backend/core/versioning.py`
- `backend/core/_env.py`
- `backend/core/server_helpers.py`
- `backend/routers/health.py`
- `scripts/check_release_gate.py`
- `scripts/prepare_release.py`
- `scripts/write_frontend_config.js`
- `scripts/write_release_manifest.py`
- `deploy/deploy_server.sh`
- `deploy/README.md`
- `docs/release_process.md`
- `docs/changelog.md`
- `package.json`
- `package-lock.json`
- `tests/test_prepare_release.py`
- `tests/test_versioning.py`

Validation already run:

- `npm run release:prepare -- --title "Version management baseline"`
- `npm run release:check`
- `npm run build:frontend`
- `PYTHONPATH=. venv/bin/pytest tests/test_prepare_release.py tests/test_versioning.py -q`
- `PYTHONPATH=. venv/bin/pytest tests/test_versioning.py tests/test_frontend_routes.py::test_client_routes_fall_back_to_frontend_index -q`
- `bash -n deploy/deploy_server.sh`
- `git diff --check`

Commit shape:

```bash
git add VERSION .github/workflows/ci.yml backend/core/versioning.py backend/core/_env.py backend/core/server_helpers.py backend/routers/health.py scripts/check_release_gate.py scripts/prepare_release.py scripts/write_frontend_config.js scripts/write_release_manifest.py deploy/deploy_server.sh deploy/README.md docs/release_process.md docs/changelog.md package.json package-lock.json tests/test_prepare_release.py tests/test_versioning.py
git commit -m "Add release version management"
```

Notes:

- `docs/changelog.md` also contains other unreleased product notes. Review the
  staged hunk before committing so this group only stages version-management
  entries.

## Group B: ElevenLabs As Default Cloud STT

Status: candidate for current release, but needs an end-to-end smoke test with
real cloud credentials before commit.

Purpose:

- Replace Azure as the public/default cloud transcription path.
- Keep Azure only as a legacy compatibility route.
- Normalize user-facing copy from Azure-specific wording to cloud STT wording.

Files:

- `README.md`
- `backend/core/_pipeline.py`
- `frontend/src/app/jobMorph.js`
- `frontend/src/app/shared.jsx`
- `frontend/src/lib/format.js`
- `frontend/src/lib/localExecution.js`
- `frontend/src/routes/dashboard.jsx`
- `frontend/src/routes/editor.jsx`
- `frontend/src/routes/media-text.jsx`
- `frontend/src/routes/processing.jsx`
- `scripts/check_deployment_readiness.py`
- `scripts/report_stt_performance.py`
- `tests/test_beta_guardrails.py`
- `tests/test_frontend_routes.py`
- `tests/test_report_stt_performance.py`
- `docs/architecture.md`
- `docs/event_logging.md`
- `docs/ops_runbook.md`
- `docs/product_overview.md`
- `docs/regression_checklist.md`
- `docs/usage_guide_cn.md`

Required validation before commit:

```bash
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_beta_guardrails.py tests/test_frontend_routes.py tests/test_report_stt_performance.py -q
PYTHONPATH=. venv/bin/pytest tests/test_versioning.py -q
git diff --check
```

Manual smoke test before deployment:

- Configure `ELEVENLABS_API_KEY` in the backend environment.
- Upload a short course or lecture file.
- Confirm cloud transcription completes.
- Reopen the result from tasks/history.
- Download TXT/SRT/VTT.
- Confirm local faster-whisper remains selectable where local execution is
  allowed.

Commit shape:

```bash
git add README.md backend/core/_pipeline.py frontend/src/app/jobMorph.js frontend/src/app/shared.jsx frontend/src/lib/format.js frontend/src/lib/localExecution.js frontend/src/routes/dashboard.jsx frontend/src/routes/editor.jsx frontend/src/routes/media-text.jsx frontend/src/routes/processing.jsx scripts/check_deployment_readiness.py scripts/report_stt_performance.py tests/test_beta_guardrails.py tests/test_frontend_routes.py tests/test_report_stt_performance.py docs/architecture.md docs/event_logging.md docs/ops_runbook.md docs/product_overview.md docs/regression_checklist.md docs/usage_guide_cn.md
git commit -m "Make ElevenLabs the default cloud transcription route"
```

Risks:

- Frontend terminology changes are mixed with workflow-page terminology. Review
  staged hunks carefully and keep pure Agent Workflow UI changes in Group C.
- Deployment readiness now expects ElevenLabs semantics; do not deploy without
  confirming the server env file.

## Group C: Agent Workflow UI And Information Architecture

Status: hold until user confirms the UI direction. Do not silently commit.

Purpose:

- Rename the old "Processing settings" mental model toward "Agent workflow".
- Add `/processing` back as a visible route.
- Move execution explanation out of the editor into a future workflow surface.

Files touched now:

- `frontend/src/app/AppShell.jsx`
- `frontend/src/components/SideNav.jsx`
- `frontend/src/app/shared.jsx`
- `frontend/src/routes/editor.jsx`
- `frontend/src/routes/processing.jsx`
- `docs/next_execution_plan.md`
- `docs/ai_workflow_editor_refactor_plan.md`

Before implementation continues:

- Confirm the new left-nav label and page responsibility with the user.
- Confirm what remains in Settings versus Agent Workflow.
- Confirm whether `/processing` should be a settings page, workflow page, or
  both during transition.

Validation after UI work:

```bash
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_frontend_routes.py -q
git diff --check
```

Risks:

- The user previously asked that major UI/information-architecture changes be
  discussed before editing.
- Current copy changes may make the UI look like a completed Agent workflow
  before the workflow explanation is actually implemented.

## Group D: Task Recovery And Stale Job Cleanup

Status: candidate for current release, but should be separated from UI naming.

Purpose:

- Avoid repeated `/jobs/{id}` 404 errors when cached or stale tasks no longer
  exist on the backend.
- Preserve status codes from SSE subscription failures so the UI can react
  correctly.

Files:

- `frontend/src/routes/dashboard.jsx`
- `frontend/src/app/shared.jsx`
- `frontend/src/routes/editor.jsx`
- `tests/test_frontend_routes.py`

Required validation:

```bash
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_frontend_routes.py -q
git diff --check
```

Notes:

- This group overlaps file paths with Group B and Group C. Use patch-level
  staging, not whole-file staging, if splitting commits.

## Group E: Documentation Long-Term Cleanup

Status: needs review before commit.

Purpose:

- Move old planning content into product documentation or delete it after its
  content is actually landed.
- Keep public docs aligned with the current ElevenLabs + Agent workflow product
  direction.

Deleted files:

- `docs/long_transcript_coverage_notes_plan.md`
- `docs/note_mode_evaluation_plan.md`

New / modified planning files:

- `docs/next_execution_plan.md`
- `docs/ai_workflow_editor_refactor_plan.md`
- `CONTEXT.md`

Before commit:

- Confirm the deleted docs are fully superseded by current product docs and
  changelog entries.
- Decide whether `CONTEXT.md` is a public repo document or a local agent memory
  file. If it is local agent memory, keep it untracked and add an ignore rule in
  a separate housekeeping commit.

Risk:

- Deleting planning docs can erase rationale that is still useful for future
  product decisions. Prefer moving important rationale into a focused product
  doc before deletion.

## Group F: Local Agent And Tooling Files

Status: do not commit to the public repo by default.

Files:

- `.claude/settings.local.json`
- `.claude/launch.json`
- `.agents/skills/vercel-ui-skills/SKILL.md`
- `.superpowers/`

Decision:

- `.claude/settings.local.json` contains local tool permissions and should not
  be committed.
- `.claude/launch.json` is local runner config; keep private unless the project
  intentionally standardizes Claude launch behavior.
- `.agents/skills/vercel-ui-skills/SKILL.md` duplicates local skill material;
  keep private unless the project intentionally vendors this skill.
- `.superpowers/` should be inspected before any commit decision.

Recommended next action:

```bash
git status --short
git check-ignore .claude/settings.local.json .claude/launch.json .agents/skills/vercel-ui-skills/SKILL.md .superpowers 2>/dev/null || true
```

If they are meant to stay local, add ignore rules in a dedicated housekeeping
commit after confirming with the user.

## Recommended Integration Order

1. Commit Group A first.
2. Commit Group D if the 404/stale-task behavior is still needed and tests pass.
3. Commit Group B after a real ElevenLabs smoke test.
4. Pause Group C until the user confirms the UI direction.
5. Review Group E doc deletions after product docs are confirmed complete.
6. Keep Group F untracked or ignore it; do not mix it with product code.

## Versioning Decision

Current `VERSION` is `0.1.0`.

Do not bump it again until the release boundary is decided. When preparing a
real release, use:

```bash
npm run release:prepare -- --version 0.2.0 --title "Release theme"
```

Use `--apply` only after changelog content and staged commit groups are clear.
