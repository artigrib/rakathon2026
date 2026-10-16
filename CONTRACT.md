# Engine output contract (v1)

Engine = pure function: `run(data_dir, ref_date, config) -> RunResult` (JSON).
Backend serves it, frontend renders it. Both can start on `examples/run_result.json` now.

## RunResult
```json
{
  "ref_date": "2026-10-16",
  "config": { "recent_ct_days": 30, "ldct_interval_days": 365, "ldct_interval_negative_days": 730, "min_age": 55, "max_age": 74, "min_pack_years": 20, "contact_cooldown_days": 14 },
  "summary": { "total": 300, "by_status": {"ELIGIBLE": 102, "...": 0}, "by_next_action": {"SEND_INVITE": 40, "...": 0} },
  "providers": [ { "provider_id": "VPL-0142", "patients": 25, "eligible": 9, "needs_review": 4, "to_contact": 7 } ],
  "data_issues": [ { "file": "2_smoking_history.csv", "row": 7, "patient_id": "SYN-000006", "code": "MISSING_COLUMN", "text": "…" } ],
  "patients": [ Patient ]
}
```

## Patient
```json
{
  "patient_id": "SYN-000001",
  "age": 62, "sex": "F", "region": "Jihomoravský kraj",
  "gp_id": "VPL-0142", "pneumologist_id": "PNEU-0081",

  "status": "ELIGIBLE | EXCLUDED_AGE | EXCLUDED_SMOKING_STATUS | EXCLUDED_PACK_YEARS | EXCLUDED_RECENT_CT | NEEDS_REVIEW",
  "reasons": [ { "code": "AGE_OK", "text": "Věk 62 let (55–74)" } ],
  "flags":   [ { "code": "CT_NEARBY", "severity": "info | warning", "text": "CT hrudníku 15. 8. 2026 (62 dní)" } ],

  "smoking": {
    "status": "former", "pack_years": 26.0, "pack_years_source": "calculated | reported | derived | none",
    "pack_years_reported": null, "pack_years_calculated": 26.0,
    "quit_year": 2012, "data_quality": "complete", "note": "Bývalý kuřák jedna krabička denně"
  },
  "ct": [ { "ct_id": "CT-000001", "date": "2026-08-15", "region": "chest", "protocol": "standard_chest",
            "status": "completed", "external": false, "days_ago": 62, "report": "…" } ],

  "contact": {
    "history": [ { "date": "2026-09-01", "channel": "portal", "type": "lung_screening_information",
                   "delivery": "read", "response": "no_response", "by": "SYSTEM" } ],
    "next_action": "SEND_INVITE | SEND_REMINDER | TRY_OTHER_CHANNEL | GP_REFERRAL | WAIT | DO_NOT_CONTACT | NONE",
    "recommended_channel": "portal | sms | voice | email | letter | printout | null",
    "message_variant": "FIRST_INVITE | REMINDER | MOTIVATION | null",
    "reason": "Zpráva na portálu byla přečtena, ale bez odpovědi → doporučen telefonát asistenta"
  }
}
```

Statuses = README. Every status has ≥1 human-readable Czech reason. `flags` never change status
on their own except where SPEC says so (external recent CT → NEEDS_REVIEW).
