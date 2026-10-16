"""Export engine output in the slim shape the web app reads (web/app/data/patients.json)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import run
from engine.loader import load

ROOT = Path(__file__).resolve().parents[1]
ref = sys.argv[1] if len(sys.argv) > 1 else "2026-10-16"
r = run(ROOT / "data", ref)
raw = {p["patient_id"]: p for p in load(ROOT / "data")[0]["patients"]}
patients = []
for p in r["patients"]:
    x, s = raw[p["patient_id"]], p["smoking"]
    patients.append({
        "id": p["patient_id"], "age": p["age"], "sex": p["sex"], "region": p["region"],
        "gp": p["gp_id"], "pneu": p["pneumologist_id"],
        "portal": x["patient_portal_active"] == "true" and x["consent_for_portal_messages"] == "true",
        "pref": x["preferred_contact_channel"],
        "status": p["status"], "reasons": [r_["text"] for r_ in p["reasons"]],
        "flags": [{"sev": f["severity"], "text": f["text"], "code": f["code"]} for f in p["flags"]],
        "smoking": s and {"status": s["status"], "packYears": s["pack_years"], "source": s["pack_years_source"],
                          "quitYear": s["quit_year"], "note": s["note"]},
        "ct": [{"date": c["date"], "protocol": c["protocol"], "region": c["region"], "status": c["status"],
                "external": c["external"], "report": c["report"]} for c in p["ct"]],
        "history": [{"date": h["date"], "channel": h["channel"], "type": h["type"],
                     "delivery": h["delivery"], "response": h["response"]} for h in p["contact"]["history"]],
        "next": p["contact"]["next_action"], "channel": p["contact"]["recommended_channel"],
        "variant": p["contact"]["message_variant"], "why": p["contact"]["reason"],
    })
out = {"refDate": r["ref_date"], "issues": r["data_issues"], "patients": patients}
dst = ROOT / "web/app/data/patients.json"
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(dst, dst.stat().st_size)
