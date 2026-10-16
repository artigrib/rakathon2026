"""Render patient messages from the same JSON the web app uses (web/app/content/messages.cs.json)."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "web/app/content/messages.cs.json").read_text(encoding="utf-8"))
PRACTICE_PHONE = os.getenv("PRACTICE_PHONE", "")  # shown in texts when set (deck slide 20)
MARKER = M["parts"]["link_marker"]


def _fill(tpl: str, vars: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: vars.get(m.group(1), m.group(0)), tpl)


def render(patient: dict, channel: str, variant: str = "FIRST_INVITE", url: str = "") -> str:
    kind = M["channel_template"].get(channel, "email")
    tpl = M[kind].get(variant) or M[kind]["FIRST_INVITE"]
    return _fill(tpl, {
        "gp": patient.get("gp") or "",
        "contact": M["parts"]["contact_with_pneu" if patient.get("pneu") else "contact"],
        "call_us": _fill(M["parts"]["call_us"], {"phone": PRACTICE_PHONE}) if PRACTICE_PHONE else "",
        "link": _fill(M["parts"]["link"], {"url": url}) if url else "",
        "link_short": _fill(M["parts"]["link_short"], {"url": url}) if url else "",
    })


def with_link(text: str, url: str, channel: str = "") -> str:
    """Personal reply link. Old texts may carry a marker; texts from the web app get the link appended
    (SMS / WhatsApp short form, e-mail long form, nothing for a call)."""
    if url and MARKER in text:
        return text.replace(MARKER, url)
    if url and url not in text and channel in ("sms", "whatsapp", "email"):
        part = M["parts"]["link" if channel == "email" else "link_short"]
        return text.rstrip() + _fill(part, {"url": url})
    if url:
        return text
    for part in ("link", "link_short"):  # no public URL (mock mode): drop the whole link sentence
        text = text.replace(_fill(M["parts"][part], {"url": MARKER}), "")
    return text


def to_gsm(text: str) -> str:
    """Strip diacritics so the SMS uses the GSM alphabet (160 chars per segment, not 70)."""
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def sms_trial() -> str:
    """Short invite for a Twilio trial account: 38 chars of trial prefix + this must fit 160."""
    return to_gsm(M["sms"]["TRIAL"])


def sms_reply(intent: str, stage: str) -> str:
    """Short confirmation for an inbound SMS. None for opt-out: Twilio answers STOP itself."""
    if intent == "opt_out":
        return ""
    t = M["sms_reply"].get(stage) or M["sms_reply"]["callback"]
    from .settings import settings
    return to_gsm(t) if settings.trial else t
