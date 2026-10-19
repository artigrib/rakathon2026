"""Jsem v pořádku hooks called by the core (backend/messages.py, backend/app.py)."""
import re

from . import dialog

MOOD_OF_INTENT = {"ok": 4, "low_mood": 2}  # when the answer itself says nothing about mood


def extra_placeholders(patient: dict, M: dict) -> dict:
    """{name}: ', paní Nováková' / ', pane Nováku' (vocative, empty without a record), {senior}: 'paní Marie Nováková',
    {worker}: the social worker."""
    voc = patient.get("vocative") or ""
    return {
        "name": f", {voc}" if voc else "",
        "senior": patient.get("title") or "Váš blízký",
        "worker": patient.get("worker") or "",
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


def _mood(raw, intent):
    try:
        m = int(float(raw))
        return m if 1 <= m <= 5 else None
    except (TypeError, ValueError):
        return MOOD_OF_INTENT.get(intent)


def on_reply(pid: str, intent: str, extra: dict, store) -> None:
    """Keep what the senior said for the social service: latest mood, health flag and the needs basket.

    decisions[pid] gets mood, moodDate, health, and needs = [{id, item, date, status: "new"}]
    (the basket in the web app; statuses ordered / done are the mark "basket")."""
    d = store.get(pid)
    day = (d.get("journey") or [{}])[-1].get("date")
    extra = extra or {}
    patch = {}
    mood = _mood(extra.get("mood"), intent)
    if mood:
        patch.update(mood=mood, moodDate=day)
    health = extra.get("health_flag") in (True, "true", "ano", "yes", 1) or intent in ("health_problem", "emergency")
    if health:
        patch["health"] = {"date": day, "intent": intent}
    items = _items(extra.get("items"))
    if intent == "need_items" and not items:
        items = ["jine"]  # e.g. the button on the personal page: the social worker asks what exactly
    if items:
        needs = list(d.get("needs") or [])
        have = {n["id"] for n in needs}
        for it in items:
            nid = f"{pid}-{day}-{it}"
            if nid not in have:
                needs.append({"id": nid, "item": it, "date": day, "status": "new"})
        patch["needs"] = needs
    if patch:
        store.patch(pid, **patch)
