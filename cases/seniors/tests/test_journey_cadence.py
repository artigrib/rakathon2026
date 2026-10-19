"""Journey and the contact ladder: call → retry after 1 h → SMS to the relative the same day → call → visit the next
morning (a person), restart after an answer; quiet hours 9:00–19:00 even for a retry."""
import json
from datetime import date, datetime
from pathlib import Path

from backend import fsm
from backend.cadence import PLAN, next_touch
from cases.seniors import cadence

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


def test_new_intents_land_on_existing_stages():
    from cases.seniors import dialog
    for intent in dialog.INTENTS:
        ev = dialog.INTENT_EVENT[intent]
        assert fsm.next_state("no_answer", ev) == dialog.STAGE[intent], intent
    assert fsm.next_state("no_answer", dialog.INTENT_EVENT["crisis"]) == "escalated"
    assert fsm.next_state("ok", dialog.INTENT_EVENT["pause"]) == "paused"
    assert fsm.next_state("ok", dialog.INTENT_EVENT["human"]) == "escalated"
    assert fsm.next_state("paused", "emergency") == "escalated"  # a crisis or an emergency is heard even while paused


def send(day, variant="CHECKIN", channel="voice", **kw):
    return {"stage": "no_answer", "event": "send", "date": day, "channel": channel, "variant": variant, **kw}


def test_ladder_escalates_to_a_visit_next_morning():
    j = [send("2026-10-19", time="10:00")]
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"], n["at"]) == ("voice", "RETRY", date(2026, 10, 19), "11:00")  # retry after 1 h
    j.append(send("2026-10-19", "RETRY", auto=True, time="11:00"))
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"], n["at"]) == ("sms", "RELATIVE", date(2026, 10, 19), "11:05")  # 2x no answer: the relative, the same day
    j.append(send("2026-10-19", "RELATIVE", "sms", auto=True, time="11:05"))
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"]) == ("voice", "RETRY", date(2026, 10, 19))
    j.append(send("2026-10-19", "RETRY", auto=True, time="12:05"))
    n = next_touch(j)
    assert n["channel"] == PLAN.human == "visit" and n["due"] == date(2026, 10, 20) and n["at"] == "09:00"  # the next morning
    j.append({"stage": "escalated", "event": "visit", "date": "2026-10-20", "auto": True})
    assert next_touch(j) is None


def test_ladder_without_times_keeps_the_same_day():
    j = [send("2026-10-19")]
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"], n["at"]) == ("voice", "RETRY", date(2026, 10, 19), "za 1 h")
    j.append(send("2026-10-19", "RETRY", auto=True))
    n = next_touch(j)
    assert (n["channel"], n["variant"], n["due"], n["at"]) == ("sms", "RELATIVE", date(2026, 10, 19), "ihned")


def test_quiet_hours_move_a_late_retry_to_the_next_morning():
    assert cadence.next_call_at("2026-10-19", "17:30") == (date(2026, 10, 19), "18:30")
    assert cadence.next_call_at("2026-10-19", "18:30") == (date(2026, 10, 20), "09:00")  # 19:30 is after the window
    assert cadence.next_call_at("2026-10-19", "07:00") == (date(2026, 10, 19), "09:00")
    assert cadence.next_call_at("2026-10-19", None) == (date(2026, 10, 19), None)
    j = [send("2026-10-19", time="18:30")]
    n = next_touch(j)
    assert (n["variant"], n["due"], n["at"]) == ("RETRY", date(2026, 10, 20), "09:00")
    assert cadence.allowed_at(datetime(2026, 10, 19, 9, 0)) and cadence.allowed_at(datetime(2026, 10, 19, 18, 59))
    assert not cadence.allowed_at(datetime(2026, 10, 19, 8, 59)) and not cadence.allowed_at(datetime(2026, 10, 19, 19, 0))
    assert cadence.QUIET == (9, 19) and cadence.RETRY_AFTER.total_seconds() == 3600


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
