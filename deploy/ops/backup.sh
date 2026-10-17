#!/usr/bin/env bash
# Nightly backup: the app state volume (decisions, outbox, tokens) and backend/.env. Keeps the last $KEEP of each.
# IRIS is not backed up: its FHIR data is rebuilt from the CSV + this state with POST /api/fhir/push.
set -euo pipefail
for f in $(compgen -A function); do unset -f "$f"; done   # shell wrappers (e.g. a login profile) must not change grep/docker/git
REPO="${REPO:-/root/rakathon2026}"
DEST="${DEST:-/root/backups/jsemvcas}"
KEEP="${KEEP:-14}"
DOCKER=/usr/bin/docker

umask 077
mkdir -p "$DEST"
ts="$(date +%F-%H%M)"
vol="$($DOCKER volume inspect deploy_plice-data --format '{{.Mountpoint}}')"
tar czf "$DEST/state-$ts.tgz" -C "$vol" .
install -m 600 "$REPO/backend/.env" "$DEST/env-$ts"

for pattern in 'state-*.tgz' 'env-*'; do
  ls -1t "$DEST"/$pattern 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
done
echo "backup ok: $DEST/state-$ts.tgz ($(du -h "$DEST/state-$ts.tgz" | cut -f1))"
