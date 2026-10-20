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

**Live traffic is opt-in for every case except screening.** `backend/.env` holds the production screening keys,
`PUBLIC_URL` and ElevenLabs agent. A case other than screening:
- does not read `backend/.env` at all unless `CASE_LIVE=1` (in the environment or in `cases/<id>/.env`);
- runs in MOCK mode (`settings.live` and `settings.email_live` are false, `/api/health` says `"mode": "mock"`) unless
  `CASE_LIVE=1`, even when Twilio / e-mail keys are in the environment (the compose services pass `backend/.env`).
To go live put `CASE_LIVE=1` together with the case's own `PUBLIC_URL`, `ELEVENLABS_AGENT_ID` (or `VOICE_MODE=gather`)
and `DEMO_PASSWORD` into `cases/<id>/.env`. Screening is unaffected (`tests/test_case_live.py`).

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
| `scenario.json` | yes | `backend/scenario.py`: the guided demo ("Spustit celou ukázku"), see below |
| `landing/` | no | `index.html` served at `/`, its other files at `/landing/<path>` (public); without it `/` opens the app, except screening (`case.json "landing"`: `submission/landing`) |
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
  "marks": ["basket"],                   // optional: extra fields the web app may set with POST /api/mark
  "row_demo": false,                     // optional: false = the demo toggle shows no simulated-reply buttons in the rows
                                         // (the case renders them itself, e.g. in the card); default true
  "login": {"email": "optional"},        // optional: the sign-in form accepts an empty e-mail (phone stays required)
  "data": "cases/seniors/synthetic/seniors.json",   // repo-relative data file; NOT under a `data/` directory
                                         // (gitignored: challenge data), so commit synthetic data e.g. in synthetic/
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
  "hall": {"sms": "…{centres} {info}…", "email": "…", "join_title": "…", "…": "only with features.hall"},
  "login": {"heading", "intro", "note"},          // sign-in page /login of the case (plain text); no lung texts elsewhere
  "scenario": {…}                                 // texts of the guided demo, see scenario.json
}
```

Variants used by core: `FIRST_INVITE` (fallback of every channel), every `Step.variant` and `Plan.restart_variant`
of the cadence **(checked)**. Keys starting with `_` are comments.

## scenario.json **(checked)** – the guided demo

"Spustit celou ukázku" in the demo panel runs the whole case on the signed-in visitor's own phone and e-mail
(`backend/scenario.py`, `web/app/js/components/scenario.js`). Only for a visitor signed in at `/login` (access code +
own phone and e-mail), never for the shared demo or `DEMO_TO`. Works in MOCK too (nothing leaves the machine; "Další krok"
simulates the answer).

```jsonc
{
  "persona": {…record…},     // a record of the data shape WITHOUT id: the core adds id "demo-you", demo: true and the
                             // case's default group; "{phone}" / "{email}" anywhere become the visitor's contacts.
                             // It lives only in that visitor's demo: store.data["personas"]["demo-you"], sent to the web
                             // app as /api/state "personas". Core lookups (render, page hook, on_tick) see it; a hook that
                             // reads records itself must fall back to store.data["personas"] (collections hooks.on_reply).
  "steps": [                 // in order; the web app's polling of /api/state moves them on
    {"id": "call",           // texts: messages.cs.json scenario.steps[id] = {"title", "look": where to look / what to do}
     "after": 3,             // seconds before it starts (default 0); "Další krok" starts it at once
     "if_stage": ["…"],      // run only in these stages, else "skipped"
     "do": [                 // actions, in order; one the state machine does not allow → the step is "skipped"
       {"send": "voice", "variant": "REMINDER"},   // real send to the visitor (bypasses LIVE_LIMIT, keeps DEMO_DAILY_LIMIT);
                                                    // "simulate": true = only recorded, "delivery": "failed" = not answered
       {"event": "booked", "result": "…"},          // a staff action (journey event, extra fields)
       {"reply": "Ano"},                            // a simulated answer through the real reply understanding
       {"tick": 7}, {"tick_until": ["paid", "…"], "max": 40},   // the demo clock (on_tick + contact plan)
       {"patch": {"verified": "{today}"}}           // store.patch of the persona ({today} = demo day)
     ],
     "wait": {"reply": true | ["link", "sms", "voice"], "stages": ["…"], "field": "verified"},  // any one met = "done"
     "timeout": 150,         // seconds of waiting (default 60), then:
     "fallback": {"reply": "Ano, mám zájem"},     // actions as in "do" → "simulated"; none → "noreply"
     "optional": true,       // nothing to answer, only to look at: a timeout without fallback is "done"
     // presentation (all optional; the web shell applies them once when the step starts):
     "view": "basket",       // switch to this view of case.json "views"
     "card": true,           // true = open the persona's card, false = close the card, "other" = the record of "who"
     "text": "…{who}…",      // a paragraph under the step once it ran ({who} = the record a "reply" with "who" acted on)
     "while_waiting": {"title": "…", "text": "…", "bullets": ["…"]}}   // shown while the step waits for a reply
  ]
}
```

A `reply` action may name another record: `{"reply": "Upadla jsem", "who": "other" | "<id>"}` acts on the first untouched
record of the persona's group whose stage allows "send" (or the given id); the record is kept in `scenario.others` and
reset by `POST /api/scenario/reset`. A live voice `send` keeps the Twilio call sid on the step: the wait ends at once when
the call is over without a conversation (no-answer, busy, failed, or completed with nothing said → `fallback`), the
`timeout` is suspended while the call rings, runs or is analysed (hard cap 300 s), and `/api/state` exposes the step's
`call` state (dialing | in_progress | analysing | over) and `who`. Replies made by the scenario or the demo panel are
recorded with via `"sim"` (timeline label `comm.via.sim`, core default "simulovaná odpověď"); staff entries stay `"ui"`.

A step without `do` and `wait` is an explanation shown for `after` seconds. Statuses: pending, active, waiting, done,
simulated, noreply, skipped. Texts in `messages.cs.json "scenario"`: `title, intro, facts[] (shown while it runs, e.g. the
verification value), start, next, reset, restart, openCard, openLink, unavailable, mock, finished, now, left ({s}),
status{…}, note{daily_limit, failed}, steps{id: {title, look}}`. No exclamation marks, no spaced dashes.
API: `POST /api/scenario/start | next | reset` (403 without a visitor session), progress in `/api/state` → `scenario`.

### Notices: `POST /api/notify`

`{"id", "channel": "sms" | "email", "variant", "date"?}` sends a message *about* a record that is not a check-in (e.g. the
relative's emergency SMS, the crisis lines): rendered from `messages.cs.json` without the personal link, to the signed-in
visitor's own contact like every send, within the daily budget, logged to the outbox with `notify: true` and the variant.
No state-machine guard, no journey event, the stage stays. 400 for an unknown channel or a variant the case has no text for.
The timeline titles such an item by `comm.variant[variant]` of the case i18n when present.

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
AGENT_TTS: dict = {"speed": 0.9, "voice_id": "…"}   # optional: merged into the ElevenLabs agent's tts config
                                   # (scripts/elevenlabs_agent.py --case x); default voice and speed 0.95 otherwise
DTMF: dict[str, str]               # key pressed in a call → words for RULES, e.g. {"1": "ano", "2": "teď ne"}
DECISIONS: set[str]                # ElevenLabs agent decision values (⊆ INTENTS, contains "unclear")
AGENT_NAME: str
AGENT_DECISIONS: dict[str, str]    # decision → description for the agent's data collection
AGENT_WHEN: str                    # description of data collection `preferred_time` (→ event `when`)
AGENT_DATA: dict[str, str]         # extra data collection fields → event `extra` ({} = none)
AGENT_SUMMARY: str                 # optional: description of data collection `summary` (core default in
                                   # scripts/elevenlabs_agent.py); core also adds `recap_confirmed` (ano / ne / empty)
def agent_prompt() -> str          # the whole agent prompt (only approved sentences); must contain CLOSING["handoff"];
                                   # ends with a recap step: say back what was collected, ask to confirm, take one correction
def recap(intent, extra) -> str    # optional: the recap said at the end of a scripted (gather) call, e.g.
                                   # "Rozuměla jsem, že potřebujete nákup a léky z lékárny. Je to tak?"; '' = none.
                                   # extra = understood extra (+ "when"). Never for VOICE_FINAL intents. Without it: no recap.
RECAP_FIX: str                     # optional: "Co mám opravit?" after "ne" (messages voice_ui.recap_fix overrides)
# features.hall only:
HALL_CLOSING: dict[str, str]; HALL_NOT_UNDERSTOOD: str; HALL_STATUS: dict[str, str]  # intent → card status
HALL_LINKS: dict = {"centres": "/centra", "info": "/prevence"}   # optional, SMS placeholders → paths
```

Core policy (`backend/replies.understand`, not overridable): rules first; `opt_out` from rules or AI always wins;
an AI answer with confidence ≠ high becomes `unclear` (→ a person); AI failures fall back to rules.
Recap (scripted call, `backend/app.py`): after the last answer, unless the intent is in `VOICE_FINAL`, the call says
`recap(intent, extra)` and listens once: 1 / "ano" = confirmed, 2 / "ne" = one more open answer ("Co mám opravit?"),
anything else said = the correction; silence or a hang-up records what we have. The reply event (and the call in the
outbox) get `summary` (the recap without its question) and `confirmed` (true / false, absent = not answered). Agent
calls (`backend/agent_call.py`) store the data collection `summary` (else ElevenLabs `transcript_summary`) and
`recap_confirmed` the same way. The web app shows them above "Celý rozhovor" (`core/components/comm.js recapLine`). The result is
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
    cycle_stages=frozenset(),        # optional: stages that close a contact cycle; the next send starts the ladder
                                     # again at step 0 (seniors: every answered daily check-in)
)

def adjust(touch: dict, journey: list, record: dict | None = None) -> dict | None   # optional, per touch from PLAN
```

`adjust` gets `{"due": date, "channel", "variant", "step"}` and returns it changed (another channel, a later `due`, an
extra `at` time label …) or `None` = no automatic touch (collections: channel opt-out, working days, weekly cap).
If it raises, the core logs it and plans no touch. With a third parameter it also gets the record (`None` when the caller
has none) and may return `{"skip": True}`: that step does not apply to this record and the ladder moves to the next one
(seniors: no relative → no RELATIVE SMS, the visit the same day). With skips the core walks the ladder from step 0 and
calls `adjust` for every step, so it must be cheap and side-effect free. Other cadence helpers (collections `allowed_at`, `is_contact_day`)
are case-internal; the core does not call them.

Algorithm (`backend/cadence.next_touch`, core): nothing until the first `sent_stage`; stops when the last stage is
terminal or a stop stage; the pause stage restarts the ladder after `pause_days` with `restart_variant`; never the
same channel three times in a row. A send is a journey event with the `sent_stage` reached by event `send`
(`backend.cadence.is_send`); a reply that keeps that stage (collections: `channel_opt_out` while `contacted`) is not
counted. `POST /api/tick` (demo clock) sends what is due.

## hooks.py **(checked)**

```python
def extra_placeholders(patient: dict, M: dict) -> dict[str, str]   # message placeholders from a record ({} ok)
def on_reply(pid: str, intent: str, extra: dict, store) -> None    # after every recorded reply (webhook, link, UI,
                                                                     # relay call, agent call); store = backend Store
# optional:
def on_tick(day: str, store, transition, patients: dict) -> list   # every demo day of POST /api/tick, before the
    # contact plan; transition(pid, event, day, **extra) = the core state machine; patients = records by id;
    # returns touches for the toast, e.g. [{"id", "channel": "system", "event"}] (collections: promises kept/broken)
def page(pid: str, record: dict, form: dict | None, store, day: str) -> dict   # replaces the core personal page
    # GET/POST /p/{token}; form = POSTed fields or None; returns {"html", "title"?, "reply"?: {"event", "intent",
    # "extra"?}}; a reply goes through transition + on_reply like any other answer (collections: identity check first)
```

`store` is always the store of the current demo session (each visitor has their own), never a global; keep no
per-session state in module globals. A hook that raises in `on_reply` / `on_tick` is logged and skipped (the reply
or the clock still goes through); `page` errors are a 500 of that page only.

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
(`POST /api/mark`): only `skipped`, `draft`, `override`, `resultAck` and the case's `case.json "marks"`.

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
- `tests/` (except `test_case_contract.py`, `test_case_live.py`, `test_recipient.py`, `test_sessions.py`,
  `test_password_landing.py`)
  is screening and runs only with `CASE=screening`.
