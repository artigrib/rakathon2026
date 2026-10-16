"""Contact plan (cadence): when and through which channel the next automatic touch goes out.

Deterministic on purpose – the practice must know exactly what will be sent and when.
AI only interprets replies; it never decides to contact anyone.

Default ladder (days from the first invitation of the current cycle):
  0 SMS  →  3 voice call  →  5 voice call (other time of day)  →  8 WhatsApp  →  12 nurse calls personally
Stops immediately on any reply. "Not now" pauses the plan, then a new cycle starts with a motivating text.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class Step:
    day: int
    channel: str          # sms | voice | whatsapp | email | nurse
    variant: str = "REMINDER"


@dataclass(frozen=True)
class Plan:
    steps: tuple = field(default_factory=lambda: (
        Step(0, "sms", "FIRST_INVITE"),
        Step(3, "voice"),
        Step(5, "voice"),
        Step(8, "whatsapp"),
        Step(12, "nurse"),
    ))
    pause_days: int = 90      # after "not now"
    restart_variant: str = "MOTIVATION"


PLAN = Plan()
REPLY_STAGES = {"interested", "callback", "booked", "ldct", "result", "declined"}


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def next_touch(journey: list, plan: Plan = PLAN):
    """Next automatic touch for a patient, or None when the plan is finished or the patient replied.

    Returns {"due": date, "channel", "variant", "step"} – step = index in the ladder."""
    if not journey:
        return None
    staged = [e for e in journey if e.get("stage")]
    if not staged:
        return None
    last = staged[-1]
    if last["stage"] in REPLY_STAGES or last["stage"] == "nurse_call":
        return None
    if last["stage"] == "not_now":
        return {"due": _d(last["date"]) + timedelta(days=plan.pause_days), "channel": plan.steps[0].channel,
                "variant": plan.restart_variant, "step": 0}
    # current cycle = sends after the last "not_now" (or all)
    cut = max((i for i, e in enumerate(staged) if e["stage"] == "not_now"), default=-1)
    sends = [e for e in staged[cut + 1:] if e["stage"] == "sent"]
    if not sends:
        return None
    done = len(sends)
    if done >= len(plan.steps):
        return None
    step = plan.steps[done]
    start = _d(sends[0]["date"])
    variant = plan.restart_variant if cut >= 0 and done == 0 else step.variant
    channel = step.channel
    # Never the same channel three times in a row (e.g. the first invitation was already a call).
    recent = [e.get("channel") for e in sends[-2:]]
    if channel != "nurse" and len(recent) == 2 and recent[0] == recent[1] == channel:
        channel = "sms" if channel != "sms" else "whatsapp"
    return {"due": start + timedelta(days=step.day), "channel": channel, "variant": variant, "step": done}
