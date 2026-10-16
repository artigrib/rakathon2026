"""Outbound channels. LIVE → Twilio REST; otherwise MOCK (recorded in the outbox, nothing is sent).
All real traffic goes to settings.demo_to: the challenge data has synthetic phone numbers."""
from xml.sax.saxutils import escape

from . import tts
from .settings import settings


def _client():
    from twilio.rest import Client  # imported lazily: tests and mock mode need no Twilio
    return Client(settings.account_sid, settings.auth_token)


def send_sms(body: str, live: bool) -> dict:
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    m = _client().messages.create(
        to=settings.demo_to, from_=settings.from_number, body=body,
        status_callback=f"{settings.public_url}/twilio/status",
    )
    return {"sid": m.sid, "live": True, "to": settings.demo_to, "status": m.status}


def send_whatsapp(body: str, live: bool) -> dict:
    """WhatsApp via the Twilio sandbox (the demo phone must first join the sandbox)."""
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    m = _client().messages.create(
        to=f"whatsapp:{settings.demo_to}", from_=f"whatsapp:{settings.whatsapp_from}", body=body,
        status_callback=f"{settings.public_url}/twilio/status",
    )
    return {"sid": m.sid, "live": True, "to": settings.demo_to, "status": m.status}


def start_call(patient_id: str, live: bool) -> dict:
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    c = _client().calls.create(
        to=settings.demo_to, from_=settings.from_number,
        url=f"{settings.public_url}/twilio/voice/{patient_id}",
        status_callback=f"{settings.public_url}/twilio/call-status/{patient_id}",
        status_callback_event=["completed"],
    )
    return {"sid": c.sid, "live": True, "to": settings.demo_to, "status": c.status}


NO_ANSWER = "Neslyšeli jsme odpověď. Ozveme se Vám znovu. Na shledanou."


def speak(text: str) -> str:
    """ElevenLabs audio when available (natural Czech voice), Twilio's built-in voice otherwise."""
    name = tts.ensure(text)
    if name and settings.public_url:
        return f"<Play>{escape(settings.public_url)}/audio/{name}</Play>"
    return f'<Say language="{settings.voice_lang}" voice="{settings.voice_name}">{escape(text)}</Say>'


def voice_twiml(patient_id: str, script: str) -> str:
    """Voice flow without AI: play the script, wait for 1 (interested) / 2 (not now) or a spoken answer."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf speech" numDigits="1" language="{settings.voice_lang}" timeout="8" '
        f'action="{settings.public_url}/twilio/voice/{patient_id}/answer" method="POST">'
        + speak(script.strip()) +
        "</Gather>"
        + speak(NO_ANSWER)
        + "</Response>"
    )


def twiml_say(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{speak(text)}</Response>'


def relay_twiml(ws_url: str, greeting: str) -> str:
    """AI conversation: Twilio ConversationRelay (cs-CZ speech in/out) connected to our WebSocket."""
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Connect>'
            f'<ConversationRelay url="{escape(ws_url)}" language="{settings.voice_lang}" '
            f'welcomeGreeting="{escape(greeting, {chr(34): "&quot;"})}" dtmfDetection="true"{_relay_voice()}/>'
            "</Connect></Response>")


def _relay_voice() -> str:
    """Same ElevenLabs voice in the AI conversation (Twilio ConversationRelay supports ElevenLabs voice IDs)."""
    import os
    vid = os.getenv("ELEVENLABS_VOICE_ID")
    return f' ttsProvider="ElevenLabs" voice="{escape(vid)}"' if vid else ""
