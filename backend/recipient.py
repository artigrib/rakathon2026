"""Where real demo messages go. The challenge data has synthetic phone numbers, so every live SMS, WhatsApp, call and
e-mail goes to one demo recipient: DEMO_TO / DEMO_EMAIL from .env by default, or the phone and e-mail a presenter
sets in the demo panel (stored next to the app state, survives restarts).

Guard rails, because anyone with the demo password can set a number: only DEMO_ALLOWED_PREFIXES (default +420, the
country with Twilio geo permissions; no premium or foreign numbers) and at most DEMO_DAILY_LIMIT live sends a day to
one recipient.
"""
import json
import os
import re
import threading
from pathlib import Path

from .settings import settings

PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_lock = threading.Lock()


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


def phone() -> str:
    return _load().get("phone") or settings.demo_to


def email() -> str:
    return _load().get("email") or settings.demo_email


def normalize_phone(raw: str) -> str:
    p = re.sub(r"[\s\-().]", "", raw or "")
    if p.startswith("00"):
        p = "+" + p[2:]
    if p and not p.startswith("+") and len(p) == 9:  # Czech number typed without the country code
        p = "+420" + p
    return p


def save(raw_phone: str, raw_email: str) -> dict:
    """Validate and store. Empty value = back to the default from .env. Raises ValueError with a Czech message."""
    p, e = normalize_phone(raw_phone), (raw_email or "").strip()
    if p and not PHONE.match(p):
        raise ValueError("Telefon zadejte s předvolbou, např. +420 601 234 567.")
    if p and not any(p.startswith(x) for x in prefixes()):
        raise ValueError(f"Povolená jsou jen čísla s předvolbou {', '.join(prefixes())}.")
    if e and not EMAIL.match(e):
        raise ValueError("Zadejte platný e-mail.")
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
    """For the demo panel. The default recipient (Artem) is masked; a number the presenter typed is shown as typed."""
    own = _load()
    return {
        "phone": own.get("phone") or _mask_phone(settings.demo_to),
        "email": own.get("email") or _mask_email(settings.demo_email),
        "customPhone": bool(own.get("phone")),
        "customEmail": bool(own.get("email")),
        "prefixes": prefixes(),
        "dailyLimit": daily_limit(),
        "whatsappFrom": settings.whatsapp_from,
        "whatsappJoin": os.getenv("WHATSAPP_JOIN", ""),
    }
