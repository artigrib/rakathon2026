# Jsem včas – running the VPS long-term

https://jsemvcas.cz – `/` landing (public), `/rakathon` (public), `/app` the app (password `DEMO_USER`/`DEMO_PASSWORD`).

## What runs

| Piece | Where | Restarts by itself |
|---|---|---|
| App (FastAPI + web) | `deploy-app-1`, compose in `deploy/`, state in volume `deploy_plice-data` | `unless-stopped` |
| HTTPS | named Cloudflare tunnel `jsemvcas` in `deploy-tunnel-1` (`--profile tunnel`, `TUNNEL_TOKEN` in `backend/.env`) | `unless-stopped` |
| FHIR server | InterSystems IRIS for Health in `fhir-template` (`~/iris-fhir-template`, ports on 127.0.0.1 only), joined to `deploy_default` | `always` |
| Health check | `jsemvcas-health.timer`, every 5 min | e-mail on down and on recovery, starts missing containers |
| Auto-deploy | `jsemvcas-autodeploy.timer`, every 10 min | new commit on `origin/main` → pip, `build_web_data.py`, tests, rebuild, FHIR sync, e-mail |
| Backup | `jsemvcas-backup.timer`, 03:17 nightly | `/root/backups/jsemvcas`: state volume + `.env`, last 14 |

Scripts: `deploy/ops/*.sh`, units: `deploy/ops/systemd/` (installed by copying to `/etc/systemd/system`).
Alerts go to `OPS_EMAIL` (else `DEMO_EMAIL`) through the app's SMTP settings. Logs: 10 MB × 3 per container, journald 200 MB.
Docker commands on this host: use `/usr/bin/docker` (the root login shell wraps `docker`/`grep` in a function that truncates output).

## Everyday

```bash
systemctl list-timers 'jsemvcas-*'                    # next runs
journalctl -u jsemvcas-autodeploy -n 50               # last deploy; full log: /var/lib/jsemvcas/autodeploy.log
cat /var/lib/jsemvcas/deployed                        # commit that runs now
curl -s https://jsemvcas.cz/api/health                # mode, trial, voice, email, fhir
cd ~/rakathon2026/deploy && /usr/bin/docker compose --profile tunnel logs -f app   # live log
```

A commit that fails tests is not deployed; it is reported once and the server stays on the previous commit.
After fixing, push a new commit. To redeploy by hand: `systemctl start jsemvcas-autodeploy` (only when origin/main moved),
or `cd deploy && /usr/bin/docker compose --profile tunnel up -d --build`.

## Restore

```bash
cd ~/rakathon2026/deploy && /usr/bin/docker compose stop app
vol=$(/usr/bin/docker volume inspect deploy_plice-data --format '{{.Mountpoint}}')
rm -rf "$vol"/* && tar xzf /root/backups/jsemvcas/state-<date>.tgz -C "$vol"
/usr/bin/docker compose --profile tunnel up -d
```
`.env`: `install -m 600 /root/backups/jsemvcas/env-<date> ~/rakathon2026/backend/.env`.

IRIS keeps its data inside the container. If it is recreated (`docker compose up` in `~/iris-fhir-template`, the local
override keeps the network), restore it from the app: `curl -u USER:PASS -X POST localhost:8000/api/fhir/push`.

## Things that expire or cost money

| What | Limit | What happens |
|---|---|---|
| Domain `jsemvcas.cz` (Active24) | yearly renewal | site gone if not renewed |
| Twilio | prepaid balance; number billed monthly | SMS/calls stop when the balance is 0 |
| ElevenLabs | Starter plan (from 17.10.2026), 30 000 characters a month, resets on the 17th | the agent call goes silent when used up; `VOICE_MODE=gather` avoids it |
| WhatsApp sandbox | join valid 72 h, free text only 24 h after the phone's last message | WhatsApp sends fail; production needs a WhatsApp sender approved by Meta |
| Gmail app password | until revoked | e-mail channel and alerts stop |
| Cloudflare tunnel token | until the tunnel is deleted | – |

## Secrets

Only in `backend/.env` (mode 600, gitignored) and in the backups. Never in git or bridge notes.
Rotate a key: change it at the provider, edit `.env`, then `cd deploy && /usr/bin/docker compose --profile tunnel up -d`.

## GitHub Actions

`.github/workflows/deploy.yml` deploys only when the `VPS_*` secrets exist. Leave them unset: this VPS deploys itself
(auto-deploy timer), and the workflow would copy to a different directory with its own `.env`.
