"""Ukázka v sále: join by QR, call everybody, SMS to whoever does not answer, ANO to the SMS."""
import pytest
from fastapi.testclient import TestClient


class FakeTwilio:
    def __init__(self):
        self.calls, self.sms = [], []
        outer = self

        class Calls:
            def create(self, **kw):
                outer.calls.append(kw)
                return type("C", (), {"sid": f"CA{len(outer.calls)}"})()

        class Messages:
            def create(self, **kw):
                outer.sms.append(kw)
                return type("M", (), {"sid": f"SM{len(outer.sms)}"})()
        self.calls_api, self.messages = Calls(), Messages()

    @property
    def calls(self):
        return self._calls

    @calls.setter
    def calls(self, v):
        self._calls = v


@pytest.fixture()
def hall(tmp_path, monkeypatch):
    import importlib
    from dataclasses import replace
    import backend.settings as st
    s = replace(st.settings, state_file=tmp_path / "state.json", account_sid="AC1", auth_token="t", from_number="+19800000000",
                demo_to="+420600000000", public_url="https://jsemvcas.test", demo_password="", validate_signature=False)
    monkeypatch.setattr(st, "settings", s)
    import backend.recipient, backend.hall, backend.channels, backend.ctx, backend.sessions
    for mod in (backend.recipient, backend.hall, backend.channels, backend.ctx, backend.sessions):
        monkeypatch.setattr(mod, "settings", s)
    tw = FakeTwilio()
    client = type("Client", (), {"calls": tw.calls_api, "messages": tw.messages})()
    monkeypatch.setattr(backend.channels, "_client", lambda: client)
    monkeypatch.setattr(backend.hall.tts, "ensure", lambda *a, **k: None)
    m = importlib.reload(__import__("backend.app", fromlist=["app"]))
    return m, backend.hall, tw


def test_join_validation_and_projector_masks_numbers(hall):
    m, h, _ = hall
    c = TestClient(m.app)
    eid = c.get("/api/hall").json()["id"]
    assert "Zapojte se" in c.get(f"/j/{eid}").text
    assert c.post(f"/j/{eid}", data={"phone": "601 234 567"}).status_code == 400            # no consent
    assert c.post(f"/j/{eid}", data={"phone": "+44 7700 900123", "consent": "1"}).status_code == 400
    r = c.post(f"/j/{eid}", data={"phone": "601 234 567", "email": "a@b.cz", "consent": "1"})
    assert r.status_code == 200 and "Hotovo" in r.text
    c.post(f"/j/{eid}", data={"phone": "+420601234567", "consent": "1"})                     # same phone: no duplicate
    st = c.get("/api/hall").json()
    assert st["count"] == 1 and st["participants"][0]["phone"] == "*** *** 567" and "<svg" in st["qr"]
    assert c.get("/j/unknown").status_code == 404


def test_call_everybody_then_sms_to_who_did_not_answer_and_ano_reply(hall, monkeypatch):
    m, h, tw = hall
    monkeypatch.setattr(h, "_start", lambda fn: fn())
    monkeypatch.setattr(h.time, "sleep", lambda s: None)
    c = TestClient(m.app)
    eid = c.get("/api/hall").json()["id"]
    for ph in ("+420601000001", "+420601000002"):
        c.post(f"/j/{eid}", data={"phone": ph, "consent": "1"})
    assert c.post("/api/hall/call").json() == {"calling": 2}
    assert [k["to"] for k in tw.calls] == ["+420601000001", "+420601000002"]
    assert tw.calls[0]["url"] == f"https://jsemvcas.test/twilio/hall/voice/{eid}/1"
    # 1 picks up and presses 1
    assert "Gather" in c.post(f"/twilio/hall/voice/{eid}/1").text
    assert "ozve" in c.post(f"/twilio/hall/answer/{eid}/1", data={"Digits": "1"}).text
    c.post(f"/twilio/hall/status/{eid}/1", data={"CallStatus": "completed"})
    # 2 does not pick up → SMS with the centre links
    c.post(f"/twilio/hall/status/{eid}/2", data={"CallStatus": "no-answer"})
    ps = {p["n"]: p for p in c.get("/api/hall").json()["participants"]}
    assert ps[1]["status"] == "interested" and ps[2]["status"] == "no_answer" and ps[2]["fallback"] == ["sms"]
    assert len(tw.sms) == 1 and tw.sms[0]["to"] == "+420601000002" and "jsemvcas.test/centra" in tw.sms[0]["body"]
    # 2 answers ANO to the SMS
    r = c.post("/twilio/sms", data={"From": "+420601000002", "Body": "Ano"})
    assert "<Message>" in r.text
    assert {p["n"]: p for p in c.get("/api/hall").json()["participants"]}[2]["status"] == "interested"
    assert c.get("/centra", follow_redirects=False).headers["location"].startswith("https://www.vzp.cz/")


def test_closed_event_is_replaced_so_the_qr_code_keeps_working(hall):
    m, h, _ = hall
    c = TestClient(m.app)
    old = c.get("/api/hall").json()["id"]
    d = h._load()
    d["events"][old]["created"] -= (h.ttl_hours() + 1) * 3600  # joining closed, but not yet 2 days old
    h._save(d)
    st = c.get("/api/hall").json()
    assert st["id"] != old and st["open"]
    assert "Zapojte se" in c.get(f"/j/{st['id']}").text
