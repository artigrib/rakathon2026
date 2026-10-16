"""Read the practice's patients back from a FHIR R4 server (InterSystems IRIS for Health) and run the engine on them.

The export (backend/fhir.py) keeps every NIS column as an extension, so this is lossless:
FHIR server → tables in the NIS shape → the same engine → web/app/data/patients.json.
"""
import base64
import csv
import json
import urllib.request
from pathlib import Path

from engine.loader import FILES

from .fhir import NIS

TYPES = ("Patient", "Observation", "ImagingStudy", "Communication")
HEADERS = {
    "patients": ["patient_id", "date_of_birth", "sex", "residence_region", "primary_care_provider_id", "pneumologist_provider_id",
                 "patient_portal_active", "preferred_contact_channel", "consent_for_portal_messages", "last_primary_care_visit",
                 "phone_number", "home_address", "email"],
    "smoking": ["patient_id", "smoking_status", "cigarettes_per_day", "smoking_start_year", "smoking_end_year", "pack_years_reported",
                "pack_years_calculated", "source", "data_quality", "recorded_at", "free_text_note"],
    "ct": ["ct_id", "patient_id", "performed_at", "modality", "body_region", "protocol", "status", "referral_text", "report_text",
           "source_system", "is_external"],
    "contacts": ["contact_id", "patient_id", "created_at", "channel", "message_type", "delivery_status", "response", "handled_by"],
}


def _get(url, user=None, password=None, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
    if user:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(base, user=None, password=None, get=_get) -> list:
    """All resources of the types we need, following Bundle 'next' links."""
    out, base = [], base.rstrip("/")
    for t in TYPES:
        url = f"{base}/{t}?_count=500"
        while url:
            b = get(url, user, password)
            out += [e["resource"] for e in b.get("entry", []) if "resource" in e]
            url = next((l["url"] for l in b.get("link", []) if l.get("relation") == "next"), None)
    return out


def _row(res):
    return {x["url"][len(NIS) + 1:]: x.get("valueString", "") for x in res.get("extension", []) if x.get("url", "").startswith(NIS + "/")}


def tables_from(resources) -> dict:
    """Resources → NIS tables. Only resources that came from the NIS export (they carry the NIS extensions)."""
    t = {k: [] for k in HEADERS}
    for r in resources:
        row = _row(r)
        if not row:
            continue  # created by us (app Communications) or by another system: not NIS source data
        kind = {"Patient": "patients", "ImagingStudy": "ct", "Communication": "contacts"}.get(r["resourceType"])
        if r["resourceType"] == "Observation" and r.get("id", "").startswith("smoking-"):
            kind = "smoking"
        if kind:
            t[kind].append(row)
    return t


def write(tables, data_dir) -> Path:
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    for key, rows in tables.items():
        with open(d / f"{FILES[key]}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS[key], extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return d
