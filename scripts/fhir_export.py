"""Export the challenge data + evaluation as a FHIR R4 transaction Bundle, optionally push it to a FHIR server.

  python scripts/fhir_export.py                       # → examples/fhir_bundle.json
  python scripts/fhir_export.py --gp VPL-0142
  python scripts/fhir_export.py --post http://localhost:52773/fhir/r4 --user _SYSTEM --password ISCDEMO   # IRIS kit
"""
import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.fhir import bundle  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ref-date", default="2026-10-16")
ap.add_argument("--gp")
ap.add_argument("-o", "--out", default=str(ROOT / "examples/fhir_bundle.json"))
ap.add_argument("--post", help="FHIR base URL, e.g. http://localhost:52773/fhir/r4")
ap.add_argument("--user"); ap.add_argument("--password")
a = ap.parse_args()

b = bundle(ROOT / "data", a.ref_date, gp=a.gp)
Path(a.out).write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
kinds = {}
for e in b["entry"]:
    kinds[e["resource"]["resourceType"]] = kinds.get(e["resource"]["resourceType"], 0) + 1
print(a.out, kinds)

if a.post:
    req = urllib.request.Request(a.post.rstrip("/"), data=json.dumps(b).encode(), method="POST",
                                 headers={"Content-Type": "application/fhir+json"})
    if a.user:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{a.user}:{a.password}".encode()).decode())
    with urllib.request.urlopen(req) as r:
        print("POST", r.status)
