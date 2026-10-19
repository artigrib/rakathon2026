#!/usr/bin/env bash
# Puts jsemvcas.cz back on the image and backend/.env from before deploy_all.sh. Usage: rollback_prod.sh <backend.env backup>
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f "${1:-}" ] && cp -p "$1" backend/.env
docker tag deploy-app:rollback deploy-app:latest
docker compose -f deploy/docker-compose.yml up -d --no-deps --no-build app
sleep 5; curl -s https://jsemvcas.cz/api/health; echo
