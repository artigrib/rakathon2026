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
    auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number: str = os.getenv("TWILIO_FROM", "")          # Twilio number (SMS + voice)
    public_url: str = os.getenv("PUBLIC_URL", "").rstrip("/")  # e.g. https://xxxx.ngrok-free.app – needed for webhooks
    whatsapp_from: str = os.getenv("TWILIO_WHATSAPP_FROM", "+14155238886")  # Twilio sandbox number
    demo_to: str = os.getenv("DEMO_TO", "")                  # all real messages go to this verified phone (synthetic data has fake numbers)
    live_limit: int = int(os.getenv("LIVE_LIMIT", "1"))      # max real messages per send request; the rest is simulated
    validate_signature: bool = os.getenv("VALIDATE_SIGNATURE", "1") == "1"
    voice_name: str = os.getenv("VOICE_NAME", "Google.cs-CZ-Standard-A")
    voice_mode: str = os.getenv("VOICE_MODE", "gather")       # gather = read script + keys 1/2; relay = AI conversation
    voice_lang: str = os.getenv("VOICE_LANG", "cs-CZ")
    state_file: Path = Path(os.getenv("STATE_FILE", str(Path(__file__).with_name("state.json"))))

    @property
    def live(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number and self.demo_to and self.public_url)


settings = Settings()
