# FluentFlow Versioning Strategy

This document defines how FluentFlow controls change risk. It is for Codex,
Claude, and human maintainers working in the same repository.

## Core Principle

Version management is not only the `VERSION` file. It is the combination of:

- App version: the user-facing release snapshot.
- Atomic commits: the internal rollback unit.
- Schema versions: compatibility for persisted data and contracts.
- Changelog: the human-readable product history.
- Tags and release manifests: the deployable rollback anchor.

For the current FluentFlow stage, use one app version for the whole product.
Do not create separate user-facing versions for transcription, notes, Feishu,
tasks, account, or UI modules.

## What Each Layer Answers

| Layer | Answers | Example |
| --- | --- | --- |
| App version | Which product build is running? | `0.1.0` |
| Git commit | What exact change happened? | `fix: handle stale dashboard jobs` |
| Schema version | How should old and new data be read? | `result_schema_version = "2"` |
| Changelog | What changed for users and maintainers? | `docs/changelog.md` |
| Release tag | What can be redeployed or rolled back to? | `v0.2.0` |

## Commit Rules

The rollback unit is the commit, not the conversation.

Atomic does not mean "commit every tiny edit." It means the smallest coherent
change that can be understood, validated, and reverted as one unit.

One conversation may produce several commits. Split commits by product purpose:

- Transcription route changes.
- Task/history behavior.
- AI note generation.
- Feishu export.
- Account/quota/auth.
- UI-only changes.
- Docs-only changes.
- Tooling/release changes.

Avoid broad commits such as:

```text
update app
misc fixes
fix things
frontend and backend changes
```

Prefer intent-based commits:

```text
fix: handle stale dashboard jobs
feat: make ElevenLabs default cloud STT
docs: clarify release process
chore: ignore local agent workspace files
```

When unrelated worktree changes exist, inspect the diff and stage intentionally.
Do not use `git add .` unless the worktree has already been audited and every
changed file belongs to the same commit purpose.

## Dirty Worktree Start Gate

Before non-trivial edits, check the worktree state:

```bash
git status --short
```

If the worktree already contains unrelated changes, do not add more edits to the
same checkout. Choose one of these paths first:

- split and checkpoint the existing changes;
- move the new work to a clean Codex worktree;
- keep the current turn read-only and report the dirty boundary;
- ask the main conversation to decide when ownership is unclear.

Automatic checkpoint commits are allowed only when the work unit is complete,
validated, clearly scoped, and independently reversible. They are not a license
to commit a mixed worktree. A mixed dirty worktree must be decomposed before it
can produce trustworthy history.

Before committing a finished work unit, use the daily change-control check on
the staged files:

```bash
npm run change:check:staged
```

This check does not replace judgment. It makes routine risks visible:

- private/runtime paths accidentally staged;
- product-impacting files staged without `docs/changelog.md`;
- generated or dependency paths appearing in a commit;
- version files moving only partially.

Warnings mean "review the boundary"; failures mean "do not commit yet."

Default behavior:

- A normal checkpoint commit does not require a separate user prompt when the
  work unit is complete, validated, clearly scoped, and independently
  reversible.
- Do not commit when the user asks not to, when the change is still exploratory,
  when validation has not run, or when unrelated dirty changes make the commit
  boundary unclear. Leave the changes uncommitted and explain the reason.
- `wip:` progress commits still require an explicit user request because they
  are temporary development checkpoints, not finished history.
- `git push` and deployment still require explicit user intent.

## Documentation Checkpoint Before Commit

Before creating a finished checkpoint commit, check whether the change needs
progress documentation. This check is part of version management, not a
separate optional cleanup.

Update `docs/changelog.md` under `Unreleased` when the change affects:

- user-visible behavior, copy, navigation, recovery actions, or UI layout;
- deployment, startup, environment variables, storage, auth, quota, or data
  retention;
- persisted result/job schema, API contracts, background task semantics, or
  rollback risk.

Update `docs/private/product_iteration_log.md` when the change captures a
product decision that future work should remember:

- a page's responsibility changes;
- a user flow is simplified, removed, or moved to another page;
- a terminology decision should stay consistent across the product;
- a tradeoff explains why the product did not take an obvious alternative.

Do not document routine typo fixes, test-only refactors, formatting changes, or
internal cleanup with no product meaning. If no documentation update is needed,
say so in the final summary. If documentation is needed but intentionally
deferred, call that out before committing.

The change-control script intentionally cannot know whether a refactor has
product meaning. If it warns about a missing changelog and the change is truly
internal, it is acceptable to leave the changelog unchanged, but the final
summary should say that the warning was reviewed and why no changelog entry was
needed.

## Development History Vs Mainline History

Development speed and readable history have different needs. During exploration
on a local or feature branch, temporary commits are acceptable when they help
save progress or create a rollback point. They may use `wip:` messages if the
user explicitly asks to save progress.

Before merging, pushing for review, or treating work as a finished checkpoint,
clean the visible history into coherent commits:

- Fold typo fixes, formatting nits, and "fix previous commit" changes into the
  commit they belong to.
- Split unrelated changes into separate commits even if they happened in the
  same conversation.
- Keep large features as a small sequence of stable sub-commits, not one giant
  commit and not dozens of trivia commits.
- Ensure each final commit builds on its own intent: a bug fix, a small feature,
  a focused document update, a schema change, or a tooling/release change.

Good final commit units:

- One closed bug fix.
- One independently usable small capability.
- One focused documentation or product-language cleanup.
- One stable submodule or UI slice of a larger feature.
- One release/tooling step with its own validation.

Do not leave these as standalone final commits:

- Single typo fixes or one-line copy tweaks without independent product value.
- Broken or unvalidated half-finished code.
- Mixed changes such as "fix a backend bug, update unrelated docs, and redesign
  a page" in the same commit.

When history cleanup is needed, prefer non-interactive commands where practical.
Use interactive rebase only when the branch is local/unpushed or the user has
approved rewriting history. Never rewrite shared history casually.

## App Version Rules

`VERSION` is the single product release version. `package.json` and
`package-lock.json` must match it.

Do not bump `VERSION` for every agent conversation or every commit. Bump it only
when preparing a coherent release.

Use Semantic Versioning:

| Change type | Version move | Example |
| --- | --- | --- |
| Compatible bug fix | patch | `0.2.0 -> 0.2.1` |
| Compatible new capability | minor | `0.2.1 -> 0.3.0` |
| Breaking behavior/data/API change | major | `1.4.2 -> 2.0.0` |
| Beta or validation build | prerelease | `0.3.0-beta.1` |

During the `0.x` stage, minor versions may still contain larger product shifts.
Call out risky or breaking changes clearly in the changelog.

## Schema And Contract Versions

Use separate internal versions only for durable contracts that must read old
data or coordinate different components.

Good candidates:

- `result_schema_version`
- database migration version
- API contract version
- prompt/template version
- export format version

Poor candidates:

- individual page UI version
- button layout version
- copywriting version
- one-off experiment version

Persistent data or API changes must:

1. Define the new long-term field or contract.
2. Keep old data readable through a converter or compatibility path.
3. Stop writing deprecated fields in new tasks unless explicitly required for
   compatibility.
4. Update the relevant documentation, such as `docs/result_schema.md`.
5. Add tests that protect the new contract and old-data compatibility.

## Changelog Rules

Update `docs/changelog.md` under `Unreleased` when a change affects:

- user-visible behavior
- deployment or runtime operation
- data/schema meaning
- quota/auth/access semantics
- external integrations
- rollback or migration risk

Do not put unfinished plans into the changelog as shipped work. Keep plans in
focused planning docs until they are implemented.

## Release Flow

Prepare a release only from a clean and reviewed set of commits:

```bash
npm run release:prepare -- --version 0.2.0 --title "Short release theme"
```

Apply version metadata only after the release boundary is clear:

```bash
npm run release:prepare -- --version 0.2.0 --title "Short release theme" --apply
```

Before tagging:

```bash
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_versioning.py -q
git diff --check
npm run change:check
npm run release:check
python3 scripts/check_release_gate.py --require-clean --require-tag --require-changelog-version
```

`npm run change:check` is a daily hygiene check. The final release gate remains
`scripts/check_release_gate.py --require-clean --require-tag
--require-changelog-version`, because a real release should be clean, tagged,
and represented in the changelog.

## Rollback Rules

For development mistakes, prefer reverting the specific atomic commit:

```bash
git revert <commit>
```

Do not blindly reset the whole branch or roll back the whole app version when a
single commit can be reverted.

For deployed releases, roll back to a known tag or release manifest. If data
migrations are involved, decide whether rollback means:

- reverting code only,
- running a reversible migration, or
- keeping new data and deploying compatibility code.

If a migration is not reversible, never assume old code can safely read migrated
data.

## Agent Checklist Before Final Response

After meaningful changes, report:

- commits created, if any
- validation commands run
- whether `git diff --check` passed
- remaining risks, such as missing real cloud credentials or manual smoke tests

Do not claim a release is ready when only local tests passed and production
credentials, deployment variables, or migration behavior have not been verified.
