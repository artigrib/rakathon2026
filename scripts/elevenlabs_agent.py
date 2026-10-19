"""Create or update the ElevenLabs voice agent for the phone call (VOICE_MODE=agent). Config as code.

  python scripts/elevenlabs_agent.py [--case x]            # create, prints ELEVENLABS_AGENT_ID=… for the .env
  python scripts/elevenlabs_agent.py [--case x] <agent_id> # update the existing agent

The case defaults to env CASE, else screening. The agent may only say the approved sentences of the case dialog
(cases/<id>/dialog.py: agent_prompt(), GREETING, AGENT_DECISIONS …). The model understands the person, it never
improvises; anything else goes to a human. The result of the call comes back as data collection field `decision`
(+ `preferred_time` and the case's AGENT_DATA fields), which the backend turns into a journey event (backend/agent_call.py).
"""
import argparse
import importlib
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API = "https://api.elevenlabs.io/v1/convai"
VOICE = os.getenv("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # Sarah, premade


def dialog(case: str = ""):
    return importlib.import_module(f"cases.{case or os.getenv('CASE', 'screening')}.dialog")


def prompt(case: str = "") -> str:
    return dialog(case).agent_prompt()


def config(case: str = "") -> dict:
    d = dialog(case)
    data = {
        "decision": {"type": "string", "description": "Výsledek hovoru, právě jedna z hodnot: "
                     + "; ".join(f"{k} = {v}" for k, v in d.AGENT_DECISIONS.items())},
        "preferred_time": {"type": "string", "description": d.AGENT_WHEN},
        **{k: {"type": "string", "description": v} for k, v in getattr(d, "AGENT_DATA", {}).items()},
    }
    return {
        "name": d.AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": d.GREETING,
                "language": "cs",
                "prompt": {"prompt": d.agent_prompt(), "llm": "gemini-2.0-flash", "temperature": 0.0,
                           "tools": [{"type": "system", "name": "end_call", "description": "Ukonči hovor po závěrečné větě."}]},
            },
            "tts": {"voice_id": VOICE, "model_id": "eleven_flash_v2_5", "agent_output_audio_format": "ulaw_8000",
                    "stability": 0.6, "similarity_boost": 0.75, "speed": 0.95},
            "asr": {"user_input_audio_format": "ulaw_8000", "quality": "high"},
            "turn": {"turn_timeout": 10, "turn_eagerness": "normal", "speculative_turn": True, "silence_end_call_timeout": 20},
            "conversation": {"max_duration_seconds": 180},
        },
        "platform_settings": {"data_collection": data},
    }


def call(method, path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method=method,
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: {e.code} {e.read()[:500].decode()}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Create or update the ElevenLabs voice agent of a case.")
    ap.add_argument("--case", default=os.getenv("CASE", "screening"))
    ap.add_argument("--print", action="store_true", help="only print the config, call nothing")
    ap.add_argument("agent_id", nargs="?")
    a = ap.parse_args()
    if a.print:
        print(json.dumps(config(a.case), ensure_ascii=False, indent=1))
    elif a.agent_id:
        call("PATCH", f"/agents/{a.agent_id}", config(a.case))
        print("updated", a.agent_id)
    else:
        print("ELEVENLABS_AGENT_ID=" + call("POST", "/agents/create", config(a.case))["agent_id"])
