"""Where real demo messages go. The challenge data has synthetic phone numbers, so every live SMS, WhatsApp, call and
e-mail goes to a demo recipient: the signed-in visitor's own phone and e-mail (sessions.py, entered on /login),
else what was set in the demo panel without a session, else DEMO_TO / DEMO_EMAIL from .env.

Guard rails, because anyone with the demo password can set a number: only DEMO_ALLOWED_PREFIXES (default +420, the
country with Twilio geo permissions; no premium or foreign numbers) and at most DEMO_DAILY_LIMIT live sends a day to
one recipient.
"""
import json
import os
import re
import threading
from contextvars import ContextVar
from pathlib import Path

from .settings import settings

PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_lock = threading.Lock()
_visitor: ContextVar = ContextVar("visitor", default=None)   # {"phone", "email", "token"} of the signed-in visitor


def use(visitor):
    """Set by the auth middleware for the current request; sends in this request go to this visitor."""
    _visitor.set(visitor)


def _file() -> Path:
    return Path(settings.state_file).with_name("recipient.json")


def _load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def prefixes() -> list:
    return [p.strip() for p in os.getenv("DEMO_ALLOWED_PREFIXES", "+420").split(",") if p.strip()]


def daily_limit() -> int:
    return int(os.getenv("DEMO_DAILY_LIMIT", "30"))


def take(to: str, day: str) -> bool:
    """Count one live send to `to` on `day`; False when the daily limit is reached. Shared by all visitors' demos,
    so signing in again with the same number does not reset it."""
    f = Path(settings.state_file).with_name("sent-today.json")
    with _lock:
        try:
            counts = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts = {}
        counts = {day: counts.get(day, {})}            # keep only today
        n = counts[day].get(to, 0)
        if n >= daily_limit():
            return False
        counts[day][to] = n + 1
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(counts), encoding="utf-8")
    return True


def phone() -> str:
    v = _visitor.get() or {}
    return v.get("phone") or _load().get("phone") or settings.demo_to


def email() -> str:
    v = _visitor.get() or {}
    return v.get("email") or _load().get("email") or settings.demo_email


def normalize_phone(raw: str) -> str:
    p = re.sub(r"[\s\-().]", "", raw or "")
    if p.startswith("00"):
        p = "+" + p[2:]
    if p and not p.startswith("+") and len(p) == 9:  # Czech number typed without the country code
        p = "+420" + p
    return p


def validate(raw_phone: str, raw_email: str, required: bool = False):
    """(phone, email) normalised, or ValueError with a Czech message. required: both must be filled (sign-in)."""
    p, e = normalize_phone(raw_phone), (raw_email or "").strip()
    if required and not p:
        raise ValueError("Zadejte telefon, na který pošleme ukázkové SMS a zavoláme.")
    if required and not e:
        raise ValueError("Zadejte e-mail, na který pošleme ukázkový e-mail.")
    if p and not PHONE.match(p):
        raise ValueError("Telefon zadejte s předvolbou, např. +420 601 234 567.")
    if p and not any(p.startswith(x) for x in prefixes()):
        raise ValueError(f"Povolená jsou jen čísla s předvolbou {', '.join(prefixes())}.")
    if e and not EMAIL.match(e):
        raise ValueError("Zadejte platný e-mail.")
    return p, e


def save(raw_phone: str, raw_email: str) -> dict:
    """Demo panel. Signed-in visitor: updates their own contacts. Without a session: the shared setting
    (empty = back to .env). Raises ValueError with a Czech message."""
    v = _visitor.get()
    p, e = validate(raw_phone, raw_email, required=bool(v))
    if v:
        from . import sessions
        sessions.update(v["token"], p, e)
        _visitor.set({**v, "phone": p, "email": e})
        return public()
    with _lock:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"phone": p, "email": e}), encoding="utf-8")
    return public()


def _mask_phone(p: str) -> str:
    return f"{p[:4]} *** *** {p[-3:]}" if len(p) > 7 else ""   # UI copy: no ellipsis or bullets


def _mask_email(e: str) -> str:
    name, _, domain = e.partition("@")
    return f"{name[:1]}***@{domain}" if domain else ""


def public() -> dict:
    """For the demo panel. A visitor sees their own contacts; the default recipient (Artem) is masked."""
    v = _visitor.get()
    own = {"phone": v["phone"], "email": v["email"]} if v else _load()
    return {
        "session": bool(v),
        "phone": own.get("phone") or _mask_phone(settings.demo_to),
        "email": own.get("email") or _mask_email(settings.demo_email),
        "customPhone": bool(own.get("phone")),
        "customEmail": bool(own.get("email")),
        "prefixes": prefixes(),
        "dailyLimit": daily_limit(),
        "whatsappFrom": settings.whatsapp_from,
        "whatsappJoin": os.getenv("WHATSAPP_JOIN", ""),
    }
