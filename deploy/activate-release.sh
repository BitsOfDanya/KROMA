#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_ROOT="/opt/kroma"
readonly RELEASES_DIR="${APP_ROOT}/releases"
readonly CURRENT_LINK="${APP_ROOT}/current"
readonly COMPOSE_FILE="docker-compose.prod.yml"
readonly LOCK_FILE="${APP_ROOT}/deploy.lock"
readonly REVISION="${1:-}"

if [[ ! "${REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected a full Git commit SHA." >&2
  exit 2
fi

readonly RELEASE_DIR="${RELEASES_DIR}/${REVISION}"
if [[ ! -f "${RELEASE_DIR}/${COMPOSE_FILE}" || ! -L "${RELEASE_DIR}/.env" ]]; then
  echo "Release ${RELEASE_DIR} is incomplete." >&2
  exit 2
fi

exec 9>"${LOCK_FILE}"
flock -n 9 || exit 0

previous_release="$(readlink -f "${CURRENT_LINK}" 2>/dev/null || true)"

rollback() {
  local exit_code=$?
  echo "Deployment failed (exit ${exit_code})."
  if [[ -n "${previous_release}" && -f "${previous_release}/${COMPOSE_FILE}" ]]; then
    echo "Rolling back to ${previous_release}."
    cd "${previous_release}"
    docker compose -p kroma -f "${COMPOSE_FILE}" build
    docker compose -p kroma -f "${COMPOSE_FILE}" up -d --remove-orphans
  fi
  exit "${exit_code}"
}
trap rollback ERR

cd "${RELEASE_DIR}"
docker compose -p kroma -f "${COMPOSE_FILE}" build --pull
docker compose -p kroma -f "${COMPOSE_FILE}" up -d --remove-orphans

for attempt in {1..45}; do
  if curl --fail --silent --show-error --max-time 5 http://127.0.0.1/health >/dev/null \
    && curl --fail --silent --show-error --max-time 5 http://127.0.0.1/ >/dev/null; then
    ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"
    printf '%s\n' "${REVISION}" >"${APP_ROOT}/deployed-revision"
    docker image prune -f >/dev/null
    trap - ERR
    echo "KROMA ${REVISION} is healthy."
    exit 0
  fi
  sleep 2
done

echo "Health check timed out." >&2
false
