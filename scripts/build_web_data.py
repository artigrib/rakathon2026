"""Export engine output in the slim shape the web app reads (web/app/data/patients.json).

  python scripts/build_web_data.py [ref-date]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.webdata import build  # noqa: E402

ref = sys.argv[1] if len(sys.argv) > 1 else "2026-10-16"
out = build(ROOT / "data", ref)
dst = ROOT / "web/app/data/patients.json"
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(dst, dst.stat().st_size)
