"""Debtor journey (journey.json): consistency and the paths of the case."""
import json
from pathlib import Path

import pytest

from backend import fsm
from cases.collections import dialog

J = json.loads((Path(__file__).resolve().parents[1] / "journey.json").read_text(encoding="utf-8"))


def walk(*events, start="new"):
    s = start
    for e in events:
        t = J["transitions"][s].get(e)
        assert t, f"{s} --{e}--> not allowed"
        s = t
    return s


def test_consistent():
    assert fsm.check(J) == []


def test_finals_are_never_contacted():
    for s, meta in J["states"].items():
        if meta["final"]:
            assert "send" not in J["transitions"][s]
    assert J["states"]["paid"]["final"] and J["states"]["do_not_contact"]["final"]


@pytest.mark.parametrize("events,end", [
    (("send", "will_pay", "paid"), "paid"),
    (("send", "will_pay", "broken"), "broken_promise"),
    (("send", "will_pay", "broken", "send", "will_pay", "paid"), "paid"),
    (("send", "need_plan", "plan_chosen", "paid"), "paid"),
    (("send", "cannot_pay", "plan_chosen", "plan_missed"), "broken_promise"),
    (("send", "want_refi", "refi_accept", "paid"), "paid"),
    (("send", "dispute"), "dispute"),
    (("send", "vulnerable"), "hardship_review"),
    (("send", "callback"), "human_handoff"),
    (("send", "send", "send", "send", "human"), "human_handoff"),
    (("send", "wrong_person"), "wrong_contact"),
    (("send", "opt_out"), "do_not_contact"),
    (("send", "will_pay", "partial_paid", "plan_chosen"), "plan_active"),
    (("send", "need_plan", "offer_expired", "resume", "send"), "contacted"),
    (("send", "dispute", "resume"), "new"),
])
def test_paths(events, end):
    assert walk(*events) == end


def test_opt_out_reachable_from_every_active_state():
    for s, meta in J["states"].items():
        if not meta["final"] and s != "wrong_contact":
            assert J["transitions"][s].get("opt_out") == "do_not_contact", s


def test_channel_opt_out_keeps_the_stage():
    for s, row in J["transitions"].items():
        if "channel_opt_out" in row:
            assert row["channel_opt_out"] == s


def test_stop_stages_never_send():
    for s in ("dispute", "hardship_review", "human_handoff", "wrong_contact", "promise_to_pay", "plan_offered", "plan_active", "refi_offered"):
        assert "send" not in J["transitions"][s], s


def test_every_intent_is_an_event():
    events = {e for row in J["transitions"].values() for e in row}
    assert set(dialog.INTENT_EVENT.values()) <= events
