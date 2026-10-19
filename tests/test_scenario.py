"""Guided demo ("Spustit celou ukázku") of the active case, end to end in MOCK mode, and the recipient guard; inbound
SMS forwarding between case containers (one Twilio number). Runs under every CASE."""
import re
import time

import pytest
from fastapi.testclient import TestClient

PHONE, EMAIL = "+420601555111", "host@example.cz"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import importlib
    from dataclasses import replace
    import backend.settings as st
    monkeypatch.setattr(st, "settings", replace(st.settings, state_file=tmp_path / "state.json", demo_password="rakathon",
                                                 public_url="https://demo.test", internal_token="tajne"))
    import backend.recipient, backend.sessions, backend.ctx, backend.channels, backend.app
    for mod in (backend.recipient, backend.sessions, backend.ctx, backend.channels):
        monkeypatch.setattr(mod, "settings", st.settings)
    m = importlib.reload(backend.app)
    m.store.reset()
    return m


def login(m, phone=PHONE, email=EMAIL):
    c = TestClient(m.app)
    r = c.post("/login", data={"code": "rakathon", "phone": phone, "email": email, "next": "/app/"}, follow_redirects=False)
    assert r.status_code == 303
    return c


def test_login_page_is_the_cases(app):
    page = TestClient(app.app).get("/login").text
    assert f"<title>Přihlášení do ukázky {app.CASE.manifest['brand']}</title>" in page and "Přístupový kód" in page
    if app.CASE.id != "screening":
        assert "plic" not in page.lower() and "Pacienti" not in page


def run_all(c, limit=40):
    s = c.post("/api/scenario/start").json()
    for _ in range(limit):
        if s["scenario"].get("finished"):
            return s
        s = c.post("/api/scenario/next").json()
    raise AssertionError(f"scenario did not finish: {s['scenario']}")


def test_every_case_declares_a_scenario(app):
    assert app.scenario.SPEC and app.scenario.STEPS


def test_full_scenario_in_mock_mode(app):
    c = login(app)
    s = c.get("/api/state").json()
    assert s["scenario"]["available"] and "steps" not in s["scenario"]
    s = c.post("/api/scenario/start").json()
    pid = s["scenario"]["pid"]
    assert s["personas"][0]["id"] == pid and s["personas"][0]["demo"]
    assert s["scenario"]["steps"][0]["status"] in ("waiting", "done")          # the first step started at once
    s = run_all(c)
    st = s["scenario"]
    assert st["finished"] and not st["running"]
    assert all(x["status"] in ("done", "simulated", "noreply", "skipped") for x in st["steps"])
    d = s["decisions"][pid]
    events = [e.get("event") for e in d["journey"] if not e.get("ignored")]
    out = c.get(f"/api/patient/{pid}").json()["outbox"]
    assert out and not any(m["live"] for m in out)                             # MOCK: nothing left the machine
    cid = app.CASE.id
    if cid == "screening":
        assert {"booked", "ldct", "result"} <= set(events) and out[-1]["variant"] == "RESCREEN"
        assert [x["status"] for x in st["steps"]][:3] == ["noreply", "simulated", "done"]
    elif cid == "seniors":
        assert d.get("needs") and "visit" in events and d["stage"] == "escalated"
        assert [m["variant"] for m in out] == ["CHECKIN", "CHECKIN", "RETRY", "RELATIVE", "RETRY"]  # three unanswered before the visit
        replies = [e for e in d["journey"] if e.get("text")]
        assert replies and all(e["via"] == "sim" for e in replies)                 # simulated answers are labelled so
    elif cid == "collections":
        assert d["verified"] and d["promises"][-1]["status"] == "broken"
        assert "broken" in events and out[-1]["variant"] == "BROKEN_PROMISE"
    # the persona exists only in this visitor's demo, and a reset removes it
    assert pid not in app._default_store.decisions()
    s = c.post("/api/scenario/reset").json()
    assert pid not in s["decisions"] and "personas" not in s and "steps" not in s["scenario"]


def test_waits_time_out_so_the_demo_never_stalls(app, monkeypatch):
    c = login(app)
    c.post("/api/scenario/start")
    shift = [0]
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + shift[0])
    for _ in range(40):
        shift[0] += 400                      # longer than any step's timeout or pause
        s = c.get("/api/state").json()       # the app's polling moves it on
        if s["scenario"]["finished"]:
            break
    assert s["scenario"]["finished"]


def test_scenario_needs_a_signed_in_visitor(app):
    c = TestClient(app.app)
    assert c.post("/api/scenario/start", auth=("plice", "rakathon")).status_code in (401, 403)  # scripts: shared demo
    assert c.get("/api/state", auth=(app.settings.demo_user, "rakathon")).json()["scenario"]["available"] is False
    assert c.post("/api/scenario/start", auth=(app.settings.demo_user, "rakathon")).status_code == 403


def test_live_scenario_sends_only_to_the_visitor(app, monkeypatch, tmp_path):
    """Live: every step's message goes to the visitor's own phone / e-mail (never DEMO_TO), past LIVE_LIMIT, and the
    daily limit still holds."""
    from dataclasses import replace
    c = login(app)
    monkeypatch.setattr(app, "settings", replace(app.settings, account_sid="AC1", auth_token="t", from_number="+1",
                                                 demo_to="+420602000879", demo_email="artem@example.com",
                                                 sendgrid_key="k", email_from="f@example.com", case_live=True))
    sent = []

    def fake(kind):
        def f(*a, **k):
            if not a[1]:                 # a simulated step (seniors: the unanswered calls)
                return {"sid": None, "live": False, "to": None, "status": "simulated"}
            to = app.recipient.email() if kind == "email" else app.recipient.phone()
            sent.append((kind, to))
            return {"sid": f"X{len(sent)}", "live": True, "to": to, "status": "queued"}
        return f
    monkeypatch.setattr(app.channels, "send_sms", fake("sms"))
    monkeypatch.setattr(app.channels, "send_email", fake("email"))
    monkeypatch.setattr(app.channels, "send_whatsapp", fake("sms"))
    monkeypatch.setattr(app.channels, "start_call", fake("voice"))
    monkeypatch.setattr(app.tts, "ensure", lambda text: None)
    run_all(c)
    assert sent and all(to in (PHONE, EMAIL) for _, to in sent), sent
    assert len(sent) > app.settings.live_limit                                  # the per-batch limit does not apply
    # daily limit: a second full run the same day stops sending for real when the limit is reached
    monkeypatch.setenv("DEMO_DAILY_LIMIT", str(len([1 for k, _ in sent if k != "email"])))
    sent.clear()
    s = run_all(c)
    assert not [1 for k, _ in sent if k != "email"]
    assert any(x.get("note") == "daily_limit" for x in s["scenario"]["steps"])


# ---------- one Twilio number: inbound SMS forwarded to the case container of the visitor's latest demo ----------
class _Resp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_internal_endpoints_need_the_token(app):
    c = TestClient(app.app)
    assert c.get("/internal/has-phone", params={"phone": PHONE}).status_code == 403
    assert c.get("/internal/has-phone", params={"phone": PHONE}, headers={"X-Internal-Token": "spatne"}).status_code == 403
    assert c.post("/internal/sms", data={"From": PHONE, "Body": "Ano"}).status_code == 403
    r = c.get("/internal/has-phone", params={"phone": PHONE}, headers={"X-Internal-Token": "tajne"})
    assert r.status_code == 200 and r.json() == {"session": False, "active": 0.0}
    login(app)
    assert c.get("/internal/has-phone", params={"phone": PHONE}, headers={"X-Internal-Token": "tajne"}).json()["session"]


def test_internal_endpoints_off_without_token(app, monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr(app, "settings", replace(app.settings, internal_token=""))
    c = TestClient(app.app)
    assert c.get("/internal/has-phone", params={"phone": PHONE}, headers={"X-Internal-Token": ""}).status_code == 403


def test_forwarded_sms_lands_in_the_visitors_demo(app):
    c = login(app)
    s = c.post("/api/scenario/start").json()
    pid = s["scenario"]["pid"]
    sid = app.sessions.sid(next(t for t, x in app.sessions._load().items() if x["phone"] == PHONE))
    app._store_for(sid).data["outbox"].append({"patient": pid, "channel": "sms", "to": PHONE, "live": True, "sid": "SMf"})
    n = len(app._store_for(sid).get(pid).get("journey", []))
    r = TestClient(app.app).post("/internal/sms", data={"From": PHONE, "Body": "Ano"}, headers={"X-Internal-Token": "tajne"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert len(app._store_for(sid).get(pid)["journey"]) > n and app._store_for(sid).get(pid)["journey"][-1]["via"] == "sms"


def test_sms_forwarder(app, monkeypatch):
    import urllib.request
    calls = []
    other = {"active": 0.0}

    def urlopen(req, timeout=0):
        calls.append((req.get_method(), req.full_url, req.headers.get("X-internal-token")))
        if "/internal/has-phone" in req.full_url:
            return _Resp(f'{{"session": true, "active": {other["active"]}}}'.encode())
        return _Resp(b'<?xml version="1.0" encoding="UTF-8"?><Response><Message>z druheho</Message></Response>')
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    tw = TestClient(app.app)
    # SMS_FORWARD unset: handled here, nothing asked (screening unchanged)
    tw.post("/twilio/sms", data={"From": PHONE, "Body": "Ano"})
    assert calls == []
    monkeypatch.setattr(app, "FORWARD", ["http://app-other:8000"])
    # the phone signed in only in the other container → forwarded, the TwiML answer is relayed to Twilio
    other["active"] = time.time()
    r = tw.post("/twilio/sms", data={"From": PHONE, "Body": "Ano"})
    assert "z druheho" in r.text
    assert calls[0][:2] == ("GET", "http://app-other:8000/internal/has-phone?phone=%2B420601555111") and calls[0][2] == "tajne"
    assert calls[1][:2] == ("POST", "http://app-other:8000/internal/sms")
    # signed in here later than there → stays here
    calls.clear()
    login(app)
    other["active"] = time.time() - 3600
    r = tw.post("/twilio/sms", data={"From": PHONE, "Body": "Ano"})
    assert "z druheho" not in r.text and [m for m, *_ in calls] == ["GET"]
    # the other container is down → handled here
    calls.clear()

    def down(req, timeout=0):
        raise OSError("connection refused")
    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert tw.post("/twilio/sms", data={"From": PHONE, "Body": "Ano"}).status_code == 200
