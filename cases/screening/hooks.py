"""Screening hooks called by the core (backend/messages.py, backend/app.py)."""


def extra_placeholders(patient: dict, M: dict) -> dict:
    """Message placeholders from the patient record: {gp}, and {contact} names the pneumologist when the patient has one."""
    return {
        "gp": patient.get("gp") or "",
        "contact": M["parts"]["contact_with_pneu" if patient.get("pneu") else "contact"],
    }


def on_reply(pid: str, intent: str, extra: dict, store) -> None:
    """Side effects of an understood reply beyond the journey event (none in screening)."""
