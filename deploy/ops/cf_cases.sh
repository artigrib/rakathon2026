#!/usr/bin/env bash
# Adds seniori.jsemvcas.cz and vymahani.jsemvcas.cz to the jsemvcas tunnel (keeps jsemvcas.cz) and creates their DNS records.
# Token: deploy/.cf (CF_API_TOKEN=…, Cloudflare Tunnel:Edit + DNS:Edit + Zone:Read).
set -euo pipefail
cd "$(dirname "$0")/../.."
. deploy/.cf
A=6ed6bff897393de7dfab03faba026a67
T=39a7fb35-2c8e-4fbe-8269-e8f9398b7af4
Z=2253a23bc92ca33a517e5af389403cc7
API=https://api.cloudflare.com/client/v4
H="Authorization: Bearer $CF_API_TOKEN"

mkdir -p /root/backups/cloudflare
curl -s -H "$H" "$API/accounts/$A/cfd_tunnel/$T/configurations" > "/root/backups/cloudflare/tunnel-config-$(date +%Y%m%d-%H%M%S).json"

curl -s -X PUT -H "$H" -H 'Content-Type: application/json' "$API/accounts/$A/cfd_tunnel/$T/configurations" --data '{"config":{"ingress":[
 {"hostname":"jsemvcas.cz","service":"http://app:8000"},
 {"hostname":"seniori.jsemvcas.cz","service":"http://app-seniors:8000"},
 {"hostname":"vymahani.jsemvcas.cz","service":"http://app-collections:8000"},
 {"service":"http_status:404"}],"warp-routing":{"enabled":false}}}' \
 | python3 -c 'import json,sys;d=json.load(sys.stdin);print("tunnel",d["success"],d["errors"])'

for s in seniori vymahani; do
  curl -s -X POST -H "$H" -H 'Content-Type: application/json' "$API/zones/$Z/dns_records" \
    --data "{\"type\":\"CNAME\",\"name\":\"$s.jsemvcas.cz\",\"content\":\"$T.cfargotunnel.com\",\"proxied\":true}" \
    | python3 -c 'import json,sys;d=json.load(sys.stdin);print("dns '"$s"'",d["success"],d["errors"])'
done
