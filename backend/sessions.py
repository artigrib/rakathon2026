"""Visitor sign-in for the demo: access code + the visitor's own phone and e-mail (where their test messages go).

A session is a random token in an HttpOnly cookie; the server keeps {phone, email, created} next to the app state.
Contacts are kept only for sending demo messages and are deleted after MAX_AGE_DAYS.
"""
import json
import secrets
import threading
import time
from pathlib import Path

from .settings import settings

COOKIE = "jv_session"
MAX_AGE_DAYS = 30
_lock = threading.Lock()


def _file() -> Path:
    return Path(settings.state_file).with_name("sessions.json")


def _load() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cutoff = time.time() - MAX_AGE_DAYS * 86400
    return {t: s for t, s in data.items() if s.get("created", 0) > cutoff}   # expired sessions are dropped


def _save(data: dict):
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), encoding="utf-8")


def create(phone: str, email: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock:
        data = _load()
        data[token] = {"phone": phone, "email": email, "created": time.time()}
        _save(data)
    return token


def get(token):
    return _load().get(token) if token else None


def update(token: str, phone: str, email: str):
    with _lock:
        data = _load()
        if token in data:
            data[token].update(phone=phone, email=email)
            _save(data)


def delete(token):
    with _lock:
        data = _load()
        if data.pop(token or "", None) is not None:
            _save(data)


def sid(token: str) -> str:
    """Short public id of a session (callback URLs, state file names). Not the cookie token."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def by_sid(session_id: str):
    """(token, session) for a short id from a callback URL, or (None, None)."""
    for t, s in _load().items():
        if sid(t) == session_id:
            return t, s
    return None, None


def by_phone(phone: str):
    """(token, session) of the latest visitor who signed in with this phone: inbound SMS / WhatsApp replies."""
    hits = [(s["created"], t, s) for t, s in _load().items() if s.get("phone") == phone]
    return max(hits)[1:] if hits else (None, None)
