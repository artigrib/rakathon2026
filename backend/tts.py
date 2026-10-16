"""Natural Czech voice for phone calls via ElevenLabs text-to-speech.

Twilio plays the generated MP3 (<Play>) instead of its built-in robotic voice (<Say>).
Audio is cached by text, so each sentence is generated once. Any failure falls back to <Say>,
so a call never breaks because of the voice service.

  ELEVENLABS_API_KEY=…            (required to enable)
  ELEVENLABS_VOICE_ID=…           (pick a voice that sounds good in Czech in the ElevenLabs Voice Library)
  ELEVENLABS_MODEL=eleven_multilingual_v2

Warm the cache before a demo:  python -m backend.tts
"""
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

CACHE = Path(os.getenv("TTS_CACHE", str(Path(__file__).with_name("audio_cache"))))
NAME = re.compile(r"^[0-9a-f]{24}\.mp3$")


def _key():
    return os.getenv("ELEVENLABS_API_KEY", "")


def enabled() -> bool:
    return bool(_key())


def _voice():
    return os.getenv("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # Sarah, premade, works on the free plan and in Czech


def _model():
    return os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")


def name_for(text: str) -> str:
    h = hashlib.sha256(f"{_voice()}|{_model()}|{text}".encode()).hexdigest()[:24]
    return f"{h}.mp3"


def _synthesize(text: str, timeout: float) -> bytes:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{_voice()}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": _model(),
                         "voice_settings": {"stability": 0.6, "similarity_boost": 0.75}}).encode(),
        headers={"xi-api-key": _key(), "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ensure(text: str, timeout: float = 8.0):
    """Cached audio file name for the text, generating it if needed. None when disabled or on any error."""
    if not enabled() or not text.strip():
        return None
    name = name_for(text)
    path = CACHE / name
    if path.exists():
        return name
    try:
        audio = _synthesize(text, timeout)
    except Exception:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return name


def path_for(name: str):
    """Safe lookup for the /audio endpoint (only names we generate)."""
    return CACHE / name if NAME.match(name) and (CACHE / name).exists() else None


def phrases():
    """Everything the phone assistant can say in the keys-1/2 flow, for warming the cache."""
    from .app import VOICE_NO_DIGIT, VOICE_THANKS, NO_ANSWER
    from .messages import M
    return [*M["voice"].values(), VOICE_NO_DIGIT, NO_ANSWER, *VOICE_THANKS.values()]


if __name__ == "__main__":
    if not enabled():
        raise SystemExit("ELEVENLABS_API_KEY is not set (backend/.env)")
    for t in phrases():
        print("ok " if ensure(t, timeout=30) else "ERR", t[:60].replace("\n", " "))
