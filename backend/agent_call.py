"""Phone call through an ElevenLabs voice agent (VOICE_MODE=agent), Twilio stays the carrier.

Our server still starts the call (channels.start_call) and receives its status. When the call connects, Twilio asks
/twilio/voice/{pid}; we register the call with ElevenLabs, which returns the TwiML that streams audio to the agent.
After the call, the agent's data collection field `decision` becomes a journey event through the state machine.
The agent itself is configured in scripts/elevenlabs_agent.py (approved sentences only).
"""
import json
import os
import time
import urllib.request

from .case import CASE

API = "https://api.elevenlabs.io/v1/convai"
DECISIONS = set(CASE.dialog.DECISIONS)
DATA = getattr(CASE.dialog, "AGENT_DATA", {})  # extra data collection fields of the case → `extra`


def agent_id() -> str:
    return os.getenv("ELEVENLABS_AGENT_ID", "")


def _req(method, path, body=None, timeout=10):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", ""), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def register(pid: str, from_number: str, to_number: str) -> str:
    """TwiML that connects this Twilio call to the agent."""
    return _req("POST", "/twilio/register-call", {
        "agent_id": agent_id(), "from_number": from_number, "to_number": to_number, "direction": "outbound",
        "conversation_initiation_client_data": {"dynamic_variables": {"patient_id": pid}},
    })


def _find(call_sid: str):
    convs = json.loads(_req("GET", f"/conversations?agent_id={agent_id()}&page_size=10")).get("conversations", [])
    for c in convs:
        full = json.loads(_req("GET", f"/conversations/{c['conversation_id']}"))
        pc = (full.get("metadata") or {}).get("phone_call") or {}
        if call_sid in (pc.get("call_sid"), pc.get("external_call_sid"), (full.get("metadata") or {}).get("call_sid")):
            return full
    return None


def outcome(call_sid: str, wait_s: float = 90, step_s: float = 5):
    """{'intent', 'text', 'when', 'conversation_id'[, 'extra']} once the agent's analysis is ready, else None."""
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            c = _find(call_sid)
        except Exception:  # noqa: BLE001 – network hiccup, retry until the deadline
            c = None
        if c and c.get("status") == "done" and c.get("analysis"):
            dc = c["analysis"].get("data_collection_results") or {}
            decision = str((dc.get("decision") or {}).get("value") or "unclear").strip().lower()
            when = str((dc.get("preferred_time") or {}).get("value") or "").strip()
            said = " | ".join(t.get("message") or "" for t in c.get("transcript") or [] if t.get("role") == "user")
            extra = {k: (dc.get(k) or {}).get("value") for k in DATA if (dc.get(k) or {}).get("value") not in (None, "")}
            return {"intent": decision if decision in DECISIONS else "unclear", "text": said.strip(" |"),
                    "when": when, "conversation_id": c.get("conversation_id"), **({"extra": extra} if extra else {})}
        time.sleep(step_s)
    return None
