#!/usr/bin/env bash
# Every few minutes: is the public site up? E-mail once when it goes down and once when it is back.
# If a container stopped, start it again (restart policies cover crashes; this covers a manual stop or a failed deploy).
set -uo pipefail
for f in $(compgen -A function); do unset -f "$f"; done   # shell wrappers (e.g. a login profile) must not change grep/docker/git
REPO="${REPO:-/root/rakathon2026}"
STATE="${STATE:-/var/lib/jsemvcas}"
DOCKER=/usr/bin/docker
mkdir -p "$STATE"

url="${URL:-$(grep -E '^PUBLIC_URL=' "$REPO/backend/.env" | cut -d= -f2-)}"   # URL=… overrides, for a test
check() { curl -fsS -m 15 -o /dev/null "$1/api/health"; }

if check "$url" || { sleep 20; check "$url"; }; then
  if [ -f "$STATE/down" ]; then
    since="$(cat "$STATE/down")"; rm -f "$STATE/down"
    python3 -I "$REPO/deploy/ops/notify.py" "OK again" "$url is up again (down since $since)."
  fi
  exit 0
fi

local_ok=no; check http://localhost:8000 && local_ok=yes
running="$($DOCKER ps --format '{{.Names}}' | grep -E '^deploy-(app|tunnel)-1$' | sort | tr '\n' ' ')"
if [ "$running" != "deploy-app-1 deploy-tunnel-1 " ]; then   # sorted, so the order of docker ps does not matter
  (cd "$REPO/deploy" && $DOCKER compose --profile tunnel up -d) >/dev/null 2>&1 || true
fi
if [ ! -f "$STATE/down" ]; then
  date '+%F %H:%M' > "$STATE/down"
  python3 -I "$REPO/deploy/ops/notify.py" "DOWN" "$url/api/health does not answer.
App on the VPS (localhost:8000): $local_ok. Running containers: ${running:-none}.
If the app answers locally, the Cloudflare tunnel is the problem: docker compose --profile tunnel logs tunnel (in $REPO/deploy).
Containers were started again if one was missing. See deploy/OPERATIONS.md."
fi
exit 1
