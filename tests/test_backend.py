"""Backend in MOCK mode: no Twilio keys, nothing leaves the machine."""
import importlib
import os

import pytest

os.environ["STATE_FILE"] = "/tmp/plice-test-state.json"
for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "PUBLIC_URL", "DEMO_TO"):
    os.environ[k] = ""

from fastapi.testclient import TestClient  # noqa: E402

from backend.replies import classify  # noqa: E402


@pytest.fixture()
def client():
    import backend.app as m
    importlib.reload(m)
    m.store.reset()
    return TestClient(m.app), m.store


@pytest.mark.parametrize("text,intent", [
    ("Ano, mám zájem", "interested"),
    ("ano", "interested"),
    ("1", "interested"),
    ("Už jsem objednaný na 3.11.", "booked"),
    ("Zavolejte mi prosím odpoledne", "callback"),
    ("Ano, ale až po Vánocích", "not_now"),
    ("Teď ne, děkuji", "not_now"),
    ("Nemám zájem", "declined"),
    ("2", "declined"),
    ("STOP", "opt_out"),
    ("Nepište mi už", "opt_out"),
    ("Kolik to stojí?", "question"),
    ("🙂", "unclear"),
])
def test_classify_czech_replies(text, intent):
    assert classify(text)["intent"] == intent


def test_health_reports_mock(client):
    c, _ = client
    assert c.get("/api/health").json()["mode"] == "mock"


def test_send_then_sms_reply_moves_patient(client):
    c, store = client
    r = c.post("/api/send", json={"items": [{"id": "SYN-000001", "channel": "sms", "text": "Dobrý den…"}], "date": "2026-10-16"})
    assert r.json()["sent"][0]["status"] == "simulated"
    assert store.get("SYN-000001")["stage"] == "sent"
    c.post("/api/step", json={"id": "SYN-000001", "text": "Ano, mám zájem", "date": "2026-10-17"})
    d = c.get("/api/state").json()["decisions"]["SYN-000001"]
    assert d["stage"] == "interested" and d["journey"][-1]["intent"] == "interested"


def test_first_refusal_is_soft_second_stops(client):
    c, store = client
    c.post("/api/step", json={"id": "P1", "text": "Nemám zájem"})
    assert store.get("P1")["stage"] == "not_now"
    c.post("/api/step", json={"id": "P1", "text": "Opravdu nechci"})
    assert store.get("P1")["stage"] == "declined"


def test_opt_out_stops_immediately(client):
    c, store = client
    c.post("/api/step", json={"id": "P2", "text": "STOP"})
    assert store.get("P2")["stage"] == "declined"


def test_nurse_steps_and_result(client):
    c, store = client
    for st in ("booked", "ldct"):
        c.post("/api/step", json={"id": "P3", "stage": st})
    c.post("/api/step", json={"id": "P3", "stage": "result", "result": "negative"})
    assert store.get("P3")["result"] == "negative"


def test_voice_twiml_and_digit_answer(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "P4", "channel": "voice", "text": "Dobrý den.\n\nStiskněte 1 nebo 2."}]})
    x = c.post("/twilio/voice/P4").text
    assert "<Gather" in x and "cs-CZ" in x and "Stiskněte 1 nebo 2." in x
    a = c.post("/twilio/voice/P4/answer", data={"Digits": "1"}).text
    assert "ozve" in a and store.get("P4")["stage"] == "interested"


def test_inbound_sms_unknown_number_is_ignored(client):
    c, store = client
    r = c.post("/twilio/sms", data={"From": "+420000", "Body": "ano"})
    assert r.status_code == 200 and store.decisions() == {}


def test_serves_web_app(client):
    c, _ = client
    assert c.get("/app/index.html").status_code == 200


def test_tick_runs_the_contact_plan(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "SYN-000001", "channel": "sms", "text": "x"}]})
    assert c.get("/api/state").json()["plans"]["SYN-000001"]["channel"] == "voice"
    r = c.post("/api/tick", json={"days": 3}).json()
    assert r["clock"] == "2026-10-19" and r["touches"][0]["id"] == "SYN-000001"
    last = store.get("SYN-000001")["journey"][-1]
    assert last["channel"] == "voice" and last["auto"] is True
    c.post("/api/tick", json={"days": 9})
    assert store.get("SYN-000001")["stage"] == "nurse_call"
    assert "SYN-000001" not in c.get("/api/state").json()["plans"]


def test_reply_stops_automatic_touches(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": "SYN-000001", "channel": "sms", "text": "x"}]})
    c.post("/api/step", json={"id": "SYN-000001", "text": "Ano"})
    assert c.post("/api/tick", json={"days": 10}).json()["touches"] == []


def test_patient_link_page_and_answer(client):
    c, store = client
    token = store.token("SYN-000001")
    page = c.get(f"/p/{token}").text
    assert "Ano, mám zájem" in page and "SYN-000001" not in page  # no identifiers or health data on the page
    done = c.post(f"/p/{token}", data={"answer": "interested"}).text
    assert "ozve" in done and store.get("SYN-000001")["stage"] == "interested"
    assert "neplatí" in c.get("/p/nonsense").text


def test_link_opt_out_stops_everything(client):
    c, store = client
    token = store.token("SYN-000002")
    c.post(f"/p/{token}", data={"answer": "stop"})
    assert store.get("SYN-000002")["stage"] == "declined"


def test_ai_understanding_with_fake_model(client, monkeypatch):
    c, store = client
    import backend.llm as llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "classify", lambda t: {"intent": "callback", "when": "zítra odpoledne", "confidence": "high",
                                                     "why": "Chce zavolat zítra odpoledne."})
    c.post("/api/step", json={"id": "P5", "text": "Mohla byste mi brnknout zítra po obědě?"})
    e = store.get("P5")["journey"][-1]
    assert (e["intent"], e["source"], e["when"]) == ("callback", "ai", "zítra odpoledne")


def test_opt_out_rule_wins_over_ai(client, monkeypatch):
    c, store = client
    import backend.llm as llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "classify", lambda t: {"intent": "interested", "confidence": "high", "why": "x"})
    c.post("/api/step", json={"id": "P6", "text": "STOP"})
    assert store.get("P6")["stage"] == "declined"


def test_ai_failure_falls_back_to_rules(client, monkeypatch):
    c, store = client
    import backend.llm as llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    def boom(t):
        raise TimeoutError()
    monkeypatch.setattr(llm, "classify", boom)
    c.post("/api/step", json={"id": "P7", "text": "Ano, mám zájem"})
    e = store.get("P7")["journey"][-1]
    assert e["intent"] == "interested" and e["source"] == "rules"


def test_low_confidence_ai_goes_to_nurse(client, monkeypatch):
    c, store = client
    import backend.llm as llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "classify", lambda t: {"intent": "interested", "confidence": "low", "why": "asi ano"})
    c.post("/api/step", json={"id": "P8", "text": "no uvidíme"})
    assert store.get("P8")["stage"] == "callback"


def test_ai_call_conversation_over_websocket(client):
    c, store = client
    with c.websocket_connect("/ws/relay/P9") as ws:
        ws.send_json({"type": "setup", "callSid": "CA1"})
        ws.send_json({"type": "prompt", "voicePrompt": "A kolik to stojí?"})
        r = ws.receive_json()
        assert "bezplatné" in r["token"] and "ozvala sestra" in r["token"]
        ws.send_json({"type": "prompt", "voicePrompt": "Tak jo, ano, mám zájem"})
        assert "ozve" in ws.receive_json()["token"]
        assert ws.receive_json()["type"] == "end"
    e = store.get("P9")["journey"][-1]
    assert (store.get("P9")["stage"], e["via"]) == ("interested", "voice-ai")


def test_ai_call_hands_unclear_to_nurse(client):
    c, store = client
    with c.websocket_connect("/ws/relay/P10") as ws:
        for _ in range(2):
            ws.send_json({"type": "prompt", "voicePrompt": "hmm"})
            last = ws.receive_json()
        assert "sestře" in last["token"]
    assert store.get("P10")["stage"] == "callback"


def test_relay_twiml_when_enabled(monkeypatch, client):
    c, _ = client
    import backend.app as m
    from dataclasses import replace
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="relay", public_url="https://demo.example"))
    x = c.post("/twilio/voice/P11").text
    assert "ConversationRelay" in x and "wss://demo.example/ws/relay/P11" in x and 'language="cs-CZ"' in x
