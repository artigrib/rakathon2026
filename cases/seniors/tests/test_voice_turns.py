"""The whole call is kept: scripted (gather) calls ask a follow-up and record one reply at the end; agent calls store
the ElevenLabs transcript and understand everything the senior said."""
import json

from .test_api import PID

DAY = "2026-10-19"


def _send(c):
    c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "Dobrý den, jak se máte?"}], "date": DAY})


def _replies(store):
    return [e for e in store.get(PID).get("journey", []) if e.get("intent")]


def test_gather_asks_follow_up_and_records_whole_call_once(client):
    c, store = client
    _send(c)
    x = c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA1"}).text
    assert 'speechTimeout="3"' in x and "<Gather" in x
    a = c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA1", "SpeechResult": "Mám se dobře", "Confidence": "0.9"}).text
    assert "<Gather" in a and "Potřebujete ještě něco?" in a  # follow-up, nothing recorded yet
    assert _replies(store) == []
    a = c.post(f"/twilio/voice/{PID}/answer?n=2", data={"CallSid": "CA1", "SpeechResult": "Došly mi léky a potřebovala bych nakoupit"}).text
    assert "<Gather" in a and _replies(store) == []
    a = c.post(f"/twilio/voice/{PID}/answer?n=3", data={"CallSid": "CA1", "SpeechResult": "Ne, nic, děkuji"}).text
    assert "<Gather" in a and "Rozuměla jsem, že potřebujete nákup a léky z lékárny. Je to tak?" in a  # the recap
    assert _replies(store) == []
    a = c.post(f"/twilio/voice/{PID}/answer?recap=1", data={"CallSid": "CA1", "SpeechResult": "Ano, je to tak"}).text
    assert "<Gather" not in a
    r = _replies(store)
    assert len(r) == 1 and r[0]["intent"] == "need_items" and set(r[0]["extra"]["items"]) == {"nakup", "leky"}
    assert r[0]["summary"] == "Rozuměla jsem, že potřebujete nákup a léky z lékárny." and r[0]["confirmed"] is True
    tr = r[0]["transcript"]
    assert [t["who"] for t in tr] == ["bot", "user", "bot", "user", "bot", "user", "bot", "user", "bot"]
    assert tr[1] == {"who": "user", "text": "Mám se dobře", "confidence": "0.9"} and tr[2]["text"] == "Potřebujete ještě něco?"
    # the status callback after the call does not record it again
    c.post(f"/twilio/call-status/{PID}", data={"CallSid": "CA1", "CallStatus": "completed"})
    assert len(_replies(store)) == 1
    assert json.loads(store.path.read_text(encoding="utf-8"))["decisions"][PID]["journey"][-1]["transcript"][-1]["who"] == "bot"


def test_gather_emergency_ends_at_once(client):
    c, store = client
    _send(c)
    c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA2"})
    a = c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA2", "SpeechResult": "Ležím na zemi a nemůžu vstát"}).text
    assert "<Gather" not in a and "155" in a
    assert [e["intent"] for e in _replies(store)] == ["emergency"]


def test_gather_hang_up_during_follow_up_keeps_the_answer(client):
    c, store = client
    _send(c)
    c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA3"})
    c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA3", "SpeechResult": "Je mi smutno, nikdo za mnou nechodí"})
    assert _replies(store) == []
    c.post(f"/twilio/call-status/{PID}", data={"CallSid": "CA3", "CallStatus": "completed"})
    r = _replies(store)
    assert len(r) == 1 and r[0]["intent"] == "low_mood" and len(r[0]["transcript"]) == 4


def test_gather_silence_after_follow_up_records_what_was_said(client):
    c, store = client
    _send(c)
    c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA4"})
    c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA4", "SpeechResult": "Jsem v pořádku"})
    a = c.post(f"/twilio/voice/{PID}/answer?n=2&end=1", data={"CallSid": "CA4"}).text
    assert "Rozuměla jsem, že jste v pořádku a nic nepotřebujete. Je to tak?" in a and _replies(store) == []
    a = c.post(f"/twilio/voice/{PID}/answer?recap=1&end=1", data={"CallSid": "CA4"}).text  # silence to the recap too
    assert "<Gather" not in a and [e["intent"] for e in _replies(store)] == ["ok"]
    r = _replies(store)[0]
    assert r["summary"] == "Rozuměla jsem, že jste v pořádku a nic nepotřebujete." and "confirmed" not in r


def test_gather_recap_corrected_in_the_same_answer(client):
    c, store = client
    _send(c)
    c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA5"})
    c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA5", "Digits": "2"})
    a = c.post(f"/twilio/voice/{PID}/answer?recap=1", data={"CallSid": "CA5", "Digits": "2"}).text
    assert "Co mám opravit?" in a  # key 2 = no → one more open answer
    a = c.post(f"/twilio/voice/{PID}/answer?recap=2", data={"CallSid": "CA5", "SpeechResult": "Potřebuju nakoupit"}).text
    assert "<Gather" not in a
    r = _replies(store)
    assert len(r) == 1 and r[0]["intent"] == "need_items" and r[0]["confirmed"] is False
    assert r[0]["summary"] == "Rozuměla jsem, že potřebujete nákup."


def test_gather_recap_hang_up_keeps_answer_and_recap(client):
    c, store = client
    _send(c)
    c.post(f"/twilio/voice/{PID}", data={"CallSid": "CA6"})
    c.post(f"/twilio/voice/{PID}/answer", data={"CallSid": "CA6", "Digits": "1"})
    c.post(f"/twilio/call-status/{PID}", data={"CallSid": "CA6", "CallStatus": "completed"})
    r = _replies(store)
    assert len(r) == 1 and r[0]["intent"] == "ok" and "confirmed" not in r[0] and r[0]["summary"]
    a = c.post(f"/twilio/voice/{PID}/answer?recap=1", data={"CallSid": "CA6", "Digits": "1"}).text  # late: nothing new
    assert len(_replies(store)) == 1 and "<Gather" not in a


def test_recap_sentences():
    from cases.seniors import dialog as d
    assert d.recap("need_items", {"items": ["nakup", "leky", "obed"]}) == \
        "Rozuměla jsem, že potřebujete nákup, léky z lékárny a obědy. Je to tak?"
    assert d.recap("need_items", {}) == "Rozuměla jsem, že potřebujete pomoc. Je to tak?"
    assert d.recap("low_mood", {"items": "nakup"}).endswith("Potřebujete také nákup. Je to tak?")
    for intent in ("emergency", "opt_out", "callback", "unclear", "question"):
        assert d.recap(intent, {"items": ["nakup"]}) == ""
    p = d.agent_prompt()
    assert d.EMERGENCY in p and "Při ohrožení shrnutí nikdy nedělej" in p and "!" not in p


def test_agent_outcome_keeps_transcript_and_reads_all_turns(monkeypatch, client):
    c, store = client
    import backend.app as m
    from dataclasses import replace
    conv = {"conversation_id": "conv_9", "status": "done", "metadata": {"phone_call": {"call_sid": "CA9"}},
            "analysis": {"data_collection_results": {"decision": {"value": "ok"}}},
            "transcript": [{"role": "agent", "message": "Dobrý den, jak se máte?", "time_in_call_secs": 0},
                           {"role": "user", "message": "Ale jo, ujde to.", "time_in_call_secs": 4},
                           {"role": "agent", "message": None, "time_in_call_secs": 6},
                           {"role": "agent", "message": "Potřebujete ještě něco?", "time_in_call_secs": 7},
                           {"role": "user", "message": "Došly mi léky a potřebovala bych nakoupit.", "time_in_call_secs": 10}]}

    def fake_req(method, path, body=None, timeout=10):
        return json.dumps({"conversations": [{"conversation_id": "conv_9"}]} if path.startswith("/conversations?") else conv)
    monkeypatch.setattr(m.agent_call, "_req", fake_req)
    o = m.agent_call.outcome("CA9", wait_s=1)
    assert o["intent"] == "ok" and set(o["extra"]["items"]) == {"nakup", "leky"}
    assert [t["who"] for t in o["transcript"]] == ["bot", "user", "bot", "user"] and o["transcript"][1]["t"] == 4
    # through the webhook: the reply event and the outbox entry of the call keep the dialogue
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="agent"))
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    _send(c)
    store.data["outbox"][-1]["sid"] = "CA9"
    c.post(f"/twilio/call-status/{PID}", data={"CallSid": "CA9", "CallStatus": "completed"})
    r = _replies(store)
    assert len(r) == 1 and r[0]["via"] == "voice-agent" and len(r[0]["transcript"]) == 4
    assert store.data["outbox"][-1]["transcript"][3]["text"].startswith("Došly")


def test_agent_emergency_in_transcript_wins(monkeypatch, client):
    import backend.app as m
    conv = {"conversation_id": "c", "analysis": {"data_collection_results": {"decision": {"value": "ok"}}},
            "transcript": [{"role": "user", "message": "Mám bolest na hrudi"}]}
    assert m.agent_call.read(conv)["intent"] == "emergency"


def test_agent_outcome_stores_summary_and_confirmation(monkeypatch, client):
    c, store = client
    import backend.app as m
    from dataclasses import replace
    conv = {"conversation_id": "conv_s", "status": "done", "metadata": {"phone_call": {"call_sid": "CAS"}},
            "analysis": {"transcript_summary": "The senior needs groceries.",
                         "data_collection_results": {"decision": {"value": "need_items"}, "items": {"value": "nakup"},
                                                     "summary": {"value": "Paní potřebuje nákup, jinak je v pořádku."},
                                                     "recap_confirmed": {"value": "ano"}}},
            "transcript": [{"role": "agent", "message": "Dobrý den, jak se máte?"},
                           {"role": "user", "message": "Potřebovala bych nakoupit."},
                           {"role": "agent", "message": "Rozuměla jsem, že potřebujete nákup. Je to tak?"},
                           {"role": "user", "message": "Ano."}]}

    def fake_req(method, path, body=None, timeout=10):
        return json.dumps({"conversations": [{"conversation_id": "conv_s"}]} if path.startswith("/conversations?") else conv)
    monkeypatch.setattr(m.agent_call, "_req", fake_req)
    o = m.agent_call.outcome("CAS", wait_s=1)
    assert o["summary"] == "Paní potřebuje nákup, jinak je v pořádku." and o["confirmed"] is True
    assert "summary" not in o["extra"] and "recap_confirmed" not in o["extra"]
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="agent"))
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    _send(c)
    store.data["outbox"][-1]["sid"] = "CAS"
    c.post(f"/twilio/call-status/{PID}", data={"CallSid": "CAS", "CallStatus": "completed"})
    r = _replies(store)
    assert len(r) == 1 and r[0]["summary"].startswith("Paní potřebuje") and r[0]["confirmed"] is True
    assert store.data["outbox"][-1]["summary"] == r[0]["summary"] and store.data["outbox"][-1]["confirmed"] is True
    # no data collection summary → ElevenLabs' transcript summary; a corrected recap → confirmed False
    dc = conv["analysis"]["data_collection_results"]
    dc.pop("summary")
    dc["recap_confirmed"] = {"value": "ne"}
    o = m.agent_call.read(conv)
    assert o["summary"] == "The senior needs groceries." and o["confirmed"] is False
    dc["recap_confirmed"] = {"value": ""}
    assert "confirmed" not in m.agent_call.read(conv)


def test_agent_config_has_summary_fields():
    from scripts.elevenlabs_agent import config
    dc = config("seniors")["platform_settings"]["data_collection"]
    assert {"summary", "recap_confirmed", "decision", "items"} <= set(dc)
    assert "Je to tak?" in config("seniors")["conversation_config"]["agent"]["prompt"]["prompt"]
