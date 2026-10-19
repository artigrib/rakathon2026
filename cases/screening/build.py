"""Build the screening data file (case.json "data") from the challenge CSVs in data/ with the rules engine.

  python -m cases.screening.build [ref-date]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((Path(__file__).with_name("case.json")).read_text(encoding="utf-8"))


def build(ref: str = MANIFEST["ref_date"]) -> dict:
    from engine.webdata import build as engine_build
    return engine_build(ROOT / "data", ref)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = build(argv[0] if argv else MANIFEST["ref_date"])
    dst = ROOT / MANIFEST["data"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(dst, dst.stat().st_size)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
