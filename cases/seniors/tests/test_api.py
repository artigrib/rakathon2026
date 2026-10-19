"""API smoke in mock mode: a check-in call, a simulated answer moves the stage and the needs land in the basket."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads((ROOT / "cases/seniors/synthetic/seniors.json").read_text(encoding="utf-8"))
PID = next(p["id"] for p in DATA["patients"] if p["stage"] == "ok")


def test_case_and_health(client):
    c, _ = client
    assert c.get("/api/health").json()["case"] == "seniors"
    m = c.get("/api/case").json()
    assert m["id"] == "seniors" and m["sent_stage"] == "no_answer"
    assert c.get("/app/content/items.json").json()["items"]["nakup"]["label"] == "nákup"
    assert c.get("/app/data/patients.json").json()["refDate"] == DATA["refDate"]
    assert c.get("/app/case/views/today.js").status_code == 200


def test_call_then_answer_with_needs(client):
    c, store = client
    r = c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "Dobrý den"}], "date": "2026-10-19"})
    assert r.status_code == 200 and store.get(PID)["stage"] == "no_answer"
    d = c.post("/api/step", json={"id": PID, "text": "Došly mi léky a potřebovala bych nakoupit.", "date": "2026-10-19"}).json()
    assert d["stage"] == "needs_help"
    assert d["journey"][-1]["extra"]["items"] == ["nakup", "leky"]
    s = c.get("/api/state").json()["decisions"][PID]
    assert {n["item"] for n in s["needs"]} == {"nakup", "leky"} and all(n["status"] == "new" for n in s["needs"])
    assert PID not in c.get("/api/state").json()["plans"]  # answered: nothing automatic follows
    # the social worker orders it: the case's own mark
    nid = s["needs"][0]["id"]
    assert c.post("/api/mark", json={"id": PID, "field": "basket", "value": {nid: "ordered"}}).status_code == 200
    assert store.get(PID)["basket"] == {nid: "ordered"}


def test_emergency_escalates_and_mood(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "x"}], "date": "2026-10-19"})
    d = c.post("/api/step", json={"id": PID, "text": "Upadla jsem a nemůžu vstát.", "date": "2026-10-19"}).json()
    assert d["stage"] == "escalated" and store.get(PID)["health"]["intent"] == "emergency"
    d = c.post("/api/step", json={"id": PID, "stage": "resolve", "date": "2026-10-19"}).json()
    assert d["stage"] == "resolved"


def test_low_mood_stores_mood(client):
    c, store = client
    c.post("/api/step", json={"id": PID, "text": "Nic moc, je mi smutno.", "date": "2026-10-19"})
    assert store.get(PID)["stage"] == "low_mood" and store.get(PID)["mood"] == 2


def test_tick_runs_the_ladder_to_a_visit(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "x"}], "date": DATA["refDate"]})
    for _ in range(4):
        c.post("/api/tick", json={"days": 1})
    auto = [(e.get("channel") or e["event"], e.get("variant")) for e in store.get(PID)["journey"] if e.get("auto")]
    assert auto == [("voice", "RETRY"), ("sms", "RELATIVE"), ("voice", "RETRY"), ("visit", None)]
    assert store.get(PID)["stage"] == "escalated"
    sms = [m for m in store.data["outbox"] if m["patient"] == PID and m["channel"] == "sms"][0]
    assert "nedovolali" in sms["text"] and sms["variant"] == "RELATIVE"


def test_personal_page_answer(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "sms", "variant": "CHECKIN", "text": "x"}], "date": "2026-10-19"})
    token = store.token(PID)
    assert "<form" in c.get(f"/p/{token}").text  # the personal page, not "invalid" (its words are the case's)
    r = c.post(f"/p/{token}", data={"answer": "help"})
    assert "155" in r.text and store.get(PID)["stage"] == "escalated"
    r = c.post(f"/p/{token}", data={"answer": "need"})  # escalated: a need is recorded, the stage stays
    assert store.get(PID)["stage"] == "escalated" and store.get(PID)["needs"][0]["item"] == "jine"


# ---------- the guided demo (scenario.json) in mock mode ----------
def _visitor(app_module, monkeypatch, tmp_path, email="host@example.cz"):
    """A signed-in visitor of a fresh app: own state, own contacts (tests/test_scenario.py does the same)."""
    import importlib
    from dataclasses import replace
    from fastapi.testclient import TestClient
    import backend.settings as st
    monkeypatch.setattr(st, "settings", replace(st.settings, state_file=tmp_path / "state.json", demo_password="demo",
                                                 public_url="https://demo.test"))
    import backend.recipient, backend.sessions, backend.ctx, backend.channels
    for mod in (backend.recipient, backend.sessions, backend.ctx, backend.channels):
        monkeypatch.setattr(mod, "settings", st.settings)
    m = importlib.reload(app_module)
    m.store.reset()
    c = TestClient(m.app)
    r = c.post("/login", data={"code": "demo", "phone": "+420601555111", "email": email, "next": "/app/"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return m, c


def _run(c, limit=40):
    s = c.post("/api/scenario/start").json()
    for _ in range(limit):
        if s["scenario"].get("finished"):
            return s
        s = c.post("/api/scenario/next").json()
    raise AssertionError(s["scenario"])


def test_persona_history_is_fresh_so_she_is_not_lost_at_start(monkeypatch, tmp_path):
    """Marie's registry: about 12 calls in the last 30 days, the newest yesterday (the web's lostOf counts scheduled
    days since the last answer: with the last call three days back she landed in 'Naléhavé' as lost)."""
    import backend.app as app
    from datetime import date, timedelta
    m, c = _visitor(app, monkeypatch, tmp_path)
    s = c.post("/api/scenario/start").json()
    p = s["personas"][0]
    ref = date.fromisoformat(m.REF_DATE)
    calls = p["calls"]
    answered = [x for x in calls if x["answered"]]
    assert 11 <= len(answered) <= 14 and any(not x["answered"] for x in calls)
    assert calls[-1]["date"] == (ref - timedelta(days=1)).isoformat() and calls[0]["date"] >= (ref - timedelta(days=30)).isoformat()
    assert calls == sorted(calls, key=lambda x: (x["date"], x.get("time", "")))
    moods = [x["mood"] for x in answered]
    assert moods[0] == 4 and moods[-1] <= 3 and min(moods) == 2 and all(1 <= v <= 5 for v in moods)
    assert p["flags"][0]["sev"] == "warning" and "Horáková" in p["flags"][0]["text"]
    assert p["stage"] == "ok" and p["phone"] == "+420601555111" and p["relative"]["phone"] == "+420601555111"
    # the persona's link carries the visitor's session, so it opens in their demo
    link = s["links"][s["scenario"]["pid"]]
    assert link.startswith("/p/") and "?s=" in link
    page = c.get(link)
    assert page.status_code == 200 and "<form" in page.text  # the personal page of this visitor's demo, not "invalid"


def test_scenario_runs_all_steps_fallback_has_mood_emergency_hits_another_senior(monkeypatch, tmp_path):
    import backend.app as app
    m, c = _visitor(app, monkeypatch, tmp_path)
    s = _run(c)
    sc, pid = s["scenario"], s["scenario"]["pid"]
    assert [x["id"] for x in sc["steps"]] == ["checkin", "basket", "missed", "relative", "visit", "emergency"]
    assert [x["status"] for x in sc["steps"]] == ["simulated", "done", "done", "noreply", "done", "done"]
    d = s["decisions"][pid]
    # the fallback answer carries a mood and two needs
    fb = next(e for e in d["journey"] if e.get("text"))
    assert fb["via"] == "sim" and fb["intent"] == "need_items" and fb["extra"]["mood"] == 3
    assert {n["item"] for n in d["needs"]} == {"nakup", "leky"} and d["mood"] == 3
    # three unanswered calls before the visit: two the next day, the third right before the social worker goes
    out = c.get(f"/api/patient/{pid}").json()["outbox"]
    assert [x["variant"] for x in out] == ["CHECKIN", "CHECKIN", "RETRY", "RELATIVE", "RETRY"]
    assert len([e for e in d["journey"] if e.get("delivery") == "failed"]) == 3 and d["stage"] == "escalated"
    # the emergency is another senior's: the persona's story stays clean
    other = sc["steps"][-1]["who"]
    assert other and other != pid and sc["steps"][-1]["card"] == "other" and sc["steps"][-1]["view"] == "today"
    e = s["decisions"][other]["journey"][-1]
    assert e["intent"] == "emergency" and e["via"] == "sim" and s["decisions"][other]["stage"] == "escalated"
    assert "emergency" not in [x.get("intent") for x in d["journey"]]
    # presentation hints and the waiting block reach the web app
    assert sc["steps"][0]["card"] is True and sc["steps"][0]["while_waiting"]["bullets"]
    assert sc["steps"][1]["view"] == "basket" and sc["steps"][1]["card"] is False
    assert "{who}" in sc["steps"][-1]["text"]
    # a reset also takes the emergency back
    s = c.post("/api/scenario/reset").json()
    assert other not in s["decisions"] and pid not in s["decisions"]


def test_call_without_a_conversation_ends_the_step_at_once(monkeypatch, tmp_path):
    """Live call of the check-in: no answer / busy / failed from Twilio, or completed without a word, runs the fallback
    before the timeout; while the call rings, runs or is analysed the step waits (up to the hard limit)."""
    import time
    from dataclasses import replace
    import backend.app as app
    m, c = _visitor(app, monkeypatch, tmp_path)
    monkeypatch.setattr(m, "settings", replace(m.settings, account_sid="AC1", auth_token="t", from_number="+1",
                                               demo_to="+420602000879", case_live=True, validate_signature=False))
    monkeypatch.setattr(m.channels, "start_call", lambda pid, live, progress=False: {"sid": "CA1", "live": True, "to": "+420601555111", "status": "queued"} if live
                        else {"sid": None, "live": False, "to": None, "status": "simulated"})
    monkeypatch.setattr(m.tts, "ensure", lambda text: None)
    s = c.post("/api/scenario/start").json()
    st = s["scenario"]["steps"][0]
    assert st["status"] == "waiting" and st["live"] and st["call"] == "dialing"
    sid = m.ctx.session_id.get() or ""
    c.post("/twilio/call-status/demo-you", data={"CallSid": "CA1", "CallStatus": "ringing"})
    shift = [0]
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + shift[0])
    shift[0] = 120                                  # past the 60 s timeout, but the phone still rings: keep waiting
    s = c.get("/api/state").json()
    assert s["scenario"]["steps"][0]["status"] == "waiting" and s["scenario"]["steps"][0]["call"] == "dialing"
    c.post("/twilio/call-status/demo-you", data={"CallSid": "CA1", "CallStatus": "in-progress"})
    assert c.get("/api/state").json()["scenario"]["steps"][0]["call"] == "in_progress"
    assert c.get("/api/patient/demo-you").json()["outbox"][0]["status"] == "in-progress"
    c.post("/twilio/call-status/demo-you", data={"CallSid": "CA1", "CallStatus": "no-answer"})
    s = c.get("/api/state").json()
    assert s["scenario"]["steps"][0]["status"] == "simulated"   # the fallback answer, at once
    assert s["decisions"]["demo-you"]["stage"] == "needs_help"


def test_login_email_is_optional_for_this_case(monkeypatch, tmp_path):
    import backend.app as app
    m, c = _visitor(app, monkeypatch, tmp_path, email="")
    assert m.EMAIL_OPTIONAL
    assert c.get("/api/state").json()["scenario"]["available"] is True
    assert c.post("/api/scenario/start").status_code == 200
    r = c.post("/login", data={"code": "demo", "phone": "", "email": "", "next": "/app/"}, follow_redirects=False)
    assert r.status_code == 400 and "telefon" in r.text.lower()
