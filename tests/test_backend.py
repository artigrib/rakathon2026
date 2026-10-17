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


def test_elevenlabs_voice_is_played_and_cached(client, monkeypatch, tmp_path):
    c, store = client
    import backend.tts as tts
    import backend.channels as ch
    from dataclasses import replace
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    calls = []
    monkeypatch.setattr(tts, "_synthesize", lambda text, timeout: calls.append(text) or b"ID3fake-mp3")
    monkeypatch.setattr(ch, "settings", replace(ch.settings, public_url="https://demo.example"))
    c.post("/api/send", json={"items": [{"id": "P12", "channel": "voice", "text": "Dobrý den.\n\nStiskněte 1."}]})
    x = c.post("/twilio/voice/P12").text
    assert "<Play>https://demo.example/audio/" in x and "<Say" not in x
    name = x.split("/audio/")[1].split("<")[0]
    assert c.get(f"/audio/{name}").content == b"ID3fake-mp3"
    c.post("/twilio/voice/P12")
    assert calls.count("Dobrý den.\n\nStiskněte 1.") == 1  # cached, generated once
    assert c.get("/audio/../../etc/passwd").status_code == 404


def test_voice_falls_back_to_twilio_say_when_tts_fails(client, monkeypatch, tmp_path):
    c, _ = client
    import backend.tts as tts
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    def boom(text, timeout):
        raise TimeoutError()
    monkeypatch.setattr(tts, "_synthesize", boom)
    c.post("/api/send", json={"items": [{"id": "P13", "channel": "voice", "text": "Dobrý den."}]})
    x = c.post("/twilio/voice/P13").text
    assert "<Say" in x and "Dobrý den." in x


def test_inbound_sms_gets_a_confirmation(client):
    c, store = client
    store.data["outbox"].append({"patient": "P5", "to": "+420111", "live": True, "channel": "sms"})
    x = c.post("/twilio/sms", data={"From": "+420111", "Body": "Ano"}).text
    assert "<Message>" in x and "ozve" in x and store.get("P5")["stage"] == "interested"
    y = c.post("/twilio/sms", data={"From": "+420111", "Body": "STOP"}).text
    assert "<Message>" not in y


def test_nurse_first_refusal_is_soft(client):
    c, store = client
    c.post("/api/step", json={"id": "P6", "stage": "declined"})
    assert store.get("P6")["stage"] == "not_now"
    c.post("/api/step", json={"id": "P6", "stage": "declined"})
    assert store.get("P6")["stage"] == "declined"


def test_email_is_simulated_without_sendgrid(client):
    c, store = client
    r = c.post("/api/send", json={"items": [{"id": "P7", "channel": "email", "text": "Dobrý den."}]}).json()
    assert store.get("P7")["stage"] == "sent" and store.data["outbox"][-1]["channel"] == "email"


def test_patient_messages_hide_phone_and_link_token(client):
    c, store = client
    store.log(patient="P9", channel="sms", text="Ahoj https://x/p/SECRETtok", to="+420777", live=True, status="delivered", day="2026-10-16")
    o = c.get("/api/patient/P9").json()["outbox"][0]
    assert "to" not in o and "SECRETtok" not in o["text"] and o["ts"] and o["status"] == "delivered"


def test_email_via_smtp(monkeypatch):
    import backend.channels as ch
    sent = {}

    class S:
        def __init__(self, host, port, timeout): sent["host"] = host
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): pass
        def login(self, u, p): sent["user"] = u
        def send_message(self, m): sent["to"] = m["To"]; sent["body"] = m.get_content()
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", S)
    from dataclasses import replace
    monkeypatch.setattr(ch, "settings", replace(ch.settings, smtp_host="smtp.gmail.com", smtp_user="a@gmail.com", smtp_password="x", demo_email="b@x.cz"))
    r = ch.send_email("Dobrý den.", True)
    assert r["live"] and sent["to"] == "b@x.cz" and "Dobrý den." in sent["body"]


def test_agent_call_registers_with_elevenlabs_and_records_outcome(monkeypatch, client):
    c, store = client
    import backend.app as m
    from dataclasses import replace
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="agent"))
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    seen = {}
    monkeypatch.setattr(m.agent_call, "register", lambda pid, f, t: seen.update(pid=pid, f=f, t=t) or "<Response><Connect/></Response>")
    monkeypatch.setattr(m.agent_call, "outcome", lambda sid, **k: {"intent": "interested", "text": "Ano, klidně", "when": "odpoledne",
                                                                  "conversation_id": "conv_1"})
    c.post("/api/send", json={"items": [{"id": "P12", "channel": "voice", "text": "Dobrý den."}]})
    x = c.post("/twilio/voice/P12", data={"From": "+1980", "To": "+420111"}).text
    assert "<Connect/>" in x and seen == {"pid": "P12", "f": "+1980", "t": "+420111"}
    c.post("/twilio/call-status/P12", data={"CallSid": "CA1", "CallStatus": "completed", "CallDuration": "40"})
    d = store.get("P12")
    assert d["stage"] == "interested" and d["journey"][-1]["when"] == "odpoledne" and d["journey"][-1]["via"] == "voice-agent"


def test_agent_unreachable_falls_back_to_scripted_call(monkeypatch, client):
    c, _ = client
    import backend.app as m
    from dataclasses import replace
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="agent"))
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")

    def boom(*a):
        raise OSError("down")
    monkeypatch.setattr(m.agent_call, "register", boom)
    c.post("/api/send", json={"items": [{"id": "P13", "channel": "voice", "text": "Dobrý den."}]})
    assert "<Gather" in c.post("/twilio/voice/P13", data={"From": "+1", "To": "+2"}).text


def test_delivery_status_keeps_the_message_channel(client):
    c, store = client
    store.data["outbox"].append({"patient": "P14", "channel": "whatsapp", "sid": "SM_wa", "text": "x"})
    c.post("/twilio/status", data={"MessageSid": "SM_wa", "MessageStatus": "delivered"})
    e = store.get("P14")["journey"][-1]
    assert e["delivery"] == "delivered" and e["channel"] == "whatsapp"


def test_marks_are_stored_on_the_server(client):
    c, store = client
    assert c.post("/api/mark", json={"id": "M1", "field": "skipped", "value": True}).status_code == 200
    c.post("/api/mark", json={"id": "M1", "field": "draft", "value": {"channel": "sms", "text": "Ahoj"}})
    assert store.get("M1")["skipped"] is True and store.get("M1")["draft"]["text"] == "Ahoj"
    assert c.post("/api/mark", json={"id": "M1", "field": "stage", "value": "result"}).status_code == 400


def test_password_protects_app_but_not_webhooks(client, monkeypatch):
    import base64
    from dataclasses import replace
    import backend.app as m
    c, _ = client
    monkeypatch.setattr(m, "settings", replace(m.settings, demo_password="tajne"))
    assert c.get("/api/state").status_code == 401
    assert c.get("/app/index.html").status_code == 401
    assert c.get("/api/health").status_code == 200
    assert c.post("/twilio/sms", data={"From": "+420000", "Body": "ano"}).status_code == 200
    good = {"Authorization": "Basic " + base64.b64encode(b"plice:tajne").decode()}
    bad = {"Authorization": "Basic " + base64.b64encode(b"plice:spatne").decode()}
    assert c.get("/api/state", headers=good).status_code == 200
    assert c.get("/api/state", headers=bad).status_code == 401


def test_whatsapp_reply_goes_to_the_whatsapp_patient_not_the_last_call(client):
    c, store = client
    store.data["outbox"] += [
        {"patient": "P15", "channel": "whatsapp", "to": "+420777", "live": True, "sid": "SM1"},
        {"patient": "P16", "channel": "voice", "to": "+420777", "live": True, "sid": "CA1"},
        {"patient": "P17", "channel": "sms", "to": "+420777", "live": True, "sid": "SM2"},
    ]
    for pid in ("P15", "P16", "P17"):
        c.post("/api/send", json={"items": [{"id": pid, "channel": "sms", "text": "x"}]})
    c.post("/twilio/sms", data={"From": "whatsapp:+420777", "Body": "Ano"})
    e = store.get("P15")["journey"][-1]
    assert store.get("P15")["stage"] == "interested" and e["via"] == "whatsapp"
    assert store.get("P16")["stage"] != "interested"
