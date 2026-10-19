"""API smoke in mock mode: the same paths as real webhooks, the secure page, the demo clock."""
import re

import pytest

from cases.collections import hooks, strategy

FORGETFUL = "DL-1076"


def first(store, seg=None):
    import backend.app as m
    return next(p for p in m.PATIENTS.values() if (seg is None or p["segment"] == seg))


def send(c, pid, channel="sms"):
    return c.post("/api/send", json={"items": [{"id": pid, "channel": channel, "variant": "FIRST_INVITE", "text": "x"}]}).json()


def reply(c, pid, text):
    return c.post("/api/step", json={"id": pid, "text": text}).json()


def tick(c, n=1):
    return [c.post("/api/tick", json={"days": 1}).json() for _ in range(n)]


def test_health_and_case(client):
    c, _ = client
    h = c.get("/api/health").json()
    assert h["case"] == "collections" and h["mode"] == "mock"
    assert c.get("/api/case").json()["id"] == "collections"
    assert c.get("/app/data/patients.json").status_code == 200


def test_promise_to_pay_recorded(client):
    c, store = client
    pid = first(store, "long_term")["id"]
    send(c, pid)
    d = reply(c, pid, "Dobrý den, zaplatím v pátek 5000 Kč.")
    assert d["stage"] == "promise_to_pay"
    p = store.get(pid)["promises"][-1]
    assert p == {**p, "date": "2026-10-23", "amount": 5000, "status": "open", "dateGiven": True}
    assert c.get("/api/state").json()["decisions"][pid]["promises"][-1]["amount"] == 5000
    # the contact plan waits for the promise
    assert pid not in c.get("/api/state").json()["plans"]


def test_promise_resolved_on_tick(client):
    c, store = client
    pid = first(store, "temporary")["id"]
    send(c, pid)
    reply(c, pid, "zaplatím zítra")
    tick(c, 4)
    d = store.get(pid)
    assert d["promises"][-1]["status"] in ("kept", "broken")
    if d["promises"][-1]["status"] == "kept":
        assert d["payments"] and d["stage"] in ("paid", "plan_offered")
    else:
        assert any(e.get("event") == "broken" for e in d["journey"])


def test_broken_promise_gets_a_kind_reminder(client):
    c, store = client
    pid = first(store, "uncooperative")["id"]  # demo: they rarely keep promises
    for p in hooks._records().values():
        if p["segment"] == "uncooperative" and not hooks._kept(p["id"], "2026-10-19" + "2026-10-20", "uncooperative"):
            pid = p["id"]
            break
    send(c, pid)
    reply(c, pid, "zaplatím zítra")
    out = tick(c, 8)
    d = store.get(pid)
    assert d["promises"][-1]["status"] == "broken"
    sent = [e for e in d["journey"] if e.get("event") == "send"]
    assert sent[-1]["variant"] == "BROKEN_PROMISE" and sent[-1]["auto"]


def test_dispute_and_vulnerability_stop_the_automation(client):
    c, store = client
    a, b = [p["id"] for p in list(hooks._records().values())[:2]]
    for pid, text, stage in ((a, "Nic vám nedlužím, už jsem to zaplatil.", "dispute"), (b, "Jsem v nemocnici, teď to nezvládnu.", "hardship_review")):
        send(c, pid)
        assert reply(c, pid, text)["stage"] == stage
        assert store.get(pid)["stopped"]["reason"] in ("dispute", "vulnerable")
    out = tick(c, 14)
    assert not [t for r in out for t in r["touches"] if t["id"] in (a, b)]


def test_opt_out_wins_and_wrong_person_ends(client):
    c, store = client
    a, b = [p["id"] for p in list(hooks._records().values())[2:4]]
    send(c, a)
    assert reply(c, a, "STOP, zaplatím v pátek")["stage"] == "do_not_contact"
    assert send(c, a)["sent"][0]["status"] == "not_allowed"
    send(c, b)
    assert reply(c, b, "To nejsem já, máte špatné číslo.")["stage"] == "wrong_contact"
    assert store.get(b)["contactInvalid"]
    from backend import messages
    assert messages.to_gsm(messages.sms_reply("wrong_person", "wrong_contact")).startswith("Omlouvame se")
    out = tick(c, 14)
    assert not [t for r in out for t in r["touches"] if t["id"] in (a, b)]


def test_channel_opt_out(client):
    c, store = client
    pid = list(hooks._records())[5]
    send(c, pid)
    d = reply(c, pid, "Nevolejte mi prosím, pište jen SMS.")
    assert d["stage"] == "contacted" and store.get(pid)["optout"] == ["voice"]
    plan = c.get("/api/state").json()["plans"][pid]
    assert plan["channel"] != "voice"
    for r in tick(c, 12):
        for t in r["touches"]:
            if t["id"] == pid:
                assert t.get("channel") != "voice"


def test_tick_respects_weekends_and_cap(client):
    c, store = client
    pid = list(hooks._records())[6]
    send(c, pid)  # Monday 19. 10.
    days = {}
    for r in tick(c, 14):
        for t in r["touches"]:
            if t["id"] == pid and t.get("channel") != "human":
                days[r["clock"]] = t
    from datetime import date
    from cases.collections import cadence
    for d in days:
        assert cadence.is_contact_day(date.fromisoformat(d)), d
    j = store.get(pid)["journey"]
    for d in days:
        assert cadence.contacts_in_week(j, date.fromisoformat(d)) <= cadence.WEEKLY_CAP


def page(c, store, pid):
    t = store.token(pid)
    return t, c.get(f"/p/{t}").text


def test_secure_page_shows_nothing_before_verification(client):
    c, store = client
    p = hooks.record(FORGETFUL)
    t, html = page(c, store, FORGETFUL)
    assert "Ověřit" in html and "<title>Finance Demo a.s.</title>" in html
    for secret in (strategy.czk(p["outstanding"]), str(p["outstanding"]), p["contract"], p["name"], p["birthDate"]):
        assert secret not in html
    # wrong answer → error, nothing shown
    html = c.post(f"/p/{t}", data={"action": "verify", "value": "0000"}).text
    assert "nesouhlasí" in html and strategy.czk(p["outstanding"]) not in html
    # an action without verification is refused
    html = c.post(f"/p/{t}", data={"action": "pay"}).text
    assert "Ověřit" in html and store.get(FORGETFUL).get("stage") is None


def test_secure_page_locks_after_three_failures(client):
    c, store = client
    t, _ = page(c, store, FORGETFUL)
    for _ in range(3):
        html = c.post(f"/p/{t}", data={"action": "verify", "value": "1.1.1900"}).text
    assert "nepodařilo" in html
    assert store.get(FORGETFUL)["stage"] == "human_handoff" and store.get(FORGETFUL)["verifyLocked"]


@pytest.mark.parametrize("how", ["contract", "birth"])
def test_secure_page_after_verification(client, how):
    c, store = client
    p = hooks.record(FORGETFUL)
    send(c, FORGETFUL)
    t, _ = page(c, store, FORGETFUL)
    y, m, d = p["birthDate"].split("-")
    value = p["contract"][-4:] if how == "contract" else f"{int(d)}. {int(m)}. {y}"
    html = c.post(f"/p/{t}", data={"action": "verify", "value": value}).text
    assert strategy.czk(p["outstanding"]) in html and p["contract"] in html
    for o in strategy.plan_options(p["outstanding"]):
        assert strategy.czk(o["monthly"]) in html
    assert "RPSN" not in html or "Ilustrativní" in html
    html = c.post(f"/p/{t}", data={"action": "plan", "n": "3"}).text
    assert "Splátkový kalendář je aktivní" in html
    d = store.get(FORGETFUL)
    assert d["stage"] == "plan_active" and d["plan"]["n"] == 3 and sum(i["amount"] for i in d["plan"]["items"]) == p["outstanding"]


def test_secure_page_promise_refi_pay_and_channel(client):
    c, store = client
    ids = [p["id"] for p in hooks._records().values() if p["strategy"] == "refi"][:3]
    for pid, form, stage in ((ids[0], {"action": "promise", "date": "2026-10-30", "amount": "700"}, "promise_to_pay"),
                             (ids[1], {"action": "refi"}, "refi_accepted"),
                             (ids[2], {"action": "pay"}, "paid")):
        p = hooks.record(pid)
        send(c, pid)
        t, _ = page(c, store, pid)
        html = c.post(f"/p/{t}", data={"action": "verify", "value": p["contract"][-4:]}).text
        assert "RPSN" in html and "Ilustrativní příklad" in html  # refinancing strategy: the example is shown, clearly illustrative
        c.post(f"/p/{t}", data=form)
        assert store.get(pid)["stage"] == stage
    assert store.get(ids[0])["promises"][-1] == {**store.get(ids[0])["promises"][-1], "date": "2026-10-30", "amount": 700}
    assert store.get(ids[2])["payments"][0]["amount"] == hooks.record(ids[2])["outstanding"]
    pid = list(hooks._records())[9]
    send(c, pid)
    t, _ = page(c, store, pid)
    c.post(f"/p/{t}", data={"action": "verify", "value": hooks.record(pid)["contract"][-4:]})
    c.post(f"/p/{t}", data={"action": "channel", "channel": "whatsapp"})
    assert store.get(pid)["optout"] == ["whatsapp"] and store.get(pid)["stage"] == "contacted"


def test_wrong_person_on_page_without_verification(client):
    c, store = client
    send(c, FORGETFUL)
    t, _ = page(c, store, FORGETFUL)
    html = c.post(f"/p/{t}", data={"action": "answer", "answer": "wrong"}).text
    assert "Omlouváme se" in html and store.get(FORGETFUL)["stage"] == "wrong_contact"
    assert "neplatí" in c.get(f"/p/{t}").text


def test_patient_messages_hide_tokens(client):
    c, store = client
    send(c, FORGETFUL)
    out = c.get(f"/api/patient/{FORGETFUL}").json()["outbox"]
    assert out and not re.search(r"/p/[A-Za-z0-9_-]{4,}", out[0]["text"])
