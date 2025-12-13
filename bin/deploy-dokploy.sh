#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME=${PROJECT_NAME:-saas}
TRAEFIK_NETWORK=${TRAEFIK_NETWORK:-dokploy-network}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.mediamtx.yml}

echo "Deploying project='${PROJECT_NAME}' compose='${COMPOSE_FILE}' traefik_network='${TRAEFIK_NETWORK}'"

check_router() {
  local router="$1"
  local found=0
  while read -r cid name; do
    labels=$(docker inspect -f '{{json .Config.Labels}}' "$cid" 2>/dev/null || true)
    if echo "$labels" | grep -q "${router}"; then
      echo "  Collision: container=$name ($cid) has label matching ${router}"
      found=1
    fi
  done < <(docker ps --format '{{.ID}} {{.Names}}')
  return $found
}

echo "Checking for existing conflicting Traefik routers..."
api_router="traefik.http.routers.${PROJECT_NAME}-api"
worker_router="traefik.http.routers.${PROJECT_NAME}-ai-worker"
check_router "$api_router" || true
check_router "$worker_router" || true

echo "If there are collisions above, stop/remove the old Dokploy project before continuing."
read -p "Proceed with docker compose up? [y/N] " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  echo "Running: docker compose -f ${COMPOSE_FILE} up -d"
  docker compose -f "${COMPOSE_FILE}" up -d
  echo "Deployment triggered. Traefik may take a few seconds to update routes." 
else
  echo "Aborted by user.";
  exit 1
fi

echo "Done. Verify endpoints: https://dev.pellit.com.ar/api and /worker"
