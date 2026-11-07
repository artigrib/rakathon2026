# Phone assistant demo

https://asistent.jsemvcas.cz: set up an assistant on a page, get a Twilio number and a forwarding code. Calls to that
number are answered by the assistant's own ElevenLabs agent, whether forwarded after N seconds or dialled directly.

```
caller → Vodafone (no answer, **61*NUMBER**10#) → Twilio number → POST /twilio/inbound → ElevenLabs agent
                                     after the call: POST /twilio/status → transcript + summary → page, e-mail
          during the call the agent may call /tools/{id}/availability | book | message
```

Separate on purpose: own image, database, `.env` and compose profile. The auto-deploy (`--profile tunnel`), health check
and backup do not touch it, so **data in `deploy_assistant-data` is not backed up** and a new commit is not deployed by itself.

## Operate

```bash
cd ~/rakathon2026/deploy
/usr/bin/docker compose --profile assistant up -d --build --no-deps app-assistant   # build and restart only this service
/usr/bin/docker logs -f deploy-app-assistant-1                                      # no phone numbers in the log
curl -s localhost:8003/api/health
.venv/bin/python -m pytest assistant/tests                                          # needs assistant/requirements.txt, else skipped
```

`assistant/.env` (mode 600, gitignored, see `.env.example`) holds its own copies of the Twilio, ElevenLabs and SMTP keys.
This container takes input from the public, so it does not get `backend/.env`. **When you rotate one of those keys, change it here too.**

## Add a number

1. Buy it on Twilio. A Czech number needs an approved regulatory bundle first.
2. Add it to `ASSISTANT_NUMBERS` in `assistant/.env` (comma separated), restart the service.
3. Point it here. This changes voice settings only and saves the old ones to the volume:
   `/usr/bin/docker exec deploy-app-assistant-1 python -m assistant.provision +420... --apply` (without `--apply`: dry run).

New assistants take the number with the fewest assistants. Existing assistants keep their number.

## Who answers on a shared number

One assistant on a number answers every call. With more: the one whose owner matches `ForwardedFrom`, else the one whose
owner is calling, else the newest. Each call stores its `route`; the log says whether `ForwardedFrom` arrived, which
depends on the operator.

## Connect Google

Google Cloud Console, your own project:
1. Enable Google Calendar API and Gmail API.
2. OAuth consent screen, then an OAuth client of type Web application, redirect URI `https://asistent.jsemvcas.cz/oauth/google/callback`.
3. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `assistant/.env`, restart the service.

While the consent screen is in **Testing**, only the listed test users can connect and their tokens expire after 7 days.
Other people need the app published, and Google's verification for these scopes.

## What an assistant can reach

A caller is an unauthenticated stranger, so the limits are enforced by the server, not by the prompt:

| Permission | Scope | Limit |
|---|---|---|
| Free time | `calendar.freebusy` | free/busy only, event titles are never requested; 60 days ahead |
| Book a meeting | `calendar.events` | free slot in working hours (Mon–Fri 9–17), 15–60 min, 5 a day, no guests, no notifications |
| Summary, urgent message | `gmail.send` or SMTP | only to the owner: the recipient is not a parameter; 20 messages a day |

The mailbox is never read. Google refresh tokens are encrypted with `ASSISTANT_SECRET`. Booking is off until switched on.
Also: greeting always ends with the AI and transcript notice; 5 minutes per call; 50 calls a day per number; 20 assistants;
calls and activity deleted after 30 days. An assistant's URL is its secret, and the page also needs the access code.

ElevenLabs stores inline webhook tools as workspace objects that outlive the agent, so `agents.py` deletes them with it.
