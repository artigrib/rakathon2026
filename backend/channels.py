"""Outbound channels. LIVE → Twilio REST; otherwise MOCK (recorded in the outbox, nothing is sent).
All real traffic goes to settings.demo_to: the challenge data has synthetic phone numbers."""
from xml.sax.saxutils import escape

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


def voice_twiml(patient_id: str, script: str) -> str:
    """Fallback voice flow without AI: read the script, wait for 1 (interested) / 2 (not now).
    The AI conversation (ConversationRelay, cs-CZ) replaces <Gather> once the LLM endpoint is ready."""
    say = lambda t: f'<Say language="{settings.voice_lang}" voice="{settings.voice_name}">{escape(t)}</Say>'
    parts = [p for p in script.split("\n\n") if p.strip()]
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf speech" numDigits="1" language="{settings.voice_lang}" timeout="8" '
        f'action="{settings.public_url}/twilio/voice/{patient_id}/answer" method="POST">'
        + "".join(say(p) for p in parts) +
        "</Gather>"
        + say("Neslyšeli jsme odpověď. Ozveme se Vám znovu. Na shledanou.")
        + "</Response>"
    )


def twiml_say(text: str) -> str:
    return (f'<?xml version="1.0" encoding="UTF-8"?><Response><Say language="{settings.voice_lang}" '
            f'voice="{settings.voice_name}">{escape(text)}</Say></Response>')


def relay_twiml(ws_url: str, greeting: str) -> str:
    """AI conversation: Twilio ConversationRelay (cs-CZ speech in/out) connected to our WebSocket."""
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Connect>'
            f'<ConversationRelay url="{escape(ws_url)}" language="{settings.voice_lang}" '
            f'welcomeGreeting="{escape(greeting, {chr(34): "&quot;"})}" dtmfDetection="true"/>'
            "</Connect></Response>")
