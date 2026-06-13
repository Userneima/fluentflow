# FluentFlow Server Deploy Workflow

This document defines the standard workflow Codex should run when Wang Yuchao asks to upload or deploy FluentFlow to the server.

## Trigger Phrases

Treat these user messages as an explicit deployment request:

- 上传服务器
- 部署到服务器
- 上线
- 更新线上版本
- 发布到 fluentflow.icu
- 把当前修改同步到服务器

These phrases satisfy the project rule that `git push` must be explicit. Do not ask the user to confirm the obvious again unless the working tree contains unrelated changes or a real destructive risk exists.

## Goal

Make the production server match the intended GitHub version with the fewest user operations.

The target flow is:

```text
local workspace
→ validate
→ commit
→ push to GitHub
→ server pulls GitHub
→ server builds frontend
→ server restarts service
→ health check
```

## Before Acting

1. Inspect `git status --short`.
2. Identify which changed files belong to the requested deployment.
3. If there are unrelated or ambiguous dirty files, do not stage everything blindly. Stage only the relevant files or ask one concise question.
4. Check whether `docs/changelog.md` needs an entry. User-visible, deployment, data, auth, quota, storage, or recovery changes need one.
5. Never print, commit, or expose secrets.

## Local Validation

Run the smallest validation set that matches the changed surface:

```bash
npm run build:frontend
```

For backend, auth, quota, storage, deployment, or queue changes, also run:

```bash
./venv/bin/python -m pytest
```

If the full test suite is too slow or clearly unnecessary, run the focused test files and state the residual risk.

## Commit And Push

Use English commit messages. Prefer one concise commit for one deployment unit.

```bash
git add <relevant files>
git commit -m "<concise English intent>"
git push origin main
```

Do not use `git add -A` when the working tree has unrelated changes.

## Server Deployment

Preferred server command:

```bash
deploy-fluentflow
```

If that alias does not exist, use:

```bash
cd /opt/fluentflow
bash deploy/deploy_server.sh
```

The script should:

- create a server data backup
- pull the latest `main` from GitHub
- install backend dependencies
- install frontend dependencies
- build frontend assets
- run deployment readiness checks
- restart `fluentflow`
- check `/health`
- roll back to the previous Git revision if the health check fails

## Verification

After deployment, verify:

```bash
systemctl status fluentflow --no-pager
systemctl status nginx --no-pager
curl -fsS http://127.0.0.1:8000/health
```

For UI changes, ask the user to hard refresh only if browser cache may still show old assets.

## When User Action Is Still Needed

Ask the user only for actions Codex cannot safely do:

- entering secrets or credentials
- completing account authorization
- server access when no SSH or terminal access is available
- payment or cloud-provider confirmation
- CAPTCHA or browser-only security checks

When user action is needed, provide exactly the next field or command, not the whole manual again.

## Non-Goals

- Do not edit production files manually as the normal path.
- Do not use `nano` for server edits.
- Do not make the server the source of truth.
- Do not bypass GitHub for routine deployment.
- Do not deploy exploratory or unvalidated local changes.
