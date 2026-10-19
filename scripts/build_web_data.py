"""Export engine output in the slim shape the web app reads (web/app/data/patients.json).
Same as `python -m cases.screening.build`.

  python scripts/build_web_data.py [ref-date]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.screening.build import main  # noqa: E402

main()
