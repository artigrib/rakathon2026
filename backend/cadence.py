"""Contact plan (cadence): when and through which channel the next automatic touch goes out.

Deterministic on purpose – the practice must know exactly what will be sent and when.
AI only interprets replies; it never decides to contact anyone. The ladder itself (PLAN) belongs to the case
(cases/<id>/cadence.py); stages come from its case.json.
"""
from datetime import date, timedelta

from .case import CASE
from .plan import Plan, Step  # noqa: F401  (re-exported)

PLAN: Plan = CASE.cadence.PLAN
REPLY_STAGES = set(CASE.manifest["terminal_reply_stages"])
SENT = CASE.manifest["sent_stage"]


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
    if last["stage"] in REPLY_STAGES or last["stage"] in plan.stop_stages:
        return None
    pause = plan.pause_stage
    if pause and last["stage"] == pause:
        return {"due": _d(last["date"]) + timedelta(days=plan.pause_days), "channel": plan.steps[0].channel,
                "variant": plan.restart_variant, "step": 0}
    # current cycle = sends after the last pause (or all)
    cut = max((i for i, e in enumerate(staged) if pause and e["stage"] == pause), default=-1)
    sends = [e for e in staged[cut + 1:] if e["stage"] == SENT]
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
    if channel != plan.human and len(recent) == 2 and recent[0] == recent[1] == channel:
        channel = "sms" if channel != "sms" else "whatsapp"
    return {"due": start + timedelta(days=step.day), "channel": channel, "variant": variant, "step": done}
