"""Create or update the ElevenLabs voice agent for the phone call (VOICE_MODE=agent). Config as code.

  python scripts/elevenlabs_agent.py            # create, prints ELEVENLABS_AGENT_ID=… for backend/.env
  python scripts/elevenlabs_agent.py <agent_id> # update the existing agent

The agent may only say the approved sentences from backend/voice_ai.py. The model understands the patient,
it never improvises medical content; anything else goes to the nurse. The result of the call comes back as
data collection field `decision`, which the backend turns into a journey event (backend/agent_call.py).
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.voice_ai import ASK_AGAIN, CLOSING, FAQ, GREETING, NOT_UNDERSTOOD  # noqa: E402

API = "https://api.elevenlabs.io/v1/convai"
VOICE = os.getenv("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # Sarah, premade

DECISIONS = {
    "interested": "chce, aby se ozvala sestra (ano, má zájem)",
    "callback": "chce, aby mu sestra zavolala, nebo má otázku, na kterou nemáš schválenou odpověď",
    "booked": "už má termín vyšetření nebo už byl vyšetřen",
    "not_now": "teď ne, později",
    "declined": "nemá zájem, nechce další kontakt",
    "unclear": "nepodařilo se zjistit odpověď",
}


def prompt() -> str:
    faq = "\n".join(f"- {answer}" for _, answer in FAQ)
    closing = "\n".join(f"- {k}: {v}" for k, v in CLOSING.items())
    return f"""Jsi hlasový asistent ordinace praktického lékaře. Voláš pacientovi kvůli bezplatnému preventivnímu
vyšetření plic (program časného záchytu karcinomu plic). Mluvíš česky, klidně, pomalu a zdvořile, vykáš.
Volaný je starší člověk: nech ho domluvit, nespěchej, mluv krátce.

PRAVIDLA, která nesmíš porušit:
1. Říkáš jen věty z tohoto zadání, doslova nebo jen s malou úpravou slovosledu. Nic dalšího o zdraví, nemoci,
   riziku, výsledcích, lécích ani o pacientovi neříkáš. Nejsi lékař a neradíš.
2. Na otázku, na kterou tu nemáš schválenou odpověď, řekni: "{CLOSING['handoff']}" a ukonči hovor.
3. Nikdy nesděluj žádné údaje o pacientovi a na žádné se neptej, kromě toho, kdy se mu hodí, aby sestra zavolala.
4. Pokud pacient chce ukončit hovor nebo nechce být kontaktován, poděkuj a ukonči hovor.

Postup:
- Úvodní věta už zazněla: "{GREETING}"
- Když odpoví ano: zeptej se "Kdy se Vám hodí, aby sestra zavolala, spíš dopoledne, nebo odpoledne?"
  Odpověď si zapamatuj, pak řekni "{CLOSING['interested']}" a ukonči hovor.
- Když řekne, že už má termín nebo byl vyšetřen: "{CLOSING['booked']}" a ukonči hovor.
- Když chce, aby mu sestra zavolala: "{CLOSING['callback']}" a ukonči hovor.
- Když řekne teď ne nebo později: "{CLOSING['not_now']}" a ukonči hovor.
- Když nemá zájem: "{CLOSING['declined']}" a ukonči hovor.
- Když se ptá na vyšetření, použij jen tyto odpovědi a potom se znovu zeptej: "{ASK_AGAIN}"
{faq}
- Když nerozumíš: "{NOT_UNDERSTOOD}" Po druhém nedorozumění řekni "{CLOSING['handoff']}" a ukonči hovor.

Schválené závěrečné věty:
{closing}
"""


def config() -> dict:
    return {
        "name": "Plíce včas – hlasový asistent ordinace",
        "conversation_config": {
            "agent": {
                "first_message": GREETING,
                "language": "cs",
                "prompt": {"prompt": prompt(), "llm": "gemini-2.0-flash", "temperature": 0.0,
                           "tools": [{"type": "system", "name": "end_call", "description": "Ukonči hovor po závěrečné větě."}]},
            },
            "tts": {"voice_id": VOICE, "model_id": "eleven_flash_v2_5", "agent_output_audio_format": "ulaw_8000",
                    "stability": 0.6, "similarity_boost": 0.75, "speed": 0.95},
            "asr": {"user_input_audio_format": "ulaw_8000", "quality": "high"},
            "turn": {"turn_timeout": 10, "turn_eagerness": "patient", "silence_end_call_timeout": 20},
            "conversation": {"max_duration_seconds": 180},
        },
        "platform_settings": {
            "data_collection": {
                "decision": {"type": "string", "description": "Výsledek hovoru, právě jedna z hodnot: "
                             + "; ".join(f"{k} = {v}" for k, v in DECISIONS.items())},
                "preferred_time": {"type": "string", "description": "Kdy se pacientovi hodí telefonát sestry (dopoledne, odpoledne, konkrétní den), jinak prázdné."},
            },
        },
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
    if len(sys.argv) > 1:
        call("PATCH", f"/agents/{sys.argv[1]}", config())
        print("updated", sys.argv[1])
    else:
        print("ELEVENLABS_AGENT_ID=" + call("POST", "/agents/create", config())["agent_id"])
