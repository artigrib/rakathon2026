"""Backend of the active case (CASE env, default screening = Plíce včas): serves the web app, sends messages
through Twilio, receives replies. Everything domain-specific comes from cases/<id>/ (backend/case.py).

  uvicorn backend.app:app --reload --port 8000        (from the project root)
  CASE=seniors uvicorn backend.app:app --port 8001

Without Twilio keys it runs in MOCK mode. With keys + PUBLIC_URL (ngrok) + DEMO_TO it sends for real."""
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace
from urllib.parse import quote
import json
import logging
import re
from datetime import timedelta

from . import agent_call, channels, ctx, fhir_sink, fsm, hall, messages, recipient, scenario, sessions, tts
from .case import CASE
from .channels import NO_ANSWER  # noqa: F401  (re-exported for tts warmup)
from .cadence import PLAN, next_touch
from .replies import understand
from .settings import settings
from .store import Store

_rlog = logging.getLogger("uvicorn.error")  # voice turns and agent outcomes in the container log (no phone numbers)

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "app"
app = FastAPI(title=CASE.manifest["title"])
REDIRECTS = CASE.manifest.get("redirects", {})  # public short links of the case, e.g. /centra
# case.json "login": {"email": "optional"}: the case sends nothing by e-mail, so the sign-in asks only for the phone
# (the login template may use $email_required = the input attribute and $email_hint = "nepovinný" or empty).
EMAIL_OPTIONAL = CASE.manifest.get("login", {}).get("email") == "optional"

OPEN = ("/twilio/", "/p/", "/audio/", "/ws/", "/api/health", "/projekt", "/img/", "/j/",
        "/internal/", "/landing/")  # Twilio, ElevenLabs and patients need these without a password; /internal/ checks INTERNAL_TOKEN
OPEN_EXACT = {"/", "/rakathon", "/rakathon/", "/demo.mp4", "/login", "/logout", *REDIRECTS}  # public pages (exact: "/" as a prefix would open everything)

# ---------- demo state per visitor ----------
# A signed-in visitor (/login: access code + own phone and e-mail) gets their own demo: their own patient journeys,
# outbox and demo clock, and every live message goes to their own contacts. Without a session (scripts with Basic
# auth, webhooks of the shared demo) the shared state is used, as before.
_default_store = Store(settings.state_file)
_stores: dict = {}
_current: ContextVar = ContextVar("store", default=None)


def _store_for(session_id: str) -> Store:
    if session_id not in _stores:
        path = Path(settings.state_file).with_name("sessions") / f"{session_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _stores[session_id] = Store(path)
    return _stores[session_id]


class _CurrentStore:
    """`store` in this module = the demo state of the current visitor, else the shared one."""
    def __getattr__(self, name):
        return getattr(_current.get() or _default_store, name)


store = _CurrentStore()


def _enter(token: str, sess: dict):
    """Run the rest of this request in the visitor's demo: their state, recipient and callback tag."""
    sid = sessions.sid(token)
    _current.set(_store_for(sid))
    ctx.session_id.set(sid)
    recipient.use({"phone": sess["phone"], "email": sess["email"], "token": token})


def _basic_ok(request: Request) -> bool:
    """Basic auth stays for scripts (auto-deploy FHIR sync, monitoring); browsers use /login."""
    import base64
    import secrets
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("basic "):
        return False
    try:
        user, _, pw = base64.b64decode(h[6:]).decode().partition(":")
        return secrets.compare_digest(user, settings.demo_user) and secrets.compare_digest(pw, settings.demo_password)
    except Exception:  # noqa: BLE001 – malformed header = not authorised
        return False


@app.middleware("http")
async def access(request: Request, call_next):
    """Who is this: a signed-in visitor (cookie), a Twilio callback / patient link of a visitor's demo (?s=…),
    a script with Basic auth, or nobody (→ /login). No browser password dialog any more."""
    path = request.url.path
    token = request.cookies.get(sessions.COOKIE)
    sess = sessions.get(token)
    if not sess and path.startswith(("/twilio/", "/p/")) and request.query_params.get("s"):
        token, sess = sessions.by_sid(request.query_params["s"])
    if sess:
        _enter(token, sess)
    if not settings.demo_password or sess or path in OPEN_EXACT or path.startswith(OPEN) or _basic_ok(request):
        return await call_next(request)
    if request.method == "GET" and not path.startswith("/api/"):
        return RedirectResponse("/login?next=" + quote(path))
    return JSONResponse({"detail": "Přihlášení vyžadováno"}, status_code=401)
PATIENTS: dict = {}
REF_DATE = CASE.manifest["ref_date"]


def load_patients():
    """The case data file (case.json "data"; screening: web/app/data/patients.json = engine output from CSV, or from
    the FHIR server after /api/fhir/sync). Missing file = no records yet (run `python -m cases.<id>.build`)."""
    global REF_DATE
    if not CASE.data.exists():
        _rlog.warning("data file %s missing: python -m cases.%s.build", CASE.data, CASE.id)
        PATIENTS.clear()
        return
    d = json.loads(CASE.data.read_text(encoding="utf-8"))
    PATIENTS.clear()
    PATIENTS.update({p["id"]: p for p in d["patients"]})
    REF_DATE = d.get("refDate") or CASE.manifest["ref_date"]


load_patients()


def record(pid: str) -> dict:
    """A record of the case data, or the guided demo's persona of the current visitor (scenario.py)."""
    return PATIENTS.get(pid) or store.data.get("personas", {}).get(pid) or {}


def records() -> dict:
    """Records by id incl. the current visitor's persona (case hooks.on_tick)."""
    personas = store.data.get("personas")
    return {**PATIENTS, **personas} if personas else PATIENTS


def today() -> str:
    """Demo clock: starts at the data's evaluation date; "Posunout čas o den" moves it forward."""
    return store.data.get("clock") or REF_DATE


def patient_link(pid: str) -> str:
    token = store.token(pid)  # created on first contact; the page works on any host
    return ctx.url(f"/p/{token}")  # tagged with the visitor's session, so the answer lands in their demo
VOICE_NO_DIGIT = messages.text("voice_ui.no_digit", "Děkujeme. Na shledanou.")
VOICE_THANKS = messages.M.get("voice_ui", {}).get("thanks", {})  # stage after the keys-1/2 answer → sentence


# ---------- API for the web app ----------
class SendItem(BaseModel):
    id: str
    channel: str
    variant: str = "FIRST_INVITE"
    text: str = ""


class SendRequest(BaseModel):
    items: list[SendItem]
    date: str | None = None


class StepRequest(BaseModel):
    id: str
    stage: str | None = None
    date: str | None = None
    result: str | None = None
    text: str | None = None
    sim: bool = False   # a simulated reply from the demo panel (via "sim"), not something an operator wrote down


class MarkRequest(BaseModel):
    id: str
    field: str
    value: object = None


MARKS = {"skipped", "draft", "override", "resultAck", *CASE.manifest.get("marks", [])}  # decisions that are not journey events (+ the case's own)


@app.post("/api/mark")
def mark(req: MarkRequest):
    """Nurse / doctor decisions kept on the server (not only in one browser): skip this week, edited invitation,
    inclusion override, doctor acknowledged a result."""
    if req.field not in MARKS:
        raise HTTPException(400, "unknown field")
    store.patch(req.id, **{req.field: req.value})
    return store.get(req.id)


@app.get("/api/case")
def case_manifest():
    """Manifest of the active case: the web app loads its modules, views, title and storage key from it."""
    return CASE.manifest


@app.get("/api/health")
def health():
    from . import llm
    return {"ok": True, "mode": "live" if settings.live else "mock", "liveLimit": settings.live_limit,
            "ai": llm.provider() if llm.enabled() else None, "voice": "elevenlabs" if tts.enabled() else "twilio",
            "trial": settings.live and settings.trial,
            "email": settings.email_live,
            "case": CASE.id,
            # how a call is held: gather = script + keys, relay = rules, agent = ElevenLabs voice agent (its first
            # sentence, so the web app shows what the agent really said instead of the keys-1/2 script)
            "voiceMode": settings.voice_mode,
            "agentGreeting": (getattr(CASE.dialog, "GREETING", None)
                              if settings.voice_mode == "agent" and agent_call.agent_id() else None),
            "fhir": ({"server": settings.fhir_base.split("//")[-1].split("/")[0], "sync": store.data.get("fhir_sync"),
                      "written": fhir_sink.state["sent"], "errors": fhir_sink.state["errors"], "lastError": fhir_sink.state["last_error"]}
                     if settings.fhir_base and CASE.feature("fhir") else None)}


@app.get("/audio/{name}")
def audio(name: str):
    """Generated call audio for Twilio <Play> (only cached files we created)."""
    from fastapi.responses import FileResponse
    path = tts.path_for(name)
    if not path:
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/state")
def state():
    if _scenario_ok():
        scenario.poll(store, OPS)  # the guided demo moves on while the visitor's app polls
    plans = {}
    for pid, d in store.decisions().items():
        n = next_touch(d.get("journey", []), record=record(pid) or None)
        if n:
            plans[pid] = {**n, "due": n["due"].isoformat()}
    # relative: works on any host; a visitor's link carries their session (?s=), so it opens in their demo (also from
    # another browser or phone); the shared demo keeps the bare link
    sid = ctx.session_id.get()
    links = {pid: f"/p/{t}" + (f"?s={sid}" if sid else "") for t, pid in store.data.get("tokens", {}).items()}
    out = {"version": store.version, "clock": today(), "decisions": store.decisions(), "plans": plans, "links": links,
           "scenario": scenario.public(store, _scenario_ok(), OPS)}
    if store.data.get("personas"):  # the guided demo's persona: a record only this visitor has
        out["personas"] = list(store.data["personas"].values())
    return out


@app.post("/api/send")
def send(req: SendRequest):
    """Approved invitations. The first `live_limit` go out for real (demo phone), the rest is simulated."""
    budget = [settings.live_limit if settings.live else 0]
    return {"sent": [_send(it.id, it.channel, it.variant, it.text, req.date or today(), budget) for it in req.items]}


def _send(pid, channel, variant, text, day, budget, auto=False, step=None, progress=False):
    """One outbound touch. budget[0] = how many may still go out for real in this request.
    progress: a live call also reports ringing / in progress (the guided demo shows them); otherwise only its end."""
    if not fsm.allowed(fsm.state_of(store.get(pid)), "send"):  # e.g. referred, refused, excluded: never contact
        return {"id": pid, "sid": None, "live": False, "status": "not_allowed"}
    text = messages.with_link(text, patient_link(pid), channel)
    real = ("sms", "voice", "whatsapp") + (("email",) if settings.email_live else ())
    live = budget[0] > 0 and channel in real
    if live and not recipient.take(recipient.email() if channel == "email" else recipient.phone(), day):
        return {"id": pid, "sid": None, "live": False, "status": "daily_limit"}   # guard: anyone with the code can set a number
    try:
        if channel == "voice":
            if live:  # generate the Czech audio before dialling, so the call starts without a pause
                tts.ensure(text.strip())
            r = channels.start_call(pid, live, progress=progress)
        elif channel == "whatsapp":
            r = channels.send_whatsapp(text, live)
        elif channel == "email":
            r = channels.send_email(text, live)
        else:
            r = channels.send_sms(text, live)
    except Exception as e:  # a failed send is a delivery fact, not a crash
        r = {"sid": None, "live": live, "to": recipient.email() if channel == "email" else recipient.phone(),
             "status": "failed", "error": str(e)}
    budget[0] -= int(r["live"])
    store.log(patient=pid, channel=channel, text=text, day=day, variant=variant, auto=auto, step=step, **r)
    extra = {"auto": True, "step": step} if auto else {}
    transition(pid, "send", day, channel=channel, variant=variant, live=r["live"], **extra)
    return {"id": pid, **r}


class NotifyRequest(BaseModel):
    id: str
    channel: str = "sms"
    variant: str
    date: str | None = None


@app.post("/api/notify")
def notify(req: NotifyRequest):
    """A notice about a patient (seniors: the relative's emergency SMS, the crisis lines for the senior), not a check-in:
    no `send` guard of the state machine, no journey event, no transition. The text is a messages.cs.json variant of the
    channel, rendered without the personal reply link; recipient, live limit and the daily budget as for every send.
    Only the outbox keeps it (store.log bumps the version, so polling clients refresh their timeline)."""
    if req.channel not in ("sms", "email"):
        raise HTTPException(400, "unknown channel")
    kind = messages.M["channel_template"].get(req.channel, "email")
    if req.variant not in (messages.M.get(kind) or {}):
        raise HTTPException(400, "unknown variant")
    text = messages.render(record(req.id), req.channel, req.variant)
    day = req.date or today()
    to = recipient.email() if req.channel == "email" else recipient.phone()
    live = bool(settings.live and settings.live_limit > 0 and (req.channel != "email" or settings.email_live))
    if live and not recipient.take(to, day):
        return {"id": req.id, "sid": None, "live": False, "status": "daily_limit"}
    try:
        r = channels.send_email(text, live) if req.channel == "email" else channels.send_sms(text, live)
    except Exception as e:  # a failed send is a delivery fact, not a crash
        r = {"sid": None, "live": live, "to": to, "status": "failed", "error": str(e)}
    store.log(patient=req.id, channel=req.channel, text=text, day=day, variant=req.variant, notify=True, **r)
    return {"id": req.id, **r}


class RecipientRequest(BaseModel):
    phone: str = ""
    email: str = ""


@app.get("/api/recipient")
def get_recipient():
    """Where live demo messages go (default recipient masked)."""
    return recipient.public()


@app.post("/api/recipient")
def set_recipient(req: RecipientRequest):
    """Presenter sets the test phone and e-mail in the demo panel; empty = default from .env."""
    try:
        return recipient.save(req.phone, req.email)
    except ValueError as e:
        raise HTTPException(400, str(e))


class TickRequest(BaseModel):
    days: int = 1


ON_TICK = getattr(CASE.hooks, "on_tick", None)  # optional case hook: daily duties before the contact plan


@app.post("/api/tick")
def tick(req: TickRequest):
    """Advance the demo clock and run every automatic touch that is due (what a cron does every 15 min)."""
    budget = [settings.live_limit if settings.live and settings.tick_live else 0]
    done = []
    for _ in range(max(1, req.days)):
        day = (date.fromisoformat(today()) + timedelta(days=1)).isoformat()
        store.data["clock"] = day
        if ON_TICK:  # e.g. collections: a promise to pay was kept or broken (journey events through transition)
            try:
                done += ON_TICK(day, store, transition, records()) or []
            except Exception:  # a broken case hook must not stop the clock or the contact plan
                _rlog.exception("case hooks.on_tick failed on %s", day)
        for pid, d in list(store.decisions().items()):
            n = next_touch(d.get("journey", []), record=record(pid) or None)
            if not n or n["due"].isoformat() > day:
                continue
            if n["channel"] == PLAN.human:  # the plan hands over to a person (screening: the nurse calls)
                transition(pid, PLAN.human, day, auto=True, step=n["step"])
                done.append({"id": pid, "channel": PLAN.human})
                continue
            text = messages.render(record(pid), n["channel"], n["variant"], patient_link(pid))
            done.append(_send(pid, n["channel"], n["variant"], text, day, budget, auto=True, step=n["step"]))
    store._save()
    return {"clock": today(), "touches": done}


@app.post("/api/step")
def step(req: StepRequest):
    """Nurse action or simulated patient reply from the UI (same path as a real webhook)."""
    if req.text is not None:
        return _apply_reply(req.id, req.text, "sim" if req.sim else "ui", req.date or today())
    extra = {"result": req.result} if req.result else {}
    # Nurse or doctor action = an event of the state machine (first "declined" is soft, see journey.json).
    return transition(req.id, req.stage, req.date or today(), via="ui", **extra)


@app.get("/api/patient/{pid}")
def patient_messages(pid: str):
    """Everything we sent to one patient, for the communication timeline. No phone number, no link token."""
    keep = ("day", "ts", "channel", "text", "live", "status", "error", "auto", "step", "variant", "duration", "analysing",
            "transcript")
    out = []
    for m in store.data["outbox"]:
        if m.get("patient") != pid:
            continue
        item = {k: m.get(k) for k in keep if m.get(k) is not None}
        if "text" in item:
            item["text"] = re.sub(r"/p/[A-Za-z0-9_-]+(\?s=[A-Za-z0-9_-]+)?", "/p/…", item["text"])
        if "error" in item:
            item["error"] = str(item["error"])[:120]
        out.append(item)
    return {"outbox": out}


def fhir_sync():
    """Load the practice's patients from the FHIR server (IRIS) and evaluate them with the same engine."""
    if not settings.fhir_base:
        raise HTTPException(400, "FHIR_BASE is not set")
    from engine.webdata import build
    from .fhir_source import fetch, tables_from, write
    res = fetch(settings.fhir_base, settings.fhir_user, settings.fhir_password)
    t = tables_from(res)
    out = build(write(t, ROOT / "data_fhir"), REF_DATE)
    if not out["patients"]:  # an empty or unreachable server must not wipe the practice's patient list
        raise HTTPException(409, f"FHIR server returned no patients ({len(res)} resources); run /api/fhir/push first")
    CASE.data.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    load_patients()
    info = {"at": datetime_now(), "resources": len(res), "patients": len(out["patients"])}
    store.data["fhir_sync"] = info
    store._save()
    return info


def fhir_push():
    """Upload the whole practice data + evaluation + journey to the FHIR server as one transaction Bundle."""
    if not settings.fhir_base:
        raise HTTPException(400, "FHIR_BASE is not set")
    import base64
    import urllib.request
    from .fhir import bundle
    b = bundle(ROOT / "data", REF_DATE, store.decisions())
    req = urllib.request.Request(settings.fhir_base, data=json.dumps(b).encode(), method="POST",
                                 headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"})  # IRIS: 406 without Accept
    if settings.fhir_user:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{settings.fhir_user}:{settings.fhir_password}".encode()).decode())
    with urllib.request.urlopen(req, timeout=120) as r:
        return {"status": r.status, "entries": len(b["entry"])}


def datetime_now():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/Prague")).strftime("%Y-%m-%d %H:%M")


def fhir_bundle(gp: str | None = None):
    """FHIR R4 transaction Bundle (patients, smoking, CT, contacts, evaluation, tasks) – POST it to any FHIR server."""
    from .fhir import bundle
    return bundle(ROOT / "data", REF_DATE, store.decisions(), gp)


if CASE.feature("fhir"):  # screening: the practice's patients live on an IRIS FHIR server
    app.post("/api/fhir/sync")(fhir_sync)
    app.post("/api/fhir/push")(fhir_push)
    app.get("/api/fhir")(fhir_bundle)


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}


# ---------- guided demo: the whole case on the visitor's own phone (backend/scenario.py, cases/<id>/scenario.json) ----------
def _scenario_ok() -> bool:
    """Only for a signed-in visitor with own contacts: never the shared demo or the default DEMO_TO."""
    v = recipient.visitor()
    return bool(scenario.SPEC and _current.get() is not None and v and v.get("phone") and (v.get("email") or EMAIL_OPTIONAL))


def _scenario_send(pid, channel, variant, live=True, delivery=None):
    """A step's send. Bypasses LIVE_LIMIT (one real message per step), still only to the visitor's own contacts and
    within DEMO_DAILY_LIMIT (_send → recipient.take). A live call reports its progress (ringing, in progress)."""
    real = settings.email_live if channel == "email" else settings.live
    budget = [1 if live and real and _scenario_ok() else 0]
    day = today()
    text = messages.render(record(pid), channel, variant, patient_link(pid))
    r = _send(pid, channel, variant, text, day, budget, progress=True)
    if delivery and r.get("status") != "not_allowed":  # e.g. seniors: the check-in call was not answered
        store.event(pid, None, day, delivery=delivery, channel=channel, note="no-answer", simulated=True)
    return r


def _scenario_other(persona_id: str, who) -> str | None:
    """Another record of the visitor's set for a step's reply ({"who": "<id>" | "other"}): that record, or the first
    record of the persona's group that nothing happened to yet and whose registry stage still allows contact."""
    if who != "other":
        return who if who in PATIENTS else _scenario_other(persona_id, "other")  # the id is not in this data: pick one
    g = CASE.manifest.get("group")
    group = record(persona_id).get(g["field"]) if g else None
    for p in PATIENTS.values():
        if g and p.get(g["field"]) != group or store.get(p["id"]).get("journey"):
            continue
        if p.get("stage") and not fsm.allowed(p["stage"], "send"):  # e.g. escalated, paused, declined in the registry
            continue
        return p["id"]
    return None


OPS = SimpleNamespace(
    send=_scenario_send,
    allowed=lambda pid, ev: fsm.next_state(fsm.state_of(store.get(pid)), ev, _refusals(pid)) is not None,
    event=lambda pid, ev, **extra: transition(pid, ev, today(), via="ui", scenario=True, **extra),
    reply=lambda pid, text: _apply_reply(pid, text, "sim"),   # a simulated answer, not one an operator wrote down
    tick=lambda days: tick(TickRequest(days=days)),
    patch=lambda pid, fields: store.patch(pid, **fields),
    stage=lambda pid: fsm.state_of(store.get(pid)),
    today=lambda: today(),
    other=_scenario_other,
    call=lambda sid: next((m for m in store.data["outbox"] if m.get("sid") == sid), None),  # the step's live call
)


def _need_scenario():
    if not scenario.SPEC:
        raise HTTPException(404, "Tento případ nemá řízenou ukázku.")
    if not _scenario_ok():
        raise HTTPException(403, "Celá ukázka běží jen po přihlášení s vlastním telefonem a e-mailem.")


@app.post("/api/scenario/start")
def scenario_start():
    _need_scenario()
    scenario.start(store, recipient.visitor(), OPS)
    return state()


@app.post("/api/scenario/next")
def scenario_next():
    """"Další krok": start the waiting step now, or give up waiting and run its fallback."""
    _need_scenario()
    scenario.poll(store, OPS, force=True)
    return state()


@app.post("/api/scenario/reset")
def scenario_reset():
    _need_scenario()
    scenario.reset(store)
    return state()


# ---------- Twilio webhooks ----------
async def _form(request: Request) -> dict:
    form = dict(await request.form())
    # Signatures are signed with the Auth Token; with only an API key there is nothing to check against.
    if settings.live and settings.validate_signature and settings.auth_token:
        from twilio.request_validator import RequestValidator
        url = settings.public_url + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not RequestValidator(settings.auth_token).validate(url, form, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "invalid Twilio signature")
    return form


def _refusals(pid):
    return sum(1 for e in store.get(pid).get("journey", [])
               if e.get("intent") in ("declined", "opt_out") and not e.get("ignored"))


def transition(pid, event, day=None, **extra):
    """The only way a patient's stage changes: through the state machine in content/journey.json.
    An event that is not allowed in the current stage is kept in the history but changes nothing."""
    day = day or today()
    state = fsm.state_of(store.get(pid))
    target = fsm.next_state(state, event, _refusals(pid))
    if target is None:
        return store.event(pid, None, day, event=event, ignored=True, **extra)
    if event in ("declined", "opt_out"):
        extra.setdefault("intent", event)
    d = store.event(pid, target, day, event=event, **extra)
    if _current.get() is None and CASE.feature("fhir"):  # only the shared demo writes back; visitors' demos would overwrite each other in IRIS
        fhir_sink.push(settings, pid, event, d, PATIENTS.get(pid, {}).get("gp"))  # write-back to the FHIR server, async
    return d


def _on_reply(pid, intent, extra):
    """Case side effects after a recorded reply. The reply is already in the journey, so a failing hook is logged
    and the webhook still answers (Twilio would otherwise retry and record the reply twice)."""
    try:
        CASE.hooks.on_reply(pid, intent, extra, store)
    except Exception:
        _rlog.exception("case hooks.on_reply failed (%s)", intent)


def _record_reply(pid, text, understood, via, day=None, transcript=None, summary=None, confirmed=None):
    """transcript: the whole call as turns [{who: bot|user, text, …}] (shown as a dialogue in the timeline);
    summary: what the call agreed / collected (the recap), confirmed: did the person confirm it (None = not asked)."""
    c = understood
    d = transition(pid, fsm.INTENT_EVENT.get(c["intent"], "callback"), day, via=via, text=text, intent=c["intent"],
                   why=c["why"], source=c.get("source", "rules"), **({"when": c["when"]} if c.get("when") else {}),
                   **({"extra": c["extra"]} if c.get("extra") else {}), **({"transcript": transcript} if transcript else {}),
                   **({"summary": summary} if summary else {}), **({"confirmed": confirmed} if confirmed is not None else {}))
    _on_reply(pid, c["intent"], c.get("extra") or {})  # case side effects (needs basket, promise to pay …)
    return d


def _apply_reply(pid, text, via, day=None):
    return _record_reply(pid, text, understand(text), via, day)


@app.post("/twilio/sms")
async def inbound_sms(request: Request):
    return await _inbound_sms(await _form(request), forward=True)


async def _inbound_sms(form: dict, forward: bool):
    sender = form.get("From") or ""
    via = "whatsapp" if sender.startswith("whatsapp:") else "sms"  # SMS and WhatsApp share this webhook
    hall_reply = hall.inbound(sender.replace("whatsapp:", ""), form.get("Body", "")) if via == "sms" and HALL else None
    if hall_reply is not None:  # someone from the hall demo answered the SMS after a missed call
        body = f"<Message>{escape(hall_reply)}</Message>" if hall_reply else ""
        return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")
    if forward and FORWARD and _current.get() is None:  # the visitor's latest demo may run in another case container
        fwd = await asyncio.to_thread(_forward_sms, form)
        if fwd is not None:
            return fwd
    if _current.get() is None:  # a reply from a visitor's phone belongs to their demo
        token, sess = sessions.by_phone(sender.replace("whatsapp:", ""))
        if sess:
            _enter(token, sess)
    pid = store.last_contacted(sender.replace("whatsapp:", ""), via)
    reply = ""
    if pid:
        d = _apply_reply(pid, form.get("Body", ""), via)
        last = d["journey"][-1]
        reply = "" if last.get("ignored") else messages.sms_reply(last.get("intent"), d["stage"])
    body = f"<Message>{escape(reply)}</Message>" if reply else ""
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


# ---------- one Twilio number for every case: inbound SMS forwarded between case containers ----------
FORWARD = [u.strip().rstrip("/") for u in settings.sms_forward.split(",") if u.strip()]
INTERNAL_HEADER = "X-Internal-Token"


def _internal_ok(request: Request) -> bool:
    import secrets
    tok = request.headers.get(INTERNAL_HEADER, "")
    return bool(settings.internal_token) and secrets.compare_digest(tok, settings.internal_token)


def _ts(s: str) -> float:
    """Outbox "ts" (Europe/Prague, minutes) → epoch seconds; 0 when unknown."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Prague")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def phone_activity(phone: str) -> float:
    """When this phone was last active in this container: the latest visitor session signed in with it, or the latest
    live message its demo sent to it (epoch seconds; 0 = no session here)."""
    token, sess = sessions.by_phone(phone)
    if not sess:
        return 0.0
    st = _store_for(sessions.sid(token))
    sent = [_ts(m.get("ts")) for m in st.data["outbox"] if m.get("to") == phone and m.get("live")]
    return max([sess.get("created", 0), *sent])


def _forward_sms(form: dict):
    """The case container whose demo this phone used most recently gets the SMS (this one wins ties and errors).
    Returns its TwiML response, or None = handle it here."""
    import urllib.parse
    import urllib.request
    phone = (form.get("From") or "").replace("whatsapp:", "")
    best, when = None, phone_activity(phone)
    hdr = {INTERNAL_HEADER: settings.internal_token}
    for base in FORWARD:
        try:
            req = urllib.request.Request(f"{base}/internal/has-phone?" + urllib.parse.urlencode({"phone": phone}), headers=hdr)
            with urllib.request.urlopen(req, timeout=3) as r:
                a = float(json.loads(r.read()).get("active") or 0)
        except Exception as e:  # noqa: BLE001 – a case container that is down must not lose the reply here
            _rlog.warning("sms forward: %s unreachable: %s", base, str(e)[:120])
            continue
        if a > when:
            best, when = base, a
    if not best:
        return None
    try:
        req = urllib.request.Request(f"{best}/internal/sms", data=urllib.parse.urlencode(form).encode(), method="POST",
                                     headers={**hdr, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            _rlog.info("sms forwarded to %s", best)
            return Response(r.read(), media_type="application/xml")
    except Exception as e:  # noqa: BLE001
        _rlog.warning("sms forward to %s failed: %s", best, str(e)[:120])
        return None


@app.get("/internal/has-phone")
def internal_has_phone(phone: str, request: Request):
    if not _internal_ok(request):
        raise HTTPException(403)
    a = phone_activity(phone)
    return {"session": a > 0, "active": a}


@app.post("/internal/sms")
async def internal_sms(request: Request):
    """An inbound SMS forwarded by the container that owns the Twilio webhook (it checked Twilio's signature)."""
    if not _internal_ok(request):
        raise HTTPException(403)
    return await _inbound_sms(dict(await request.form()), forward=False)


@app.post("/twilio/status")
async def sms_status(request: Request):
    form = await _form(request)
    m = store.outbox_update(form.get("MessageSid"), status=form.get("MessageStatus"))
    if m and form.get("MessageStatus") in ("delivered", "failed", "undelivered"):
        store.event(m["patient"], None, today(), delivery=form["MessageStatus"], channel=m.get("channel") or "sms")  # SMS and WhatsApp share this callback
    return Response(status_code=204)


@app.post("/twilio/voice/{pid}")
async def voice(pid: str, request: Request):
    form = await _form(request)
    if settings.voice_mode == "agent" and agent_call.agent_id():
        try:  # outbound call: Twilio's From is our number, To is the patient
            twiml = await asyncio.to_thread(agent_call.register, pid, form.get("From", ""), form.get("To", ""))
            return Response(twiml, media_type="application/xml")
        except Exception as e:  # noqa: BLE001 – agent unreachable: fall back to the scripted call below
            _rlog.warning("agent %s register failed, scripted call instead: %s", pid, str(e)[:200])
    if settings.voice_mode == "relay" and settings.public_url:
        from .voice_ai import GREETING
        ws = settings.public_url.replace("https://", "wss://").replace("http://", "ws://") + f"/ws/relay/{pid}"
        return Response(channels.relay_twiml(ws, GREETING), media_type="application/xml")
    script = next((m["text"] for m in reversed(store.data["outbox"]) if m["patient"] == pid and m["channel"] == "voice"), "")
    _CALLS[_call_key(pid, form)] = {"pid": pid, "turns": [{"who": "bot", "text": (script or VOICE_NO_DIGIT).strip()}], "said": [], "keys": []}
    return Response(channels.voice_twiml(pid, script or VOICE_NO_DIGIT), media_type="application/xml")


# ---------- scripted call (gather): up to MAX_TURNS answers, one reply recorded at the end ----------
_CALLS: dict = {}  # CallSid (or pid without one) → {pid, turns, said, keys}; lives for one call
MAX_TURNS = 3
VOICE_FOLLOW_UP = messages.text("voice_ui.follow_up", "Potřebujete ještě něco?")
# an answer after which we do not ask anything more (a person takes over, or the conversation must stop)
VOICE_FINAL = set(getattr(CASE.dialog, "VOICE_FINAL", {"opt_out", "emergency", "health_problem", "declined", "callback", "question",
                                                        "unclear", "wrong_person", "channel_opt_out", "vulnerable", "dispute"}))
_NOTHING_MORE = re.compile(r"^(ne|nic|uz nic|nic dalsiho|nic jineho|to je vse|to je vsechno|to staci|ne dekuji|ne diky|dekuji ne|"
                           r"ne nic|ne nepotrebuji|nepotrebuji|nepotrebuju|ne nepotrebuju|ne to je vse|ne to je vsechno)( dekuji| diky)?$")


# recap at the end of a scripted call (optional case hook dialog.recap(intent, extra) -> str, '' = none)
RECAP = getattr(CASE.dialog, "recap", None)
VOICE_RECAP_FIX = messages.text("voice_ui.recap_fix", getattr(CASE.dialog, "RECAP_FIX", "Co mám opravit?"))
_YES = re.compile(r"^(ano|jo|jj|jojo|presne|spravne|souhlasi|je to tak|tak je|to je tak|ok|dobre)\b")
_NO = re.compile(r"^(ne|nee|neni|to neni|to neni tak|nesouhlasi|spatne|nespravne)\b")


def _call_key(pid, form) -> str:
    return form.get("CallSid") or f"pid:{pid}"


def _plain(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def _understood(call) -> dict:
    """Everything the person said in this call, understood at once (cached per number of answers)."""
    if call.get("u_n") != len(call["said"]):
        call["u"], call["u_n"] = understand(". ".join(call["said"])), len(call["said"])
    return call["u"]


def _recap_of(call) -> str:
    """The case's recap of what this call collected (dialog.recap), '' = none (no hook, a final intent, nothing to say)."""
    if RECAP is None or not call["said"]:
        return ""
    u = _understood(call)
    if u["intent"] in VOICE_FINAL:
        return ""
    try:
        return (RECAP(u["intent"], {**(u.get("extra") or {}), **({"when": u["when"]} if u.get("when") else {})}) or "").strip()
    except Exception:  # noqa: BLE001 – a recap is a nicety, the call goes on without it
        _rlog.exception("case dialog.recap failed")
        return ""


def _summary(recap: str) -> str:
    """The recap without its closing question ("… nákup a léky. Je to tak?" → "… nákup a léky.")."""
    return re.sub(r"\s*[^.?]*\?\s*$", "", recap).strip()


def _finish_call(key: str):
    """Record the call's answers as one reply (whole conversation understood at once). None = nothing was said."""
    call = _CALLS.pop(key, None)
    if not call or not call["said"]:
        return None
    pid = call["pid"]
    turns = call["turns"]
    confirmed = call.get("confirmed")
    summary = None
    if "recap" in call:  # after a correction: the corrected understanding (none when it became e.g. a handoff)
        summary = _summary(call["recap"] if confirmed is not False else _recap_of(call)) or None
    d = _record_reply(pid, " | ".join(call["keys"]), _understood(call), "voice", transcript=turns,
                      summary=summary, confirmed=confirmed)
    thanks = VOICE_THANKS.get(d["stage"], VOICE_NO_DIGIT)
    turns.append({"who": "bot", "text": thanks})  # the closing sentence depends on the stage the reply led to
    store.patch(pid)  # saves the journey event that holds `turns`
    if not key.startswith("pid:"):
        store.outbox_update(key, transcript=turns, **({"summary": d["summary"]} if d.get("summary") else {}),
                            **({"confirmed": confirmed} if confirmed is not None else {}))
    return thanks


def _recap_answer(key: str, call: dict, step: int, digits: str, speech: str, end: int):
    """The answer to the recap question (step 1: yes / no / a correction) or to "what should I correct?" (step 2).
    "ne" alone → one more open answer; anything else said is taken as the correction. Then the call is recorded."""
    p = _plain(speech)
    if step == 1 and not end and (digits or speech):
        if digits == "1" or (not digits and _YES.match(p)):
            call["confirmed"] = True
        elif digits == "2" or (not digits and _NO.match(p)):
            call["confirmed"] = False
            rest = _NO.sub("", p).strip() if speech else ""
            if len(rest.split()) >= 2:  # "ne, potřebuju jen léky": the correction is already here
                call["said"].append(speech)
                call["keys"].append(speech)
            else:
                call["turns"].append({"who": "bot", "text": VOICE_RECAP_FIX})
                if not key.startswith("pid:"):
                    store.outbox_update(key, transcript=call["turns"])
                return channels.ask_twiml(call["pid"], VOICE_RECAP_FIX, recap=2)
        elif speech:  # neither yes nor no: what they said is the correction (another key: not answered)
            call["confirmed"] = False
            call["said"].append(speech)
            call["keys"].append(speech)
    elif step == 2 and speech and not end:
        call["said"].append(speech)
        call["keys"].append(speech)
    return channels.twiml_say(_finish_call(key) or VOICE_NO_DIGIT)


@app.post("/twilio/voice/{pid}/answer")
async def voice_answer(pid: str, request: Request, n: int = 1, end: int = 0, recap: int = 0):
    form = await _form(request)
    key = _call_key(pid, form)
    if recap and key not in _CALLS:  # the call was already recorded (hung up): nothing more to do
        return Response(channels.twiml_say(VOICE_NO_DIGIT), media_type="application/xml")
    call = _CALLS.setdefault(key, {"pid": pid, "turns": [], "said": [], "keys": []})
    digits, speech = form.get("Digits") or "", (form.get("SpeechResult") or "").strip()
    said = digits or speech
    more = bool(said)
    if said:
        conf = form.get("Confidence")
        call["turns"].append({"who": "user", "text": said, **({"dtmf": True} if digits else {}),
                              **({"confidence": conf} if conf and not digits else {})})
    if recap:
        _rlog.info("voice %s recap %s %s", pid, recap, "keys" if digits else "speech" if speech else "silence")
        return Response(_recap_answer(key, call, recap, digits, speech, end), media_type="application/xml")
    if said:
        if n > 1 and _NOTHING_MORE.match(_plain(said) or ""):
            more = False  # "ne, nic" to "anything else?": nothing new to understand
        else:
            call["said"].append(CASE.dialog.DTMF.get(digits, digits) if digits else speech)
            call["keys"].append(said)
    _rlog.info("voice %s turn %s %s", pid, n, "keys" if digits else "speech" if speech else "silence")
    if not call["said"]:  # silence, or only "nothing more"
        _CALLS.pop(key, None)
        return Response(channels.twiml_say(VOICE_NO_DIGIT), media_type="application/xml")
    if more and not end and not digits and n < MAX_TURNS and _understood(call)["intent"] not in VOICE_FINAL:
        call["turns"].append({"who": "bot", "text": VOICE_FOLLOW_UP})
        if not key.startswith("pid:"):
            store.outbox_update(key, transcript=call["turns"])
        return Response(channels.followup_twiml(pid, VOICE_FOLLOW_UP, n + 1), media_type="application/xml")
    rc = _recap_of(call)
    if rc:  # say back what we understood and ask to confirm (1 / ano, 2 / ne)
        call["recap"] = rc
        call["turns"].append({"who": "bot", "text": rc})
        if not key.startswith("pid:"):
            store.outbox_update(key, transcript=call["turns"])
        return Response(channels.ask_twiml(pid, rc, recap=1), media_type="application/xml")
    thanks = _finish_call(key)
    return Response(channels.twiml_say(thanks or VOICE_NO_DIGIT), media_type="application/xml")


@app.websocket("/ws/relay/{pid}")
async def relay(ws: WebSocket, pid: str):
    """ConversationRelay: Twilio sends what the patient said, we answer with approved sentences."""
    from .voice_ai import GREETING, Conversation
    await ws.accept()
    _rlog.info("relay %s open", pid)
    conv = Conversation()
    turns = [{"who": "bot", "text": GREETING}]  # the whole conversation, stored with the reply and the call
    call_sid = ""
    try:
        while True:
            msg = await ws.receive_json()
            _rlog.info("relay %s in %s %s", pid, msg.get("type"),
                       {k: msg.get(k) for k in ("voicePrompt", "last", "digit", "utteranceUntilInterrupt", "durationUntilInterruptMs", "description") if k in msg})
            if msg.get("type") == "setup":
                call_sid = msg.get("callSid") or ""
            if msg.get("type") == "dtmf":
                msg = {"type": "prompt", "voicePrompt": CASE.dialog.DTMF.get(msg.get("digit"), "")}
            if msg.get("type") != "prompt":
                continue
            said = msg.get("voicePrompt", "")
            understood = understand(said)
            reply, done, intent = conv.feed(said, understood)
            turns += [{"who": "user", "text": said}, {"who": "bot", "text": reply}]
            if intent:
                _record_reply(pid, said, {**understood, "intent": intent}, "voice-ai", transcript=turns)
            if call_sid:
                store.outbox_update(call_sid, transcript=turns)
            _rlog.info("relay %s out intent=%s done=%s %r", pid, intent, done, reply)
            await ws.send_json({"type": "text", "token": reply, "last": True})
            if done:
                await ws.send_json({"type": "end"})
                break
    except WebSocketDisconnect:
        pass


@app.post("/twilio/call-status/{pid}")
async def call_status(pid: str, request: Request):
    form = await _form(request)
    st = form.get("CallStatus")
    store.outbox_update(form.get("CallSid"), status=st, duration=form.get("CallDuration"))
    if st in ("no-answer", "busy", "failed"):
        store.event(pid, None, today(), delivery="failed", channel="voice", note=st)
    if st == "completed" and form.get("CallSid") in _CALLS:  # hung up during a follow-up: keep what was said
        _finish_call(form["CallSid"])
    if st == "in-progress" and settings.voice_mode == "agent" and agent_call.agent_id() and form.get("CallSid"):
        asyncio.get_running_loop().create_task(_agent_live(pid, form["CallSid"]))  # a task: keeps the visitor's store
    if st == "completed" and settings.voice_mode == "agent" and agent_call.agent_id():
        store.outbox_update(form.get("CallSid"), analysing=True)  # the outcome is being read from ElevenLabs
        asyncio.get_running_loop().create_task(_agent_outcome(pid, form.get("CallSid", "")))
    return Response(status_code=204)


CALL_FINAL = ("completed", "no-answer", "busy", "failed", "canceled")
_LIVE: set = set()  # call sids whose agent conversation is being followed


def _call_over(call_sid: str) -> bool:
    m = next((x for x in store.data["outbox"] if x.get("sid") == call_sid), None)
    return not m or m.get("status") in CALL_FINAL


async def _agent_live(pid: str, call_sid: str):
    """While an agent call runs: find its ElevenLabs conversation (once, then by id) and keep the outbox entry's
    `transcript` current, so the card shows the conversation as it happens. Stops when the call is over; quiet on errors.
    Started as an asyncio task from the request, so it writes into the same visitor's store."""
    if call_sid in _LIVE:
        return
    _LIVE.add(call_sid)
    loop = asyncio.get_running_loop()
    try:
        start = loop.time()
        conv = None
        while not conv:
            if _call_over(call_sid):
                return
            conv = await asyncio.to_thread(agent_call._find, call_sid)
            if conv:
                break
            if loop.time() - start >= agent_call.LIVE_FIND_S:
                return
            await asyncio.sleep(agent_call.LIVE_STEP_S)
        cid = conv.get("conversation_id")
        if not cid:
            return
        store.outbox_update(call_sid, conversation_id=cid)  # _agent_outcome reads it directly instead of searching again
        start, last = loop.time(), None
        while True:
            if _call_over(call_sid):  # the outcome (full transcript) takes over
                return
            tr = agent_call.turns(conv)
            if tr and tr != last:
                store.outbox_update(call_sid, transcript=tr)
                last = tr
            if loop.time() - start >= agent_call.LIVE_MAX_S:
                return
            await asyncio.sleep(agent_call.LIVE_STEP_S)
            if _call_over(call_sid):
                return
            conv = await asyncio.to_thread(agent_call.get, cid)
    except Exception as e:  # noqa: BLE001 – live view only; the outcome after the call is what counts
        _rlog.info("agent %s live transcript stopped: %s", pid, type(e).__name__)
    finally:
        _LIVE.discard(call_sid)


async def _agent_outcome(pid: str, call_sid: str):
    """After an agent call: its decision → the same journey event as a reply (state machine, FHIR write-back).
    The outbox entry says `analysing` meanwhile; `outcome: "none"` when no conversation was found."""
    try:
        m = next((x for x in store.data["outbox"] if x.get("sid") == call_sid), None)
        cid = (m or {}).get("conversation_id") or ""  # found during the call by _agent_live
        o = await asyncio.to_thread(agent_call.outcome, call_sid, **({"conversation_id": cid} if cid else {}))
    finally:
        store.outbox_update(call_sid, analysing=False)
    _rlog.info("agent %s outcome %s", pid, {k: v for k, v in (o or {}).items() if k != "text"})
    if not o:
        store.outbox_update(call_sid, outcome="none")
        return
    _record_reply(pid, o["text"], {"intent": o["intent"], "why": f"hlasový asistent: {o['intent']}", "source": "elevenlabs-agent",
                                   **({"when": o["when"]} if o["when"] else {}), **({"extra": o["extra"]} if o.get("extra") else {})},
                  "voice-agent", transcript=o.get("transcript"), summary=o.get("summary"), confirmed=o.get("confirmed"))
    if o.get("transcript") or o.get("summary"):
        store.outbox_update(call_sid, transcript=o.get("transcript") or [], conversation_id=o.get("conversation_id"),
                            **({"summary": o["summary"]} if o.get("summary") else {}),
                            **({"confirmed": o["confirmed"]} if o.get("confirmed") is not None else {}))


# ---------- patient page (personal link from SMS / e-mail) ----------
from string import Template  # noqa: E402

from fastapi import Form  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

PAGE = Template((Path(__file__).with_name("templates") / "patient.html").read_text(encoding="utf-8"))
P = messages.M["page"]  # texts of the personal page (case messages.cs.json); no health data is ever shown on it
# answer → (journey event, intent, thank-you text)
ANSWERS = {a["value"]: (a["event"], a["intent"], a["thanks"]) for a in P["answers"]}


def _page(html: str) -> HTMLResponse:
    body = PAGE.substitute(content=html)
    if P.get("title"):  # the template's <title> is screening's
        body = re.sub(r"<title>.*?</title>", f"<title>{escape(P['title'])}</title>", body, count=1)
    return HTMLResponse(body)


PAGE_HOOK = getattr(CASE.hooks, "page", None)  # optional: the case renders its own personal page (collections: verification first)
if PAGE_HOOK:
    @app.api_route("/p/{token}", methods=["GET", "POST"])
    async def case_page(token: str, request: Request):
        """hooks.page(pid, record, form or None, store, day) -> {"html", "title"?, "reply"?: {event, intent, extra?}}.
        A reply goes through the state machine and hooks.on_reply like any other answer."""
        pid = store.patient_by_token(token)
        if not pid:
            return _page(P["invalid"])
        form = {k: str(v) for k, v in (await request.form()).items()} if request.method == "POST" else None
        out = PAGE_HOOK(pid, record(pid), form, store, today())
        r = out.get("reply")
        if r:
            extra = r.get("extra") or {}
            transition(pid, r["event"], today(), via="link", intent=r["intent"], **({"extra": extra} if extra else {}))
            _on_reply(pid, r["intent"], extra)
        body = PAGE.substitute(content=out["html"])
        if out.get("title"):
            body = re.sub(r"<title>.*?</title>", f"<title>{escape(out['title'])}</title>", body, count=1)
        return HTMLResponse(body)


@app.get("/p/{token}")
def patient_page(token: str):
    pid = store.patient_by_token(token)
    if not pid:
        return _page(P["invalid"])
    cls = lambda a: f' class="{a["class"]}"' if a.get("class") else ""  # noqa: E731
    buttons = "\n".join(f'  <button{cls(a)} name="answer" value="{a["value"]}">{a["label"]}</button>' for a in P["answers"])
    return _page(f"""
{P["head"]}
<form method="post">
{buttons}
</form>
{P["foot"]}""")


@app.post("/p/{token}")
def patient_answer(token: str, answer: str = Form(...)):
    pid = store.patient_by_token(token)
    if not pid or answer not in ANSWERS:
        return _page(P["invalid"])
    event, intent, thanks = ANSWERS[answer]
    transition(pid, event, today(), via="link", intent=intent)
    _on_reply(pid, intent, {})
    return _page(f'<h1>{P["thanks_title"]}</h1><div class="box"><p>{thanks}</p></div>')


# ---------- web app (same origin → no CORS) ----------
# ---------- Ukázka v sále: the audience joins by QR code, the presenter calls everybody (hall.py) ----------
HALL_PAGE = Template((Path(__file__).with_name("templates") / "hall.html").read_text(encoding="utf-8"))
HALL_JOIN = Template((Path(__file__).with_name("templates") / "hall_join.html").read_text(encoding="utf-8"))


for _path, _url in REDIRECTS.items():  # short links of the case for SMS, e.g. /centra → list of screening centres
    app.get(_path, include_in_schema=False)(lambda _u=_url: RedirectResponse(_u))

HALL = CASE.feature("hall")
HT = messages.M.get("hall", {})


def hall_page():
    from html import escape as h
    return HTMLResponse(HALL_PAGE.safe_substitute(**{"from": h(settings.from_number)}))


def hall_state():
    ev = hall.current()
    return {**hall.public(ev), "qr": hall.qr_svg(hall.public(ev)["joinUrl"])}


def hall_new():
    return hall.public(hall.new_event())


def hall_call():
    if not settings.live:
        raise HTTPException(409, "Twilio není nastavené, hovory nejdou naostro.")
    return {"calling": hall.call_all(hall.current()["id"])}


def _join_page(content: str, status: int = 200):
    return HTMLResponse(HALL_JOIN.safe_substitute(content=content), status_code=status)


def _join_form(eid: str, error: str = "", phone: str = "", email: str = "", status: int = 200):
    from html import escape as h
    err = f'<p class="err" role="alert">{h(error)}</p>' if error else ""
    return _join_page(f"""
<h1>{HT["join_title"]}</h1>
<p>{HT["join_intro"].replace("{from}", h(settings.from_number))}</p>
{err}
<form method="post" action="/j/{h(eid)}">
  <label>Telefon<input name="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="+420 601 234 567" required value="{h(phone)}"></label>
  <label>E-mail (nepovinné)<input name="email" type="email" autocomplete="email" value="{h(email)}"></label>
  <label class="check"><input type="checkbox" name="consent" value="1" required>
    <span>{HT["join_consent"]}</span></label>
  <button type="submit">Zapojit se</button>
</form>
<p class="muted">{HT["join_note"]}</p>""", status)


def hall_join_form(eid: str):
    ev = hall.get(eid)
    if not hall.is_open(ev) or ev["id"] != hall.current()["id"]:
        return _join_page(HT["join_closed"], 404)
    return _join_form(eid)


async def hall_join(eid: str, request: Request):
    from html import escape as h
    f = await request.form()
    phone, email = str(f.get("phone", "")).strip(), str(f.get("email", "")).strip()
    if not f.get("consent"):
        return _join_form(eid, HT["join_no_consent"], phone, email, 400)
    try:
        p = hall.join(eid, phone, email)
    except ValueError as e:
        return _join_form(eid, str(e), phone, email, 400)
    return _join_page(f"""
<h1>{HT["join_done_title"]}</h1>
<div class="big">{p["n"]}</div>
<p>{HT["join_done"].replace("{from}", h(settings.from_number))}</p>
<p class="muted">{HT["join_done_note"]}</p>""")


async def hall_voice(eid: str, n: int, request: Request):
    await _form(request)
    return Response(hall.voice_twiml(eid, n), media_type="application/xml")


async def hall_answer(eid: str, n: int, request: Request):
    form = await _form(request)
    return Response(hall.answer(eid, n, form.get("Digits") or form.get("SpeechResult") or ""), media_type="application/xml")


async def hall_status(eid: str, n: int, request: Request):
    form = await _form(request)
    await asyncio.to_thread(hall.call_status, eid, n, form.get("CallStatus", ""))
    return Response(status_code=204)


if HALL:  # Ukázka v sále: only cases with features.hall
    app.get("/sal")(hall_page)
    app.get("/api/hall")(hall_state)
    app.post("/api/hall/new")(hall_new)
    app.post("/api/hall/call")(hall_call)
    app.get("/j/{eid}")(hall_join_form)
    app.post("/j/{eid}")(hall_join)
    app.post("/twilio/hall/voice/{eid}/{n}")(hall_voice)
    app.post("/twilio/hall/answer/{eid}/{n}")(hall_answer)
    app.post("/twilio/hall/status/{eid}/{n}")(hall_status)


# ---------- sign-in: access code + the visitor's own phone and e-mail ----------
LOGIN = Template((Path(__file__).with_name("templates") / "login.html").read_text(encoding="utf-8"))


def _safe_next(n: str) -> str:
    return n if n.startswith("/") and not n.startswith("//") else "/app/"


LOGIN_TEXT = {  # messages.cs.json "login" of the case (HTML-free texts); these defaults are screening's
    "heading": "Ukázka aplikace",
    "intro": "Zadejte přístupový kód a svůj telefon a e-mail. Ukázkové SMS, hovor, WhatsApp a e-mail z aplikace půjdou jen na ně, každý návštěvník má svou vlastní ukázku.",
    "note": "Povolená jsou česká čísla. Kontakty použijeme jen k odeslání ukázkových zpráv a po 30 dnech je smažeme. Pacienti v ukázce jsou smyšlení.",
    **messages.M.get("login", {})}


def _login_page(nxt="/app/", error="", code="", phone="", email="", status=200):
    from html import escape as h
    back = '<p class="muted"><a href="/">Zpět na stránku projektu</a></p>' if LANDING_ON or _case_landing() else ""
    return HTMLResponse(LOGIN.safe_substitute(next=h(_safe_next(nxt)), code=h(code), phone=h(phone), email=h(email),
                                              brand=h(CASE.manifest["brand"]), back=back,
                                              email_required="" if EMAIL_OPTIONAL else "required",
                                              email_hint="nepovinný" if EMAIL_OPTIONAL else "",
                                              **{k: h(v) for k, v in LOGIN_TEXT.items() if not k.startswith("_")},
                                              error=f'<p class="err" role="alert">{h(error)}</p>' if error else ""), status_code=status)


@app.get("/login")
def login_form(next: str = "/app/"):
    return _login_page(next)


@app.post("/login")
async def login(request: Request):
    import secrets
    f = await request.form()
    code, phone, email, nxt = (str(f.get(k, "")).strip() for k in ("code", "phone", "email", "next"))
    if not settings.demo_password or not secrets.compare_digest(code.lower(), settings.demo_password.lower()):
        return _login_page(nxt, "Nesprávný přístupový kód.", "", phone, email, 401)
    try:
        if EMAIL_OPTIONAL and not email:
            p, e = recipient.validate(phone, "", required=False)
            if not p:
                raise ValueError("Zadejte telefon, na který pošleme ukázkové SMS a zavoláme.")
        else:
            p, e = recipient.validate(phone, email, required=True)
    except ValueError as err:
        return _login_page(nxt, str(err), code, phone, email, 400)
    token = sessions.create(p, e)
    r = RedirectResponse(_safe_next(nxt), status_code=303)
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    r.set_cookie(sessions.COOKIE, token, max_age=sessions.MAX_AGE_DAYS * 86400, httponly=True, samesite="lax", secure=https)
    return r


@app.get("/logout")
def logout(request: Request):
    sessions.delete(request.cookies.get(sessions.COOKIE))
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(sessions.COOKIE)
    return r


@app.get("/")
def root():
    """The public landing of the case: cases/<id>/landing/index.html (assets at /landing/…), else the project landing
    of case.json "landing" (screening: submission/landing), else the app itself (sign-in)."""
    from fastapi.responses import FileResponse
    if _case_landing():
        return FileResponse(CASE_LANDING / "index.html", media_type="text/html")
    return projekt() if LANDING_ON else RedirectResponse("/app/")


CASE_LANDING = CASE.dir / "landing"


def _case_landing() -> bool:
    return (CASE_LANDING / "index.html").is_file()  # checked per request: the files may be added while it runs


@app.get("/landing/{path:path}")
def case_landing_file(path: str):
    """Assets of the case landing (cases/<id>/landing/), public; nothing outside that directory."""
    from fastapi.responses import FileResponse
    base = CASE_LANDING.resolve()
    f = (base / path).resolve()
    if not f.is_relative_to(base) or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


@app.get("/app")
def app_redirect():
    return RedirectResponse("/app/")


# Public project page (no password): the landing from submission/landing and the demo video. Only for a case whose
# case.json has "landing" (screening); the other cases have no lung-screening pages.
LANDING = ROOT / CASE.manifest.get("landing", "submission/landing")
LANDING_ON = bool(CASE.manifest.get("landing")) and LANDING.exists()
LANDING_HEAD = ('<!doctype html><html lang="cs"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')


@app.get("/projekt")
def projekt_redirect():
    return RedirectResponse("/projekt/")


@app.get("/projekt/")
def projekt():
    if not LANDING_ON:
        return RedirectResponse("/app/")
    body = (LANDING / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(LANDING_HEAD + body + "</body></html>")


@app.get("/rakathon")
def rakathon():
    """How the project came about at Rakathon: its own page when submission/landing/rakathon.html exists, else the landing section.
    Served without a trailing slash so the page's relative img/… links resolve to /img/…"""
    page = LANDING / "rakathon.html"
    if not LANDING_ON:
        return RedirectResponse("/app/")
    if not page.exists():
        return RedirectResponse("/#vznik")
    return HTMLResponse(LANDING_HEAD + page.read_text(encoding="utf-8") + "</body></html>")


@app.get("/rakathon/")
def rakathon_slash():
    return RedirectResponse("/rakathon")


@app.get("/demo.mp4")
@app.get("/projekt/demo.mp4")
def projekt_video():
    from fastapi.responses import FileResponse
    if not LANDING_ON:
        raise HTTPException(404)
    return FileResponse(ROOT / "submission" / "demo.mp4", media_type="video/mp4")


# ---------- the case's part of the web app (before the /app mount, which would answer first) ----------
@app.get("/app/content/{name}")
def case_content(name: str):
    """case.json, journey.json, messages.cs.json … of the case (only top-level JSON files, never its Python)."""
    from fastapi.responses import FileResponse
    path = CASE.dir / name
    if not name.endswith(".json") or "/" in name or name.startswith(".") or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/json")


@app.get("/app/data/patients.json")
def case_data():
    """The case's records (case.json "data"); the web app reads the key `patients`."""
    from fastapi.responses import FileResponse
    if not CASE.data.is_file():
        raise HTTPException(404, f"run: python -m cases.{CASE.id}.build")
    return FileResponse(CASE.data, media_type="application/json")


if LANDING_ON:
    app.mount("/projekt", StaticFiles(directory=LANDING), name="landing")
    app.mount("/img", StaticFiles(directory=LANDING / "img"), name="landing-img")  # landing images at the domain root
if CASE.web.is_dir():
    app.mount("/app/case", StaticFiles(directory=CASE.web), name="case-web")  # ES modules of the case
app.mount("/app", StaticFiles(directory=WEB, html=True), name="web")
