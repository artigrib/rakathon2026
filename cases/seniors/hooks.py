"""Jsem v pořádku hooks called by the core (backend/messages.py, backend/app.py).

What on_reply stores in decisions[pid] (visible in the web app as store.get(id).<field>):
  mood, moodDate            latest mood 1–5 (absolute words, or the last mood moved by mood_delta -1/0/+1)
  health                    {date, intent} only for a real health_problem / emergency / crisis (an alert)
  health_note               {date, text} a chronic or mild complaint ("bolí mě kolena"), the calls go on
  needs                     [{id, item, date, status: "new"}] the basket (statuses ordered / done are the mark "basket")
  pause                     {date, until, reason} after intent pause ("jsem v nemocnici do neděle")
  schedule_note             {date, note, when} after intent schedule_change ("stačí jednou týdně")
  human_request             {date} after intent human (wants a person, not a robot)
  crisis                    {date, lines, sms} after intent crisis: the crisis lines to send the senior (sms variant CRISIS)
  emergency                 {date, kind: medical|fire, sms} after intent emergency: the SMS for the relative (EMERGENCY_RELATIVE)"""
import re

from . import dialog

MOOD_OF_INTENT = {"ok": 4, "low_mood": 2, "crisis": 1}  # when the answer itself says nothing about mood
DEFAULT_WORKER = "Vaše sociální pracovnice"


def extra_placeholders(patient: dict, M: dict) -> dict:
    """{name}: ', paní Nováková' / ', pane Nováku' (vocative, empty without a record), {senior}: 'paní Marie Nováková',
    {worker}: the social worker (a generic fallback, so a sentence never ends in nothing), {relative}: the relative's name,
    {crisis_lines}: the crisis phone lines."""
    voc = patient.get("vocative") or ""
    rel = patient.get("relative") or {}
    return {
        "name": f", {voc}" if voc else "",
        "senior": patient.get("title") or "Váš blízký",
        "worker": patient.get("worker") or DEFAULT_WORKER,
        "relative": (rel.get("name") if isinstance(rel, dict) else None) or "",
        "crisis_lines": dialog.CRISIS_LINES,
    }


def _items(raw) -> list:
    """Item keys from the event extra: a list of keys, or free words / a comma string from the AI or the voice agent."""
    if isinstance(raw, str):
        raw = [s for s in re.split(r"[,;]", raw) if s.strip()]
    out = []
    for x in raw or []:
        x = str(x).strip()
        keys = [x] if x in dialog.ITEMS else dialog.items_of(x) or (["jine"] if x else [])
        out += [k for k in keys if k not in out]
    return out


def _int(raw):
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _mood(extra: dict, intent: str, last):
    """Absolute mood 1–5; or the last stored mood (default 3) moved by mood_delta; or the intent's default."""
    m = _int(extra.get("mood"))
    if m is not None and 1 <= m <= 5:
        return m
    delta = _int(extra.get("mood_delta"))
    if delta is not None and -1 <= delta <= 1:
        base = last if isinstance(last, int) and 1 <= last <= 5 else 3
        return max(1, min(5, base + delta))
    return MOOD_OF_INTENT.get(intent)


def _yes(v) -> bool:
    return v in (True, "true", "ano", "yes", 1, "1", "True")


def on_reply(pid: str, intent: str, extra: dict, store) -> None:
    """Keep what the senior said for the social service: latest mood, health alert or note, the needs basket,
    a pause, a schedule wish, a request for a person, the crisis lines / the relative's emergency SMS to send."""
    d = store.get(pid)
    last = (d.get("journey") or [{}])[-1]
    day = last.get("date")
    text = last.get("text") or ""
    extra = extra or {}
    patch = {}
    mood = _mood(extra, intent, d.get("mood"))
    if mood:
        patch.update(mood=mood, moodDate=day)
    if intent in ("health_problem", "emergency", "crisis"):
        patch["health"] = {"date": day, "intent": intent}
    elif _yes(extra.get("health_note")) or _yes(extra.get("health_flag")):
        patch["health_note"] = {"date": day, "text": text}
    items = _items(extra.get("items"))
    if intent == "need_items" and not items:
        items = ["jine"]  # e.g. the button on the personal page: the social worker asks what exactly
    if intent == "low_mood" and "spolecnost" not in items and any(k in dialog.COMPANY_ITEMS for k in dialog.items_of(text)):
        items.append("spolecnost")
    if items:
        needs = list(d.get("needs") or [])
        have = {n["id"] for n in needs}
        for it in items:
            nid = f"{pid}-{day}-{it}"
            if nid not in have:
                needs.append({"id": nid, "item": it, "date": day, "status": "new"})
        patch["needs"] = needs
    if intent == "pause":
        patch["pause"] = {"date": day, "until": extra.get("pause_until") or extra.get("when") or "", "reason": text}
    if intent == "schedule_change":
        patch["schedule_note"] = {"date": day, "note": extra.get("schedule") or extra.get("when") or text, "when": extra.get("when") or ""}
    if intent == "human":
        patch["human_request"] = {"date": day}
    if intent == "crisis":
        patch["crisis"] = {"date": day, "lines": dialog.CRISIS_LINES, "sms": "CRISIS"}
    if intent == "emergency":
        patch["emergency"] = {"date": day, "kind": extra.get("emergency_kind") or "medical", "sms": "EMERGENCY_RELATIVE"}
    if patch:
        store.patch(pid, **patch)
