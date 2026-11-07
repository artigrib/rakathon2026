"""Google: OAuth with the smallest scopes that work, free/busy, creating events, sending mail to the owner.

The mailbox is never read and calendar contents never leave Google: a phone caller is an unauthenticated stranger, so
the assistant can only learn free time, add an event without guests and write to the owner.
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage

from . import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CAL = "https://www.googleapis.com/calendar/v3"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

SCOPE_FREEBUSY = "https://www.googleapis.com/auth/calendar.freebusy"
SCOPE_EVENTS = "https://www.googleapis.com/auth/calendar.events"
SCOPE_GMAIL_SEND = "https://www.googleapis.com/auth/gmail.send"
WANT = {"calendar": [SCOPE_FREEBUSY, SCOPE_EVENTS], "mail": [SCOPE_GMAIL_SEND]}
STATE_TTL = 600


class GoogleError(Exception):
    pass


def secret() -> bytes:
    s = config.env("ASSISTANT_SECRET")
    if not s:
        raise GoogleError("ASSISTANT_SECRET is not set")
    return s.encode()


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"google-token:" + secret()).digest()))


def seal(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def unseal(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()


def redirect_uri() -> str:
    return f"{config.public_url()}/oauth/google/callback"


def make_state(aid: str, want: str, now: float = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"a": aid, "w": want, "t": int(now or time.time())}).encode()).decode()
    return body + "." + hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()


def read_state(state: str, now: float = None):
    body, _, sig = (state or "").partition(".")
    if not hmac.compare_digest(sig, hmac.new(secret(), body.encode(), hashlib.sha256).hexdigest()):
        return None
    d = json.loads(base64.urlsafe_b64decode(body))
    return d if (now or time.time()) - d["t"] <= STATE_TTL else None


def auth_url(aid: str, want: list) -> str:
    scopes = ["openid", "email"] + [s for w in want for s in WANT[w]]
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": config.env("GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent", "state": make_state(aid, ",".join(want)),
    })


def _http(method: str, url: str, headers: dict = None, form: dict = None, body: dict = None) -> dict:
    data, h = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
    elif body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h), timeout=10) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise GoogleError(f"{url.split('?')[0]}: {e.code} {e.read()[:200].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise GoogleError(f"{url.split('?')[0]}: {e.reason}") from None


def exchange_code(code: str) -> dict:
    """→ {refresh_token, scopes, email}."""
    t = _http("POST", TOKEN_URL, form={"code": code, "client_id": config.env("GOOGLE_CLIENT_ID"), "grant_type": "authorization_code",
                                       "client_secret": config.env("GOOGLE_CLIENT_SECRET"), "redirect_uri": redirect_uri()})
    if not t.get("refresh_token"):
        raise GoogleError("Google returned no refresh token")
    who = _http("GET", USERINFO_URL, headers={"Authorization": f"Bearer {t['access_token']}"})
    return {"refresh_token": t["refresh_token"], "scopes": t.get("scope", ""), "email": who.get("email", "")}


def _access(a: dict) -> str:
    if not a["google_token"]:
        raise GoogleError("not connected")
    return _http("POST", TOKEN_URL, form={"refresh_token": unseal(a["google_token"]), "grant_type": "refresh_token",
                                          "client_id": config.env("GOOGLE_CLIENT_ID"),
                                          "client_secret": config.env("GOOGLE_CLIENT_SECRET")})["access_token"]


def revoke(a: dict):
    if a["google_token"]:
        _http("POST", REVOKE_URL, form={"token": unseal(a["google_token"])})


def has(a: dict, scope: str) -> bool:
    return scope in (a["google_scopes"] or "").split()


def busy(a: dict, start: datetime, end: datetime) -> list:
    """Busy intervals of the primary calendar as (start, end) datetimes in the local zone. Titles are never requested."""
    r = _http("POST", f"{CAL}/freeBusy", headers={"Authorization": f"Bearer {_access(a)}"}, body={
        "timeMin": start.isoformat(), "timeMax": end.isoformat(), "timeZone": str(config.TZ), "items": [{"id": "primary"}]})
    out = []
    for b in r.get("calendars", {}).get("primary", {}).get("busy", []):
        out.append((datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(config.TZ),
                    datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(config.TZ)))
    return out


def free_windows(day, busy_list: list, now: datetime) -> list:
    """Free (start, end) within working hours of one date. Closed at weekends; the past of today is not free."""
    if day.weekday() >= 5:
        return []
    start = datetime(day.year, day.month, day.day, config.WORK_START, tzinfo=config.TZ)
    end = datetime(day.year, day.month, day.day, config.WORK_END, tzinfo=config.TZ)
    cur, out = max(start, now), []
    for b_start, b_end in sorted(busy_list):
        if b_start > cur:
            out.append((cur, min(b_start, end)))
        cur = max(cur, b_end)
    if cur < end:
        out.append((cur, end))
    return [(s, e) for s, e in out if e - s >= timedelta(minutes=15)]


def create_event(a: dict, start: datetime, minutes: int, title: str, description: str) -> str:
    """No attendees and no notifications, so a caller cannot make the owner's Google send anything to anyone."""
    r = _http("POST", f"{CAL}/calendars/primary/events?sendUpdates=none", headers={"Authorization": f"Bearer {_access(a)}"}, body={
        "summary": title, "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": str(config.TZ)},
        "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat(), "timeZone": str(config.TZ)},
    })
    return r.get("id", "")


def send_to_self(a: dict, message: EmailMessage):
    message["From"] = message["To"] = a["google_email"]
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    _http("POST", GMAIL_SEND_URL, headers={"Authorization": f"Bearer {_access(a)}"}, body={"raw": raw})
