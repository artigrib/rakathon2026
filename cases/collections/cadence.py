"""Collections contact plan and its compliance limits (deterministic; AI never decides to contact anybody).

Ladder (days from the first approved message of the cycle):
  0 SMS  →  2 call  →  5 e-mail  →  8 WhatsApp ("last automatic message")  →  12 an operator takes over
After a broken promise (pause stage) the ladder starts again the next contact day with BROKEN_PROMISE.
Any reply that leads to promise / offer / person / dispute / hardship stops it (case.json terminal_reply_stages).

Limits applied to every automatic touch by `adjust` (backend/cadence.py calls it):
  * contact only on working days (Mon–Fri, not on Czech public holidays) between 8:00 and 20:00 (`allowed_at`);
    a touch due on a weekend or holiday moves to the next working day and gets a time slot inside the window;
  * at most WEEKLY_CAP contacts in any 7 days (manual and automatic sends both count);
  * a channel the person refused (intent channel_opt_out) is never used again: the next allowed channel replaces it,
    and when none is left nothing automatic is sent.
"""
from datetime import date, datetime, timedelta

from backend.plan import Plan, Step

SENT = "contacted"
HUMAN = "human"
CONTACT_HOURS = (8, 20)          # [from, to): 8:00–19:59
WEEKLY_CAP = 3                   # contacts per rolling 7 days
CHANNEL_ORDER = ("sms", "email", "whatsapp", "voice")
SLOT = {"sms": "09:00", "whatsapp": "09:30", "email": "08:30", "voice": "10:30", HUMAN: "08:00"}
# Czech public holidays (státní svátky a ostatní svátky): fixed dates + Easter Friday and Monday.
FIXED_HOLIDAYS = {(1, 1), (5, 1), (5, 8), (7, 5), (7, 6), (9, 28), (10, 28), (11, 17), (12, 24), (12, 25), (12, 26)}
EASTER = {2025: (4, 20), 2026: (4, 5), 2027: (3, 28), 2028: (4, 16)}

_cycle = {"cycle_stages": frozenset({"new"})} if "cycle_stages" in Plan.__dataclass_fields__ else {}
PLAN = Plan(
    steps=(
        Step(0, "sms", "FIRST_INVITE"),
        Step(2, "voice", "REMINDER"),
        Step(5, "email", "REMINDER"),
        Step(8, "whatsapp", "LAST_TRY"),
        Step(12, HUMAN),
    ),
    pause_days=1,
    restart_variant="BROKEN_PROMISE",
    pause_stage="broken_promise",
    human=HUMAN,
    stop_stages=frozenset({"human_handoff", "dispute", "hardship_review", "wrong_contact", "do_not_contact", "paid", "closed"}),
    **_cycle,  # back in the queue after a person handled it (resume → new): the next approved send starts a new ladder
)


def is_holiday(d: date) -> bool:
    if (d.month, d.day) in FIXED_HOLIDAYS:
        return True
    e = EASTER.get(d.year)
    if e:
        easter = date(d.year, *e)
        return d in (easter - timedelta(days=2), easter + timedelta(days=1))
    return False


def is_contact_day(d: date) -> bool:
    return d.weekday() < 5 and not is_holiday(d)


def allowed_at(when: datetime) -> bool:
    """May the person be contacted at this moment? Working day, 8:00–20:00 (Europe/Prague local time)."""
    return is_contact_day(when.date()) and CONTACT_HOURS[0] <= when.hour < CONTACT_HOURS[1]


def next_contact_day(d: date) -> date:
    while not is_contact_day(d):
        d += timedelta(days=1)
    return d


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def sends_of(journey: list) -> list:
    return [_d(e["date"]) for e in journey if e.get("stage") == SENT and e.get("event", "send") == "send"]


def contacts_in_week(journey: list, day: date) -> int:
    """Contacts in the 7 days ending with `day` (day-6 … day)."""
    return sum(1 for s in sends_of(journey) if day - timedelta(days=6) <= s <= day)


def blocked_channels(journey: list) -> set:
    """Channels the person refused (reply intent channel_opt_out; its extra.channels, else the channel it came by)."""
    out = set()
    for e in journey:
        if e.get("intent") == "channel_opt_out" and not e.get("ignored"):
            chans = (e.get("extra") or {}).get("channels") or []
            via = {"voice-ai": "voice", "voice-agent": "voice"}.get(e.get("via"), e.get("via"))
            out |= set(chans) or ({via} if via in CHANNEL_ORDER else set())
    return out


def adjust(touch: dict, journey: list):
    """Compliance limits over the ladder's touch: channel opt-out, working days, weekly cap, time slot. None = no touch."""
    t = dict(touch)
    if t["channel"] != HUMAN:
        blocked = blocked_channels(journey)
        if t["channel"] in blocked:
            alt = next((c for c in CHANNEL_ORDER if c not in blocked), None)
            if not alt:
                return None
            t["channel"] = alt
    due = next_contact_day(_d(t["due"]))
    if t["channel"] != HUMAN:
        for _ in range(60):  # weekly cap: move after the oldest contact of the window drops out
            week = sorted(s for s in sends_of(journey) if due - timedelta(days=6) <= s <= due)
            if len(week) < WEEKLY_CAP:
                break
            due = next_contact_day(week[0] + timedelta(days=7))
    t["due"] = due
    t["at"] = SLOT.get(t["channel"], "09:00")
    return t
