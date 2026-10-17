"""FHIR R4 export: challenge data + our evaluation + contact history as one transaction Bundle.

Why: every GP uses different software (doctor 16.10.) and EHDS is coming – FHIR is the common language.
The Bundle can be POSTed as-is to any FHIR R4 server (e.g. InterSystems IRIS from the hackathon kit);
PUT entries make the upload idempotent, so a weekly cron can simply resend it.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from engine.loader import load
from engine.rules import run

LOCAL = "https://jsemvcas.cz/fhir/CodeSystem"
# Every original NIS column is kept as an extension, so the data can be read back from the FHIR server without loss
# (backend/fhir_source.py). The standard FHIR fields carry the same facts for any other system.
NIS = "https://jsemvcas.cz/fhir/StructureDefinition/nis"
SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
SMOKING = {"current": ("77176002", "Smoker"), "former": ("8517006", "Ex-smoker"), "never": ("266919005", "Never smoked tobacco")}
CT_STATUS = {"completed": "available", "scheduled": "registered", "cancelled": "cancelled"}
GENDER = {"F": "female", "M": "male"}
ACTIONABLE = {"ELIGIBLE": ("invite", "Oslovit pacienta – Prevence pro plíce"),
              "NEEDS_REVIEW": ("review", "Zkontrolovat údaje – rozhoduje lékař")}


def _clean(x):
    """FHIR forbids nulls and empty values."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items() if v not in (None, "", [], {})}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def _entry(res):
    res = _clean(res)
    return {"fullUrl": f"{res['resourceType']}/{res['id']}", "resource": res,
            "request": {"method": "PUT", "url": f"{res['resourceType']}/{res['id']}"}}


def _nis(row):
    return [{"url": f"{NIS}/{k}", "valueString": str(v)} for k, v in row.items() if v not in (None, "")]


def _ref(kind, id_):
    return {"reference": f"{kind}/{id_}"}


def _dt(s):
    """FHIR dateTime with a time part needs a zone; source data is local Prague time."""
    if not s or "T" not in s:
        return _date(s)
    return datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("Europe/Prague")).isoformat()


def _date(s):
    return (s or "")[:10] or None


def bundle(data_dir, ref_date, decisions=None, gp=None) -> dict:
    """Transaction Bundle for one practice (gp) or all. decisions = backend journey events (optional)."""
    decisions = decisions or {}
    tables, _ = load(data_dir)
    result = {p["patient_id"]: p for p in run(data_dir, ref_date)["patients"]}
    smoking = {s["patient_id"]: s for s in tables["smoking"]}
    cts, contacts = {}, {}
    for c in tables["ct"]:
        cts.setdefault(c["patient_id"], []).append(c)
    for c in tables["contacts"]:
        contacts.setdefault(c["patient_id"], []).append(c)

    entries, orgs = [], set()
    for p in tables["patients"]:
        pid, org = p["patient_id"], p["primary_care_provider_id"]
        if gp and org != gp:
            continue
        r = result[pid]
        if org and org not in orgs:
            orgs.add(org)
            entries.append(_entry({"resourceType": "Organization", "id": org, "name": f"Ordinace praktického lékaře {org}",
                                   "type": [{"text": "Praktický lékař"}]}))
        entries.append(_entry({
            "resourceType": "Patient", "id": pid,
            "identifier": [{"system": "urn:rakathon:patient", "value": pid}],
            "gender": GENDER.get(p["sex"], "unknown"), "birthDate": p["date_of_birth"],
            "address": [{"state": p["residence_region"], "country": "CZ"}],
            "telecom": [t for t in ({"system": "phone", "value": p.get("phone_number")}, {"system": "email", "value": p.get("email")}) if t["value"]],
            "extension": _nis(p),
            **({"generalPractitioner": [_ref("Organization", org)]} if org else {}),
        }))
        derived = []
        s = smoking.get(pid)
        if s:  # also "unknown": the row must survive the round trip through the FHIR server
            code, name = SMOKING.get(s.get("smoking_status"), (None, s.get("smoking_status") or "unknown"))
            entries.append(_entry({
                "resourceType": "Observation", "id": f"smoking-{pid}", "status": "final",
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "social-history"}]}],
                "code": {"coding": [{"system": LOINC, "code": "72166-2", "display": "Tobacco smoking status"}]},
                "subject": _ref("Patient", pid), "effectiveDateTime": _date(s.get("recorded_at")),
                "valueCodeableConcept": {"coding": [{"system": SNOMED, "code": code, "display": name}]} if code else {"text": name},
                **({"note": [{"text": s["free_text_note"]}]} if s.get("free_text_note") else {}),
                "extension": _nis(s),
            }))
            derived.append(_ref("Observation", f"smoking-{pid}"))
        py = (r.get("smoking") or {}).get("pack_years")
        if py is not None:
            entries.append(_entry({
                "resourceType": "Observation", "id": f"packyears-{pid}", "status": "final",
                "code": {"coding": [{"system": SNOMED, "code": "401201003", "display": "Cigarette pack-years"}]},
                "subject": _ref("Patient", pid), "effectiveDateTime": _date(s.get("recorded_at")) if s else None,
                "valueQuantity": {"value": py, "unit": "pack-years", "system": "http://unitsofmeasure.org", "code": "{PackYears}"},
                "note": [{"text": f"Zdroj: {r['smoking'].get('pack_years_source')}"}],
            }))
            derived.append(_ref("Observation", f"packyears-{pid}"))
        for c in cts.get(pid, []):
            notes = [t for t in (c.get("report_text"), "Externí vyšetření" if c.get("is_external") == "true" else "") if t]
            entries.append(_entry({
                "resourceType": "ImagingStudy", "id": c["ct_id"], "status": CT_STATUS.get(c["status"], "unknown"),
                "extension": _nis(c),
                "subject": _ref("Patient", pid), "started": _dt(c["performed_at"]),
                "modality": [{"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "CT"}],
                "description": f"{c['body_region']} · {c['protocol']}" + (f" · {c['referral_text']}" if c.get("referral_text") else ""),
                **({"note": [{"text": t} for t in notes]} if notes else {}),
            }))
            if c["body_region"] == "chest":
                derived.append(_ref("ImagingStudy", c["ct_id"]))
        for c in contacts.get(pid, []):
            entries.append(_entry({
                "resourceType": "Communication", "id": c["contact_id"], "status": "completed",
                "subject": _ref("Patient", pid), "sent": _dt(c["created_at"]),
                "medium": [{"coding": [{"system": f"{LOCAL}/channel", "code": c["channel"]}]}],
                "category": [{"coding": [{"system": f"{LOCAL}/message-type", "code": c["message_type"]}]}],
                "note": [{"text": f"doručení: {c['delivery_status'] or '—'}; odpověď: {c['response'] or '—'}"}],
                "extension": _nis(c),
            }))
        for i, e in enumerate(decisions.get(pid, {}).get("journey", [])):
            if e.get("stage") == "sent":
                entries.append(_entry({
                    "resourceType": "Communication", "id": f"pv-{pid}-{i}", "status": "completed",
                    "subject": _ref("Patient", pid), "sent": e["date"],
                    "medium": [{"coding": [{"system": f"{LOCAL}/channel", "code": e.get("channel", "sms")}]}],
                    "category": [{"coding": [{"system": f"{LOCAL}/message-type", "code": "lung_screening_information"}]}],
                    "note": [{"text": "automaticky dle plánu kontaktů" if e.get("auto") else "schváleno ordinací"}],
                }))
        entries.append(_entry({
            "resourceType": "Observation", "id": f"eligibility-{pid}", "status": "final",
            "code": {"coding": [{"system": f"{LOCAL}/evaluation", "code": "lcs-eligibility",
                                 "display": "Vyhodnocení vstupních kritérií – Prevence pro plíce"}]},
            "subject": _ref("Patient", pid), "effectiveDateTime": str(ref_date),
            "valueCodeableConcept": {"coding": [{"system": f"{LOCAL}/eligibility-status", "code": r["status"]}]},
            "note": [{"text": x["text"]} for x in r["reasons"]] + [{"text": f"⚠ {f['text']}"} for f in r["flags"] if f["severity"] == "warning"],
            **({"derivedFrom": derived} if derived else {}),
        }))
        if r["status"] in ACTIONABLE:
            code, text = ACTIONABLE[r["status"]]
            entries.append(_entry({
                "resourceType": "Task", "id": f"task-{pid}", "status": "requested", "intent": "order",
                "code": {"coding": [{"system": f"{LOCAL}/task", "code": code}], "text": text},
                "for": _ref("Patient", pid), "authoredOn": str(ref_date),
                **({"owner": _ref("Organization", org)} if org else {}),
                "description": r["contact"].get("reason") or text,
                "reasonReference": _ref("Observation", f"eligibility-{pid}"),
            }))
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}
