"""Plíce včas backend: serves the web app, sends invitations through Twilio, receives replies.

  uvicorn backend.app:app --reload --port 8000        (from the project root)

Without Twilio keys it runs in MOCK mode. With keys + PUBLIC_URL (ngrok) + DEMO_TO it sends for real."""
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import asyncio
import json
import logging
import re
from datetime import timedelta

from . import agent_call, channels, fhir_sink, fsm, messages, tts
from .channels import NO_ANSWER  # noqa: F401  (re-exported for tts warmup)
from .cadence import next_touch
from .replies import understand
from .settings import settings
from .store import Store

_rlog = logging.getLogger("uvicorn.error")  # voice turns and agent outcomes in the container log (no phone numbers)

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "app"
app = FastAPI(title="Plíce včas")
store = Store(settings.state_file)
PATIENTS: dict = {}
REF_DATE = "2026-10-16"


def load_patients():
    """web/app/data/patients.json = engine output (from CSV, or from the FHIR server after /api/fhir/sync)."""
    global REF_DATE
    d = json.loads((WEB / "data/patients.json").read_text(encoding="utf-8"))
    PATIENTS.clear()
    PATIENTS.update({p["id"]: p for p in d["patients"]})
    REF_DATE = d["refDate"]


load_patients()


def today() -> str:
    """Demo clock: starts at the data's evaluation date; "Posunout čas o den" moves it forward."""
    return store.data.get("clock") or REF_DATE


def patient_link(pid: str) -> str:
    token = store.token(pid)  # created on first contact; the page works on any host
    return f"{settings.public_url}/p/{token}" if settings.public_url else ""
VOICE_NO_DIGIT = "Děkujeme. Pokud budete chtít, ozvěte se prosím své ordinaci. Na shledanou."
VOICE_THANKS = {"interested": "Děkujeme. Sestra z ordinace se Vám ozve a domluví další postup. Na shledanou.",
                "callback": "Děkujeme, sestra z ordinace Vám zavolá. Na shledanou."}


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


@app.get("/api/health")
def health():
    from . import llm
    return {"ok": True, "mode": "live" if settings.live else "mock", "liveLimit": settings.live_limit,
            "ai": llm.provider() if llm.enabled() else None, "voice": "elevenlabs" if tts.enabled() else "twilio",
            "trial": settings.live and settings.trial,
            "email": settings.email_live,
            "fhir": ({"server": settings.fhir_base.split("//")[-1].split("/")[0], "sync": store.data.get("fhir_sync"),
                      "written": fhir_sink.state["sent"], "errors": fhir_sink.state["errors"], "lastError": fhir_sink.state["last_error"]}
                     if settings.fhir_base else None)}


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
    plans = {}
    for pid, d in store.decisions().items():
        n = next_touch(d.get("journey", []))
        if n:
            plans[pid] = {**n, "due": n["due"].isoformat()}
    links = {pid: f"/p/{t}" for t, pid in store.data.get("tokens", {}).items()}  # relative: works on any host
    return {"version": store.version, "clock": today(), "decisions": store.decisions(), "plans": plans, "links": links}


@app.post("/api/send")
def send(req: SendRequest):
    """Approved invitations. The first `live_limit` go out for real (demo phone), the rest is simulated."""
    budget = [settings.live_limit if settings.live else 0]
    return {"sent": [_send(it.id, it.channel, it.variant, it.text, req.date or today(), budget) for it in req.items]}


def _send(pid, channel, variant, text, day, budget, auto=False, step=None):
    """One outbound touch. budget[0] = how many may still go out for real in this request."""
    if not fsm.allowed(fsm.state_of(store.get(pid)), "send"):  # e.g. referred, refused, excluded: never contact
        return {"id": pid, "sid": None, "live": False, "status": "not_allowed"}
    text = messages.with_link(text, patient_link(pid), channel)
    real = ("sms", "voice", "whatsapp") + (("email",) if settings.email_live else ())
    live = budget[0] > 0 and channel in real
    try:
        if channel == "voice":
            if live:  # generate the Czech audio before dialling, so the call starts without a pause
                tts.ensure(text.strip())
            r = channels.start_call(pid, live)
        elif channel == "whatsapp":
            r = channels.send_whatsapp(text, live)
        elif channel == "email":
            r = channels.send_email(text, live)
        else:
            r = channels.send_sms(text, live)
    except Exception as e:  # a failed send is a delivery fact, not a crash
        r = {"sid": None, "live": live, "to": settings.demo_to, "status": "failed", "error": str(e)}
    budget[0] -= int(r["live"])
    store.log(patient=pid, channel=channel, text=text, day=day, variant=variant, auto=auto, step=step, **r)
    extra = {"auto": True, "step": step} if auto else {}
    transition(pid, "send", day, channel=channel, variant=variant, live=r["live"], **extra)
    return {"id": pid, **r}


class TickRequest(BaseModel):
    days: int = 1


@app.post("/api/tick")
def tick(req: TickRequest):
    """Advance the demo clock and run every automatic touch that is due (what a cron does every 15 min)."""
    budget = [settings.live_limit if settings.live and settings.tick_live else 0]
    done = []
    for _ in range(max(1, req.days)):
        day = (date.fromisoformat(today()) + timedelta(days=1)).isoformat()
        store.data["clock"] = day
        for pid, d in list(store.decisions().items()):
            n = next_touch(d.get("journey", []))
            if not n or n["due"].isoformat() > day:
                continue
            if n["channel"] == "nurse":
                transition(pid, "nurse", day, auto=True, step=n["step"])
                done.append({"id": pid, "channel": "nurse"})
                continue
            p = PATIENTS.get(pid, {"gp": "", "pneu": None})
            text = messages.render(p, n["channel"], n["variant"], patient_link(pid))
            done.append(_send(pid, n["channel"], n["variant"], text, day, budget, auto=True, step=n["step"]))
    store._save()
    return {"clock": today(), "touches": done}


@app.post("/api/step")
def step(req: StepRequest):
    """Nurse action or simulated patient reply from the UI (same path as a real webhook)."""
    if req.text is not None:
        return _apply_reply(req.id, req.text, "ui", req.date or today())
    extra = {"result": req.result} if req.result else {}
    # Nurse or doctor action = an event of the state machine (first "declined" is soft, see journey.json).
    return transition(req.id, req.stage, req.date or today(), via="ui", **extra)


@app.get("/api/patient/{pid}")
def patient_messages(pid: str):
    """Everything we sent to one patient, for the communication timeline. No phone number, no link token."""
    keep = ("day", "ts", "channel", "text", "live", "status", "error", "auto", "step", "variant", "duration")
    out = []
    for m in store.data["outbox"]:
        if m.get("patient") != pid:
            continue
        item = {k: m.get(k) for k in keep if m.get(k) is not None}
        if "text" in item:
            item["text"] = re.sub(r"/p/[A-Za-z0-9_-]+", "/p/…", item["text"])
        if "error" in item:
            item["error"] = str(item["error"])[:120]
        out.append(item)
    return {"outbox": out}


@app.post("/api/fhir/sync")
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
    (WEB / "data/patients.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    load_patients()
    info = {"at": datetime_now(), "resources": len(res), "patients": len(out["patients"])}
    store.data["fhir_sync"] = info
    store._save()
    return info


@app.post("/api/fhir/push")
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


@app.get("/api/fhir")
def fhir_bundle(gp: str | None = None):
    """FHIR R4 transaction Bundle (patients, smoking, CT, contacts, evaluation, tasks) – POST it to any FHIR server."""
    from .fhir import bundle
    return bundle(ROOT / "data", REF_DATE, store.decisions(), gp)


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}


# ---------- Twilio webhooks ----------
async def _form(request: Request) -> dict:
    form = dict(await request.form())
    # Signatures are signed with the Auth Token; with only an API key there is nothing to check against.
    if settings.live and settings.validate_signature and settings.auth_token:
        from twilio.request_validator import RequestValidator
        url = settings.public_url + request.url.path
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
    fhir_sink.push(settings, pid, event, d, PATIENTS.get(pid, {}).get("gp"))  # write-back to the FHIR server, async
    return d


def _record_reply(pid, text, understood, via, day=None):
    c = understood
    return transition(pid, fsm.INTENT_EVENT.get(c["intent"], "callback"), day, via=via, text=text, intent=c["intent"],
                      why=c["why"], source=c.get("source", "rules"), **({"when": c["when"]} if c.get("when") else {}))


def _apply_reply(pid, text, via, day=None):
    return _record_reply(pid, text, understand(text), via, day)


@app.post("/twilio/sms")
async def inbound_sms(request: Request):
    form = await _form(request)
    pid = store.last_contacted((form.get("From") or "").replace("whatsapp:", ""))  # SMS and WhatsApp share this webhook
    reply = ""
    if pid:
        d = _apply_reply(pid, form.get("Body", ""), "sms")
        last = d["journey"][-1]
        reply = "" if last.get("ignored") else messages.sms_reply(last.get("intent"), d["stage"])
    body = f"<Message>{escape(reply)}</Message>" if reply else ""
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


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
    return Response(channels.voice_twiml(pid, script or VOICE_NO_DIGIT), media_type="application/xml")


@app.post("/twilio/voice/{pid}/answer")
async def voice_answer(pid: str, request: Request):
    form = await _form(request)
    said = form.get("Digits") or form.get("SpeechResult") or ""
    d = _apply_reply(pid, said, "voice")
    thanks = VOICE_THANKS.get(d["stage"], VOICE_NO_DIGIT)
    return Response(channels.twiml_say(thanks), media_type="application/xml")


@app.websocket("/ws/relay/{pid}")
async def relay(ws: WebSocket, pid: str):
    """ConversationRelay: Twilio sends what the patient said, we answer with approved sentences."""
    from .voice_ai import Conversation
    await ws.accept()
    _rlog.info("relay %s open", pid)
    conv = Conversation()
    try:
        while True:
            msg = await ws.receive_json()
            _rlog.info("relay %s in %s %s", pid, msg.get("type"),
                       {k: msg.get(k) for k in ("voicePrompt", "last", "digit", "utteranceUntilInterrupt", "durationUntilInterruptMs", "description") if k in msg})
            if msg.get("type") == "dtmf":
                msg = {"type": "prompt", "voicePrompt": {"1": "ano", "2": "teď ne"}.get(msg.get("digit"), "")}
            if msg.get("type") != "prompt":
                continue
            said = msg.get("voicePrompt", "")
            understood = understand(said)
            reply, done, intent = conv.feed(said, understood)
            if intent:
                _record_reply(pid, said, {**understood, "intent": intent}, "voice-ai")
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
    if st == "completed" and settings.voice_mode == "agent" and agent_call.agent_id():
        asyncio.get_running_loop().create_task(_agent_outcome(pid, form.get("CallSid", "")))
    return Response(status_code=204)


async def _agent_outcome(pid: str, call_sid: str):
    """After an agent call: its decision → the same journey event as a reply (state machine, FHIR write-back)."""
    o = await asyncio.to_thread(agent_call.outcome, call_sid)
    _rlog.info("agent %s outcome %s", pid, {k: v for k, v in (o or {}).items() if k != "text"})
    if not o:
        return
    _record_reply(pid, o["text"], {"intent": o["intent"], "why": f"hlasový asistent: {o['intent']}", "source": "elevenlabs-agent",
                                   **({"when": o["when"]} if o["when"] else {})}, "voice-agent")


# ---------- patient page (personal link from SMS / e-mail) ----------
from string import Template  # noqa: E402

from fastapi import Form  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

PAGE = Template((Path(__file__).with_name("templates") / "patient.html").read_text(encoding="utf-8"))
PNEU_LIST = "https://www.vzp.cz/poskytovatele/informace-pro-praxi/seznamy-center-a-szz/seznam-center-casneho-zachytu-karcinomu-plic"
# answer → (journey stage, intent, thank-you text). No health data is ever shown on this page.
ANSWERS = {
    "interested": ("interested", "interested", "Děkujeme. Sestra z Vaší ordinace se Vám ozve a domluví další postup. "
                   f'Objednat se můžete i sami u kteréhokoli pneumologa v programu, viz <a href="{PNEU_LIST}">seznam pracovišť</a>.'),
    "booked": ("booked", "booked", "Děkujeme. Další připomínky Vám už posílat nebudeme."),
    "callback": ("callback", "callback", "Děkujeme. Sestra z Vaší ordinace Vám zavolá."),
    "not_now": ("not_now", "not_now", "Děkujeme. Ozveme se později. Pokud si to rozmyslíte, ozvěte se své ordinaci."),
    "stop": ("declined", "opt_out", "Další zprávy o tomto programu Vám posílat nebudeme."),
}


def _page(html: str) -> HTMLResponse:
    return HTMLResponse(PAGE.substitute(content=html))


@app.get("/p/{token}")
def patient_page(token: str):
    pid = store.patient_by_token(token)
    if not pid:
        return _page("<h1>Odkaz už neplatí</h1><p>Obraťte se prosím na svou ordinaci.</p>")
    gp = PATIENTS.get(pid, {}).get("gp") or ""
    return _page(f"""
<p class="muted">Vaše ordinace praktického lékaře</p>
<h1>Bezplatné preventivní vyšetření plic</h1>
<p>Lidé, kteří kouří nebo dříve kouřili, mohou v programu Prevence pro plíce absolvovat krátké vyšetření plic. Nebolí a hradí ho zdravotní pojišťovna.</p>
<form method="post">
  <button class="primary" name="answer" value="interested">Ano, mám zájem</button>
  <button name="answer" value="booked">Už jsem objednaný/á</button>
  <button name="answer" value="callback">Zavolejte mi prosím</button>
  <button name="answer" value="not_now">Teď ne</button>
  <button class="quiet" name="answer" value="stop">Nepřeji si další zprávy o tomto programu</button>
</form>
<p class="muted">Více informací: <a href="https://www.prevenceproplice.cz">prevenceproplice.cz</a></p>""")


@app.post("/p/{token}")
def patient_answer(token: str, answer: str = Form(...)):
    pid = store.patient_by_token(token)
    if not pid or answer not in ANSWERS:
        return _page("<h1>Odkaz už neplatí</h1><p>Obraťte se prosím na svou ordinaci.</p>")
    event, intent, thanks = ANSWERS[answer]
    transition(pid, "opt_out" if intent == "opt_out" else event, today(), via="link", intent=intent)
    return _page(f'<h1>Děkujeme</h1><div class="box"><p>{thanks}</p></div>')


# ---------- web app (same origin → no CORS) ----------
@app.get("/")
def root():
    return RedirectResponse("/app/index.html")


app.mount("/app", StaticFiles(directory=WEB, html=True), name="web")
