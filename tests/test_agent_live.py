"""Live transcript of an agent call (VOICE_MODE=agent): found once, then followed by id. No network: agent_call._req is canned."""
import asyncio
import importlib
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient  # the root conftest.py sets the env (runs with CASE=screening)

SID = "CA_live"


@pytest.fixture()
def app(monkeypatch):
    import backend.app as m
    importlib.reload(m)
    m.store.reset()
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="agent"))
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    monkeypatch.setattr(m.agent_call, "LIVE_STEP_S", 0)
    m.store.data["outbox"].append({"patient": "P1", "channel": "voice", "sid": SID, "live": True, "status": "in-progress"})
    return m


def _entry(m):
    return next(x for x in m.store.data["outbox"] if x.get("sid") == SID)


class Fake:
    """ElevenLabs: a list of two conversations, the second is our call; every GET by id adds one turn.
    stop_after: per-id GETs after which Twilio reports the call completed."""

    def __init__(self, m, stop_after=3, done=False):
        self.m, self.stop_after, self.done = m, stop_after, done
        self.lists, self.gets = 0, []

    def conv(self, cid):
        n = len(self.gets)
        tr = [{"role": "agent" if i % 2 == 0 else "user", "message": f"věta {i}", "time_in_call_secs": i} for i in range(n)]
        c = {"conversation_id": cid, "status": "done" if self.done else "processing", "transcript": tr,
             "metadata": {"phone_call": {"call_sid": SID if cid == "conv_ours" else "CA_other"}}}
        if self.done:
            c["analysis"] = {"data_collection_results": {"decision": {"value": "unclear"}}}
        return c

    def __call__(self, method, path, body=None, timeout=10):
        if path.startswith("/conversations?"):
            self.lists += 1
            return json.dumps({"conversations": [{"conversation_id": "conv_other"}, {"conversation_id": "conv_ours"}]})
        cid = path.rsplit("/", 1)[1]
        self.gets.append(cid)
        if self.m and len([g for g in self.gets if g == "conv_ours"]) > self.stop_after:
            self.m.store.outbox_update(SID, status="completed")
        return json.dumps(self.conv(cid))


def test_finds_once_then_follows_by_id_and_stores_turns(app, monkeypatch):
    m = app
    f = Fake(m, stop_after=4)
    monkeypatch.setattr(m.agent_call, "_req", f)
    asyncio.run(m._agent_live("P1", SID))
    assert f.lists == 1  # (a) the conversation list is searched once
    assert f.gets[:2] == ["conv_other", "conv_ours"] and set(f.gets[2:]) == {"conv_ours"} and len(f.gets) > 3
    e = _entry(m)
    assert e["conversation_id"] == "conv_ours"  # cached for the outcome
    tr = e["transcript"]  # (b) turns in the agent_call.turns() shape
    assert tr and tr[0] == {"who": "bot", "text": "věta 0", "t": 0} and tr[1]["who"] == "user"


def test_final_status_stops_the_loop(app, monkeypatch):
    m = app
    f = Fake(m, stop_after=2)
    monkeypatch.setattr(m.agent_call, "_req", f)
    monkeypatch.setattr(m.agent_call, "LIVE_MAX_S", 3600)
    asyncio.run(asyncio.wait_for(m._agent_live("P1", SID), 5))  # (c) returns although the time limit is far
    n = len(f.gets)
    assert _entry(m)["status"] == "completed" and n == 2 + 2
    # already over: nothing is fetched at all
    f2 = Fake(None)
    monkeypatch.setattr(m.agent_call, "_req", f2)
    asyncio.run(m._agent_live("P1", SID))
    assert f2.lists == 0 and not f2.gets


def test_gives_up_quietly(app, monkeypatch):
    m = app

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(m.agent_call, "_req", boom)
    asyncio.run(m._agent_live("P1", SID))  # no exception
    assert "transcript" not in _entry(m) and SID not in m._LIVE
    # no matching conversation: stops after LIVE_FIND_S
    monkeypatch.setattr(m.agent_call, "_req", lambda *a, **k: json.dumps({"conversations": []}))
    monkeypatch.setattr(m.agent_call, "LIVE_FIND_S", 0)
    asyncio.run(asyncio.wait_for(m._agent_live("P1", SID), 5))
    assert "conversation_id" not in _entry(m)


def test_in_progress_status_starts_the_live_task(app, monkeypatch):
    m = app
    seen = []

    async def live(pid, sid):
        seen.append((pid, sid))
    monkeypatch.setattr(m, "_agent_live", live)
    c = TestClient(m.app)
    c.post("/twilio/call-status/P1", data={"CallSid": SID, "CallStatus": "in-progress"})
    assert seen == [("P1", SID)]
    monkeypatch.setattr(m, "settings", replace(m.settings, voice_mode="gather"))
    c.post("/twilio/call-status/P1", data={"CallSid": SID, "CallStatus": "in-progress"})
    assert seen == [("P1", SID)]  # only in agent mode


def test_patient_api_returns_the_transcript_of_a_gather_call(app):
    m = app
    turns = [{"who": "bot", "text": "Dobrý den"}, {"who": "user", "text": "Ano"}]
    m.store.data["outbox"].append({"patient": "P2", "channel": "voice", "sid": "CA_g", "live": True, "status": "in-progress",
                                   "to": "+420", "text": "x"})
    m.store.outbox_update("CA_g", transcript=turns)  # as voice_answer does after each turn
    out = TestClient(m.app).get("/api/patient/P2").json()["outbox"]
    assert out[0]["transcript"] == turns and "to" not in out[0]


def test_outcome_reads_the_cached_conversation(app, monkeypatch):
    m = app
    f = Fake(None, done=True)
    monkeypatch.setattr(m.agent_call, "_req", f)
    o = m.agent_call.outcome(SID, wait_s=5, step_s=0, conversation_id="conv_ours")
    assert o and o["conversation_id"] == "conv_ours" and f.lists == 0 and f.gets == ["conv_ours"]
    # after the call, _agent_outcome passes the id _agent_live cached on the outbox entry
    seen = {}
    monkeypatch.setattr(m.agent_call, "outcome", lambda sid, **k: seen.update(sid=sid, **k))
    m.store.outbox_update(SID, conversation_id="conv_ours")
    TestClient(m.app).post("/twilio/call-status/P1", data={"CallSid": SID, "CallStatus": "completed", "CallDuration": "20"})
    assert seen == {"sid": SID, "conversation_id": "conv_ours"}
