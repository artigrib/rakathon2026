"""Core behaviour around the optional case hooks (collections uses all of them)."""
import pytest

from cases.collections import hooks


def _boom(*a, **k):
    raise RuntimeError("buggy case hook")


def test_reply_that_keeps_the_sent_stage_is_not_a_send():
    from backend import cadence
    j = [{"stage": "contacted", "date": "2026-10-19", "event": "send", "channel": "sms"},
         {"stage": "contacted", "date": "2026-10-19", "event": "channel_opt_out", "intent": "channel_opt_out"}]
    assert not cadence.is_send(j[1]) and cadence.is_send(j[0]) and cadence.is_send({"stage": "contacted"})
    assert cadence.next_touch(j)["step"] == cadence.next_touch(j[:1])["step"] == 1


def test_store_keeps_last_send_when_a_reply_keeps_the_stage(client):
    c, store = client
    import backend.app as m
    pid = next(iter(m.PATIENTS))
    c.post("/api/send", json={"items": [{"id": pid, "channel": "sms", "variant": "FIRST_INVITE", "text": "x"}]})
    m.transition(pid, "channel_opt_out", extra={"channels": ["voice"]})
    assert store.get(pid)["stage"] == "contacted" and store.get(pid)["sent"]["channel"] == "sms"


def test_failing_on_tick_does_not_stop_the_clock(client, monkeypatch):
    c, _ = client
    import backend.app as m
    monkeypatch.setattr(m, "ON_TICK", _boom)
    before = c.get("/api/state").json()["clock"]
    r = c.post("/api/tick", json={"days": 1})
    assert r.status_code == 200 and r.json()["clock"] > before


def test_failing_on_reply_still_records_the_reply(client, monkeypatch):
    c, store = client
    import backend.app as m
    pid = next(iter(m.PATIENTS))
    c.post("/api/send", json={"items": [{"id": pid, "channel": "sms", "variant": "FIRST_INVITE", "text": "x"}]})
    monkeypatch.setattr(hooks, "on_reply", _boom)
    r = c.post("/api/step", json={"id": pid, "text": "Dobrý den, zaplatím v pátek 5000 Kč."})
    assert r.status_code == 200 and store.get(pid)["journey"][-1].get("text")


def test_failing_adjust_means_no_automatic_touch(monkeypatch):
    from backend import cadence
    monkeypatch.setattr(cadence, "ADJUST", _boom)
    assert cadence.next_touch([{"stage": "contacted", "date": "2026-10-19", "event": "send", "channel": "sms"}]) is None
