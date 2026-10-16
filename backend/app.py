"""Plíce včas backend: serves the web app, sends invitations through Twilio, receives replies.

  uvicorn backend.app:app --reload --port 8000        (from the project root)

Without Twilio keys it runs in MOCK mode. With keys + PUBLIC_URL (ngrok) + DEMO_TO it sends for real."""
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import json
from datetime import timedelta

from . import channels, messages, tts
from .channels import NO_ANSWER  # noqa: F401  (re-exported for tts warmup)
from .cadence import next_touch
from .replies import STAGE, understand
from .settings import settings
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "app"
app = FastAPI(title="Plíce včas")
store = Store(settings.state_file)
PATIENTS = {p["id"]: p for p in json.loads((WEB / "data/patients.json").read_text(encoding="utf-8"))["patients"]}
REF_DATE = json.loads((WEB / "data/patients.json").read_text(encoding="utf-8"))["refDate"]


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
            "ai": llm.provider() if llm.enabled() else None, "voice": "elevenlabs" if tts.enabled() else "twilio"}


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
    text = messages.with_link(text, patient_link(pid))
    live = budget[0] > 0 and channel in ("sms", "voice", "whatsapp")
    try:
        if channel == "voice":
            if live:  # generate the Czech audio before dialling, so the call starts without a pause
                tts.ensure(text.strip())
            r = channels.start_call(pid, live)
        elif channel == "whatsapp":
            r = channels.send_whatsapp(text, live)
        else:
            r = channels.send_sms(text, live)
    except Exception as e:  # a failed send is a delivery fact, not a crash
        r = {"sid": None, "live": live, "to": settings.demo_to, "status": "failed", "error": str(e)}
    budget[0] -= int(r["live"])
    store.log(patient=pid, channel=channel, text=text, **r)
    extra = {"auto": True, "step": step} if auto else {}
    store.event(pid, "sent", day, channel=channel, variant=variant, live=r["live"], **extra)
    return {"id": pid, **r}


class TickRequest(BaseModel):
    days: int = 1


@app.post("/api/tick")
def tick(req: TickRequest):
    """Advance the demo clock and run every automatic touch that is due (what a cron does every 15 min)."""
    budget = [settings.live_limit if settings.live else 0]
    done = []
    for _ in range(max(1, req.days)):
        day = (date.fromisoformat(today()) + timedelta(days=1)).isoformat()
        store.data["clock"] = day
        for pid, d in list(store.decisions().items()):
            n = next_touch(d.get("journey", []))
            if not n or n["due"].isoformat() > day:
                continue
            if n["channel"] == "nurse":
                store.event(pid, "nurse_call", day, auto=True, step=n["step"])
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
    return store.event(req.id, req.stage, req.date or today(), **extra)


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
    return sum(1 for e in store.get(pid).get("journey", []) if e.get("intent") in ("declined", "opt_out"))


def _apply_reply(pid, text, via, day=None):
    c = understand(text)
    stage = STAGE[c["intent"]]
    # Doctor: first "not interested" → try another channel with a motivating text; second → stop.
    if c["intent"] == "declined" and _refusals(pid) == 0:
        stage = "not_now"
    return store.event(pid, stage, day or today(), via=via, text=text, intent=c["intent"], why=c["why"],
                       source=c["source"], **({"when": c["when"]} if c.get("when") else {}))


@app.post("/twilio/sms")
async def inbound_sms(request: Request):
    form = await _form(request)
    pid = store.last_contacted((form.get("From") or "").replace("whatsapp:", ""))  # SMS and WhatsApp share this webhook
    if pid:
        _apply_reply(pid, form.get("Body", ""), "sms")
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response/>', media_type="application/xml")


@app.post("/twilio/status")
async def sms_status(request: Request):
    form = await _form(request)
    m = store.outbox_update(form.get("MessageSid"), status=form.get("MessageStatus"))
    if m and form.get("MessageStatus") in ("delivered", "failed", "undelivered"):
        store.event(m["patient"], None, today(), delivery=form["MessageStatus"], channel="sms")
    return Response(status_code=204)


@app.post("/twilio/voice/{pid}")
async def voice(pid: str, request: Request):
    await _form(request)
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
    conv = Conversation()
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "dtmf":
                msg = {"type": "prompt", "voicePrompt": {"1": "ano", "2": "teď ne"}.get(msg.get("digit"), "")}
            if msg.get("type") != "prompt":
                continue
            said = msg.get("voicePrompt", "")
            understood = understand(said)
            reply, done, intent = conv.feed(said, understood)
            if intent:
                stage = STAGE.get(intent, "callback")
                if intent == "declined" and _refusals(pid) == 0:
                    stage = "not_now"
                store.event(pid, stage, today(), via="voice-ai", text=said, intent=intent,
                            why=understood["why"], source=understood.get("source", "rules"))
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
    store.outbox_update(form.get("CallSid"), status=st)
    if st in ("no-answer", "busy", "failed"):
        store.event(pid, None, today(), delivery="failed", channel="voice", note=st)
    return Response(status_code=204)


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
    stage, intent, thanks = ANSWERS[answer]
    store.event(pid, stage, today(), via="link", intent=intent)
    return _page(f'<h1>Děkujeme</h1><div class="box"><p>{thanks}</p></div>')


# ---------- web app (same origin → no CORS) ----------
@app.get("/")
def root():
    return RedirectResponse("/app/index.html")


app.mount("/app", StaticFiles(directory=WEB, html=True), name="web")
