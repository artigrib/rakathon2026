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


def with_link(text: str, url: str) -> str:
    """Texts composed in the web app carry a marker where the patient's personal link goes."""
    if url:
        return text.replace(MARKER, url)
    for part in ("link", "link_short"):  # no public URL (mock mode): drop the whole link sentence
        text = text.replace(_fill(M["parts"][part], {"url": MARKER}), "")
    return text
