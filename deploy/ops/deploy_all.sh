#!/usr/bin/env bash
# Deploys the checked-out code to all three stands (jsemvcas.cz, seniori., vymahani.) in live mode.
# - backend/.env: DEMO_PASSWORD=demo, SMS_FORWARD to the case containers, a shared INTERNAL_TOKEN (backup first)
# - the running production image is tagged deploy-app:rollback; if jsemvcas.cz does not come back, it is restored
# The tunnel container is not touched.
set -euo pipefail
cd "$(dirname "$0")/../.."
ENV=backend/.env
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p /root/backups/env && cp -p "$ENV" "/root/backups/env/backend.env.$TS"

setkey() { if grep -q "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi; }
setkey DEMO_PASSWORD demo
setkey SMS_FORWARD http://app-seniors:8000,http://app-collections:8000
grep -q '^INTERNAL_TOKEN=.\+' "$ENV" || setkey INTERNAL_TOKEN "$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
for c in seniors collections; do
  f="cases/$c/.env"
  for kv in CASE_LIVE=1 DEMO_PASSWORD=demo; do k=${kv%%=*}; grep -q "^$k=" "$f" && sed -i "s|^$k=.*|$kv|" "$f" || echo "$kv" >> "$f"; done
done

docker tag "$(docker inspect -f '{{.Image}}' deploy-app-1)" deploy-app:rollback   # what production runs right now
docker compose -f deploy/docker-compose.yml --profile cases build app app-seniors app-collections
docker compose -f deploy/docker-compose.yml --profile cases up -d --no-deps app app-seniors app-collections

ok() { curl -fsS -m 5 "https://$1/api/health" >/dev/null 2>&1; }
for _ in $(seq 1 30); do ok jsemvcas.cz && break; sleep 2; done
if ! ok jsemvcas.cz; then
  echo "jsemvcas.cz does not answer, rolling back production"
  cp -p "/root/backups/env/backend.env.$TS" "$ENV"
  docker tag deploy-app:rollback deploy-app:latest
  docker compose -f deploy/docker-compose.yml up -d --no-deps --no-build app
  exit 1
fi
sleep 3
for h in jsemvcas.cz seniori.jsemvcas.cz vymahani.jsemvcas.cz; do
  printf '%-22s ' "$h"; curl -s "https://$h/api/health" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["mode"],d.get("case","screening"))'
  printf '%-22s landing %s, login %s\n' "" "$(curl -s -o /dev/null -w '%{http_code}' "https://$h/")" "$(curl -s -o /dev/null -w '%{http_code}' "https://$h/login")"
done
echo "Rollback of production if needed: bash deploy/ops/rollback_prod.sh /root/backups/env/backend.env.$TS"
