# Case packages

One core (`backend/`, `web/app/`) runs one **case** per process. The case is chosen by env `CASE`
(default `screening`); everything domain-specific lives in `cases/<id>/`.

```
CASE=seniors .venv/bin/python -m cases.seniors.build            # build the data file
CASE=seniors .venv/bin/python -m uvicorn backend.app:app --port 8001
CASE=seniors .venv/bin/python -m pytest -q                       # core + contract of every case + cases/seniors/tests
```

Backend modules bind the case at import time (`backend/case.py: CASE = load()`), so one process = one case.
State: `backend/state.json` for screening, `backend/state-<id>.json` otherwise (env `STATE_FILE` overrides).
Optional `cases/<id>/.env` is read before `backend/.env` (own `ELEVENLABS_AGENT_ID`, `DEMO_PASSWORD` …).

`tests/test_case_contract.py` checks every rule marked **(checked)** below for every `cases/*/case.json`.
`cases/screening/` is the reference implementation of everything here.

## Files

| file | required | read by |
|---|---|---|
| `__init__.py` | yes (may be empty) | python import `cases.<id>` |
| `case.json` | yes | `backend/case.py`, `backend/settings.py`, `GET /api/case`, `web/app/js/case.js` |
| `journey.json` | yes | `backend/fsm.py`, `web/app/js/fsm.js` (served as `/app/content/journey.json`) |
| `messages.cs.json` | yes | `backend/messages.py` and the web app (`/app/content/messages.cs.json`) |
| `dialog.py` | yes | `backend/replies.py`, `llm.py`, `voice_ai.py`, `fsm.py`, `agent_call.py`, `hall.py`, `scripts/elevenlabs_agent.py` |
| `cadence.py` | yes | `backend/cadence.py` |
| `hooks.py` | yes | `backend/messages.py`, `backend/app.py` |
| `build.py` | yes | `python -m cases.<id>.build` writes the data file |
| `web/` | yes | served at `/app/case/` (ES modules, no build step) |
| `tests/` | no | `test_*.py`, run only when `CASE=<id>`; add `tests/__init__.py` |
| `.env` | no | `backend/settings.py` (gitignored) |

Only top-level `*.json` of the package are served (`/app/content/<name>.json`); Python files never are.

## case.json **(checked)**

```jsonc
{
  "id": "seniors",                       // = directory name
  "title": "Jsem v pořádku",             // <title>, FastAPI title, fallback e-mail subject
  "brand": "Jsem v pořádku",             // header wordmark, fallback e-mail sender name
  "lang": "cs",
  "about": "…",                          // free text
  "entity": {"one": "senior", "few": "senioři", "many": "seniorů"},
  "owners": {"operator": "operátor", "social": "sociální pracovník"},   // owner keys → words (informative)
  "group": {"field": "district", "label": "Obvod", "default": "Praha 4"},  // header selector over records; null = none
  "views": [                             // navigation, in this order; first = start view
    {"id": "today", "module": "views/today.js"},             // relative to web/
    {"id": "people", "module": "core/views/patients.js"}     // or a core view
  ],
  "features": {"fhir": false, "hall": false},   // fhir: /api/fhir* + FHIR write-back; hall: /sal, /j/*, /api/hall*
  "domain": "jsemvcas.cz",               // Message-ID domain, hall SMS link base without PUBLIC_URL
  "redirects": {"/info": "https://…"},   // optional public short links (open without password)
  "voice": {"mode": "gather", "lang": "cs-CZ", "name": "Google.cs-CZ-Standard-A"},  // defaults of VOICE_MODE/LANG/NAME
  "demo_user": "seniori",                // Basic-auth user (default: id)
  "ref_date": "2026-10-16",              // demo clock start when the data file has no refDate
  "initial_stage": "new",                // = journey.json "initial"
  "sent_stage": "sent",                  // stage after event "send": store keeps d.sent, cadence counts these
  "result_stage": null,                  // optional: store copies event extra `result` into d.result
  "terminal_reply_stages": ["ok", "…"],  // a last stage in this set stops the automatic plan
  "data": "cases/seniors/data/patients.json",   // repo-relative data file
  "storage_key": "seniors:v1"            // localStorage key of the web app (static mode)
}
```

## journey.json **(checked)**

Same format as screening: `{"initial", "soft_decline"?: {"event", "first_to"}, "states": {name: {"section", "final"}},
"transitions": {state: {event: target}}}`. Rules: `fsm.check(spec) == []` (all targets known, every state has a row,
non-final states have a way out, everything reachable); the initial state allows `send`; no final state allows `send`.
Core events: `send` (any outbound touch, also automatic), `Plan.human` (e.g. `nurse`: the contact plan hands over to a
person). Other events = reply intents (`dialog.INTENT_EVENT`) and buttons of the case UI (`data-action="step"
data-stage="<event>"`). Only transitions change the stage; any other event is recorded with `ignored: true`.
`section` is free for the case UI (screening: invite | waiting | replied | results | null).

## messages.cs.json **(checked)**

Every text sent to a person. Placeholders `{name}`; core fills `{call_us}` (env `PRACTICE_PHONE`), `{link}`,
`{link_short}`; the case fills the rest with `hooks.extra_placeholders` (backend) and `domain.placeholders` (web).
Every variant of every channel must render without a leftover `{…}` for sample records.

```jsonc
{
  "parts": {"call_us": " na tel. {phone}", "link": "\n\nOdpovědět můžete i zde: {url}", "link_short": " Odpověď: {url}",
            "link_marker": "[odkaz]", "…": "case parts"},
  "channel_template": {"sms": "sms", "whatsapp": "sms", "voice": "voice", "email": "email", "letter": "email", "portal": "email"},
  "sms":   {"FIRST_INVITE": "…", "TRIAL": "≤ 122 chars, Twilio trial", "<VARIANT>": "…"},
  "voice": {"FIRST_INVITE": "… keys 1/2 call script …"},
  "email": {"FIRST_INVITE": "…"},
  "sms_reply": {"<stage after reply>": "confirmation", "callback": "fallback (required)"},
  "sender": "Vaše ordinace", "email_subject": "…",
  "voice_ui": {"no_answer": "…", "no_digit": "…", "thanks": {"<stage>": "after the keys-1/2 answer"}},
  "page": {                              // personal link /p/{token}; HTML strings; never show personal data
    "invalid": "<h1>…</h1>", "head": "<h1>…</h1><p>…</p>", "foot": "<p class=\"muted\">…</p>", "thanks_title": "Děkujeme",
    "answers": [{"value": "yes", "label": "Ano", "class": "primary", "event": "<journey event>", "intent": "<intent>", "thanks": "…"}]
  },
  "hall": {"sms": "…{centres} {info}…", "email": "…", "join_title": "…", "…": "only with features.hall"}
}
```

Variants used by core: `FIRST_INVITE` (fallback of every channel), every `Step.variant` and `Plan.restart_variant`
of the cadence **(checked)**. Keys starting with `_` are comments.

## dialog.py **(checked)**

```python
INTENTS: list[str]                 # must contain "opt_out", "question", "unclear" (core safety meaning)
INTENT_EVENT: dict[str, str]       # every intent → journey event
STAGE: dict[str, str]              # every intent → stage word (informative)
RULES: list[tuple[str, list[str]]] # (intent, regexes) in priority order, run on lower-case ASCII text
QUESTION: re.Pattern               # matches a question → intent "question"
WHY: dict = {"question": "…", "unclear": "… předáno …"}   # optional, journey note texts
def extract(text: str) -> dict     # structured fields from a reply ({} = none); merged over the LLM's `extra`
LLM_SYSTEM: str                    # asks for JSON {"intent","when","confidence":"high|low","why"[,"extra":{…}]}
LLM_USER: str = "Odpověď: «{text}»"  # optional
GREETING, ASK_AGAIN, NOT_UNDERSTOOD: str
FAQ: list[tuple[tuple[str, ...], str]]   # (keywords without diacritics, approved answer)
CLOSING: dict[str, str]            # intent → closing sentence; must have "handoff" and "opt_out" or "declined"
MAX_UNCLEAR: int = 2               # optional
DTMF: dict[str, str]               # key pressed in a call → words for RULES, e.g. {"1": "ano", "2": "teď ne"}
DECISIONS: set[str]                # ElevenLabs agent decision values (⊆ INTENTS, contains "unclear")
AGENT_NAME: str
AGENT_DECISIONS: dict[str, str]    # decision → description for the agent's data collection
AGENT_WHEN: str                    # description of data collection `preferred_time` (→ event `when`)
AGENT_DATA: dict[str, str]         # extra data collection fields → event `extra` ({} = none)
def agent_prompt() -> str          # the whole agent prompt (only approved sentences); must contain CLOSING["handoff"]
# features.hall only:
HALL_CLOSING: dict[str, str]; HALL_NOT_UNDERSTOOD: str; HALL_STATUS: dict[str, str]  # intent → card status
HALL_LINKS: dict = {"centres": "/centra", "info": "/prevence"}   # optional, SMS placeholders → paths
```

Core policy (`backend/replies.understand`, not overridable): rules first; `opt_out` from rules or AI always wins;
an AI answer with confidence ≠ high becomes `unclear` (→ a person); AI failures fall back to rules. The result is
`{intent, confidence, why, source[, when][, extra]}`. In a ConversationRelay call (`backend/voice_ai.Conversation`)
an intent with its own `CLOSING` sentence ends the call; `question` → `FAQ` answer + `ASK_AGAIN` or handoff;
`unclear` twice → handoff. The bot never says anything that is not in `dialog.py` / `messages.cs.json`.

## cadence.py **(checked)**

```python
from backend.plan import Plan, Step
PLAN = Plan(
    steps=(Step(0, "sms", "FIRST_INVITE"), Step(1, "voice", "REMINDER"), Step(3, "nurse")),  # day from first send
    pause_days=90, restart_variant="MOTIVATION",
    pause_stage="not_now",           # "" = no pause cycle
    human="nurse",                   # step channel meaning "a person takes over"; fires this journey event
    stop_stages=frozenset({"nurse_call"}),   # besides case.json terminal_reply_stages
)
```

Algorithm (`backend/cadence.next_touch`, core): nothing until the first `sent_stage`; stops when the last stage is
terminal or a stop stage; the pause stage restarts the ladder after `pause_days` with `restart_variant`; never the
same channel three times in a row. `POST /api/tick` (demo clock) sends what is due.

## hooks.py **(checked)**

```python
def extra_placeholders(patient: dict, M: dict) -> dict[str, str]   # message placeholders from a record ({} ok)
def on_reply(pid: str, intent: str, extra: dict, store) -> None    # after every recorded reply (webhook, link, UI,
                                                                     # relay call, agent call); store = backend Store
```

`on_reply` runs after the journey transition. Write case data with `store.patch(pid, field=value)` (a dict per record,
returned in `/api/state` → `decisions[pid]`, visible in the web app as `store.get(id).field`) or
`store.data["<key>"]` + `store._save()` for case-wide data. Event `extra` is also stored on the journey event.

## build.py **(checked: `build` and `main` exist)**

`build(...) -> dict` returns the data; `main(argv=None)` writes it to `case.json "data"`. Deterministic (fixed seed).

### Data file shape

```jsonc
{"refDate": "2026-10-16", "issues": [], "patients": [ {…record…} ]}
```

The key stays `patients` for every case (the core reads it). Record fields the core relies on:

| field | used by |
|---|---|
| `id` (unique string) **(checked)** | everything |
| `<group.field>` when the manifest has a group **(checked)** | header selector, `mineOf()` |
| `flags: [{sev: "warning"\|…, text}]` | optional: warnings on the card |
| `history: [{date, channel, type, delivery, response}]` | optional: earlier contacts in the communication timeline |
| `portal: bool` | optional: enables the `portal` channel button |
| `sex: "F"\|"M"` | optional: Czech verb agreement in screening i18n |

Everything else is the case's own. Real messages always go to the demo recipient, never to a record's phone.

## web/ (ES modules, served at `/app/case/`)

Load order (`web/app/js/case.js`): `case.json` → `i18n.js` → `config.js` → `domain.js` → `row.js` → `card.js`? →
`actions.js`? → view modules → core shell. Import the core **only** through the import map prefix `core/`
(`import { store } from "core/state.js"`), files of the package relatively (`./domain.js`, `../i18n.js`).
Core modules for cases: `core/case.js` (`CASE, T, cfg, dom, mineOf, contentUrl`), `core/state.js` (`store`),
`core/fsm.js` (`next, allowed, sectionOf, isFinal, refusals, softEvent`), `core/util.js` (`esc, fmtDate, html, countBy,
cap`), `core/messages.js` (`message(p, channel, variant)`), `core/components/row.js` (`row, btn, stepBtn`),
`core/components/comm.js` (`comm, timeline`), `core/components/journey.js`, `core/components/compose.js`,
`core/components/toast.js` (`toast`), `core/views/patients.js` (a ready view).

Required exports **(checked)**:

```js
// i18n.js
export const T = {…};      // strings; the core uses the keys listed below
// config.js
export const CHANNELS = ["sms", "voice", "whatsapp", "email"];   // compose buttons
export const REPLIES = ["ok", "need_items"];                     // simulated replies (demo); T.demo.reply[r], T.demo.replyText[r]
export const JOURNEY = [{ key: "sent", stages: ["sent"] }, …];   // journey steps on the card; T.journey.steps[key]
export const FILTERS = ["all", "operator", "done"];              // core/views/patients.js tabs (owner keys + "all")
export const PRACTICES = { "<group>": { phone: "" } };           // optional: {call_us} phone per group
// domain.js
export function stageOf(p): string | null           // current stage (store.get(p.id).stage …)
export function ownerOf(p, clock, plans): string    // owner key (T.card.owner[key], FILTERS); "lost" = getting lost
export function lostOf(p, clock, plans): {code, days, sev} | null   // T.lost[code](days, p)
export function plannedContact(p): {channel, variant}
export function batchOf(records): records           // what "approve-batch" sends
export function failedChannels(p): Set<string>      // optional
export function groups(records): string[]           // required when case.json has a group
export function setClock(isoDate)                   // optional, called on every render
export function placeholders(p, M): {name: string}  // optional, same as hooks.extra_placeholders
// row.js
export function describe(p, d, plan): {title, sub?}  // d = store.get(p.id), plan = next automatic touch or undefined
export function actions(p, d): string               // HTML buttons (use btn / stepBtn from core/components/row.js)
export function rowClass(p, d): string              // optional, e.g. " row--skipped"
// card.js (optional)
export function blocks(p): {before?: string, after?: string}   // HTML around journey + communication
// actions.js (optional)
export const actions = { name: async (el, app, event) => {…} };  // click on [data-action="name"]
//   app = {ui, data, store, T, toast, send(items), mark(id, field, value), step(id, {stage|reply,text,result}),
//          find(id), today(), backend}   — backend null = static page
// views/<x>.js (each manifest view)
export function render(ui, data, rowCtx): string    // ui = {view, gp, filter, query, …}; mineOf(data, ui) = records
export function badge(mine, clock, plans): number   // optional, count in the navigation
```

`rowCtx.of(p)` gives the `row(p, ctx)` context. Core click actions: `pick-view`, `pick-filter`, `open-card`,
`close-card`, `open-compose`, `close-compose`, `pick-channel`, `save-draft`, `confirm-send`, `approve-batch`,
`skip`, `unskip`, `reply` (`data-reply`), `step` (`data-stage`, `data-result`), `toggle-replies`, `tick`, `reset`,
`undo`, `recipient-save`, `recipient-reset`, `fhir-sync`, `open-practice` (`data-gp`). Marks stored on the server
(`POST /api/mark`): only `skipped`, `draft`, `override`, `resultAck`.

i18n keys the core reads: `nav[viewId]`; `toast.{draftSaved, sent(ch), approved(n), skipped, unskipped, reply(label),
step[event] + step.softDeclined, recipientSaved, recipientReset, tick(n)}`; `apiError`, `loadError`,
`footer(d)`, `footerLive(d, live)`, `footerClock(d)`, `footerFhir(fhir)`; `channel[ch]`, `channelRecommended`,
`channelFailed`, `channelNoPortal`; `compose.{channel, text, voiceText, trial, link, note}`; `actions.{open, cancel,
saveDraft, sendNow(ch), undo}` (+ `actions.result[r]` when events carry `result`); `who(p)`; `lost[code](days, p)`;
`card.{owner[key], close}`; `detail.{journey, msgType, delivery, response, event[stage], noContacts}`;
`journey.steps[key]`; `comm.{title, actor[system|nurse|patient|doctor|record], sent, autoSent(step), simulated,
status[st], duration(s), showText, showScript, replied(via, p), via[via], understood, ignored, softDeclined,
unreachable, planned(ch), event[event]}` (+ `state.booked(p)`, `state.selfBooked(p)` for an event named `booked`);
`demo.{title, intro, hall, clock(d), next, replies, fhirSync, reset, replyLabel, reply[r], replyText[r], openLink,
to.{title, phone, email, hint(r), save, reset, logout}}`; core patients view: `patients.{title, search, searchHint,
groups, empty, filters[f]}`. Copy `cases/screening/web/i18n.js` and change the words.

Static mode (no backend): serve the repository root with any web server and open `/web/app/?case=<id>`; the app
then reads `../../cases/<id>/` and simulates sending locally.

## Tests

- `tests/test_case_contract.py` validates every case automatically (manifest, web exports, journey, dialog, cadence,
  hooks, build, message rendering, data shape).
- Case tests in `cases/<id>/tests/test_*.py` (+ `__init__.py`) run with `CASE=<id> .venv/bin/python -m pytest -q`;
  the root `conftest.py` sets the env, skips other cases' tests and offers the `client` fixture
  (`(TestClient(app), store)`, fresh state).
- `tests/` (except `test_case_contract.py`, `test_recipient.py`, `test_sessions.py`, `test_password_landing.py`)
  is screening and runs only with `CASE=screening`.
