"""Czech voice-over for the demo video with ElevenLabs (same voice as the phone calls).

  python scripts/narrate.py            # reads submission/narration.json → submission/narration/NN.mp3
Needs ELEVENLABS_API_KEY (backend/.env is read). Existing files are kept; delete one to regenerate it.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import settings as _s  # noqa: E402,F401  (loads backend/.env)
from backend import tts  # noqa: E402

out = ROOT / "submission" / "narration"
out.mkdir(parents=True, exist_ok=True)
for seg in json.loads((ROOT / "submission" / "narration.json").read_text(encoding="utf-8")):
    f = out / f"{seg['id']}.mp3"
    if f.exists():
        print("keep", f.name)
        continue
    f.write_bytes(tts._synthesize(seg["say"], timeout=30))
    print("ok", f.name, f.stat().st_size)
