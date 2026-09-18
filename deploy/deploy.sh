#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="/opt/kroma"
readonly COMPOSE_FILE="docker-compose.prod.yml"
readonly REVISION_FILE="${APP_DIR}/.deployed-revision"
readonly LOCK_FILE="/run/lock/kroma-deploy.lock"

exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0

cd "${APP_DIR}"
git fetch --quiet --prune origin main
target_revision="$(git rev-parse origin/main)"
deployed_revision="$(cat "${REVISION_FILE}" 2>/dev/null || true)"

if [[ "${target_revision}" == "${deployed_revision}" && "${FORCE_DEPLOY:-0}" != "1" ]]; then
  exit 0
fi

echo "Deploying KROMA revision ${target_revision}"
git checkout --quiet -B main "${target_revision}"

rollback() {
  local exit_code=$?
  echo "Deployment failed (exit ${exit_code})."
  if [[ -n "${deployed_revision}" ]] && git cat-file -e "${deployed_revision}^{commit}" 2>/dev/null; then
    echo "Rolling back to ${deployed_revision}"
    git checkout --quiet -B main "${deployed_revision}"
    docker compose -f "${COMPOSE_FILE}" build
    docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans
    git checkout --quiet -B main "${target_revision}"
  fi
  exit "${exit_code}"
}
trap rollback ERR

docker compose -f "${COMPOSE_FILE}" build --pull
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

for attempt in {1..30}; do
  if curl --fail --silent --show-error --max-time 5 http://127.0.0.1/health >/dev/null \
    && curl --fail --silent --show-error --max-time 5 http://127.0.0.1/ >/dev/null; then
    printf '%s\n' "${target_revision}" >"${REVISION_FILE}"
    docker image prune -f >/dev/null
    trap - ERR
    echo "KROMA ${target_revision} is healthy."
    exit 0
  fi
  sleep 2
done

echo "Health check timed out." >&2
false
