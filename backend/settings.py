"""Runtime settings from environment (.env). Without Twilio keys the backend runs in MOCK mode: nothing leaves the machine."""
import os
from dataclasses import dataclass
from pathlib import Path


def _env_file():
    p = Path(__file__).with_name(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_env_file()


@dataclass(frozen=True)
class Settings:
    account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")      # needed to check webhook signatures
    api_key: str = os.getenv("TWILIO_API_KEY", "")            # SK..., preferred for REST calls
    api_secret: str = os.getenv("TWILIO_API_SECRET", "")
    from_number: str = os.getenv("TWILIO_FROM", "")          # Twilio number (SMS + voice)
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")  # e.g. https://xxxx.ngrok-free.app – needed for webhooks
    whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")  # Twilio sandbox number
    demo_to: str = os.getenv("DEMO_TO", "")                  # all real messages go to this verified phone (synthetic data has fake numbers)
    live_limit: int = int(os.getenv("LIVE_LIMIT", "1"))      # max real messages per send request; the rest is simulated
    validate_signature: bool = os.getenv("VALIDATE_SIGNATURE", "1") == "1"
    # Twilio trial: an SMS must fit one segment after the trial prefix, so a short text without diacritics is sent.
    trial: bool = os.getenv("TWILIO_TRIAL", "1") == "1"
    # E-mail via Twilio SendGrid (verified single sender). All real e-mail goes to demo_email.
    sendgrid_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    demo_email: str = os.getenv("DEMO_EMAIL", "")
    # Or plain SMTP, e.g. Gmail with an app password: SMTP_HOST=smtp.gmail.com SMTP_USER=you@gmail.com SMTP_PASSWORD=…
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    # FHIR server (InterSystems IRIS for Health): source of patients and target of the journey write-back
    fhir_base: str = os.getenv("FHIR_BASE", "").rstrip("/")
    fhir_user: str = os.getenv("FHIR_USER", "")
    fhir_password: str = os.getenv("FHIR_PASSWORD", "")
    # The demo clock ("Další den") simulates by default; TICK_LIVE=1 lets automatic touches go out for real.
    tick_live: bool = os.getenv("TICK_LIVE", "0") == "1"
    voice_name: str = os.getenv("VOICE_NAME", "Google.cs-CZ-Standard-A")
    voice_mode: str = os.getenv("VOICE_MODE", "gather")       # gather = script + keys 1/2; relay = rules over ConversationRelay; agent = ElevenLabs voice agent
    voice_lang: str = os.getenv("VOICE_LANG", "cs-CZ")
    state_file: Path = Path(os.getenv("STATE_FILE", str(Path(__file__).with_name("state.json"))))

    @property
    def email_live(self) -> bool:
        smtp = self.smtp_host and self.smtp_user and self.smtp_password
        return bool(self.demo_email and ((self.sendgrid_key and self.email_from) or smtp))

    @property
    def live(self) -> bool:
        creds = self.auth_token or (self.api_key and self.api_secret)
        return bool(self.account_sid and creds and self.from_number and self.demo_to and self.public_url)


settings = Settings()
