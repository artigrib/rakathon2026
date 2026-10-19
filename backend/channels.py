"""Outbound channels. LIVE → Twilio REST; otherwise MOCK (recorded in the outbox, nothing is sent).
All real traffic goes to recipient.phone(): the challenge data has synthetic phone numbers."""
from xml.sax.saxutils import escape

from . import tts
from . import ctx, recipient
from .case import CASE
from .messages import text as _text
from .settings import settings


def _client():
    from twilio.rest import Client  # imported lazily: tests and mock mode need no Twilio
    if settings.api_key and settings.api_secret:
        return Client(settings.api_key, settings.api_secret, settings.account_sid)
    return Client(settings.account_sid, settings.auth_token)


def send_sms(body: str, live: bool) -> dict:
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    if settings.trial:  # trial accounts reject multi-segment SMS (error 30044)
        from .messages import sms_trial
        body = sms_trial()
    m = _client().messages.create(
        to=recipient.phone(), from_=settings.from_number, body=body,
        status_callback=ctx.url("/twilio/status"),
    )
    return {"sid": m.sid, "live": True, "to": recipient.phone(), "status": m.status}


def send_whatsapp(body: str, live: bool) -> dict:
    """WhatsApp via the Twilio sandbox (the demo phone must first join the sandbox)."""
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    m = _client().messages.create(
        to=f"whatsapp:{recipient.phone()}", from_=f"whatsapp:{settings.whatsapp_from}", body=body,
        status_callback=ctx.url("/twilio/status"),
    )
    return {"sid": m.sid, "live": True, "to": recipient.phone(), "status": m.status}


def start_call(patient_id: str, live: bool) -> dict:
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    c = _client().calls.create(
        to=recipient.phone(), from_=settings.from_number,
        url=ctx.url(f"/twilio/voice/{patient_id}"),
        status_callback=ctx.url(f"/twilio/call-status/{patient_id}"),
        status_callback_event=["completed"],
    )
    return {"sid": c.sid, "live": True, "to": recipient.phone(), "status": c.status}


NO_ANSWER = _text("voice_ui.no_answer", "Neslyšeli jsme odpověď. Na shledanou.")


def speak(text: str) -> str:
    """ElevenLabs audio when available (natural Czech voice), Twilio's built-in voice otherwise."""
    name = tts.ensure(text)
    if name and settings.public_url:
        return f"<Play>{escape(settings.public_url)}/audio/{name}</Play>"
    return f'<Say language="{settings.voice_lang}" voice="{settings.voice_name}">{escape(text)}</Say>'


def _gather(action: str, prompt: str) -> str:
    """One listening turn: keys (one digit) or speech; speech ends after 3 s of silence, not at the first pause."""
    return (f'<Gather input="dtmf speech" numDigits="1" language="{settings.voice_lang}" timeout="8" speechTimeout="3" '
            f'action="{escape(action)}" method="POST">' + speak(prompt.strip()) + "</Gather>")


def answer_url(patient_id: str, **q) -> str:
    """The Gather action, with the turn number (and end=1 when the person said nothing more)."""
    u = ctx.url(f"/twilio/voice/{patient_id}/answer")
    if not u or not q:
        return u
    return u + ("&" if "?" in u else "?") + "&".join(f"{k}={v}" for k, v in q.items())


def voice_twiml(patient_id: str, script: str) -> str:
    """Voice flow without AI: play the script, wait for 1 (interested) / 2 (not now) or a spoken answer."""
    return ('<?xml version="1.0" encoding="UTF-8"?><Response>' + _gather(answer_url(patient_id), script)
            + speak(NO_ANSWER) + "</Response>")


def followup_twiml(patient_id: str, question: str, n: int) -> str:
    """Next turn of the scripted call: ask the case's follow-up question; silence ends the call with what we have."""
    end = answer_url(patient_id, n=n, end=1)
    return ('<?xml version="1.0" encoding="UTF-8"?><Response>' + _gather(answer_url(patient_id, n=n), question)
            + (f'<Redirect method="POST">{escape(end)}</Redirect>' if end else "") + "</Response>")


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


EMAIL_SUBJECT = _text("email_subject", CASE.manifest["title"])
SENDER = _text("sender", CASE.manifest["brand"])  # display name of the e-mail sender
DOMAIN = CASE.manifest.get("domain", "jsemvcas.cz")


def send_email(body: str, live: bool, to: str = "") -> dict:
    """Plain-text e-mail through the SendGrid v3 API (Twilio SendGrid). Replies come back through the patient link."""
    if not live:
        return {"sid": None, "live": False, "to": None, "status": "simulated"}
    if settings.smtp_host:
        return _smtp(body, to)
    import json
    import urllib.request
    payload = {
        "personalizations": [{"to": [{"email": to or recipient.email()}]}],
        "from": {"email": settings.email_from, "name": SENDER},
        "subject": EMAIL_SUBJECT,
        "content": [{"type": "text/plain", "value": body}],
    }
    req = urllib.request.Request("https://api.sendgrid.com/v3/mail/send", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {settings.sendgrid_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return {"sid": r.headers.get("X-Message-Id"), "live": True, "to": to or recipient.email(), "status": "queued" if r.status == 202 else str(r.status)}


def _smtp(body: str, to: str = "") -> dict:
    import smtplib
    from email.message import EmailMessage
    from email.utils import formataddr, make_msgid
    m = EmailMessage()
    m["Subject"] = EMAIL_SUBJECT
    m["From"] = formataddr((SENDER, settings.email_from or settings.smtp_user))
    m["To"] = to or recipient.email()
    m["Message-ID"] = make_msgid(domain=DOMAIN)
    m.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(m)
    return {"sid": m["Message-ID"], "live": True, "to": to or recipient.email(), "status": "sent"}
