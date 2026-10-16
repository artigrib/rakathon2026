from datetime import date
from pathlib import Path

import pytest

from engine import run, Config
from engine.rules import evaluate, age_on, pack_years

DATA = Path(__file__).resolve().parents[1] / "data"
REF = date(2026, 10, 16)
CFG = Config()


def patient(**kw):
    p = {"patient_id": "T1", "date_of_birth": "1960-01-01", "sex": "M", "residence_region": "Praha",
         "primary_care_provider_id": "VPL-1", "pneumologist_provider_id": "",
         "patient_portal_active": "true", "consent_for_portal_messages": "true",
         "preferred_contact_channel": "portal"}
    p.update(kw)
    return p


def smoking(**kw):
    s = {"patient_id": "T1", "smoking_status": "current", "cigarettes_per_day": "20",
         "smoking_start_year": "1980", "smoking_end_year": "", "pack_years_reported": "",
         "pack_years_calculated": "46", "data_quality": "complete", "free_text_note": "", "_repaired": False}
    s.update(kw)
    return s


def ct(days_ago, protocol="standard_chest", region="chest", status="completed", external="false", report=""):
    d = date.fromordinal(REF.toordinal() - days_ago)
    return {"ct_id": "CT-X", "patient_id": "T1", "performed_at": d.isoformat() + "T10:00:00",
            "body_region": region, "protocol": protocol, "status": status,
            "is_external": external, "report_text": report}


def contact(days_ago, channel="portal", delivery="read", response="no_response", mtype="lung_screening_information"):
    d = date.fromordinal(REF.toordinal() - days_ago)
    return {"patient_id": "T1", "created_at": d.isoformat() + "T09:00:00", "channel": channel,
            "message_type": mtype, "delivery_status": delivery, "response": response, "handled_by": "SYSTEM"}


def ev(p=None, s="default", cts=(), contacts=()):
    return evaluate(p or patient(), smoking() if s == "default" else s, list(cts), list(contacts), REF, CFG)


# --- real data ---------------------------------------------------------------

def test_real_data_counts():
    r = run(DATA, "2026-10-16")
    assert r["summary"]["total"] == 300
    assert r["summary"]["by_status"] == {
        "ELIGIBLE": 101, "EXCLUDED_PACK_YEARS": 53, "EXCLUDED_AGE": 50,
        "NEEDS_REVIEW": 50, "EXCLUDED_SMOKING_STATUS": 23, "EXCLUDED_RECENT_CT": 23}


def test_malformed_smoking_rows_are_repaired_and_reviewed():
    r = run(DATA, "2026-10-16")
    assert sum(1 for i in r["data_issues"] if i["code"] == "MISSING_COLUMN") == 28
    p = next(x for x in r["patients"] if x["patient_id"] == "SYN-000006")
    assert p["status"] == "NEEDS_REVIEW"
    assert any(f["code"] == "DATA_REPAIRED" for f in p["flags"])


def test_every_patient_has_a_reason():
    r = run(DATA, "2026-10-16")
    assert all(p["reasons"] for p in r["patients"])


# --- rules -------------------------------------------------------------------

@pytest.mark.parametrize("dob,ok", [("1971-10-16", True), ("1971-10-17", False),
                                    ("1951-10-17", True), ("1951-10-16", False)])
def test_age_boundaries(dob, ok):
    assert (ev(patient(date_of_birth=dob))["status"] != "EXCLUDED_AGE") == ok


def test_never_smoker_excluded():
    assert ev(s=smoking(smoking_status="never", pack_years_calculated="0"))["status"] == "EXCLUDED_SMOKING_STATUS"


def test_former_smoker_no_quit_limit():
    r = ev(s=smoking(smoking_status="former", smoking_end_year="1995", pack_years_calculated="30"))
    assert r["status"] == "ELIGIBLE"


def test_pack_years_threshold_inclusive():
    assert ev(s=smoking(pack_years_calculated="20"))["status"] == "ELIGIBLE"
    assert ev(s=smoking(pack_years_calculated="19.9"))["status"] == "EXCLUDED_PACK_YEARS"


def test_conflict_uses_higher_value_and_flags():
    r = ev(s=smoking(pack_years_reported="25", pack_years_calculated="15", data_quality="conflicting"))
    assert r["status"] == "ELIGIBLE"
    assert any(f["code"] == "PY_CONFLICT" for f in r["flags"])


def test_pack_years_derived_when_missing():
    v, src, *_ = pack_years(smoking(pack_years_calculated="", cigarettes_per_day="20",
                                    smoking_start_year="2000", smoking_end_year="2025"), REF)
    assert (v, src) == (25.0, "derived")


def test_missing_pack_years_needs_review():
    r = ev(s=smoking(pack_years_calculated="", cigarettes_per_day=""))
    assert r["status"] == "NEEDS_REVIEW"


def test_unknown_smoking_needs_review():
    assert ev(s=smoking(smoking_status="unknown"))["status"] == "NEEDS_REVIEW"
    assert ev(s=None)["status"] == "NEEDS_REVIEW"


# --- CT ----------------------------------------------------------------------

@pytest.mark.parametrize("protocol", ["standard_chest", "ldct"])
def test_recent_chest_ct_excludes(protocol):
    assert ev(cts=[ct(30, protocol)])["status"] == "EXCLUDED_RECENT_CT"


def test_ct_31_days_ago_does_not_exclude():
    r = ev(cts=[ct(31)])
    assert r["status"] == "ELIGIBLE"
    assert any(f["code"] == "CT_NEARBY" for f in r["flags"])


def test_recent_non_chest_ct_does_not_exclude():
    assert ev(cts=[ct(5, "standard_head", region="head")])["status"] == "ELIGIBLE"


def test_recent_external_ct_goes_to_review():
    assert ev(cts=[ct(10, external="true")])["status"] == "NEEDS_REVIEW"


def test_scheduled_and_cancelled_ct_only_flag():
    r = ev(cts=[ct(-5, status="scheduled"), ct(10, status="cancelled")])
    assert r["status"] == "ELIGIBLE"
    codes = {f["code"] for f in r["flags"]}
    assert {"CT_SCHEDULED", "CT_CANCELLED"} <= codes


def test_negative_ldct_within_two_years_means_in_screening():
    r = ev(cts=[ct(400, "ldct", report="Bez suspektních ložisek.")])
    assert r["status"] == "EXCLUDED_RECENT_CT" and r["reasons"][-1]["code"] == "IN_SCREENING"


def test_negative_ldct_after_two_years_is_due_again():
    assert ev(cts=[ct(731, "ldct", report="Bez suspektních ložisek.")])["status"] == "ELIGIBLE"


def test_ldct_with_unclear_report_repeats_after_one_year():
    assert ev(cts=[ct(200, "ldct", report="Stabilní nález.")])["status"] == "EXCLUDED_RECENT_CT"
    assert ev(cts=[ct(366, "ldct", report="Stabilní nález.")])["status"] == "ELIGIBLE"


def test_ldct_finding_flagged():
    r = ev(cts=[ct(100, "ldct", report="Malý nespecifický uzlík k další kontrole.")])
    assert any(f["code"] == "LDCT_FINDING" for f in r["flags"])
    assert r["status"] == "EXCLUDED_RECENT_CT"


# --- channel -----------------------------------------------------------------

def test_first_invite_portal():
    c = ev()["contact"]
    assert (c["next_action"], c["recommended_channel"]) == ("SEND_INVITE", "portal")


def test_first_invite_letter_without_portal():
    c = ev(patient(patient_portal_active="false", consent_for_portal_messages="false",
                   preferred_contact_channel="letter"))["contact"]
    assert c["recommended_channel"] == "letter"


def test_failed_portal_switches_channel():
    c = ev(contacts=[contact(30, delivery="failed", response="")])["contact"]
    assert c["next_action"] == "TRY_OTHER_CHANNEL" and c["recommended_channel"] != "portal"


def test_read_no_response_suggests_voice():
    c = ev(contacts=[contact(30)])["contact"]
    assert (c["next_action"], c["recommended_channel"]) == ("SEND_REMINDER", "voice")


def test_delivered_unread_suggests_sms():
    c = ev(contacts=[contact(30, delivery="delivered")])["contact"]
    assert c["recommended_channel"] == "sms"


def test_interested_creates_referral_task():
    assert ev(contacts=[contact(30, response="interested")])["contact"]["next_action"] == "GP_REFERRAL"


def test_not_interested_once_retries_with_motivation():
    c = ev(contacts=[contact(30, response="not_interested")])["contact"]
    assert c["next_action"] == "TRY_OTHER_CHANNEL" and c["message_variant"] == "MOTIVATION"


def test_not_interested_twice_stops():
    c = ev(contacts=[contact(60, response="not_interested"), contact(30, channel="sms", response="not_interested")])["contact"]
    assert c["next_action"] == "DO_NOT_CONTACT"


def test_cooldown_waits():
    assert ev(contacts=[contact(3)])["contact"]["next_action"] == "WAIT"


def test_not_eligible_gets_no_contact():
    assert ev(s=smoking(smoking_status="never"))["contact"]["next_action"] == "NONE"


def test_policy_2027_widens_age():
    from engine.rules import Config
    c = Config.policy("2027")
    assert (c.min_age, c.max_age, c.min_pack_years) == (50, 80, 20.0)
    assert Config.policy("2026") == Config()


def test_policy_2027_more_eligible_on_real_data():
    from engine.rules import Config, run
    a = run(DATA, REF, Config())["summary"]["by_status"]
    b = run(DATA, REF, Config.policy("2027"))["summary"]["by_status"]
    assert b.get("EXCLUDED_AGE", 0) < a["EXCLUDED_AGE"]
    assert b["ELIGIBLE"] >= a["ELIGIBLE"]


def test_current_smoker_gets_cessation_flag():
    from engine.rules import run
    pts = run(DATA, REF)["patients"]
    cur = [p for p in pts if p["status"] == "ELIGIBLE" and p["smoking"]["status"] == "current"]
    assert cur and all(any(f["code"] == "CESSATION" for f in p["flags"]) for p in cur)
    assert not any(f["code"] == "CESSATION" for p in pts if p["smoking"] and p["smoking"].get("status") == "former" for f in p["flags"])
