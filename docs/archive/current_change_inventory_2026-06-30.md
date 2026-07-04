# Current Change Inventory

Last updated: 2026-06-30

This document is the integration map for the current multi-agent worktree. It
groups changes by product intent, not by which agent made them. Use it before
staging, committing, deploying, or asking another agent to continue work.

## Working Rule

Do not advance the app version for each agent conversation. Advance the app
version only when a coherent release is being prepared.

Each group below should become its own reviewed commit or be explicitly held
back. Do not merge all dirty files as one "misc fixes" commit.

## Active Dirty Worktree Audit — 2026-06-30

Status: uncommitted in the main checkout. Do not add unrelated edits on top of
these files. Either split/checkpoint the groups below or move new work to a
clean worktree.

### Group F: Account Scope And Internal Queue Auth Recovery

Purpose:

- Keep the internal queue token stable across backend imports/restarts.
- Preserve account scope for internal queue requests.
- Improve user-facing diagnosis when note generation is blocked by login/auth.

Files currently touched:

- `backend/core/_env.py`
- `backend/core/server_helpers.py`
- `backend/core/task_detail.py`
- `tests/test_account_auth.py`

Suggested validation before commit:

```bash
PYTHONPATH=. venv/bin/pytest tests/test_account_auth.py -q
git diff --check
```

Suggested commit boundary:

```text
fix: preserve internal queue account scope
```

### Group G: History Records And Task Detail Recovery UI

Purpose:

- Rename user-facing "后台任务 / task management" language toward "历史记录".
- Preserve local task snapshots while task detail silently refreshes backend
  data.
- Keep local cancel/delete/retry mutations from flickering back during polling.
- Add retry affordances for failed video-link records when the original input
  is available.

Files currently touched:

- `frontend/src/app/AppShell.jsx`
- `frontend/src/app/shared.jsx`
- `frontend/src/components/TaskProgressOverview.jsx`
- `frontend/src/lib/format.js`
- `frontend/src/routes/about.jsx`
- `frontend/src/routes/agent-trace.jsx`
- `frontend/src/routes/dashboard.jsx`
- `frontend/src/routes/processing.jsx`
- `frontend/src/routes/settings.jsx`
- `frontend/src/routes/tasks.jsx`
- `scripts/write_frontend_config.js`
- `tests/test_frontend_routes.py`

Suggested validation before commit:

```bash
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_frontend_routes.py -q
git diff --check
```

Suggested commit boundary:

```text
fix: stabilize history task recovery
```

### Group H: Product Documentation Terminology Alignment

Purpose:

- Align public docs and design rules with the current "历史记录" product model.
- Keep deployment/regression docs consistent with the renamed long-task entry.

Files currently touched:

- `docs/architecture.md`
- `docs/beta_deployment_checklist.md`
- `docs/product_intro_latest.md`
- `docs/regression_checklist.md`
- `docs/ui_design_system.md`

Suggested validation before commit:

```bash
git diff --check
```

Suggested commit boundary:

```text
docs: align history record terminology
```

### Shared File Warning

`docs/changelog.md` contains changes from multiple product groups. Stage its
hunks with care:

- history/task recovery user-facing entries belong with Group G;
- documentation-only terminology may belong with Group H;
- future maintenance workflow entries should be staged only with their matching
  maintenance commit.

## Group A: Release And Version Management

Status: committed in `39b272e` (`Add release version management`).

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

Status: committed in `ca5a174` (`Make ElevenLabs the default cloud transcription route`).

Deployment still needs an end-to-end smoke test with real cloud credentials.

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

Status: first navigation/copy slice committed in `b8f54ec` (`Expose agent workflow navigation`).

Further UI or information-architecture changes still require discussion before
editing.

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

Status: committed in `633e0ab` (`Handle stale dashboard jobs`).

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

Status: reviewed. Deleted planning docs were restored because they are not fully
superseded.

Purpose:

- Move old planning content into product documentation or delete it after its
  content is actually landed.
- Keep public docs aligned with the current ElevenLabs + Agent workflow product
  direction.

Reviewed files:

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

Decision:

- Keep both documents until threshold evaluation, artifact persistence, and
  coverage-matrix work are either landed or moved into a newer focused product
  document.
- Treat `CONTEXT.md` as local agent memory and keep it ignored.

## Group F: Local Agent And Tooling Files

Status: local-only. Ignored by project `.gitignore`.

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

Current ignore coverage:

```bash
.agents/
.claude/
.superpowers/
CONTEXT.md
```

## Recommended Integration Order

1. Group A is committed.
2. Group D is committed.
3. Group B is committed, but production deployment still needs real ElevenLabs
   smoke testing.
4. Group C has only the confirmed first slice; pause before deeper UI changes.
5. Group E doc deletions were rejected for now; keep the rationale docs.
6. Group F is ignored as local-only workspace state.

## Versioning Decision

Current `VERSION` is `0.1.0`.

Do not bump it again until the release boundary is decided. When preparing a
real release, use:

```bash
npm run release:prepare -- --version 0.2.0 --title "Release theme"
```

Use `--apply` only after changelog content and staged commit groups are clear.
