# FluentFlow Release Process

FluentFlow releases must be traceable, reproducible enough for debugging, and explicit about data compatibility.

For the everyday change-control rules that happen before release preparation,
read `docs/versioning_strategy.md` first.

## Version Sources

- `VERSION` is the product release version.
- `package.json` and `package-lock.json` must match `VERSION`.
- Backend `/version` returns the backend component version, Git commit, dirty state, and schema versions.
- Frontend build config writes the frontend component version into `window.FLUENTFLOW_CONFIG.version`.
- Runtime data schema versions remain separate from the app version, for example `result_schema_version = "2"`.

## Release Branches And Tags

- Development branches use `codex/*` unless the user requests otherwise.
- Prepare releases on `release/vX.Y.Z`.
- Final release tags use `vX.Y.Z`.
- A tag must point to a commit that passed release validation.

Prepare release metadata with a dry-run first:

```bash
npm run release:prepare -- --version 0.2.0 --title "Short release theme"
```

Apply the mechanical version updates and write the release checklist:

```bash
npm run release:prepare -- --version 0.2.0 --title "Short release theme" --apply
```

If you also want the script to create the release branch, start from a clean worktree:

```bash
npm run release:prepare -- --version 0.2.0 --title "Short release theme" --apply --create-branch
```

## Changelog Rules

Before tagging a release:

1. Move completed `Unreleased` notes in `docs/changelog.md` under `## vX.Y.Z｜YYYY-MM-DD｜Theme`.
2. Keep unfinished plans under `Unreleased` or move them to planning docs.
3. Include user-visible changes, maintainer changes, data/schema changes, and deployment notes when applicable.
4. Do not describe planned work as shipped.

`scripts/prepare_release.py` does not rewrite changelog sections automatically. Deciding which notes are truly shipped is product judgment, so the script only creates a checklist and lets `check_release_gate.py --require-changelog-version` enforce that a version section exists before tagging.

## Build Manifest

After building frontend assets, write a release manifest:

```bash
python3 scripts/write_release_manifest.py --environment production --output build/release-manifest.json
```

The manifest records:

- App version
- Git commit and branch
- Dirty state
- Environment
- Schema versions
- Frontend asset filenames
- Manifest generation time

Deployment automation should copy the manifest next to the running service and keep recent manifests for rollback/debugging.

## Release Validation

Run these before tagging:

```bash
npm run change:check
npm run build:frontend
PYTHONPATH=. venv/bin/pytest tests/test_versioning.py -q
git diff --check
```

When the release gate script exists, use it as the primary command and keep the above as the human-readable breakdown.

```bash
npm run release:check
python3 scripts/check_release_gate.py --require-clean --require-tag --require-changelog-version
```

`npm run change:check` is deliberately earlier than the release gate. It helps
catch "this is still a mixed development checkpoint" before a maintainer spends
time preparing tags, manifests, and deployment notes.

## Deployment Record

Every deployment should preserve:

- The release manifest
- The deployed commit/tag
- Deployment time
- Environment name
- Database/schema migration notes
- Rollback target

## Rollback Principle

Rollbacks must be planned before a release:

- Frontend assets should be tied to a manifest.
- Backend rollback should target a known commit/tag.
- Data migrations must state whether they are reversible.
- If a migration is not reversible, rollback means code compatibility with the migrated data, not restoring old code blindly.
