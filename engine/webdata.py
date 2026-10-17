"""Engine output in the slim shape the web app reads (web/app/data/patients.json)."""
from pathlib import Path

from .loader import load
from .rules import run


def build(data_dir, ref_date: str = "2026-10-16") -> dict:
    data_dir = Path(data_dir)
    r = run(data_dir, ref_date)
    raw = {p["patient_id"]: p for p in load(data_dir)[0]["patients"]}
    patients = []
    for p in r["patients"]:
        x, s = raw[p["patient_id"]], p["smoking"]
        patients.append({
            "id": p["patient_id"], "age": p["age"], "sex": p["sex"], "region": p["region"],
            "gp": p["gp_id"], "pneu": p["pneumologist_id"],
            "portal": x["patient_portal_active"] == "true" and x["consent_for_portal_messages"] == "true",
            "pref": x["preferred_contact_channel"],
            "phone": x.get("phone_number") or None,
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
    return {"refDate": r["ref_date"], "issues": r["data_issues"], "patients": patients}
