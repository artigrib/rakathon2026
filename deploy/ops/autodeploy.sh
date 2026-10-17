#!/usr/bin/env bash
# Every 10 minutes: new commits on origin/main → tests → rebuild the app → patients from IRIS. Without a Claude session.
# A failing commit is not deployed (the checkout goes back) and is reported once by e-mail.
set -uo pipefail
for f in $(compgen -A function); do unset -f "$f"; done   # shell wrappers (e.g. a login profile) must not change grep/docker/git
REPO="${REPO:-/root/rakathon2026}"
STATE="${STATE:-/var/lib/jsemvcas}"
DOCKER=/usr/bin/docker
NOTIFY="python3 -I $REPO/deploy/ops/notify.py"
mkdir -p "$STATE"
cd "$REPO" || exit 1
exec 9>"$STATE/autodeploy.lock"; flock -n 9 || exit 0   # one run at a time

# Compare with what is actually deployed, not with HEAD: someone may have pulled without rebuilding.
old="$(cat "$STATE/deployed" 2>/dev/null || git rev-parse HEAD)"
git fetch -q origin main || exit 0
new="$(git rev-parse origin/main)"
[ "$old" = "$new" ] && exit 0
[ "$(cat "$STATE/failed" 2>/dev/null)" = "$new" ] && exit 0   # already reported
log="$STATE/autodeploy.log"; : > "$log"

fail() {
  echo "$new" > "$STATE/failed"
  git reset -q --keep "$old" 2>/dev/null || true
  $NOTIFY "deploy FAILED: $1" "Commit $new was not deployed ($1). The server stays on $old.
$(tail -n 40 "$log")"
  exit 1
}

git merge -q --ff-only origin/main >>"$log" 2>&1 || fail "cannot fast-forward (local commits on the VPS?)"
.venv/bin/pip install -q -r requirements.txt >>"$log" 2>&1 || fail "pip install"
python3 scripts/build_web_data.py >>"$log" 2>&1 || fail "build_web_data"
.venv/bin/python -m pytest -q >>"$log" 2>&1 || fail "tests"
(cd deploy && $DOCKER compose --profile tunnel up -d --build) >>"$log" 2>&1 || fail "docker build"

for _ in $(seq 1 30); do curl -fsS -m 5 -o /dev/null http://localhost:8000/api/health && break; sleep 2; done
curl -fsS -m 5 -o /dev/null http://localhost:8000/api/health || fail "app does not start"

# patients from the FHIR server (IRIS) again; harmless when FHIR_BASE is empty or IRIS is down
user="$(grep -E '^DEMO_USER=' backend/.env | cut -d= -f2-)"; pass="$(grep -E '^DEMO_PASSWORD=' backend/.env | cut -d= -f2-)"
curl -fsS -m 300 -u "$user:$pass" -X POST http://localhost:8000/api/fhir/sync >>"$log" 2>&1 || echo "fhir sync skipped" >>"$log"
$DOCKER image prune -f >/dev/null 2>&1 || true
rm -f "$STATE/failed"
echo "$new" > "$STATE/deployed"
$NOTIFY "deployed $(git rev-parse --short HEAD)" "$(git log --oneline "$old..$new")"
