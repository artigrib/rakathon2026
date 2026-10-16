"""Patient journey state machine: table consistency and the holes it closes."""
import pytest

from backend import fsm


def test_table_is_consistent():
    assert fsm.check() == []


@pytest.mark.parametrize("state", [s for s, m in fsm.STATES.items() if m["final"]])
def test_final_states_never_get_contacted(state):
    assert not fsm.allowed(state, "send")


def test_first_decline_is_soft_second_is_hard():
    assert fsm.next_state("sent", "declined", refusals=0) == "not_now"
    assert fsm.next_state("sent", "declined", refusals=1) == "declined"
    assert fsm.next_state("sent", "opt_out", refusals=0) == "declined"  # STOP is always hard


def test_late_reply_after_result_is_ignored(client):
    c, store = client
    for ev in ("send", "interested", "booked", "ldct"):
        c.post("/api/step", json={"id": "F1", "stage": ev}) if ev != "send" else \
            c.post("/api/send", json={"items": [{"id": "F1", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "F1", "stage": "result", "result": "negative"})
    c.post("/api/step", json={"id": "F1", "text": "Ano"})
    d = store.get("F1")
    assert d["stage"] == "result" and d["journey"][-1]["ignored"]


def test_link_cannot_undo_a_referral(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "F2", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "F2", "stage": "booked"})
    tok = store.token("F2")
    c.post(f"/p/{tok}", data={"answer": "not_now"})
    assert store.get("F2")["stage"] == "booked"


def test_excluded_patient_is_never_contacted(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "F3", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "F3", "stage": "exclude"})
    r = c.post("/api/send", json={"items": [{"id": "F3", "channel": "sms", "text": "x"}]}).json()
    assert r["sent"][0]["status"] == "not_allowed"
    c.post("/api/tick", json={"days": 20})
    assert store.get("F3")["stage"] == "excluded"
    c.post("/api/step", json={"id": "F3", "stage": "include"})
    assert "stage" not in store.get("F3")


def test_no_show_after_referral_offers_again(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "F4", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "F4", "stage": "booked"})
    c.post("/api/step", json={"id": "F4", "stage": "no_show"})
    assert store.get("F4")["stage"] == "not_now"


def test_patient_can_change_mind_after_refusal(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "F5", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "F5", "text": "STOP"})
    assert store.get("F5")["stage"] == "declined"
    c.post("/api/step", json={"id": "F5", "text": "Ano, mám zájem"})
    assert store.get("F5")["stage"] == "interested"
