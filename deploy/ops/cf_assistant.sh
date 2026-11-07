#!/usr/bin/env bash
# Adds a host (default asistent.jsemvcas.cz, e.g. `cf_assistant.sh zavolej.jsemvcas.cz`) to the jsemvcas tunnel and creates its DNS record. Keeps every existing rule; safe to run twice.
# Token: deploy/.cf. The old tunnel config is saved to /root/backups/cloudflare first.
set -euo pipefail
cd "$(dirname "$0")/../.."
. deploy/.cf
export CF_API_TOKEN
export HOST="${1:-asistent.jsemvcas.cz}"
exec python3 -I - <<'PY'
import json, os, time, urllib.request
A, T, Z = "6ed6bff897393de7dfab03faba026a67", "39a7fb35-2c8e-4fbe-8269-e8f9398b7af4", "2253a23bc92ca33a517e5af389403cc7"
HOST, SERVICE, API = os.environ["HOST"], "http://app-assistant:8000", "https://api.cloudflare.com/client/v4"
def call(method, path, body=None):
    r = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                               headers={"Authorization": "Bearer " + os.environ["CF_API_TOKEN"], "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(r, timeout=20))
    assert d["success"], d["errors"]
    return d["result"]
cfg = call("GET", f"/accounts/{A}/cfd_tunnel/{T}/configurations")["config"]
os.makedirs("/root/backups/cloudflare", exist_ok=True)
with open(f"/root/backups/cloudflare/tunnel-config-{time.strftime('%Y%m%d-%H%M%S')}.json", "w") as f:
    json.dump(cfg, f)
if any(i.get("hostname") == HOST for i in cfg["ingress"]):
    print("tunnel: already there")
else:
    cfg["ingress"].insert(len(cfg["ingress"]) - 1, {"hostname": HOST, "service": SERVICE})  # before the catch-all 404
    call("PUT", f"/accounts/{A}/cfd_tunnel/{T}/configurations", {"config": cfg})
    print("tunnel: added", [i.get("hostname") for i in cfg["ingress"]])
if call("GET", f"/zones/{Z}/dns_records?name={HOST}"):
    print("dns: already there")
else:
    call("POST", f"/zones/{Z}/dns_records", {"type": "CNAME", "name": HOST, "content": f"{T}.cfargotunnel.com", "proxied": True})
    print("dns: added")
PY
