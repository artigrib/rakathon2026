"""Settings, read from the environment on every use so tests can change them."""
import os
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("ASSISTANT_TZ", "Europe/Prague"))
WORK_START, WORK_END = 9, 17  # working hours offered to callers, Monday to Friday
MAX_ASSISTANTS = 20
MAX_CALLS_PER_DAY = 50        # per number: a public number must not be able to drain the voice credits
MAX_BOOKINGS_PER_DAY = 5      # per assistant
MAX_MESSAGES_PER_DAY = 20     # per assistant
MAX_OUTBOUND_PER_DAY = 10     # per assistant: calls it places for its owner
OUTBOUND_PREFIXES = ("+420",)  # only Czech numbers can be called
OUTBOUND_HOURS = (8, 21)      # Prague time; nobody gets a robot call at night
RETENTION_DAYS = 30           # calls and activity are deleted after this


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def public_url() -> str:
    return env("PUBLIC_URL").rstrip("/")


def numbers() -> list:
    return [n.strip() for n in env("ASSISTANT_NUMBERS").split(",") if n.strip()]


def google_ready() -> bool:
    return bool(env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"))


def smtp_ready() -> bool:
    return bool(env("SMTP_HOST") and env("SMTP_USER") and env("SMTP_PASSWORD"))


def normalize_phone(raw: str, default_cc: str = "+420") -> str:
    """'+420 777 123 456', '00420777123456', '777123456' → '+420777123456'. '' when it is not a phone number."""
    p = re.sub(r"[\s\-().]", "", raw or "")
    if p.startswith("00"):
        p = "+" + p[2:]
    if re.fullmatch(r"\d{9}", p):
        p = default_cc + p
    return p if re.fullmatch(r"\+[1-9]\d{7,14}", p) else ""
