"""Journey and the contact ladder: call → retry → SMS to the relative → call → visit (a person), restart after an answer."""
import json
from datetime import date
from pathlib import Path

from backend import fsm
from backend.cadence import PLAN, next_touch

ROOT = Path(__file__).resolve().parents[3]


def test_journey_is_consistent():
    spec = json.loads((ROOT / "cases/seniors/journey.json").read_text(encoding="utf-8"))
    assert fsm.check(spec) == []
    assert spec["states"]["declined"]["final"] and "send" not in spec["transitions"]["declined"]
    assert "send" not in spec["transitions"]["escalated"], "an escalation is never called automatically before a person resolves it"


def test_transitions():
    assert fsm.next_state("no_answer", "ok") == "ok"
    assert fsm.next_state("no_answer", "need_items") == "needs_help"
    assert fsm.next_state("no_answer", "low_mood") == "low_mood"
    assert fsm.next_state("ok", "emergency") == "escalated"
    assert fsm.next_state("ok", "health_problem") == "escalated"
    assert fsm.next_state("no_answer", "visit") == "escalated"
    assert fsm.next_state("escalated", "resolve") == "resolved"
    assert fsm.next_state("escalated", "ok") is None  # a late "ok" must not close an escalation, a person does
    assert fsm.next_state("resolved", "send") == "no_answer"
    assert fsm.next_state("ok", "opt_out") == "declined"
    assert fsm.next_state("paused", "send") is None and fsm.next_state("paused", "resume") == "enrolled"
    assert fsm.next_state("declined", "send") is None


def send(day, variant="CHECKIN", channel="voice", **kw):
    return {"stage": "no_answer", "event": "send", "date": day, "channel": channel, "variant": variant, **kw}


def test_ladder_escalates_to_a_visit():
    j = [send("2026-10-19")]
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"]) == ("voice", "RETRY", date(2026, 10, 19))
    j.append(send("2026-10-19", "RETRY", auto=True))
    n = next_touch(j)
    assert (n["channel"], n["variant"]) == ("sms", "RELATIVE")  # 2x no answer: the relative
    j.append(send("2026-10-20", "RELATIVE", "sms", auto=True))
    n = next_touch(j)
    assert (n["channel"], n["variant"]) == ("voice", "RETRY")
    j.append(send("2026-10-20", "RETRY", auto=True))
    n = next_touch(j)
    assert n["channel"] == PLAN.human == "visit"  # 3x no answer: a person visits
    j.append({"stage": "escalated", "event": "visit", "date": "2026-10-21", "auto": True})
    assert next_touch(j) is None


def test_answer_stops_and_next_checkin_restarts_the_ladder():
    j = [send("2026-10-19"), send("2026-10-19", "RETRY", auto=True),
         {"stage": "ok", "event": "ok", "date": "2026-10-19", "text": "Dobře"}]
    assert next_touch(j) is None
    j.append(send("2026-10-20"))  # tomorrow's check-in: step 1 again, not the relative
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["step"]) == ("voice", "RETRY", 1)


def test_escalation_and_pause_stop_the_plan():
    assert next_touch([send("2026-10-19"), {"stage": "escalated", "event": "emergency", "date": "2026-10-19"}]) is None
    assert next_touch([send("2026-10-19"), {"stage": "paused", "event": "pause", "date": "2026-10-19"}]) is None
