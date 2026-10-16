# Plíce včas – handoff for the VPS session

Rakathon 2026 (Prague, 16.–18. 10.), challenge "Cesta ke screeningu plic" (AstraZeneca, guarantor MUDr. Čierná Peterová, mentor Luboš Matys).
Team captain Artem Gribanov. Submission Saturday 13:00 (freeze 12:00), Matys judges at the team table at 14:00.

## What it is
A thin layer over GP data: finds patients eligible for the lung cancer screening programme, invites them in the GP's name
(SMS, phone assistant, WhatsApp, e-mail, letter) after a weekly one-click approval by the nurse, and follows each patient
to the LDCT result. Doctor decides exceptions and conflicting data. FHIR R4 export.

## Repo map
- `engine/` – pure Python rules (age 55–74, smoker/ex-smoker, ≥ 20 pack-years, no chest CT in 30 days, LDCT interval 1 y / 2 y after negative), data repair (broken rows, diacritics), channel recommendation. `python -m engine data --ref-date 2026-10-16`
- `backend/` – FastAPI: serves the web app, Twilio SMS/voice/WhatsApp, reply webhooks, reply understanding (`replies.py` rules + optional LLM `llm.py`), contact plan (`cadence.py`), patient link page `/p/{token}`, AI call (`voice_ai.py`, ConversationRelay), ElevenLabs voice (`tts.py`), FHIR (`fhir.py`). See `backend/README.md`.
- `web/app/` – static ES-module frontend (no build). Views `js/views/`, components `js/components/`, all UI strings `js/i18n/cs.js`, patient texts `content/messages.cs.json` (shared with backend), tokens `css/tokens.css`.
- `tests/` – 84 tests: `python -m pytest -q`
- `deploy/docker-compose.yml`, `Dockerfile`, `.github/workflows/deploy.yml`
- `SPEC.md` (rules, doctor's answers, system boundaries), `BACKLOG.md` (done / todo), `SUBMISSION.md` (texts for the submit form, 3-min table demo script)

## Private files (not in this public repo)
Everything private lives in the Google Drive folder "Plíce včas (privátní)" owned by Artem:
challenge data `plice-data.tgz`, the doctor's presentation, contacts. Keys are never stored there either.
The AstraZeneca challenge data must not be published. Copy it to the VPS separately:
`scp -r data/ vps:~/rakathon2026/data/` (1_patients.csv … 5_data_dictionary.csv, README.pdf), then
`python scripts/build_web_data.py` (creates web/app/data/patients.json). Without it the app and most tests do not run.

## Run on the VPS
```bash
cp backend/.env.example backend/.env      # fill: TWILIO_*, DEMO_TO, PUBLIC_URL, ELEVENLABS_*, LLM_*, TUNNEL_TOKEN
docker compose -f deploy/docker-compose.yml --profile tunnel up -d --build    # or without --profile tunnel behind Caddy
curl -s localhost:8000/api/health        # {"mode":"live"|"mock","voice":"elevenlabs"|"twilio",...}
python -m backend.tts                    # pre-generate call audio (ElevenLabs)
```
Twilio console: number → Messaging → "A message comes in" → `POST {PUBLIC_URL}/twilio/sms`. Geo permissions: Czech Republic (SMS + Voice).
Trial account: only verified numbers (Verified Caller IDs), trial prefix in SMS, key press before calls.
`LIVE_LIMIT=1` = one real message per click, the rest simulated.

## Rules for any change
- Secrets only in `backend/.env` (gitignored). Never commit keys.
- UI copy is Czech, plain and short. No dashes (– —), arrows, middle dots, exclamation marks, ellipses, "AI" labels, internal codes (VPL-…) in patient texts. Medical statements only if verifiable (free, covered by insurance, short, painless, low-dose CT). A test enforces this for patient templates.
- Patient texts live only in `web/app/content/messages.cs.json`.
- Design: Swiss grid, graphite on #f4f4f2, one accent (palette switch in the demo panel: petrol/orange/cobalt, pending decision), amber only for data warnings.
- AI never decides inclusion or sending. It only classifies replies; the phone assistant speaks only approved sentences.
- Run `python -m pytest -q` before pushing.

## Open tasks (owner)
1. VPS: run live, set Twilio webhook, test SMS round trip + call with key 1 (VPS session).
2. GitHub secrets for auto-deploy (VPS_HOST, VPS_USER, VPS_SSH_KEY, APP_ENV) (Artem).
3. Choose accent colour, then remove the palette switch (designer).
4. Optional: e-mail channel via Twilio/SendGrid; WhatsApp sandbox join on demo phone.
5. Saturday: fill the submit form from SUBMISSION.md, record backup video if UI changes (`submission/`).

## Who does what (two Claude sessions, one repo)
- **VPS session** (also opened from the web): runs and deploys the app, live Twilio/ElevenLabs tests, backend fixes found in live tests, server logs.
- **Cloud session** (claude.ai chat with Artem): engine, web UI and copy, patient texts, submission texts, video, design changes.
- Artem decides and relays anything that needs a human (keys, Twilio console, phone tests, Drive uploads).
- To avoid conflicts: `git pull --rebase` before every change, small commits, push right away.
  If you need to change a file the other side owns, write a note in `bridge/` first.
- Private files: if this session has Google Drive access, read the folder "Plíce včas (privátní)"; otherwise Artem copies them by scp.

## Bridge between sessions
Cloud session (claude.ai) and VPS session talk through this repo.
- Write a note as a new file `bridge/YYYY-MM-DD-HHMM-<from>.md` (from = cloud | vps), commit, push.
- Pull before work, read new notes in `bridge/`.
- Keep notes short: what changed, what you need from the other side.
