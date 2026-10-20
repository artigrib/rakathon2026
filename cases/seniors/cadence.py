"""Jsem v pořádku contact ladder of one check-in (days from the first call of the cycle):

  0 call (in the senior's window)  →  0 call again (retry after 1 h)  →  0 SMS to the relative (2x no answer, the same day)
  →  0 call again (the same day)  →  1 the social worker visits the next morning (a person takes over: event "visit" → escalated)

Quiet hours: the assistant never calls before 9:00 or after 19:00, not even a retry; a retry that would fall after 19:00
moves to the next morning at 9:00 (`adjust`, applied by backend/cadence.next_touch to every automatic touch).
Any answer stops the ladder (every reply stage is terminal in case.json). Every reply stage also closes the cycle,
so the next scheduled check-in starts again from the first call (Plan.cycle_stages). The demo clock moves by days,
so same-day touches go out on the next ticks; in production the cron runs every 15 minutes and `at` says when.

A senior without a relative (record "relative": null): the relative's SMS is skipped (`{"skip": True}`), the ladder is
call → call → call, and the social worker comes the same day at 16:00 instead of the next morning."""
from datetime import date, datetime, time, timedelta

from backend.plan import Plan, Step

REPLY_STAGES = frozenset({"enrolled", "ok", "needs_help", "low_mood", "callback", "escalated", "resolved", "paused"})
QUIET = (9, 19)            # calls only from 9:00 to 18:59 (Europe/Prague local time)
RETRY_AFTER = timedelta(hours=1)
RELATIVE_AFTER = timedelta(minutes=5)
MORNING = "09:00"
SAME_DAY_VISIT = "16:00"   # no relative to warn: the social worker comes the same afternoon
VISIT = "visit"

PLAN = Plan(
    steps=(
        Step(0, "voice", "CHECKIN"),
        Step(0, "voice", "RETRY"),
        Step(0, "sms", "RELATIVE"),
        Step(0, "voice", "RETRY"),
        Step(1, VISIT),
    ),
    pause_days=0,
    restart_variant="CHECKIN",
    pause_stage="",
    human=VISIT,
    stop_stages=frozenset({"escalated", "paused"}),
    cycle_stages=REPLY_STAGES,
)


def allowed_at(when: datetime) -> bool:
    """May the assistant call at this moment? Only inside the quiet-hours window, every day."""
    return QUIET[0] <= when.hour < QUIET[1]


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _t(s):
    """'HH:MM' → time, None when unknown."""
    try:
        h, m = str(s).split(":")[:2]
        return time(int(h), int(m))
    except (TypeError, ValueError, AttributeError):
        return None


def next_call_at(prev_day, prev_time, after: timedelta = RETRY_AFTER):
    """When the next call may go out: `after` the previous one, inside the window; after 19:00 → the next morning 9:00.
    Returns (date, 'HH:MM'). Without the previous time: the same day, 'za 1 h' is not computable, so the earliest slot."""
    day = _d(prev_day)
    t = _t(prev_time)
    if t is None:
        return day, None
    when = datetime.combine(day, t) + after
    if when.hour < QUIET[0]:
        return when.date(), MORNING
    if when.hour >= QUIET[1]:
        return when.date() + timedelta(days=1), MORNING
    return when.date(), when.strftime("%H:%M")


def _sends(journey: list) -> list:
    return [e for e in journey if e.get("stage") == "no_answer" and e.get("event", "send") == "send"]


def has_relative(record) -> bool:
    """Is there a relative to text? Unknown record (None) = yes, the ladder stays as it always was."""
    return record is None or bool(record.get("relative"))


def adjust(touch: dict, journey: list, record: dict | None = None):
    """Time labels and quiet hours for every automatic touch: a retry 1 h after the missed call (never after 19:00,
    then the next morning at 9:00), the relative's SMS right after the second miss, the visit the next morning.
    Without a relative: the SMS step is skipped and the visit comes the same day at 16:00."""
    relative = has_relative(record)
    if touch["variant"] == "RELATIVE" and not relative:
        return {"skip": True}
    sends = _sends(journey)
    prev = sends[-1] if sends else {}
    prev_time = prev.get("time") or prev.get("at")
    out = dict(touch)
    if touch["variant"] in ("CHECKIN", "RETRY"):
        # a call to the senior stays a call: the core "never the same channel three times" would turn the third
        # call (no relative's SMS in between) into an SMS to the senior
        out["channel"] = "voice"
    if out["channel"] == VISIT:
        if relative:
            out["at"] = MORNING
        else:
            out["due"] = _d(prev.get("date") or touch["due"])
            out["at"] = SAME_DAY_VISIT
        return out
    if out["channel"] == "voice":
        day, at = next_call_at(prev.get("date") or touch["due"], prev_time)
        out["due"] = max(_d(touch["due"]), day)
        out["at"] = at or "za 1 h"
        return out
    if touch["variant"] == "RELATIVE":  # the relative is not a senior: the SMS goes out at once, the same day
        t = _t(prev_time)
        out["at"] = (datetime.combine(_d(touch["due"]), t) + RELATIVE_AFTER).strftime("%H:%M") if t else "ihned"
        return out
    return out
