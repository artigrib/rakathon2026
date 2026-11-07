"""Phone assistant demo: a visitor sets up an assistant on a web page, gets a Twilio number and a forwarding code; calls
to that number (forwarded after N seconds, or dialled directly) are answered by their ElevenLabs agent.

Separate from the case containers on purpose: its own image, database and subdomain, see assistant/README.md."""
import hashlib
import hmac
import json
import logging
import re
import secrets
import smtplib
import threading
import time
from datetime import date as date_cls, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape

import asyncio
import base64
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import agents, config, db, google

log = logging.getLogger("uvicorn.error")  # phone numbers stay out of the log
STATIC = Path(__file__).parent / "static"
INDEX = STATIC / "index.html"
COOKIE = "asst"
PERMS = ("calendar_read", "calendar_book", "email_summary", "email_message")
LOGIN_FAILS: dict = {}
LOGIN_MAX, LOGIN_WINDOW = 5, 600
FETCH_WAIT_S, FETCH_STEP_S = 120.0, 5.0
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@asynccontextmanager
async def lifespan(_app):
    db.init()
    db.purge(config.RETENTION_DAYS)
    yield


app = FastAPI(title="Telefonní asistent", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def headers(request: Request, call_next):
    r = await call_next(request)
    r.headers["Referrer-Policy"] = "no-referrer"   # the assistant's URL is its secret
    r.headers["X-Robots-Tag"] = "noindex"
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    return r


# ---------- access ----------
def _cookie_value() -> str:
    return hmac.new(google.secret(), b"login:" + config.env("ASSISTANT_ACCESS_CODE").encode(), hashlib.sha256).hexdigest()


def _signed_in(request: Request) -> bool:
    if not config.env("ASSISTANT_ACCESS_CODE") or not config.env("ASSISTANT_SECRET"):
        return False  # not configured = closed
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _cookie_value())


def login_required(request: Request):
    if not _signed_in(request):
        raise HTTPException(401, "Přihlášení vyžadováno")


def _ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


class Login(BaseModel):
    code: str


@app.post("/api/login")
def login(body: Login, request: Request):
    ip, now = _ip(request), time.time()
    fails = [t for t in LOGIN_FAILS.get(ip, []) if now - t < LOGIN_WINDOW]
    if len(fails) >= LOGIN_MAX:
        raise HTTPException(429, "Příliš mnoho pokusů, zkuste to za chvíli")
    code = config.env("ASSISTANT_ACCESS_CODE")
    if not code or not config.env("ASSISTANT_SECRET") or not secrets.compare_digest(body.code.strip().encode(), code.encode()):
        LOGIN_FAILS[ip] = fails + [now]
        raise HTTPException(403, "Nesprávný kód")
    LOGIN_FAILS.pop(ip, None)
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, _cookie_value(), max_age=30 * 86400, httponly=True, samesite="lax",
                 secure=config.public_url().startswith("https://"))
    return r


@app.get("/api/health")
def health():
    return {"ok": True, "numbers": len(config.numbers()), "voice": bool(config.env("ELEVENLABS_API_KEY")),
            "twilio": bool(config.env("TWILIO_AUTH_TOKEN")), "google": config.google_ready(), "smtp": config.smtp_ready()}


@app.get("/api/config")
def client_config(request: Request):
    return {"signedIn": _signed_in(request), "google": config.google_ready(), "smtp": config.smtp_ready(),
            "languages": agents.LANGUAGES, "workHours": [config.WORK_START, config.WORK_END]}


# ---------- assistants ----------
class AssistantIn(BaseModel):
    owner_name: str
    owner_phone: str
    name: str
    greeting: str
    instructions: str = ""
    language: str = "cs"
    notify_email: str = ""


class AssistantPatch(BaseModel):
    owner_name: Optional[str] = None
    name: Optional[str] = None
    greeting: Optional[str] = None
    instructions: Optional[str] = None
    language: Optional[str] = None
    notify_email: Optional[str] = None
    perms: Optional[dict] = None


def _text(value: str, field: str, limit: int, required: bool = True) -> str:
    v = (value or "").strip()
    if required and not v:
        raise HTTPException(422, f"Vyplňte pole: {field}")
    if len(v) > limit:
        raise HTTPException(422, f"Pole {field} je příliš dlouhé (nejvýše {limit} znaků)")
    return v


def _validated(f: dict) -> dict:
    limits = {"owner_name": ("vaše jméno", 80, True), "name": ("jméno asistenta", 60, True), "greeting": ("pozdrav", 300, True),
              "instructions": ("pokyny", 3000, False), "notify_email": ("e-mail", 200, False)}
    out = {k: _text(v, *limits[k]) if k in limits else v for k, v in f.items()}
    if "language" in out and out["language"] not in agents.LANGUAGES:
        raise HTTPException(422, "Nepodporovaný jazyk")
    if out.get("notify_email") and not EMAIL_RE.fullmatch(out["notify_email"]):
        raise HTTPException(422, "Neplatný e-mail")
    return out


def _pick_number() -> str:
    """The number with the fewest assistants: an own number while there is a free one, then they share."""
    pool = config.numbers()
    if not pool:
        raise HTTPException(503, "Zatím není k dispozici žádné číslo")
    load = db.load_by_number()
    return min(pool, key=lambda n: load.get(n, 0))


def _assistant_or_404(aid: str) -> dict:
    a = db.get_assistant(aid)
    if not a:
        raise HTTPException(404, "Asistent neexistuje")
    return a


def _call_public(c: dict) -> dict:
    return {"sid": c["sid"], "from": c["from_number"], "forwarded": bool(c["forwarded_from"] or c["called_via"]),
            "forwardedFromSeen": bool(c["forwarded_from"]), "route": c["route"], "status": c["status"], "duration": c["duration"],
            "summary": c["summary"], "data": json.loads(c["data"]), "transcript": json.loads(c["transcript"]),
            "startedAt": c["started_at"], "ready": bool(c["fetched"]), "direction": c["direction"], "task": c["task"], "to": c["to_number"], "report": c["report_id"]}


def _public(a: dict) -> dict:
    """Never the tool token or the Google token."""
    missing = {p: _missing(a, p) for p in PERMS}
    return {k: a[k] for k in ("id", "owner_name", "owner_phone", "name", "greeting", "instructions", "language", "notify_email", "number",
                              "perms", "google_email")} | {
        "shared": len(db.assistants_on(a["number"])) > 1, "disclosure": agents.DISCLOSURE[a["language"]],
        "googleConnected": bool(a["google_token"]), "googleCalendar": google.has(a, google.SCOPE_EVENTS),
        "googleMail": google.has(a, google.SCOPE_GMAIL_SEND), "permMissing": missing,
        "calls": [_call_public(c) for c in db.calls_of(a["id"])], "actions": db.actions_of(a["id"]),
    }


def _missing(a: dict, perm: str) -> str:
    """Why this permission cannot be switched on, '' when it can."""
    if perm == "calendar_read" and not google.has(a, google.SCOPE_FREEBUSY):
        return "calendar"
    if perm == "calendar_book" and not (google.has(a, google.SCOPE_FREEBUSY) and google.has(a, google.SCOPE_EVENTS)):
        return "calendar"
    if perm in ("email_summary", "email_message") and not (google.has(a, google.SCOPE_GMAIL_SEND) or (a["notify_email"] and config.smtp_ready())):
        return "mail"
    return ""


def _drop_impossible(a: dict) -> dict:
    a["perms"] = {p: True for p in PERMS if a["perms"].get(p) and not _missing(a, p)}
    return a


@app.post("/api/assistants", dependencies=[Depends(login_required)])
def create_assistant(body: AssistantIn):
    f = _validated(body.model_dump())
    f["owner_phone"] = config.normalize_phone(f["owner_phone"])
    if not f["owner_phone"]:
        raise HTTPException(422, "Neplatné telefonní číslo, zadejte ho například jako +420777123456")
    if db.count_assistants() >= config.MAX_ASSISTANTS:
        raise HTTPException(429, "Demo je plné, smažte některého asistenta")
    a = {**f, "id": secrets.token_urlsafe(16), "tool_token": secrets.token_urlsafe(32), "number": _pick_number(), "perms": {}}
    if f["notify_email"] and config.smtp_ready():
        a["perms"] = {"email_summary": True}
    try:
        a["agent_id"] = agents.create(a)
    except Exception as e:  # noqa: BLE001
        log.error("create agent failed: %s", str(e)[:300])
        raise HTTPException(502, "Hlasového agenta se nepodařilo vytvořit, zkuste to znovu") from None
    db.add_assistant(**a)
    return {"id": a["id"]}


@app.get("/api/assistants/{aid}", dependencies=[Depends(login_required)])
def read_assistant(aid: str):
    a = _assistant_or_404(aid)
    for c in db.calls_of(aid):  # the status callback's fetch may have been lost to a restart
        if c["status"] == "completed" and not c["fetched"] and time.time() - c["started_at"] < 3600:
            _schedule_fetch(c["sid"])
    return _public(a)


def _sync_agent(a: dict):
    try:
        agents.update(a)
    except Exception as e:  # noqa: BLE001
        log.error("update agent failed: %s", str(e)[:300])
        raise HTTPException(502, "Změna je uložená, ale hlasového agenta se nepodařilo aktualizovat. Zkuste to znovu.") from None


@app.patch("/api/assistants/{aid}", dependencies=[Depends(login_required)])
def patch_assistant(aid: str, body: AssistantPatch):
    a = _assistant_or_404(aid)
    f = _validated(body.model_dump(exclude_none=True, exclude={"perms"}))
    a.update(f)
    if body.perms is not None:
        unknown = set(body.perms) - set(PERMS)
        if unknown:
            raise HTTPException(422, "Neznámé oprávnění")
        for p, on in body.perms.items():
            if on and _missing(a, p):
                raise HTTPException(409, "Nejdřív připojte potřebný účet nebo vyplňte e-mail")
        a["perms"] = {**a["perms"], **{p: bool(v) for p, v in body.perms.items()}}
    _drop_impossible(a)
    db.update_assistant(aid, **f, perms=a["perms"])
    _sync_agent(a)
    return _public(a)


@app.delete("/api/assistants/{aid}", dependencies=[Depends(login_required)])
def delete_assistant(aid: str):
    a = _assistant_or_404(aid)
    for undo in (lambda: google.revoke(a), lambda: agents.delete(a["agent_id"])):
        try:
            undo()
        except Exception as e:  # noqa: BLE001 – the visitor's data still goes; a left-over agent is only a tidy-up
            log.warning("delete %s: %s", a["id"][:6], str(e)[:200])
    db.delete_assistant(aid)
    return {"ok": True}


# ---------- Google ----------
@app.get("/oauth/google/start", dependencies=[Depends(login_required)])
def google_start(a: str, want: str):
    _assistant_or_404(a)
    wanted = [w for w in want.split(",") if w in google.WANT]
    if not config.google_ready() or not wanted:
        raise HTTPException(400, "Google není nastavený")
    return RedirectResponse(google.auth_url(a, wanted), status_code=303)


@app.get("/oauth/google/callback", dependencies=[Depends(login_required)])
def google_callback(state: str = "", code: str = "", error: str = ""):
    st = google.read_state(state)
    if not st:
        raise HTTPException(400, "Neplatný nebo prošlý požadavek, zkuste připojení znovu")
    a = _assistant_or_404(st["a"])
    if error or not code:
        return RedirectResponse(f"/a/{a['id']}?google=denied", status_code=303)
    try:
        g = google.exchange_code(code)
    except google.GoogleError as e:
        log.error("google exchange: %s", str(e)[:300])
        return RedirectResponse(f"/a/{a['id']}?google=failed", status_code=303)
    a.update(google_token=google.seal(g["refresh_token"]), google_email=g["email"], google_scopes=g["scopes"])
    # Switch on only the harmless part of what was just asked for; booking stays a separate decision on the page.
    wanted = st["w"].split(",")
    on = {"calendar_read": "calendar" in wanted, "email_summary": "mail" in wanted}
    a["perms"] = {**a["perms"], **{p: True for p, v in on.items() if v and not _missing(a, p)}}
    db.update_assistant(a["id"], google_token=a["google_token"], google_email=a["google_email"], google_scopes=a["google_scopes"], perms=a["perms"])
    try:
        agents.update(a)
    except Exception as e:  # noqa: BLE001
        log.error("update agent failed: %s", str(e)[:300])
        return RedirectResponse(f"/a/{a['id']}?google=sync", status_code=303)
    return RedirectResponse(f"/a/{a['id']}?google=ok", status_code=303)


@app.post("/api/assistants/{aid}/google/disconnect", dependencies=[Depends(login_required)])
def google_disconnect(aid: str):
    a = _assistant_or_404(aid)
    try:
        google.revoke(a)
    except Exception as e:  # noqa: BLE001 – our copy goes anyway
        log.warning("revoke: %s", str(e)[:200])
    a.update(google_token="", google_email="", google_scopes="")
    _drop_impossible(a)
    db.update_assistant(aid, google_token="", google_email="", google_scopes="", perms=a["perms"])
    _sync_agent(a)
    return _public(a)


# ---------- e-mail to the owner ----------
def _send_mail(a: dict, subject: str, body: str, ics: str = "") -> bool:
    m = EmailMessage()
    m["Subject"] = re.sub(r"[\r\n]+", " ", subject)[:150]
    m.set_content(body)
    if ics:  # an invitation the owner adds to any calendar with one click
        m.add_attachment(ics.encode(), maintype="text", subtype="calendar", filename="rezervace.ics", params={"method": "PUBLISH"})
    try:
        if google.has(a, google.SCOPE_GMAIL_SEND):
            google.send_to_self(a, m)
            return True
        if a["notify_email"] and config.smtp_ready():
            m["From"], m["To"] = config.env("EMAIL_FROM") or config.env("SMTP_USER"), a["notify_email"]
            with smtplib.SMTP(config.env("SMTP_HOST"), int(config.env("SMTP_PORT", "587")), timeout=20) as s:
                s.starttls()
                s.login(config.env("SMTP_USER"), config.env("SMTP_PASSWORD"))
                s.send_message(m)
            return True
    except Exception as e:  # noqa: BLE001
        log.error("mail %s: %s", a["id"][:6], str(e)[:200])
    return False


# ---------- Twilio ----------
SORRY = {"cs": ("Omlouvám se, asistent teď není dostupný. Zkuste to prosím později.", "cs-CZ"),
         "en": ("Sorry, the assistant is not available right now. Please try again later.", "en-US")}
UNASSIGNED = ("Toto číslo zatím nemá nastaveného asistenta. Na shledanou.", "cs-CZ")


def _say(text: str, language: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Say language="{language}">{escape(text)}</Say><Hangup/></Response>',
                    media_type="application/xml")


async def _twilio_form(request: Request) -> dict:
    """The form of a request that really came from Twilio. Behind the tunnel the signed URL is the public one."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    if config.env("VALIDATE_SIGNATURE", "1") == "1":
        from twilio.request_validator import RequestValidator
        token, base = config.env("TWILIO_AUTH_TOKEN"), config.public_url()
        url = base + request.url.path + (f"?{request.url.query}" if request.url.query else "")
        if not token or not base or not RequestValidator(token).validate(url, form, request.headers.get("X-Twilio-Signature", "")):
            raise HTTPException(403, "Invalid signature")
    return form


def route(to_number: str, forwarded_from: str, from_number: str):
    """Whose assistant answers: (assistant, how). One assistant on the number answers everything, forwarded or dialled.
    On a shared number: the forwarding phone, else the caller if they own one (testing by calling it), else the newest."""
    on_number = db.assistants_on(to_number)
    if not on_number:
        return None, "unassigned"
    if len(on_number) == 1:
        return on_number[0], "own_number"
    if forwarded_from:
        for a in on_number:
            if a["owner_phone"] == forwarded_from:
                return a, "forwarded_from"
    for a in on_number:
        if a["owner_phone"] == from_number:
            return a, "owner_calling"
    return on_number[0], "newest"


def _now() -> datetime:
    return datetime.now(config.TZ)


@app.post("/twilio/inbound")
async def twilio_inbound(request: Request):
    form = await _twilio_form(request)
    sid, to_raw, from_raw = form.get("CallSid", ""), form.get("To", ""), form.get("From", "")
    to_number, from_number = config.normalize_phone(to_raw), config.normalize_phone(from_raw)
    forwarded_from, called_via = config.normalize_phone(form.get("ForwardedFrom", "")), config.normalize_phone(form.get("CalledVia", ""))
    a, how = route(to_number, forwarded_from, from_number)
    log.info("inbound call %s route=%s forwardedFrom=%s calledVia=%s", sid[-6:], how, bool(forwarded_from), bool(called_via))
    if not a:
        return _say(*UNASSIGNED)
    sorry = SORRY["cs" if a["language"] in ("cs", "sk") else "en"]
    midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if db.calls_since(to_number, midnight) >= config.MAX_CALLS_PER_DAY:
        log.warning("daily call limit reached on a number")
        return _say(*sorry)
    db.add_call(sid, a["id"], to_number, from_raw, forwarded_from, called_via, how)
    now = _now()
    variables = {"today": now.strftime("%A %Y-%m-%d %H:%M"), "caller_number": from_raw or "unknown",
                 "forwarded": "yes" if forwarded_from or called_via else "unknown"}
    try:
        twiml = await asyncio.to_thread(agents.register, a, from_raw or "anonymous", to_raw, variables)
    except Exception as e:  # noqa: BLE001
        log.error("register call failed: %s", str(e)[:300])
        db.update_call(sid, status="failed", fetched=1)
        return _say(*sorry)
    return Response(twiml, media_type="application/xml")


@app.post("/twilio/status")
async def twilio_status(request: Request):
    form = await _twilio_form(request)
    sid, status = form.get("CallSid", ""), form.get("CallStatus", "")
    if db.get_call(sid):
        duration = form.get("CallDuration", "")
        db.update_call(sid, status=status, duration=int(duration) if duration.isdigit() else None,
                       **({} if status == "completed" else {"fetched": 1}))
        if status == "completed":
            _schedule_fetch(sid)
        call = db.get_call(sid)
        if call["batch_id"] and status in FINAL:
            _background(_dial_next, call["batch_id"])
    db.purge(config.RETENTION_DAYS)
    return Response(status_code=204)


def _background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


_fetching, _fetching_lock = set(), threading.Lock()


def _schedule_fetch(sid: str):
    with _fetching_lock:
        if sid in _fetching:
            return
        _fetching.add(sid)
    _background(_fetch_guarded, sid)


def _fetch_guarded(sid: str):
    try:
        fetch_outcome(sid)
    except Exception as e:  # noqa: BLE001 – the next page view tries again
        log.warning("fetch outcome: %s", str(e)[:200])
    finally:
        with _fetching_lock:
            _fetching.discard(sid)


def fetch_outcome(sid: str, wait: float = None, step: float = None) -> bool:
    """After a call: transcript and summary from ElevenLabs, then the summary e-mail if that is allowed."""
    call = db.get_call(sid)
    a = db.get_assistant(call["assistant_id"]) if call else None
    if not a:
        return False
    deadline = time.time() + (FETCH_WAIT_S if wait is None else wait)
    while True:
        conv = None
        try:
            conv = (agents.get_conversation(call["conversation_id"]) if call["conversation_id"]
                    else agents.find_conversation(call["agent_id"] or a["agent_id"], sid))
        except Exception as e:  # noqa: BLE001 – retried until the deadline
            log.warning("find conversation: %s", str(e)[:200])
        if conv and conv.get("status") in ("done", "failed") and conv.get("analysis"):
            break
        if time.time() >= deadline:
            return False
        time.sleep(FETCH_STEP_S if step is None else step)
    o = agents.read_outcome(conv)
    db.update_call(sid, conversation_id=o["conversation_id"], summary=o["summary"], data=json.dumps(o["data"], ensure_ascii=False),
                   transcript=json.dumps(o["transcript"], ensure_ascii=False), tools=json.dumps(o["tools"], ensure_ascii=False), fetched=1)
    if call["direction"] == "outbound":
        if agents.can(a, "email_summary") and db.claim_notification(sid):
            d = o["data"]
            body = "\n".join([o["summary"] or "(bez shrnutí)", "", f"Úkol: {call['task']}", f"Výsledek: {d.get('result') or '-'}",
                               *([f"Rezervace: {d['booked_time']}"] if d.get("booked_time") else []), "", "Přepis:"]
                              + [f"{'Druhá strana' if t['who'] == 'caller' else a['name']}: {t['text']}" for t in o["transcript"]])
            if _send_mail(a, f"Hovor za vás: {call['to_number']}", body):
                db.add_action(a["id"], "email_summary", _act(call, "summary", x=_mail_target(a)), sid)
        return True
    if agents.can(a, "email_summary") and o["transcript"] and db.claim_notification(sid):
        d = o["data"]
        who = d.get("caller_name") or call["from_number"] or "neznámý volající"
        lines = [o["summary"] or "(bez shrnutí)", "", f"Volající: {who}, {call['from_number'] or 'skryté číslo'}"]
        lines += [f"Důvod: {d['reason']}"] if d.get("reason") else []
        lines += [f"Chce zavolat zpět: {d['callback_wanted']}"] if d.get("callback_wanted") else []
        lines += ["", "Přepis:"] + [f"{'Volající' if t['who'] == 'caller' else a['name']}: {t['text']}" for t in o["transcript"]]
        if _send_mail(a, f"Zmeškaný hovor: {who}", "\n".join(lines)):
            db.add_action(a["id"], "email_summary", f"Shrnutí hovoru odesláno: {who}")
    return True


# ---------- errands: the assistant calls someone for its owner ----------
class ErrandIn(BaseModel):
    to: str
    task: str


def _twilio_call(to_number: str, from_number: str, url: str) -> str:
    sid, tok = config.env("TWILIO_ACCOUNT_SID"), config.env("TWILIO_AUTH_TOKEN")
    form = {"To": to_number, "From": from_number, "Url": url, "Method": "POST", "Timeout": "30", "TimeLimit": "240",
            "StatusCallback": f"{config.public_url()}/twilio/status", "StatusCallbackMethod": "POST"}
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json", data=urllib.parse.urlencode(form).encode(),
                                 headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{tok}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)["sid"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Twilio {e.code} {e.read()[:300].decode(errors='replace')}") from None


MAX_BATCH = 5
FINAL = {"completed", "busy", "no-answer", "failed", "canceled"}


def _check_window(a: dict, new_calls: int):
    now = _now()
    if not config.OUTBOUND_HOURS[0] <= now.hour < config.OUTBOUND_HOURS[1]:
        raise HTTPException(409, f"Volat lze jen mezi {config.OUTBOUND_HOURS[0]}:00 a {config.OUTBOUND_HOURS[1]}:00")
    if db.outbound_since(a["id"], _day_start()) + new_calls > config.MAX_OUTBOUND_PER_DAY:
        raise HTTPException(429, f"Dnešní limit {config.MAX_OUTBOUND_PER_DAY} hovorů za vás by se překročil")


REPORT_LANGS = ("cs", "en", "ru")


def _place_errand(a: dict, to_raw, task_raw: str, notes_raw: str, mode: str = "errand", owner: str = "", report: str = "cs") -> dict:
    """Limits first: only Czech numbers, daytime, a few a day. The callee hears who calls and that it is automated.
    Several numbers are called one after another (the next when the previous call has ended)."""
    raw = [to_raw] if isinstance(to_raw, (str, dict)) else list(to_raw)
    numbers, seen = [], set()  # [(number, label)]: label = whom we call, e.g. the restaurant's name
    for r in raw:
        number, label = (r.get("number", ""), r.get("label", "")) if isinstance(r, dict) else (r, "")
        n = config.normalize_phone(str(number))
        if not n or not n.startswith(config.OUTBOUND_PREFIXES):
            raise HTTPException(422, f"Volat lze jen na česká čísla (+420): {str(number)[:30]}")
        if n not in seen:
            seen.add(n)
            numbers.append((n, str(label).strip()[:80].replace("{{", "(").replace("}}", ")")))
    if not numbers or len(numbers) > MAX_BATCH:
        raise HTTPException(422, f"Zadejte 1 až {MAX_BATCH} čísel")
    if mode not in agents.MODES:
        raise HTTPException(422, "Neznámý scénář")
    report = report if report in REPORT_LANGS else "cs"
    clean = lambda t: t.replace("{{", "(").replace("}}", ")")  # noqa: E731
    task = clean(_text(task_raw, "scénář", 1500))
    notes = clean(_text(notes_raw, "poznámky", 1500, required=False))
    owner = clean(_text(owner, "čí je agent", 80, required=False))
    _check_window(a, len(numbers))
    language = "en" if a["language"] == "en" else "cs"
    try:
        agent_id = agents.errand_agent(language, db.kv, mode, report)
    except Exception as e:  # noqa: BLE001
        log.error("errand agent: %s", str(e)[:300])
        raise HTTPException(502, "Hlasového agenta se nepodařilo připravit") from None
    batch_id, reports = secrets.token_urlsafe(12), []
    for n, label in numbers:
        rid = secrets.token_urlsafe(12)
        db.add_outbound("pending-" + secrets.token_hex(8), a["id"], n, a["number"], task, agent_id, notes, rid,
                        secrets.token_urlsafe(24), mode, owner, batch_id, label, report)
        reports.append(rid)
    first = db.call_by("report_id", reports[0])
    if not _dial(first):
        raise HTTPException(502, "Hovor se nepodařilo zahájit")
    sid = db.call_by("report_id", reports[0])["sid"]
    return {"sid": sid, "report": reports[0], "batch": batch_id}


def _dial(call: dict) -> bool:
    a = db.get_assistant(call["assistant_id"])
    try:
        sid = _twilio_call(call["to_number"], a["number"], f"{config.public_url()}/twilio/outbound/{a['id']}?r={call['report_id']}")
    except Exception as e:  # noqa: BLE001
        log.error("dial: %s", str(e)[:300])
        db.update_call(call["sid"], status="failed", fetched=1)
        return False
    db.rename_call(call["sid"], sid)
    db.update_call(sid, status="ringing", started_at=time.time())
    log.info("outbound call %s started (%s)", sid[-6:], call["mode"])
    return True


_dial_lock = threading.Lock()


def _dial_next(batch_id: str):
    """After a call of a batch ended: the next queued number, unless one is still running or the time window closed."""
    with _dial_lock:
        calls = db.batch(batch_id)
        if any(c["status"] in ("ringing", "in-progress") for c in calls):
            return
        for c in calls:
            if c["status"] == "queued":
                now = _now()
                if not config.OUTBOUND_HOURS[0] <= now.hour < config.OUTBOUND_HOURS[1]:
                    db.update_call(c["sid"], status="canceled", fetched=1)
                    continue
                if _dial(c):
                    return


@app.post("/api/assistants/{aid}/errands", dependencies=[Depends(login_required)])
def start_errand(aid: str, body: ErrandIn):
    a = _assistant_or_404(aid)
    return _place_errand(a, body.to, body.task, a["instructions"])


@app.post("/twilio/outbound/{aid}")
async def twilio_outbound(aid: str, request: Request, r: str = ""):
    form = await _twilio_form(request)
    sid = form.get("CallSid", "")
    call, a = db.call_by("report_id", r), db.get_assistant(aid)
    if not a or not call or call["assistant_id"] != aid or call["direction"] != "outbound":
        return _say("Omlouvám se, došlo k chybě. Na shledanou.", "cs-CZ")
    if call["sid"] != sid:  # Twilio asked before start_errand stored the real sid
        db.rename_call(call["sid"], sid)
    db.update_call(sid, status="in-progress")
    now = _now()
    variables = {"today": now.strftime("%A %Y-%m-%d %H:%M"),
                 "task": call["task"] + (f"\n(Voláš do: {call['label']})" if call["label"] else ""), "owner_name": call["owner"] or a["owner_name"],
                 "assistant_name": a["name"], "owner_notes": call["notes"] or "(nic)", "call_ref": call["call_ref"],
                 # the owner's own phone only when the call is made in their own name
                 "callback_number": a["owner_phone"] if not call["owner"] or call["owner"] == a["owner_name"] else "(nesdělovat)"}
    try:
        twiml = await asyncio.to_thread(agents.register, a, form.get("From", ""), form.get("To", ""), variables, call["agent_id"], "outbound")
    except Exception as e:  # noqa: BLE001
        log.error("register outbound failed: %s", str(e)[:300])
        db.update_call(sid, status="failed", fetched=1)
        return _say("Omlouvám se, asistent teď není dostupný. Na shledanou.", "cs-CZ")
    return Response(twiml, media_type="application/xml")


# ---------- the errand agent's tools: a booking goes to the owner's calendar, a note to their e-mail ----------
def errand_auth(request: Request, call_ref: str) -> tuple:
    token = db.kv.get("errand_tool_token")
    if not token or not secrets.compare_digest(request.headers.get("x-tool-token", "").encode(), token.encode()):
        raise HTTPException(401, "Unauthorized")
    call = db.call_by("call_ref", call_ref)
    if not call or call["direction"] != "outbound" or time.time() - call["started_at"] > 1800:
        raise HTTPException(404, "Unknown call")
    return call, db.get_assistant(call["assistant_id"])


def _mail_target(a: dict) -> str:
    return a["google_email"] if google.has(a, google.SCOPE_GMAIL_SEND) else a["notify_email"]


def _ics(uid: str, start: datetime, minutes: int, title: str, description: str) -> str:
    fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
    esc = lambda t: t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")  # noqa: E731
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jsemvcas//asistent//CS", "METHOD:PUBLISH", "BEGIN:VEVENT",
                         f"UID:{uid}@asistent.jsemvcas.cz", f"DTSTAMP:{fmt(_now())}", f"DTSTART:{fmt(start)}",
                         f"DTEND:{fmt(start + timedelta(minutes=minutes))}", f"SUMMARY:{esc(title)}", f"DESCRIPTION:{esc(description)}",
                         "END:VEVENT", "END:VCALENDAR", ""])


# Activity lines written during a call, in the language of its report.
ACT = {
    "cs": {"booking": "Rezervace {when}: {place}", "to_google": " → Google Kalendář ({x})", "to_ics": " → pozvánka .ics e-mailem ({x})",
           "here": " (jen zapsáno zde)", "pledge": "{who} přispěje {n} Kč", "message": "Vzkaz pro vás: {x}", "mail": " → e-mail {x}",
           "mail_failed": " (e-mail nešel odeslat)", "summary": "Výsledek hovoru odeslán e-mailem: {x}"},
    "en": {"booking": "Booking {when}: {place}", "to_google": " → Google Calendar ({x})", "to_ics": " → .ics invitation by e-mail ({x})",
           "here": " (recorded here only)", "pledge": "{who} pledged {n} CZK", "message": "Message for you: {x}", "mail": " → e-mail {x}",
           "mail_failed": " (e-mail could not be sent)", "summary": "Call result sent by e-mail: {x}"},
    "ru": {"booking": "Бронь {when}: {place}", "to_google": " → Google Календарь ({x})", "to_ics": " → приглашение .ics на e-mail ({x})",
           "here": " (записано только здесь)", "pledge": "{who} обещал(а) {n} Kč", "message": "Сообщение вам: {x}", "mail": " → e-mail {x}",
           "mail_failed": " (e-mail не отправлен)", "summary": "Итог звонка отправлен на e-mail: {x}"},
}


def _act(call: dict, key: str, **kw) -> str:
    return ACT.get(call.get("report_lang") or "cs", ACT["cs"])[key].format(**kw)


class BookingIn(BaseModel):
    call_ref: str
    day_time: str
    details: str = ""
    people: Optional[int] = None
    place: str = ""


@app.post("/tools/errand/booking")
def errand_booking(body: BookingIn, request: Request):
    call, a = errand_auth(request, body.call_ref)
    if call["mode"] not in agents.BOOKING_MODES:  # an inquiry or a sales call never books, whatever the model does
        return {"ok": False, "error": "Booking is not part of this call."}
    try:
        start = datetime.fromisoformat(body.day_time.strip().replace(" ", "T")[:16]).replace(tzinfo=config.TZ)
    except ValueError:
        return {"ok": False, "error": "Use YYYY-MM-DD HH:MM."}
    if db.actions_since(a["id"], "booking", time.time() - 1800) >= 3:
        return {"ok": True, "note": "Already recorded."}
    place = body.place.strip()[:80] or call["to_number"]
    people = f", {body.people} os." if body.people else ""
    title = f"Rezervace: {place}{people}"[:150]
    details = f"{body.details.strip()[:1000]}\n\nZařídil telefonní asistent {a['name']} ({call['to_number']})."
    where = ""
    if google.has(a, google.SCOPE_EVENTS):
        try:
            google.create_event(a, start, 120, title, details)
            where = _act(call, "to_google", x=a["google_email"])
        except Exception as e:  # noqa: BLE001
            log.error("booking event: %s", str(e)[:200])
    if not where and _mail_target(a) and _send_mail(a, f"{title}, {start.strftime('%d.%m. %H:%M')}", details, _ics(call["call_ref"][:16], start, 120, title, details)):
        where = _act(call, "to_ics", x=_mail_target(a))
    db.add_action(a["id"], "booking", _act(call, "booking", when=start.strftime("%d.%m. %H:%M"), place=place + people) + (where or _act(call, "here")), call["sid"])
    return {"ok": True}


class PledgeIn(BaseModel):
    call_ref: str
    amount_czk: int
    name: str = ""
    note: str = ""


@app.post("/tools/errand/pledge")
def errand_pledge(body: PledgeIn, request: Request):
    call, a = errand_auth(request, body.call_ref)
    if call["mode"] != "sales":
        return {"ok": False, "error": "Not part of this call."}
    if not 0 < body.amount_czk <= 100000:
        return {"ok": False, "error": "Amount must be between 1 and 100000 CZK."}
    if any(x["kind"] == "pledge" for x in db.actions_of_call(call["sid"])):
        return {"ok": True, "note": "Already recorded."}
    who = body.name.strip()[:80] or call["to_number"]
    db.add_action(a["id"], "pledge", _act(call, "pledge", who=who, n=body.amount_czk) + (f": {body.note.strip()[:200]}" if body.note.strip() else ""), call["sid"])
    return {"ok": True}


class NotifyIn(BaseModel):
    call_ref: str
    text: str


@app.post("/tools/errand/notify")
def errand_notify(body: NotifyIn, request: Request):
    call, a = errand_auth(request, body.call_ref)
    if db.actions_since(a["id"], "message", _day_start()) >= config.MAX_MESSAGES_PER_DAY:
        return {"ok": False, "error": "Too many messages today."}
    sent = bool(_mail_target(a)) and _send_mail(a, f"Asistent volá {call['to_number']}: potřebuje vás", body.text.strip()[:1000])
    db.add_action(a["id"], "message", _act(call, "message", x=body.text.strip()[:200]) + (_act(call, "mail", x=_mail_target(a)) if sent else _act(call, "mail_failed")), call["sid"])
    return {"ok": sent}


# ---------- live report of one call ----------
_live_lock = threading.Lock()


def _refresh_live(call: dict):
    """While a call runs, at most every 3 s: transcript and tool calls so far from ElevenLabs."""
    with _live_lock:
        if time.time() - call["live_at"] < 3:
            return
        db.update_call(call["sid"], live_at=time.time())
    a = db.get_assistant(call["assistant_id"])
    try:
        conv = (agents.get_conversation(call["conversation_id"]) if call["conversation_id"]
                else agents.find_conversation(call["agent_id"] or a["agent_id"], call["sid"]))
    except Exception as e:  # noqa: BLE001
        log.warning("live: %s", str(e)[:200])
        return
    if conv:
        l = agents.live(conv)  # noqa: E741
        db.update_call(call["sid"], conversation_id=l["conversation_id"], transcript=json.dumps(l["transcript"], ensure_ascii=False),
                       tools=json.dumps(l["tools"], ensure_ascii=False))


def _report(call: dict) -> dict:
    a = db.get_assistant(call["assistant_id"]) or {}
    return {"report": call["report_id"], "status": call["status"], "duration": call["duration"], "to": call["to_number"], "from": call["from_number"],
            "label": call["label"],
            "mode": call["mode"], "lang": call["report_lang"], "owner": call["owner"] or a.get("owner_name", ""), "assistant": a.get("name", ""),
            "task": call["task"], "notes": call["notes"], "startedAt": call["started_at"], "ready": bool(call["fetched"]),
            "summary": call["summary"], "data": json.loads(call["data"]), "transcript": json.loads(call["transcript"]),
            "tools": json.loads(call["tools"]), "actions": [{"kind": x["kind"], "detail": x["detail"], "at": x["at"]} for x in db.actions_of_call(call["sid"])]}


async def _fresh(call: dict) -> dict:
    if call["status"] == "in-progress" and not call["fetched"]:
        await asyncio.to_thread(_refresh_live, call)
    elif call["status"] == "completed" and not call["fetched"]:
        _schedule_fetch(call["sid"])
    return db.call_by("report_id", call["report_id"])


@app.get("/api/report/{rid}")
async def report(rid: str):
    """Anyone with the link sees it, like a shared document; the link is random and not indexed."""
    call = db.call_by("report_id", rid)
    if not call:
        raise HTTPException(404, "Report neexistuje")
    return {"calls": [_report(await _fresh(call))]}


@app.get("/api/batch/{bid}")
async def batch_report(bid: str):
    calls = db.batch(bid)
    if not calls:
        raise HTTPException(404, "Report neexistuje")
    return {"calls": [_report(await _fresh(c)) for c in calls]}


# ---------- the demo page (zavolej.jsemvcas.cz): one configured assistant, a number, a task ----------
class DemoIn(BaseModel):
    to: list
    task: str
    notes: str = ""
    mode: str = "errand"
    owner: str = ""
    report_lang: str = "cs"


def _demo_assistant() -> dict:
    a = db.get_assistant(config.env("ASSISTANT_DEMO_ID"))
    if not a:
        raise HTTPException(503, "Demo asistent není nastavený")
    return a


def _demo_targets() -> list:
    return [n for n in (config.normalize_phone(x) for x in config.env("ASSISTANT_DEMO_TARGETS").split(",")) if n]


@app.get("/api/demo")
def demo_info(request: Request):
    """Open without the access code; without it, calls go only to the demo's own test numbers (demo_call)."""
    a = _demo_assistant()
    return {"assistant": a["name"], "owner": a["owner_name"], "number": a["number"], "notes": config.env("ASSISTANT_DEMO_NOTES") or a["instructions"],
            "mail": _mail_target(a), "googleCalendar": google.has(a, google.SCOPE_EVENTS),
            # preset numbers the demo form fills in (test phones), from assistant/.env, never in the code
            "targets": _demo_targets(), "signedIn": _signed_in(request)}


@app.post("/api/demo/call")
def demo_call(body: DemoIn, request: Request):
    if not _signed_in(request):  # a public page must not ring strangers: only the preset test phones
        allowed = set(_demo_targets())
        wanted = [config.normalize_phone(str(x.get("number", "") if isinstance(x, dict) else x)) for x in body.to]
        if not allowed or not wanted or any(n not in allowed for n in wanted):
            raise HTTPException(403, "Bez přístupového kódu lze volat jen na testovací čísla dema")
    return _place_errand(_demo_assistant(), [x if isinstance(x, dict) else str(x) for x in body.to][:20], body.task, body.notes, body.mode, body.owner, body.report_lang)


# ---------- tools the voice agent calls during a call ----------
def tool_auth(aid: str, request: Request) -> dict:
    a = db.get_assistant(aid)
    token = request.headers.get("x-tool-token", "")
    if not a or not secrets.compare_digest(token.encode(), a["tool_token"].encode()):
        raise HTTPException(401, "Unauthorized")
    return a


NOT_ALLOWED = {"ok": False, "error": "This is not allowed for this assistant. Offer to take a message."}
UNAVAILABLE = {"ok": False, "error": "The calendar is not available right now. Offer to take a message."}


class AvailabilityIn(BaseModel):
    date: str


@app.post("/tools/{aid}/availability")
def tool_availability(body: AvailabilityIn, a: dict = Depends(tool_auth)):
    if not agents.can(a, "calendar_read"):
        return NOT_ALLOWED
    try:
        day = date_cls.fromisoformat(body.date.strip()[:10])
    except ValueError:
        return {"ok": False, "error": "Use the date format YYYY-MM-DD."}
    now = _now()
    if day < now.date() or day > now.date() + timedelta(days=60):
        return {"ok": False, "error": "Only today and the next 60 days can be checked."}
    start = datetime(day.year, day.month, day.day, tzinfo=config.TZ)
    try:
        busy = google.busy(a, start, start + timedelta(days=1))
    except Exception as e:  # noqa: BLE001
        log.error("freebusy %s: %s", a["id"][:6], str(e)[:200])
        return UNAVAILABLE
    windows = google.free_windows(day, busy, now)
    return {"ok": True, "date": day.isoformat(), "weekday": day.strftime("%A"), "working_hours": f"{config.WORK_START}:00-{config.WORK_END}:00, Monday to Friday",
            "free": [{"from": s.strftime("%H:%M"), "to": e.strftime("%H:%M")} for s, e in windows]}


class BookIn(BaseModel):
    start: str
    duration_minutes: int = 30
    caller_name: str
    topic: str
    caller_phone: str = ""


def _day_start() -> float:
    return _now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


@app.post("/tools/{aid}/book")
def tool_book(body: BookIn, a: dict = Depends(tool_auth)):
    """Everything is checked here, whatever the model decided: the permission, the limits, working hours, a free slot."""
    if not agents.can(a, "calendar_book"):
        return NOT_ALLOWED
    if db.actions_since(a["id"], "booking", _day_start()) >= config.MAX_BOOKINGS_PER_DAY:
        return {"ok": False, "error": "No more bookings are possible today. Offer to take a message."}
    try:
        start = datetime.fromisoformat(body.start.strip().replace("Z", "+00:00"))
    except ValueError:
        return {"ok": False, "error": "Use the format YYYY-MM-DDTHH:MM."}
    start = start.replace(tzinfo=config.TZ) if start.tzinfo is None else start.astimezone(config.TZ)
    minutes, now = body.duration_minutes, _now()
    end = start + timedelta(minutes=minutes)
    if not 15 <= minutes <= 60:
        return {"ok": False, "error": "A meeting can take 15 to 60 minutes."}
    if start <= now or start > now + timedelta(days=60):
        return {"ok": False, "error": "The time must be in the next 60 days."}
    if start.weekday() >= 5 or start.hour < config.WORK_START or end > start.replace(hour=config.WORK_END, minute=0, second=0, microsecond=0):
        return {"ok": False, "error": "That is outside working hours. Check availability and offer another time."}
    name, topic = body.caller_name.strip()[:80] or "?", body.topic.strip()[:120]
    try:
        if google.busy(a, start, end):
            return {"ok": False, "error": "That time is already taken. Check availability and offer another time."}
        google.create_event(a, start, minutes, f"Hovor: {name} – {topic}"[:150],
                            f"Zapsal telefonní asistent {a['name']}.\nVolající: {name}, {body.caller_phone.strip()[:30] or 'číslo neuvedeno'}\nTéma: {topic}")
    except Exception as e:  # noqa: BLE001
        log.error("booking %s: %s", a["id"][:6], str(e)[:200])
        return UNAVAILABLE
    db.add_action(a["id"], "booking", f"Schůzka {start.strftime('%d.%m. %H:%M')}: {name}, {topic}")
    return {"ok": True, "booked": start.strftime("%A %Y-%m-%d %H:%M"), "minutes": minutes}


class MessageIn(BaseModel):
    text: str
    caller_name: str = ""
    caller_phone: str = ""


@app.post("/tools/{aid}/message")
def tool_message(body: MessageIn, a: dict = Depends(tool_auth)):
    """To the owner only: the recipient is not a parameter, so a caller cannot use this to mail anyone else."""
    if not agents.can(a, "email_message"):
        return NOT_ALLOWED
    if db.actions_since(a["id"], "message", _day_start()) >= config.MAX_MESSAGES_PER_DAY:
        return {"ok": False, "error": "Too many messages today. Tell the caller it will be in the call summary."}
    who = body.caller_name.strip()[:80] or "neznámý volající"
    if not _send_mail(a, f"Vzkaz z telefonu: {who}", f"{body.text.strip()[:1000]}\n\nVolající: {who}, {body.caller_phone.strip()[:30] or 'číslo neuvedeno'}"):
        return {"ok": False, "error": "The message could not be sent. Tell the caller it will be in the call summary."}
    db.add_action(a["id"], "message", f"Vzkaz od: {who}")
    return {"ok": True}


# ---------- page ----------
def _html(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC / name).read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return _html("landing.html" if request.headers.get("host", "").startswith("zavolej.") else "index.html")


@app.get("/demo", response_class=HTMLResponse)
def demo_page():
    return _html("demo.html")


@app.get("/a/{aid}", response_class=HTMLResponse)
def page(aid: str = ""):
    return _html("index.html")


@app.get("/r/{rid}", response_class=HTMLResponse)
@app.get("/b/{rid}", response_class=HTMLResponse)
def report_page(rid: str = ""):
    return _html("report.html")


@app.get("/base.css")
def base_css():
    return Response((STATIC / "base.css").read_text(encoding="utf-8"), media_type="text/css", headers={"Cache-Control": "max-age=300"})
