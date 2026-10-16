"""Recommend the next contact action + channel from patient prefs and contact history.

Mentor: preferences differ per person (some hate SMS, others never read post),
so we learn from history: failed channels are demoted, channels that got a reaction are preferred,
and the GP is always notified which channel was used.
"""
from __future__ import annotations

from datetime import date, datetime

ACTIVE_STATUSES = {"ELIGIBLE"}
CH_CS = {"portal": "portál", "sms": "SMS", "voice": "telefonát asistenta", "email": "e-mail", "letter": "dopis", "printout": "tisk"}
cs = lambda c: CH_CS.get(c, c)


def _d(x):
    try:
        return datetime.fromisoformat(x).date()
    except (TypeError, ValueError):
        return None


def _hist(contacts):
    out = []
    for c in sorted(contacts, key=lambda c: c.get("created_at", "")):
        out.append({"date": (_d(c.get("created_at")) or date.min).isoformat(),
                    "channel": c.get("channel"), "type": c.get("message_type"),
                    "delivery": c.get("delivery_status"), "response": c.get("response") or None,
                    "by": c.get("handled_by")})
    return out


def _base_channels(p: dict) -> list[str]:
    portal_ok = str(p.get("patient_portal_active")).lower() == "true" and \
        str(p.get("consent_for_portal_messages")).lower() == "true"
    pref = (p.get("preferred_contact_channel") or "").lower()
    order = []
    if portal_ok:
        order.append("portal")
    if pref in ("letter", "printout"):
        order.append(pref)
    order += ["sms", "voice", "email", "letter"]
    seen, res = set(), []
    for ch in order:
        if ch not in seen:
            seen.add(ch); res.append(ch)
    return res


def recommend(p: dict, contacts: list[dict], status: str, ref: date, cfg) -> dict:
    history = _hist(contacts)
    res = {"history": history, "next_action": "NONE", "recommended_channel": None,
           "message_variant": None, "reason": ""}
    if status not in ACTIVE_STATUSES:
        res["reason"] = "Pacient není aktuálně vhodný k oslovení" if status != "NEEDS_REVIEW" \
            else "Nejprve je potřeba kontrola lékařem"
        return res

    lung = [h for h in history if h["type"] == "lung_screening_information"]
    failed = {h["channel"] for h in history if h["delivery"] == "failed"}
    worked = [h["channel"] for h in history if h["delivery"] == "read"]
    channels = [c for c in _base_channels(p) if c not in failed]
    # a channel the patient actually reads goes first
    for ch in reversed(worked):
        if ch in channels:
            channels.remove(ch); channels.insert(0, ch)

    if not lung:
        res.update(next_action="SEND_INVITE", recommended_channel=channels[0], message_variant="FIRST_INVITE",
                   reason=_why_first(p, channels[0], failed, worked))
        return res

    last = lung[-1]
    days = (ref - date.fromisoformat(last["date"])).days
    not_int = sum(1 for h in lung if h["response"] == "not_interested")

    if last["response"] == "interested":
        res.update(next_action="GP_REFERRAL", reason=f"Pacient projevil zájem ({last['date']}) – vyplňte anamnézu a žádanku k pneumologovi (ten objedná LDCT)")
        return res
    if not_int >= 2:
        res.update(next_action="DO_NOT_CONTACT", reason="Pacient opakovaně odmítl – probrat osobně při příští návštěvě")
        return res
    if days < cfg.contact_cooldown_days and last["delivery"] != "failed":
        res.update(next_action="WAIT", reason=f"Odesláno před {days} dny ({cs(last['channel'])}) – čekáme na reakci")
        return res
    if last["response"] == "not_interested":
        ch = next((c for c in ("voice", "letter", "sms") if c in channels and c != last["channel"]), channels[0])
        res.update(next_action="TRY_OTHER_CHANNEL", recommended_channel=ch, message_variant="MOTIVATION",
                   reason="Pacient napsal, že nemá zájem – jiný kanál a motivační text (časný záchyt = vysoká šance na vyléčení)")
        return res
    if last["delivery"] == "failed":
        res.update(next_action="TRY_OTHER_CHANNEL", recommended_channel=channels[0], message_variant="FIRST_INVITE",
                   reason=f"Doručení přes {cs(last['channel'])} selhalo → zkusit {cs(channels[0])}")
        return res
    if last["delivery"] == "delivered":
        ch = "sms" if "sms" in channels else channels[0]
        res.update(next_action="SEND_REMINDER", recommended_channel=ch, message_variant="REMINDER",
                   reason=f"Zpráva ({cs(last['channel'])}) doručena, ale nepřečtena → připomínka: {cs(ch)}")
        return res
    # read, no response
    ch = "voice" if "voice" in channels else channels[0]
    res.update(next_action="SEND_REMINDER", recommended_channel=ch, message_variant="REMINDER",
               reason=f"Zpráva ({cs(last['channel'])}) přečtena, ale bez odpovědi → osobnější kanál: {cs(ch)}")
    return res


def _why_first(p, ch, failed, worked):
    if ch == "portal":
        return "Aktivní portál se souhlasem se zprávami"
    if ch in ("letter", "printout"):
        return "Pacient nemá portál, preferuje " + ("dopis" if ch == "letter" else "tištěnou informaci")
    if failed:
        return f"Předchozí doručení selhalo ({', '.join(cs(f) for f in sorted(failed))}) → {cs(ch)}"
    return f"Doporučený kanál: {cs(ch)}"
