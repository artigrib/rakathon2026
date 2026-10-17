"""Visitor sign-in: own contacts, own demo state, replies and callbacks land in the visitor's demo."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path, monkeypatch):
    import importlib
    from dataclasses import replace
    import backend.settings as st
    monkeypatch.setattr(st, "settings", replace(st.settings, state_file=tmp_path / "state.json", demo_password="rakathon",
                                                 public_url="https://jsemvcas.test"))
    import backend.recipient, backend.sessions, backend.ctx, backend.channels, backend.app
    for mod in (backend.recipient, backend.sessions, backend.ctx, backend.channels):
        monkeypatch.setattr(mod, "settings", st.settings)
    m = importlib.reload(backend.app)
    m.store.reset()
    return m


def login(m, phone, email="v@x.cz", code="rakathon"):
    c = TestClient(m.app)
    r = c.post("/login", data={"code": code, "phone": phone, "email": email, "next": "/app/"}, follow_redirects=False)
    return c, r


def test_login_page_and_errors(app):
    c = TestClient(app.app)
    assert c.get("/app/", follow_redirects=False).headers["location"] == "/login?next=/app/"
    assert "Přístupový kód" in c.get("/login").text
    _, r = login(app, "601 234 567", code="spatne")
    assert r.status_code == 401 and "Nesprávný" in r.text
    _, r = login(app, "+44 7700 900123")
    assert r.status_code == 400 and "+420" in r.text
    c, r = login(app, "601 234 567")
    assert r.status_code == 303 and r.headers["location"] == "/app/"
    assert c.get("/api/state").status_code == 200
    me = c.get("/api/recipient").json()
    assert me["session"] and me["phone"] == "+420601234567" and me["email"] == "v@x.cz"


def test_each_visitor_has_own_demo_and_replies_land_in_it(app):
    a, _ = login(app, "+420601000001", "a@x.cz")
    b, _ = login(app, "+420601000002", "b@x.cz")
    a.post("/api/step", json={"id": "S1", "stage": "send"})
    assert "S1" in a.get("/api/state").json()["decisions"]
    assert "S1" not in b.get("/api/state").json()["decisions"]           # B does not see A's demo
    assert "S1" not in app.store.decisions()                              # nor does the shared demo
    # A's phone replies "Ano": it lands in A's demo even without a cookie (Twilio has none)
    sa = app.sessions.sid(next(t for t, s in app.sessions._load().items() if s["phone"] == "+420601000001"))
    st = app._store_for(sa)
    st.data["outbox"].append({"patient": "S1", "channel": "sms", "to": "+420601000001", "live": True, "sid": "SMa"})
    TestClient(app.app).post("/twilio/sms", data={"From": "+420601000001", "Body": "Ano"})
    assert app._store_for(sa).get("S1")["stage"] == "interested"
    # a callback tagged with A's session (?s=) also lands in A's demo
    TestClient(app.app).post(f"/twilio/status?s={sa}", data={"MessageSid": "SMa", "MessageStatus": "delivered"})
    assert app._store_for(sa).get("S1")["journey"][-1]["delivery"] == "delivered"


def test_logout(app):
    c, _ = login(app, "+420601000003")
    c.get("/logout")
    assert c.get("/api/state").status_code == 401
