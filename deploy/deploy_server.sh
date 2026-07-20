#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${FLUENTFLOW_PROJECT_DIR:-/opt/fluentflow}"
SERVICE_NAME="${FLUENTFLOW_SERVICE_NAME:-fluentflow}"
ENV_FILE="${FLUENTFLOW_ENV_FILE:-/etc/fluentflow/fluentflow.env}"
HEALTH_URL="${FLUENTFLOW_HEALTH_URL:-http://127.0.0.1:8000/health}"
BRANCH="${FLUENTFLOW_DEPLOY_BRANCH:-main}"
BACKUP_ROOT_DIR="${FLUENTFLOW_BACKUP_DIR:-/var/backups/fluentflow}"
DEPLOY_BACKUP_DIR="${FLUENTFLOW_DEPLOY_BACKUP_DIR:-${BACKUP_ROOT_DIR}/deploy}"
DEPLOY_BACKUP_RETENTION_COUNT="${FLUENTFLOW_DEPLOY_BACKUP_RETENTION_COUNT:-7}"
DEPLOY_BACKUP_MIN_FREE_MB="${FLUENTFLOW_DEPLOY_BACKUP_MIN_FREE_MB:-512}"
RELEASE_DIR="${FLUENTFLOW_RELEASE_DIR:-/var/lib/fluentflow/releases}"
ALLOW_DIRTY="${FLUENTFLOW_DEPLOY_ALLOW_DIRTY:-0}"

log() {
  printf '[fluentflow-deploy] %s\n' "$*"
}

run_readiness() {
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/check_deployment_readiness.py"
}

prepare_backup_storage() {
  if [[ ! "$DEPLOY_BACKUP_RETENTION_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    log "FLUENTFLOW_DEPLOY_BACKUP_RETENTION_COUNT must be a positive integer"
    exit 2
  fi
  if [[ ! "$DEPLOY_BACKUP_MIN_FREE_MB" =~ ^[1-9][0-9]*$ ]]; then
    log "FLUENTFLOW_DEPLOY_BACKUP_MIN_FREE_MB must be a positive integer"
    exit 2
  fi

  mkdir -p "$DEPLOY_BACKUP_DIR"
  log "retaining the newest ${DEPLOY_BACKUP_RETENTION_COUNT} deployment snapshots"
  "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/backup_server_state.py" \
    --output-dir "$DEPLOY_BACKUP_DIR" \
    --retain-count "$DEPLOY_BACKUP_RETENTION_COUNT" \
    --prune-only

  local available_kb minimum_kb
  available_kb="$(df -Pk "$DEPLOY_BACKUP_DIR" | awk 'NR == 2 {print $4}')"
  minimum_kb=$((DEPLOY_BACKUP_MIN_FREE_MB * 1024))
  if [[ ! "$available_kb" =~ ^[0-9]+$ ]] || (( available_kb < minimum_kb )); then
    log "insufficient disk space for a deployment snapshot: need at least ${DEPLOY_BACKUP_MIN_FREE_MB} MB free"
    exit 3
  fi
}

restart_and_check() {
  systemctl restart "$SERVICE_NAME"
  local attempt
  for attempt in {1..30}; do
    if systemctl is-active --quiet "$SERVICE_NAME" && curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  systemctl is-active --quiet "$SERVICE_NAME"
  curl -fsS --max-time 15 "$HEALTH_URL" >/dev/null
}

rollback() {
  local previous_rev="$1"
  log "deployment failed; rolling back to ${previous_rev}"
  cd "$PROJECT_DIR"
  git checkout --force "$previous_rev"
  "$PROJECT_DIR/venv/bin/pip" install -r requirements.txt
  npm ci
  npm run build:frontend
  systemctl restart "$SERVICE_NAME" || true
}

main() {
  cd "$PROJECT_DIR"
  local previous_rev
  previous_rev="$(git rev-parse HEAD)"
  mkdir -p "$RELEASE_DIR"

  if [[ "$ALLOW_DIRTY" != "1" ]] && [[ -n "$(git status --porcelain)" ]]; then
    log "working tree is dirty; commit or stash changes before deployment"
    git status --short
    exit 2
  fi

  prepare_backup_storage
  log "creating database-only deployment snapshot"
  local backup_report backup_archive
  backup_report="$("$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/backup_server_state.py" \
    --env-file "$ENV_FILE" \
    --output-dir "$DEPLOY_BACKUP_DIR" \
    --retain-count "$DEPLOY_BACKUP_RETENTION_COUNT" \
    --database-only)"
  printf '%s\n' "$backup_report"
  backup_archive="$("$PROJECT_DIR/venv/bin/python" -c 'import json,sys; print(json.load(sys.stdin).get("archive",""))' <<<"$backup_report")"

  log "updating code from origin/${BRANCH}"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"

  log "checking release gate"
  "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/check_release_gate.py" --require-clean

  log "installing backend dependencies"
  "$PROJECT_DIR/venv/bin/pip" install -r requirements.txt

  log "installing frontend dependencies and building assets"
  npm ci
  npm run build:frontend

  local deploy_version release_stamp release_manifest_tmp release_manifest
  deploy_version="$(tr -d '[:space:]' < "$PROJECT_DIR/VERSION")"
  release_stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  release_manifest_tmp="$PROJECT_DIR/build/release-manifest.json"
  release_manifest="$RELEASE_DIR/fluentflow-${deploy_version}-${release_stamp}.json"
  FLUENTFLOW_BUILD_TIME="$release_stamp" "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/write_release_manifest.py" \
    --environment production \
    --backup-archive "$backup_archive" \
    --output "$release_manifest_tmp"

  log "checking deployment readiness"
  run_readiness

  log "restarting service and checking health"
  if ! restart_and_check; then
    rollback "$previous_rev"
    exit 1
  fi

  cp "$release_manifest_tmp" "$release_manifest"
  log "deployment complete: $(git rev-parse --short HEAD)"
  log "release manifest: $release_manifest"
}

main "$@"
