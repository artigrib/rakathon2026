"""Ukázka v sále: the audience joins by QR code with their own phone, the presenter calls everybody at once.

/sal (presenter, signed in) shows a QR code → people open /j/<event> on their phones and leave their phone (+420)
and optionally an e-mail → their cards appear on /sal → "Prozvonit všechny" calls every card with the approved
FIRST_INVITE call text (keys 1/2 or ano/ne) → whoever does not pick up or does not answer gets a short SMS (and an
e-mail) with links to the screening centres; "ANO" to that SMS marks the card too.

Guard rails: +420 only, HALL_MAX participants, the per-number daily limit of recipient.take, joining closes after
HALL_TTL_HOURS. Numbers are masked on the projector. Contacts live in /data/hall.json and go with the next event.
"""
import json
import os
import secrets
import threading
import time
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from . import channels, messages, recipient, tts
from .replies import understand
from .settings import settings

_lock = threading.RLock()
FINAL = {"interested", "not_now", "declined", "unclear", "no_answer", "limit", "error"}
CLOSING = {"interested": "Děkuji. Sestra z ordinace se Vám ozve a domluví další postup. Na shledanou.",
           "not_now": "Děkuji. Ozveme se později. Na shledanou."}
NOT_UNDERSTOOD = "Děkuji. Pošleme Vám zprávu s informacemi. Na shledanou."


def max_participants() -> int:
    return int(os.getenv("HALL_MAX", "150"))


def ttl_hours() -> float:
    return float(os.getenv("HALL_TTL_HOURS", "12"))


def _file() -> Path:
    return Path(settings.state_file).with_name("hall.json")


def _load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"current": "", "events": {}}


def _save(d: dict):
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def new_event() -> dict:
    """A fresh event; the previous one (and its contacts) is dropped."""
    with _lock:
        eid = secrets.token_urlsafe(6)
        ev = {"id": eid, "created": time.time(), "participants": []}
        _save({"current": eid, "events": {eid: ev}})
        return ev


def current() -> dict:
    """The running event; one older than 2 days is replaced (its contacts are deleted)."""
    d = _load()
    ev = d["events"].get(d.get("current", ""))
    if not ev or time.time() - ev["created"] > 2 * 86400:
        return new_event()
    return ev


def get(eid: str):
    return _load()["events"].get(eid)


def is_open(ev) -> bool:
    return bool(ev) and time.time() - ev["created"] < ttl_hours() * 3600


def _update(eid: str, n: int, **fields) -> dict:
    with _lock:
        d = _load()
        ev = d["events"].get(eid)
        if not ev or not (0 < n <= len(ev["participants"])):
            return {}
        p = ev["participants"][n - 1]
        p.update(fields, updated=time.time())
        _save(d)
        return dict(p)


def join(eid: str, raw_phone: str, raw_email: str) -> dict:
    """Add a participant (or update the same phone). ValueError with a Czech message."""
    phone, email = recipient.validate(raw_phone, raw_email)
    if not phone:
        raise ValueError("Zadejte telefon, na který Vám zavoláme.")
    with _lock:
        d = _load()
        ev = d["events"].get(eid)
        if not is_open(ev):
            raise ValueError("Tato ukázka už skončila.")
        for p in ev["participants"]:
            if p["phone"] == phone:
                p["email"] = email or p.get("email", "")
                _save(d)
                return dict(p)
        if len(ev["participants"]) >= max_participants():
            raise ValueError("Ukázka je plná, děkujeme.")
        p = {"n": len(ev["participants"]) + 1, "phone": phone, "email": email, "status": "joined", "joined": time.time()}
        ev["participants"].append(p)
        _save(d)
        return dict(p)


def _mask(phone: str) -> str:
    return f"*** *** {phone[-3:]}"


def public(ev: dict) -> dict:
    """For the projector: numbers masked, e-mails only as a flag."""
    ps = ev["participants"]
    return {
        "id": ev["id"], "open": is_open(ev),
        "joinUrl": f"{settings.public_url}/j/{ev['id']}" if settings.public_url else f"/j/{ev['id']}",
        "count": len(ps), "max": max_participants(),
        "callable": sum(1 for p in ps if p["status"] == "joined"),
        "participants": [{"n": p["n"], "phone": _mask(p["phone"]), "email": bool(p.get("email")),
                          "status": p["status"], "fallback": p.get("fallback", [])} for p in ps],
    }


def qr_svg(url: str) -> str:
    import segno
    return segno.make(url, error="m").svg_inline(scale=10, border=2, dark="#1d1d1b", light="#ffffff")


# ---------- calling ----------
def _url(path: str) -> str:
    return f"{settings.public_url}{path}"


def _dial(p: dict, eid: str) -> str:
    """Start one Twilio call; returns the call sid."""
    c = channels._client().calls.create(
        to=p["phone"], from_=settings.from_number, timeout=25,
        url=_url(f"/twilio/hall/voice/{eid}/{p['n']}"),
        status_callback=_url(f"/twilio/hall/status/{eid}/{p['n']}"),
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    return c.sid


def _start(fn):
    """Background work (the request returns at once; cards update as Twilio calls back)."""
    threading.Thread(target=fn, daemon=True).start()


def call_all(eid: str, dial=None, wait: float = 0.3) -> int:
    """Call every participant who has not been called yet, in a background thread. Returns how many."""
    dial = dial or _dial
    ev = get(eid)
    if not ev or not settings.live:
        return 0
    todo = [p for p in ev["participants"] if p["status"] == "joined"]
    for p in todo:
        _update(eid, p["n"], status="queued")

    def run():
        day = date.today().isoformat()
        # audio once before dialling: 100 calls must not each order the same ElevenLabs voice-over
        for t in (messages.M["voice"]["FIRST_INVITE"].strip(), NOT_UNDERSTOOD, *CLOSING.values()):
            tts.ensure(t, timeout=30)
        for p in todo:
            if not recipient.take(p["phone"], day):
                _update(eid, p["n"], status="limit")
                continue
            try:
                _update(eid, p["n"], status="calling", sid=dial(p, eid))
            except Exception as e:  # noqa: BLE001 – one bad number must not stop the room
                _update(eid, p["n"], status="error", error=str(e)[:120])
                fallback(eid, p["n"])
            time.sleep(wait)   # Twilio queues above its calls-per-second limit anyway; this keeps the ramp visible

    _start(run)
    return len(todo)


def voice_twiml(eid: str, n: int) -> str:
    _update(eid, n, status="talking")
    text = messages.M["voice"]["FIRST_INVITE"].strip()
    return ('<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Gather input="dtmf speech" numDigits="1" language="{settings.voice_lang}" timeout="8" speechTimeout="auto" '
            f'action="{escape(_url(f"/twilio/hall/answer/{eid}/{n}"))}" method="POST">'
            + channels.speak(text) + "</Gather>" + channels.speak(NOT_UNDERSTOOD) + "</Response>")


def answer(eid: str, n: int, said: str) -> str:
    digit = {"1": "ano", "2": "teď ne"}.get(said.strip(), said)
    intent = understand(digit)["intent"]
    status = {"interested": "interested", "booked": "interested", "callback": "interested",
              "not_now": "not_now", "declined": "declined", "opt_out": "declined"}.get(intent, "unclear")
    _update(eid, n, status=status, said=said[:120])
    return channels.twiml_say(CLOSING.get(status, CLOSING["not_now"] if status == "declined" else NOT_UNDERSTOOD))


def call_status(eid: str, n: int, st: str):
    """Twilio call progress → card. No answer, busy, failed, or a call without an answer → SMS (+ e-mail)."""
    ev = get(eid)
    if not ev or not (0 < n <= len(ev["participants"])):
        return
    p = ev["participants"][n - 1]
    if st == "ringing" and p["status"] in ("queued", "calling"):
        _update(eid, n, status="ringing")
    elif st == "in-progress" and p["status"] not in FINAL:
        _update(eid, n, status="talking")
    elif st in ("no-answer", "busy", "failed", "canceled") or (st == "completed" and p["status"] not in FINAL):
        if p["status"] != "unclear":
            _update(eid, n, status="no_answer")
        fallback(eid, n)
    elif st == "completed" and p["status"] == "unclear":
        fallback(eid, n)


def _links() -> dict:
    base = settings.public_url.replace("https://", "").replace("http://", "") or "jsemvcas.cz"
    return {"centres": f"{base}/centra", "info": f"{base}/prevence"}


def fallback(eid: str, n: int):
    """Short SMS with the screening-centre links, and the e-mail when the participant gave one. Once per card."""
    ev = get(eid)
    p = ev["participants"][n - 1] if ev and 0 < n <= len(ev["participants"]) else None
    if not p or p.get("fallback"):
        return
    sent = []
    t = messages.M["hall"]
    try:
        channels._client().messages.create(to=p["phone"], from_=settings.from_number, body=t["sms"].format(**_links()))
        sent.append("sms")
    except Exception as e:  # noqa: BLE001
        _update(eid, n, error=str(e)[:120])
    if p.get("email") and settings.email_live:
        full = {k: f"https://{v}" for k, v in _links().items()}
        try:
            channels.send_email(t["email"].format(**full), True, to=p["email"])
            sent.append("email")
        except Exception as e:  # noqa: BLE001
            _update(eid, n, error=str(e)[:120])
    _update(eid, n, fallback=sent or ["failed"])


def inbound(phone: str, body: str):
    """'ANO' to the fallback SMS → the card. Returns the confirmation text, or None when it is not a hall number."""
    ev = current()
    for p in ev["participants"]:
        if p["phone"] == phone and "sms" in p.get("fallback", []):
            intent = understand(body)["intent"]
            status = "interested" if intent in ("interested", "booked", "callback") else \
                "declined" if intent in ("declined", "opt_out") else "not_now" if intent == "not_now" else p["status"]
            _update(ev["id"], p["n"], status=status, said=body[:120])
            return messages.sms_reply(intent, status) if status in ("interested", "not_now", "declined") else ""
    return None
