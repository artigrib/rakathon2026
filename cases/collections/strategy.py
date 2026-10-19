"""Segment and strategy of a debtor: deterministic rules, readable by a supervisor and testable.

AI never chooses the strategy. It only understands replies (dialog.py); what we offer and whether the automation
may contact the person at all is decided here, from the record, in this order (first rule that applies wins):

  R1 spor          the debtor disputes the claim            → člověk, automatika stop
  R2 zranitelný    illness, bereavement, distress …          → člověk, automatika stop
  R3 nespolupracující  ≥ 2 broken promises, or DPD ≥ 90 with ≥ 4 unanswered contacts → supervizor
  R4 dlouhodobé potíže DPD > 60, or ≥ 2 other loans and DPD > 30   → refinancování / konsolidace
  R5 dočasné potíže    DPD > 30, reduced / irregular / lost income, or 1 broken promise → splátky / odklad
  R6 zapomnětlivý      everything else (DPD ≤ 30, stable income, no broken promise) → připomínka + platební odkaz

The web app shows the stored result (build.py writes it into the data file); tests check the data matches this module.
"""
import math

SEGMENTS = ["forgetful", "temporary", "long_term", "uncooperative", "dispute", "vulnerable"]
STRATEGY = {"forgetful": "reminder", "temporary": "plan", "long_term": "refi",
            "uncooperative": "supervisor", "dispute": "human", "vulnerable": "human"}
AUTOMATED = {"reminder", "plan", "refi"}  # the only strategies the contact plan may run on its own

# Thresholds (product decisions, one place).
FORGETFUL_MAX_DPD = 30
LONG_TERM_DPD = 60
UNCOOP_DPD = 90
UNCOOP_UNANSWERED = 4
UNCOOP_BROKEN = 2
MANY_LOANS = 2

# Offers (illustrative demo numbers; the real ones come from the credit policy).
PLAN_MONTHS = (3, 6, 12)
PLAN_MIN_INSTALMENT = 500      # Kč; shorter plans only when the instalment would be smaller
DEFERRAL_DAYS = 30
REFI_RATE = 0.099              # p.a., illustrative
REFI_TERMS = (24, 36, 48, 60)


def broken_promises(r: dict) -> int:
    return sum(1 for p in r.get("promises") or [] if p.get("kept") is False)


def unanswered(r: dict) -> int:
    return sum(1 for h in r.get("history") or [] if h.get("response") == "no_response")


def segment(r: dict) -> dict:
    """{segment, strategy, automation, rule, reason} for one debtor record."""
    dpd = int(r.get("dpd") or 0)
    broken = broken_promises(r)
    silent = unanswered(r)
    income = r.get("income") or "unknown"
    loans = int(r.get("otherLoans") or 0)

    def out(seg, rule, reason):
        s = STRATEGY[seg]
        return {"segment": seg, "strategy": s, "automation": s in AUTOMATED, "rule": rule, "reason": reason}

    if r.get("dispute"):
        return out("dispute", "R1", f"Rozporuje pohledávku: {r['dispute'].get('note', '')}".rstrip(": "))
    if r.get("vulnerable"):
        return out("vulnerable", "R2", f"Známka zranitelnosti: {r['vulnerable'].get('note', '')}".rstrip(": "))
    if broken >= UNCOOP_BROKEN:
        return out("uncooperative", "R3", f"{broken} nedodržené sliby platby")
    if dpd >= UNCOOP_DPD and silent >= UNCOOP_UNANSWERED:
        return out("uncooperative", "R3", f"{dpd} dní po splatnosti, {silent} kontaktů bez odpovědi")
    if dpd > LONG_TERM_DPD:
        return out("long_term", "R4", f"{dpd} dní po splatnosti")
    if loans >= MANY_LOANS and dpd > FORGETFUL_MAX_DPD:
        return out("long_term", "R4", f"{loans} další úvěry, {dpd} dní po splatnosti")
    if dpd > FORGETFUL_MAX_DPD:
        return out("temporary", "R5", f"{dpd} dní po splatnosti")
    if income in ("reduced", "irregular", "lost"):
        return out("temporary", "R5", {"reduced": "Snížený příjem", "irregular": "Nepravidelný příjem",
                                         "lost": "Ztráta příjmu"}[income])
    if broken == 1:
        return out("temporary", "R5", "1 nedodržený slib platby")
    return out("forgetful", "R6", f"{dpd} dní po splatnosti, dosud platil(a) včas")


# ---------- offers shown on the secure page /p/{token} after verification ----------
def plan_options(amount: int) -> list:
    """Instalment plans for the amount: [{n, monthly, last}] (equal instalments, the last one evens out)."""
    amount = int(amount)
    out = []
    for n in PLAN_MONTHS:
        monthly = math.ceil(amount / n)
        if n > 3 and monthly < PLAN_MIN_INSTALMENT:
            continue
        out.append({"n": n, "monthly": monthly, "last": amount - monthly * (n - 1)})
    return out


def schedule(amount: int, n: int, start: str, every_days: int = 30) -> list:
    """Instalments of a plan: [{due, amount}] starting at `start` (ISO), every `every_days` days."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    opt = next((o for o in plan_options(amount) if o["n"] == n), None) or {"monthly": math.ceil(amount / n), "last": amount - math.ceil(amount / n) * (n - 1)}
    return [{"due": (d0 + timedelta(days=every_days * i)).isoformat(),
             "amount": opt["last"] if i == n - 1 else opt["monthly"]} for i in range(n)]


def annuity(principal: float, months: int, rate: float = REFI_RATE) -> int:
    q = rate / 12
    return math.ceil(principal * q / (1 - (1 + q) ** -months))


def refi_example(amount: int, other: int = 0) -> dict:
    """Illustrative consolidation: the outstanding amount (+ other debts) as one loan. Not an offer."""
    principal = int(amount) + int(other)
    months = next((t for t in REFI_TERMS if annuity(principal, t) <= max(1500, principal / 30)), REFI_TERMS[-1])
    monthly = annuity(principal, months)
    rpsn = round(((1 + REFI_RATE / 12) ** 12 - 1) * 100, 1)  # no fees in the example
    return {"principal": principal, "months": months, "rate": round(REFI_RATE * 100, 1), "rpsn": rpsn,
            "monthly": monthly, "total": monthly * months}


def czk(n) -> str:
    """12345 → '12 345 Kč' (non-breaking space)."""
    return f"{int(round(n)):,}".replace(",", " ") + " Kč"
