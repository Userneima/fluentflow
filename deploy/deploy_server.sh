#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${FLUENTFLOW_PROJECT_DIR:-/opt/fluentflow}"
SERVICE_NAME="${FLUENTFLOW_SERVICE_NAME:-fluentflow}"
ENV_FILE="${FLUENTFLOW_ENV_FILE:-/etc/fluentflow/fluentflow.env}"
HEALTH_URL="${FLUENTFLOW_HEALTH_URL:-http://127.0.0.1:8000/health}"
BRANCH="${FLUENTFLOW_DEPLOY_BRANCH:-main}"
BACKUP_DIR="${FLUENTFLOW_BACKUP_DIR:-/var/backups/fluentflow}"
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

restart_and_check() {
  systemctl restart "$SERVICE_NAME"
  sleep 2
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

  if [[ "$ALLOW_DIRTY" != "1" ]] && [[ -n "$(git status --porcelain)" ]]; then
    log "working tree is dirty; commit or stash changes before deployment"
    git status --short
    exit 2
  fi

  log "creating data backup"
  "$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/scripts/backup_server_state.py" \
    --env-file "$ENV_FILE" \
    --output-dir "$BACKUP_DIR"

  log "updating code from origin/${BRANCH}"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"

  log "installing backend dependencies"
  "$PROJECT_DIR/venv/bin/pip" install -r requirements.txt

  log "installing frontend dependencies and building assets"
  npm ci
  npm run build:frontend

  log "checking deployment readiness"
  run_readiness

  log "restarting service and checking health"
  if ! restart_and_check; then
    rollback "$previous_rev"
    exit 1
  fi

  log "deployment complete: $(git rev-parse --short HEAD)"
}

main "$@"
