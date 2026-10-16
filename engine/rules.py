"""Eligibility rules for Prevence pro plíce (confirmed with AstraZeneca mentor, 16.10.2026)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime

from .channel import recommend
from .loader import load


@dataclass
class Config:
    min_age: int = 55
    max_age: int = 74
    min_pack_years: float = 20.0
    recent_ct_days: int = 30          # chest CT incl. LDCT in last N days -> excluded
    nearby_ct_days: int = 60          # any CT record within ±N days -> info for GP
    ldct_interval_days: int = 365           # doctor: screening LDCT is repeated after 1 year ...
    ldct_interval_negative_days: int = 730  # ... or after 2 years when the finding was negative
    contact_cooldown_days: int = 14

    @classmethod
    def policy(cls, name: str = "2026") -> "Config":
        """Program rules by period. 2027 (doctor's deck, slide 22): entry age widens to 50–80, rest unchanged."""
        presets = {"2026": {}, "2027": {"min_age": 50, "max_age": 80}}
        if name not in presets:
            raise ValueError(f"unknown policy {name!r}; known: {', '.join(presets)}")
        return cls(**presets[name])


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def _i(x):
    v = _f(x)
    return int(v) if v is not None else None


def _dt(x):
    if not x:
        return None
    try:
        return datetime.fromisoformat(x).date()
    except ValueError:
        return None


def _fmt(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def age_on(dob: date, ref: date) -> int:
    return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))


def pack_years(s: dict, ref: date):
    """Returns (value, source, reported, calculated, derived)."""
    rep, calc = _f(s.get("pack_years_reported")), _f(s.get("pack_years_calculated"))
    cpd, start, end = _f(s.get("cigarettes_per_day")), _i(s.get("smoking_start_year")), _i(s.get("smoking_end_year"))
    derived = None
    if cpd is not None and start is not None:
        derived = round(cpd / 20 * max(0, (end or ref.year) - start), 1)
    candidates = [(v, src) for v, src in ((calc, "calculated"), (rep, "reported")) if v is not None]
    if not candidates and derived is not None:
        candidates = [(derived, "derived")]
    if not candidates:
        return None, "none", rep, calc, derived
    # Mentor: if at least one documented value reaches the threshold, refer.
    value, src = max(candidates, key=lambda c: c[0])
    return value, src, rep, calc, derived


def evaluate(p: dict, smoking: dict | None, cts: list[dict], contacts: list[dict], ref: date, cfg: Config) -> dict:
    reasons, flags = [], []
    R = lambda code, text: reasons.append({"code": code, "text": text})
    F = lambda code, sev, text: flags.append({"code": code, "severity": sev, "text": text})

    dob = _dt(p.get("date_of_birth"))
    age = age_on(dob, ref) if dob else None

    # --- CT records (always shown to GP) ---
    ct_out = []
    recent_chest = []
    last_ldct = None  # (date, interval_days, negative) of an LDCT still within its screening interval
    for c in sorted(cts, key=lambda c: c.get("performed_at", "")):
        d = _dt(c.get("performed_at"))
        if not d:
            continue
        days = (ref - d).days
        rec = {"ct_id": c.get("ct_id"), "date": d.isoformat(), "region": c.get("body_region"),
               "protocol": c.get("protocol"), "status": c.get("status"),
               "external": str(c.get("is_external")).lower() == "true", "days_ago": days,
               "report": (c.get("report_text") or "").strip()}
        ct_out.append(rec)
        is_chest = rec["region"] == "chest"
        if rec["status"] == "scheduled":
            when = "naplánováno" if days < 0 else "naplánováno, ale bez záznamu o provedení"
            F("CT_SCHEDULED", "warning", f"CT {rec['region']} {when} ({_fmt(d)})")
        elif rec["status"] == "cancelled":
            F("CT_CANCELLED", "info", f"CT {rec['region']} zrušeno ({_fmt(d)})")
        elif is_chest and 0 <= days <= cfg.recent_ct_days:
            recent_chest.append(rec)
        elif abs(days) <= cfg.nearby_ct_days:
            F("CT_NEARBY", "info", f"CT {rec['region']} {_fmt(d)} ({days} dní)")
        if rec["protocol"] == "ldct" and rec["status"] == "completed":
            rep = rec["report"].lower()
            negative = "bez suspekt" in rep
            has_finding = not negative and ("kontrol" in rep or "uzl" in rep or "suspekt" in rep)
            if has_finding:
                F("LDCT_FINDING", "warning", f"LDCT {_fmt(d)} s nálezem k další kontrole – pacient je ve sledování")
            interval = cfg.ldct_interval_negative_days if negative else cfg.ldct_interval_days
            if days <= interval:
                last_ldct = (d, interval, negative)

    smoking_out = None
    status = None

    # 1. Age
    if age is None:
        status = "NEEDS_REVIEW"; R("AGE_MISSING", "Chybí datum narození")
    elif not (cfg.min_age <= age <= cfg.max_age):
        status = "EXCLUDED_AGE"; R("AGE_OUT", f"Věk {age} let – mimo rozmezí {cfg.min_age}–{cfg.max_age}")
    else:
        R("AGE_OK", f"Věk {age} let")

    # 2./3./4. Smoking
    if status is None:
        if smoking is None:
            status = "NEEDS_REVIEW"; R("SMOKING_MISSING", "Chybí kuřácká anamnéza")
        else:
            py, src, rep, calc, derived = pack_years(smoking, ref)
            st = smoking.get("smoking_status")
            smoking_out = {"status": st, "pack_years": py, "pack_years_source": src,
                           "pack_years_reported": rep, "pack_years_calculated": calc,
                           "quit_year": _i(smoking.get("smoking_end_year")),
                           "data_quality": smoking.get("data_quality"),
                           "note": smoking.get("free_text_note")}
            if smoking.get("_repaired"):
                F("DATA_REPAIRED", "warning", "Záznam o kouření byl v datech poškozený (chybějící sloupec) – zkontrolujte")
            if st == "never":
                status = "EXCLUDED_SMOKING_STATUS"; R("NEVER_SMOKER", "Nikdy nekouřil(a)")
            elif st not in ("current", "former"):
                status = "NEEDS_REVIEW"; R("SMOKING_UNKNOWN", "Kuřácký status není znám")
            elif py is None:
                status = "NEEDS_REVIEW"
                R("PY_MISSING", "Kuřák, ale chybí údaje pro výpočet balíčkoroků (počet cigaret / roky)")
            else:
                label = "Kouří" if st == "current" else f"Bývalý kuřák (přestal {smoking_out['quit_year'] or '?'})"
                if rep is not None and calc is not None and abs(rep - calc) >= 1:
                    F("PY_CONFLICT", "warning", f"Rozdílné balíčkoroky: dokumentace {rep}, výpočet {calc}")
                elif smoking.get("data_quality") == "conflicting":
                    F("PY_CONFLICT", "warning", "Dokumentace uvádí rozdílné hodnoty – použita vyšší")
                if src == "derived":
                    F("PY_DERIVED", "info", f"Balíčkoroky dopočteny: {derived}")
                if py < cfg.min_pack_years:
                    status = "EXCLUDED_PACK_YEARS"
                    R("PY_LOW", f"{label}, {py:g} balíčkoroků (< {cfg.min_pack_years:g})")
                else:
                    R("SMOKING_OK", f"{label}, {py:g} balíčkoroků")
                    if st == "current":  # program includes a brief smoking-cessation intervention (deck, slide 10)
                        F("CESSATION", "info", "Kouří – při návštěvě nabídnout krátkou intervenci k odvykání kouření")

    # 5. Recent chest CT (incl. LDCT)
    if status is None:
        internal = [c for c in recent_chest if not c["external"]]
        external = [c for c in recent_chest if c["external"]]
        if internal:
            c = internal[-1]
            status = "EXCLUDED_RECENT_CT"
            R("RECENT_CT", f"{'LDCT' if c['protocol'] == 'ldct' else 'CT'} hrudníku před {c['days_ago']} dny ({_fmt(date.fromisoformat(c['date']))})")
        elif external:
            c = external[-1]
            status = "NEEDS_REVIEW"
            R("RECENT_CT_EXTERNAL", f"Externí CT hrudníku před {c['days_ago']} dny – ke zvážení lékařem")

    # Already in screening: next LDCT is due only after 1 year (2 years if negative)
    if status is None and last_ldct:
        d, interval, negative = last_ldct
        due = date.fromordinal(d.toordinal() + interval)
        status = "EXCLUDED_RECENT_CT"
        R("IN_SCREENING", f"Už ve screeningu: LDCT {_fmt(d)}{' bez nálezu' if negative else ''} – další LDCT od {_fmt(due)}")

    if status is None:
        status = "ELIGIBLE"
        R("ELIGIBLE", "Splňuje kritéria programu Prevence pro plíce")

    contact = recommend(p, contacts, status, ref, cfg)

    return {
        "patient_id": p.get("patient_id"), "age": age, "sex": p.get("sex"),
        "region": p.get("residence_region"), "gp_id": p.get("primary_care_provider_id") or None,
        "pneumologist_id": p.get("pneumologist_provider_id") or None,
        "status": status, "reasons": reasons, "flags": flags,
        "smoking": smoking_out, "ct": ct_out, "contact": contact,
    }


def run(data_dir, ref_date: str | date | None = None, cfg: Config | None = None) -> dict:
    cfg = cfg or Config()
    ref = date.fromisoformat(ref_date) if isinstance(ref_date, str) else (ref_date or date.today())
    tables, issues = load(data_dir)
    smoking = {}
    for s in tables["smoking"]:
        smoking[s["patient_id"]] = s
    cts, contacts = {}, {}
    for c in tables["ct"]:
        cts.setdefault(c["patient_id"], []).append(c)
    for c in tables["contacts"]:
        contacts.setdefault(c["patient_id"], []).append(c)

    patients = [evaluate(p, smoking.get(p["patient_id"]), cts.get(p["patient_id"], []),
                         contacts.get(p["patient_id"], []), ref, cfg) for p in tables["patients"]]

    from collections import Counter
    by_status = Counter(p["status"] for p in patients)
    by_action = Counter(p["contact"]["next_action"] for p in patients)
    prov = {}
    for p in patients:
        g = prov.setdefault(p["gp_id"], {"provider_id": p["gp_id"], "patients": 0, "eligible": 0, "needs_review": 0, "to_contact": 0})
        g["patients"] += 1
        g["eligible"] += p["status"] == "ELIGIBLE"
        g["needs_review"] += p["status"] == "NEEDS_REVIEW"
        g["to_contact"] += p["contact"]["next_action"] in ("SEND_INVITE", "SEND_REMINDER", "TRY_OTHER_CHANNEL", "GP_REFERRAL")
    return {
        "ref_date": ref.isoformat(), "config": asdict(cfg),
        "summary": {"total": len(patients), "by_status": dict(by_status), "by_next_action": dict(by_action)},
        "providers": sorted(prov.values(), key=lambda g: -g["to_contact"]),
        "data_issues": issues, "patients": patients,
    }
