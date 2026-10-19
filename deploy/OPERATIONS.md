# Jsem včas – running the VPS long-term

https://jsemvcas.cz – `/` landing (public), `/rakathon` (public), `/app` the app.

Access: `/login` asks for the access code (`DEMO_PASSWORD`) and the visitor's own phone (+420 only) and e-mail.
Each visitor gets their own demo (state in `/data/sessions/<id>.json`), and every live SMS, call, WhatsApp and e-mail
of that demo goes to their contacts, at most `DEMO_DAILY_LIMIT` a day per number. Replies are matched by the phone,
Twilio callbacks and patient links by `?s=<id>`. Sessions and contacts expire after 30 days (`/data/sessions.json`).
Basic auth (`DEMO_USER`/`DEMO_PASSWORD`) still works for scripts and uses the shared demo (`/data/state.json`),
which is the only one that writes back to IRIS.

## What runs

| Piece | Where | Restarts by itself |
|---|---|---|
| App (FastAPI + web), case `screening` | `deploy-app-1`, compose in `deploy/`, state in volume `deploy_plice-data` | `unless-stopped` |
| HTTPS | named Cloudflare tunnel `jsemvcas` in `deploy-tunnel-1` (`--profile tunnel`, `TUNNEL_TOKEN` in `backend/.env`) | `unless-stopped` |
| FHIR server | InterSystems IRIS for Health in `fhir-template` (`~/iris-fhir-template`, ports on 127.0.0.1 only), joined to `deploy_default` | `always` |
| Health check | `jsemvcas-health.timer`, every 5 min | e-mail on down and on recovery, starts missing containers |
| Auto-deploy | `jsemvcas-autodeploy.timer`, every 10 min | new commit on `origin/main` → pip, `build_web_data.py` (= `make data`), tests (`CASE=screening`), rebuild, FHIR sync, e-mail |
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

## Seniors and collections (cases 2 and 3)

The same image runs every case (`cases/<id>/`, env `CASE`, see `cases/README.md`). Production above is case `screening`
(service `app`); `deploy/docker-compose.yml` also has two services behind the compose profile `cases`, so they never
start unless asked for. The auto-deploy (`--profile tunnel`), health check and backup do not touch them.

| Service | `CASE` | Host port | Volume | State file | Own keys (optional, gitignored) |
|---|---|---|---|---|---|
| `app` | screening | 127.0.0.1:8000 | `deploy_plice-data` | `/data/state.json` | `backend/.env` |
| `app-seniors` | seniors | 127.0.0.1:8001 | `deploy_seniors-data` | `/data/state-seniors.json` | `cases/seniors/.env` |
| `app-collections` | collections | 127.0.0.1:8002 | `deploy_collections-data` | `/data/state-collections.json` | `cases/collections/.env` |

```bash
cd ~/rakathon2026 && make data CASE=seniors && make data CASE=collections   # data files (also built in the image when missing)
cd deploy && /usr/bin/docker compose --profile cases up -d --build app-seniors app-collections   # only the two new ones
curl -s localhost:8001/api/health; curl -s localhost:8002/api/health      # "case":"seniors" / "collections"
/usr/bin/docker compose --profile cases stop app-seniors app-collections  # stop them again (make stop-cases)
```
`make up-all` does the same plus screening (it rebuilds and recreates `app` too). Naming the services keeps `app` untouched.

Env: every case container reads `backend/.env`, then `cases/<id>/.env`, which wins. **A case other than screening is
always MOCK unless `CASE_LIVE=1`** (`backend/settings.py`): with the screening keys inherited it sends nothing real, and
`make run CASE=seniors` locally does not even read `backend/.env`. `curl localhost:8001/api/health` shows `"mode"`.
To go live set in `cases/<id>/.env` `CASE_LIVE=1` and at least:
- `PUBLIC_URL=https://seniori.jsemvcas.cz` (patient links, Twilio status and voice callbacks go there; otherwise to jsemvcas.cz),
- `DEMO_USER` / `DEMO_PASSWORD` (access code of that stand),
- `ELEVENLABS_AGENT_ID` of the case's own agent (`make agent CASE=seniors` creates it from `cases/seniors/dialog.py`),
  or `VOICE_MODE=gather`; the screening agent must not answer seniors' calls,
- optionally its own `TWILIO_FROM`: incoming SMS replies go to the webhook configured on the Twilio number, which is
  `https://jsemvcas.cz/twilio/sms` (screening). A case with its own replies needs its own number whose
  "A message comes in" webhook is `{PUBLIC_URL}/twilio/sms` of that case.
After editing a case `.env`: `/usr/bin/docker compose --profile cases up -d app-seniors`.

To deploy them automatically too, change the compose line in `deploy/ops/autodeploy.sh` to
`--profile tunnel --profile cases` and add `make test-all` before it; the health check (`health.sh`, port 8000 only) and
the backup (`backup.sh`, `deploy_plice-data` only) would need the new ports and volumes as well. Not done yet.

### Public subdomains (Cloudflare tunnel, do by hand)

The tunnel `jsemvcas` is managed in the Cloudflare dashboard (token in `backend/.env`), and `deploy-tunnel-1` is on the
compose network, so it reaches the services by name. Zero Trust → Networks → Tunnels → `jsemvcas` → Public hostnames → Add:

| Hostname | Service |
|---|---|
| `jsemvcas.cz` (exists, leave as it is) | as configured now (e.g. `http://app:8000`) |
| `seniori.jsemvcas.cz` | `http://app-seniors:8000` |
| `vymahani.jsemvcas.cz` | `http://app-collections:8000` |

Cloudflare creates the DNS CNAMEs. With a locally managed tunnel (`config.yml`) the same as ingress rules, before the
catch-all `http_status:404`:
```yaml
ingress:
  - hostname: seniori.jsemvcas.cz
    service: http://app-seniors:8000
  - hostname: vymahani.jsemvcas.cz
    service: http://app-collections:8000
  - hostname: jsemvcas.cz
    service: http://app:8000
  - service: http_status:404
```
The tunnel container only depends on `app`; a hostname whose service is not running answers 502.

### Guided demo and the one Twilio number

Every case has "Spustit celou ukázku" in the demo panel (`cases/<id>/scenario.json`): a signed-in visitor gets the whole
case on their own phone (screening: SMS, call, nurse, result, e-mail; seniors: check-in call, basket, SMS to the relative,
visit; collections: SMS, verification on the page, call, promise, demo days, reminder). Steps go out for real past
`LIVE_LIMIT`, only to the visitor's own contacts and within `DEMO_DAILY_LIMIT` (default 30 a day per number, counted on
the real date; a full run uses at most 4). "Další krok" skips a wait, every wait times out on its own.

For the two case containers live:
- `cases/<id>/.env`: `CASE_LIVE=1`, their own `PUBLIC_URL` (calls, status callbacks and `/p/` links then reach the right
  container: Twilio gets `{PUBLIC_URL}/twilio/voice/…` per call; with the inherited jsemvcas.cz they would hit screening),
  `VOICE_MODE=gather` or their own `ELEVENLABS_AGENT_ID`, `DEMO_PASSWORD` (the access code of `/login`).
- Inbound SMS: the number's webhook stays `https://jsemvcas.cz/twilio/sms` (container `app`). Set in `backend/.env`
  `SMS_FORWARD=http://app-seniors:8000,http://app-collections:8000` and the same random `INTERNAL_TOKEN=…` for all three
  (case containers read `backend/.env` too). `app` then asks each one `GET /internal/has-phone` and forwards the SMS
  (`POST /internal/sms`, header `X-Internal-Token`) to the container where that phone was active last (signed in or
  last texted); ties, errors and unknown phones stay in screening. Without `SMS_FORWARD` nothing changes.
  `/internal/*` answers 403 without the token; Twilio's signature is checked by `app` only.

How to show it: open the stand, sign in with the access code and your phone and e-mail, open "Ukázka", press
"Spustit celou ukázku" and follow "where to look" in the step list.

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
