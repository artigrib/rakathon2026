#!/usr/bin/env bash
# Turns the seniors and collections stands live (real SMS, calls, e-mail, only to the signed-in visitor's own contacts).
# Recreates only app-seniors and app-collections from their current images; the production app container is not touched.
set -euo pipefail
cd "$(dirname "$0")/../.."
for c in seniors collections; do
  grep -q '^CASE_LIVE=' "cases/$c/.env" || echo 'CASE_LIVE=1' >> "cases/$c/.env"
done
docker compose -f deploy/docker-compose.yml --profile cases up -d --no-build app-seniors app-collections
sleep 5
for h in jsemvcas.cz seniori.jsemvcas.cz vymahani.jsemvcas.cz; do
  printf '%s: ' "$h"; curl -s "https://$h/api/health" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["mode"],"email" if d["email"] else "no-email",d.get("case","screening"))'
done
