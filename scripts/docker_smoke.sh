#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP_RUNNING="${KEEP_RUNNING:-0}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-civicledger_smoke}"
BACKEND_PORT="${BACKEND_PORT:-18080}"
FRONTEND_PORT="${FRONTEND_PORT:-13000}"
POSTGRES_PORT="${POSTGRES_PORT:-15432}"
export COMPOSE_PROJECT_NAME BACKEND_PORT FRONTEND_PORT POSTGRES_PORT

cd "$ROOT_DIR"

docker compose down --volumes --remove-orphans >/dev/null 2>&1 || true
docker compose up --build -d

for i in {1..40}; do
  if curl -fsS "http://localhost:${BACKEND_PORT}/meta/status" >/tmp/civicledger-backend-smoke.json; then
    break
  fi
  sleep 2
done

curl -fsS "http://localhost:${BACKEND_PORT}/meta/status" >/tmp/civicledger-backend-smoke.json
curl -fsS "http://localhost:${BACKEND_PORT}/meta/sources" >/tmp/civicledger-sources-smoke.json
curl -fsS "http://localhost:${BACKEND_PORT}/meta/source-completeness" >/tmp/civicledger-source-completeness-smoke.json

for i in {1..40}; do
  if curl -fsS "http://localhost:${FRONTEND_PORT}" >/tmp/civicledger-frontend-smoke.html; then
    break
  fi
  sleep 2
done

curl -fsS "http://localhost:${FRONTEND_PORT}" >/tmp/civicledger-frontend-smoke.html

echo "Docker smoke passed:"
echo "- backend http://localhost:${BACKEND_PORT}/meta/status"
echo "- backend http://localhost:${BACKEND_PORT}/meta/sources"
echo "- backend http://localhost:${BACKEND_PORT}/meta/source-completeness"
echo "- frontend http://localhost:${FRONTEND_PORT}/"

if [[ "$KEEP_RUNNING" != "1" ]]; then
  docker compose down --volumes
fi
