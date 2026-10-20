"""Contact plan (cadence): when and through which channel the next automatic touch goes out.

Deterministic on purpose – the practice must know exactly what will be sent and when.
AI only interprets replies; it never decides to contact anyone. The ladder itself (PLAN) belongs to the case
(cases/<id>/cadence.py); stages come from its case.json.
"""
import inspect
import logging
from datetime import date, timedelta

from .case import CASE
from .plan import Plan, Step  # noqa: F401  (re-exported)

PLAN: Plan = CASE.cadence.PLAN
# Optional case hook `adjust(touch, journey[, record]) -> touch | {"skip": True} | None` (e.g. calling window, weekly cap,
# channel opt-out, no relative to text); applied to every touch computed with the case's own PLAN. `{"skip": True}` =
# this step does not apply, plan the next one. Cases without it behave exactly as before.
ADJUST = getattr(CASE.cadence, "adjust", None)
try:
    _ADJ_RECORD = bool(ADJUST) and len(inspect.signature(ADJUST).parameters) >= 3
except (TypeError, ValueError):
    _ADJ_RECORD = False
REPLY_STAGES = set(CASE.manifest["terminal_reply_stages"])
SENT = CASE.manifest["sent_stage"]


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def next_touch(journey: list, plan: Plan = PLAN, record: dict | None = None):
    """Next automatic touch for a patient, or None when the plan is finished or the patient replied.

    Returns {"due": date, "channel", "variant", "step"} – step = index in the ladder. `record` (the patient's data
    record, optional) is passed to a 3-parameter case `adjust`; a step it skips is replaced by the next one."""
    touch = _next_touch(journey, plan)
    if not (touch and ADJUST and plan is PLAN):
        return touch
    done = touch["step"]  # sends of this cycle; a step the case skips took no send, so walk the ladder from 0
    consumed = 0
    for i in range(len(plan.steps)):
        t = touch if i == done == consumed else _next_touch(journey, plan, i)
        if t is None:
            return None
        try:
            out = ADJUST(t, journey, record) if _ADJ_RECORD else ADJUST(t, journey)
        except Exception:  # a broken case hook must not break /api/state or the tick; no touch is the safe side
            logging.getLogger("uvicorn.error").exception("case cadence.adjust failed")
            return None
        if isinstance(out, dict) and out.get("skip"):
            continue
        if consumed == done:
            return out
        consumed += 1
    return None  # skipped past the last step


def is_send(e: dict) -> bool:
    """A journey event that is an outbound touch: the sent stage reached by event `send` (old events have no event).
    A reply that keeps the sent stage (collections: channel_opt_out while contacted) is not a send."""
    return e.get("stage") == SENT and e.get("event", "send") == "send"


def _next_touch(journey: list, plan: Plan, step_index: int | None = None):
    """The ladder's touch: the first not-done step, or `step_index` (a later step, after the case skipped one)."""
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
        i = step_index or 0
        if i >= len(plan.steps):
            return None
        return {"due": _d(last["date"]) + timedelta(days=plan.pause_days), "channel": plan.steps[i].channel,
                "variant": plan.restart_variant if i == 0 else plan.steps[i].variant, "step": i}
    # current cycle = sends after the last pause or the last stage that closes a cycle (or all)
    cut = max((i for i, e in enumerate(staged) if (pause and e["stage"] == pause) or e["stage"] in plan.cycle_stages), default=-1)
    sends = [e for e in staged[cut + 1:] if is_send(e)]
    if not sends:
        return None
    done = len(sends) if step_index is None else step_index
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
