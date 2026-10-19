"""Synthetic debtors of a fictional consumer lender (Finance Demo a.s.): deterministic, fixed seed.

  python -m cases.collections.build [ref-date]       # writes case.json "data"

Everything is invented: names, birth dates, contracts, amounts. Phone numbers come from the range +420 000 …, which no
Czech number uses; e-mails are @example.com. Real demo messages go only to the demo recipient, never to a record.
The segment and strategy of each record come from strategy.py (deterministic rules, not AI).
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "case.json").read_text(encoding="utf-8"))
SEED = 2026
N = 100

PORTFOLIO = {"loan": "Spotřebitelské úvěry", "card": "Kreditní karty", "bnpl": "BNPL", "phone": "Telefony na splátky"}
PREFIX = {"loan": "SU", "card": "KK", "bnpl": "BN", "phone": "TS"}
PRODUCTS = ["loan"] * 40 + ["card"] * 25 + ["bnpl"] * 20 + ["phone"] * 15
# archetype → how the record is drawn (the segment itself is computed by strategy.py from the fields)
ARCHETYPES = ["forgetful"] * 32 + ["temporary"] * 26 + ["long_term"] * 22 + ["uncooperative"] * 12 + ["dispute"] * 3 + ["vulnerable"] * 5

M_FIRST = ["Jan", "Petr", "Tomáš", "Martin", "Jiří", "Pavel", "Lukáš", "Jakub", "Michal", "David", "Ondřej", "Karel", "Josef", "Miroslav", "Filip", "Roman"]
F_FIRST = ["Jana", "Eva", "Lenka", "Petra", "Lucie", "Kateřina", "Martina", "Hana", "Veronika", "Tereza", "Markéta", "Zuzana", "Alena", "Monika", "Barbora", "Ivana"]
SURNAMES = [("Novák", "Nováková"), ("Svoboda", "Svobodová"), ("Novotný", "Novotná"), ("Dvořák", "Dvořáková"), ("Černý", "Černá"),
            ("Procházka", "Procházková"), ("Kučera", "Kučerová"), ("Veselý", "Veselá"), ("Horák", "Horáková"), ("Němec", "Němcová"),
            ("Marek", "Marková"), ("Pospíšil", "Pospíšilová"), ("Hájek", "Hájková"), ("Jelínek", "Jelínková"), ("Král", "Králová"),
            ("Růžička", "Růžičková"), ("Beneš", "Benešová"), ("Fiala", "Fialová"), ("Sedláček", "Sedláčková"), ("Doležal", "Doležalová")]
CITIES = ["Praha", "Brno", "Ostrava", "Plzeň", "Liberec", "Olomouc", "Hradec Králové", "České Budějovice", "Pardubice", "Zlín", "Kladno", "Jihlava"]
VULNERABLE = [("illness", "Dlouhodobá nemoc, v SMS zmínil(a) pobyt v nemocnici"), ("bereavement", "Úmrtí v rodině, sděleno na pobočce"),
              ("job_loss", "Ztráta zaměstnání, při posledním hovoru velmi rozrušen(a)"), ("illness", "Onkologická léčba, sděleno operátorovi"),
              ("care", "Pečuje o blízkou osobu, ztráta příjmu")]
DISPUTES = ["Tvrdí, že úvěr nesjednal(a), možné zneužití totožnosti", "Rozporuje výši poplatku za upomínku",
            "Tvrdí, že telefon vrátil(a) v zákonné lhůtě"]


def _amounts(rnd, product, arche):
    if product == "loan":
        principal = rnd.randrange(30_000, 300_001, 5_000)
        instalment = round(principal / rnd.choice([24, 36, 48, 60]) / 10) * 10
    elif product == "card":
        principal = rnd.randrange(10_000, 80_001, 5_000)
        instalment = max(500, round(principal * 0.05 / 10) * 10)
    elif product == "bnpl":
        principal = rnd.randrange(1_500, 15_001, 100)
        instalment = round(principal / 3 / 10) * 10
    else:
        principal = rnd.randrange(8_000, 40_001, 500)
        instalment = round(principal / 24 / 10) * 10
    return principal, instalment


DPD = {"forgetful": (5, 30), "temporary": (12, 60), "long_term": (61, 180), "uncooperative": (35, 180), "dispute": (10, 120), "vulnerable": (10, 120)}


def build(ref: str = MANIFEST["ref_date"]) -> dict:
    from cases.collections.strategy import segment
    rnd = random.Random(SEED)
    today = date.fromisoformat(ref)
    products = PRODUCTS[:]
    archetypes = ARCHETYPES[:]
    rnd.shuffle(products)
    rnd.shuffle(archetypes)
    vulnerable, disputes = VULNERABLE[:], DISPUTES[:]
    out = []
    for i in range(N):
        product, arche = products[i], archetypes[i]
        sex = rnd.choice("FM")
        first = rnd.choice(F_FIRST if sex == "F" else M_FIRST)
        sur = rnd.choice(SURNAMES)[1 if sex == "F" else 0]
        age = rnd.randint(21, 74)
        born = date(today.year - age, rnd.randint(1, 12), rnd.randint(1, 28))
        principal, instalment = _amounts(rnd, product, arche)
        lo, hi = DPD[arche]
        dpd = rnd.randint(lo, hi)
        missed = max(1, -(-dpd // 30))
        balance = round(principal * rnd.uniform(0.35, 0.95)) if product != "bnpl" else principal
        outstanding = min(balance, instalment * missed) if product != "bnpl" else principal
        income = {"forgetful": "stable", "temporary": rnd.choice(["reduced", "irregular", "lost", "stable"]),
                  "long_term": rnd.choice(["reduced", "stable", "irregular"]), "uncooperative": rnd.choice(["unknown", "stable", "irregular"]),
                  "dispute": rnd.choice(["stable", "unknown"]), "vulnerable": rnd.choice(["reduced", "lost"])}[arche]
        other = {"long_term": rnd.choice([0, 1, 2, 2, 3])}.get(arche, rnd.choice([0, 0, 0, 1]))
        # earlier promises to pay (kept True / broken False)
        promises = []
        n_prom = {"forgetful": rnd.choice([0, 0, 1]), "temporary": rnd.choice([0, 1, 1]), "long_term": rnd.choice([0, 1, 2]),
                  "uncooperative": rnd.choice([2, 2, 3]), "dispute": 0, "vulnerable": rnd.choice([0, 1])}[arche]
        for k in range(n_prom):
            when = today - timedelta(days=rnd.randint(20, 170))
            kept = True if arche == "forgetful" else (False if arche == "uncooperative" else rnd.random() < 0.5)
            if arche == "temporary" and k == 0 and not kept:
                kept = rnd.random() < 0.5
            promises.append({"date": when.isoformat(), "amount": round(outstanding * rnd.uniform(0.3, 1.0) / 100) * 100 or 100, "kept": kept})
        promises.sort(key=lambda p: p["date"])
        if arche == "long_term" and sum(1 for p in promises if p["kept"] is False) >= 2:
            promises[-1]["kept"] = True
        # earlier contacts by the creditor's own reminders (before this tool)
        history = []
        n_hist = {"uncooperative": rnd.randint(4, 6), "long_term": rnd.randint(1, 4)}.get(arche, rnd.randint(0, 2))
        for _ in range(n_hist):
            ch = rnd.choice(["sms", "sms", "email", "letter", "voice"])
            resp = "no_response" if arche == "uncooperative" or rnd.random() < 0.6 else "replied"
            history.append({"date": (today - timedelta(days=rnd.randint(3, max(4, dpd)))).isoformat(), "channel": ch, "type": "reminder",
                            "delivery": "failed" if rnd.random() < 0.08 else "delivered", "response": resp})
        history.sort(key=lambda h: h["date"])
        pref = rnd.choice(["sms"] * 5 + ["email"] * 2 + ["whatsapp"] * 2 + ["voice"])
        rec = {
            "id": f"DL-{1001 + i}",
            "name": f"{first} {sur}", "sex": sex, "age": age, "birthDate": born.isoformat(), "city": rnd.choice(CITIES),
            "portfolio": PORTFOLIO[product], "product": product,
            "contract": f"{PREFIX[product]}-{rnd.randint(2021, 2025)}-{rnd.randint(10000, 99999)}",
            "principal": principal, "balance": balance, "instalment": instalment, "outstanding": outstanding,
            "dpd": dpd, "dueSince": (today - timedelta(days=dpd)).isoformat(),
            "promises": promises, "income": income, "otherLoans": other,
            "vulnerable": None, "dispute": None,
            "pref": pref,
            "phone": f"+420 000 {rnd.randint(100, 199)} {rnd.randint(100, 999)}",
            "email": f"dluznik{1001 + i}@example.com",
            "history": history, "flags": [],
        }
        if arche == "vulnerable":
            kind, note = vulnerable.pop(0)
            rec["vulnerable"] = {"kind": kind, "note": note}
            rec["flags"].append({"sev": "warning", "code": "VULNERABLE", "text": f"Zranitelný klient: {note}. Automatika je zastavena, kontaktuje jen člověk."})
        if arche == "dispute":
            note = disputes.pop(0)
            rec["dispute"] = {"note": note, "since": (today - timedelta(days=rnd.randint(2, 20))).isoformat()}
            rec["flags"].append({"sev": "warning", "code": "DISPUTE", "text": f"Spor: {note}. Vymáhání pozastaveno do vyřešení."})
        if any(h["delivery"] == "failed" for h in history):
            rec["flags"].append({"sev": "info", "code": "DELIVERY", "text": "Některá dřívější zpráva nebyla doručena."})
        rec.update(segment(rec))
        out.append(rec)
    return {"refDate": ref, "issues": [], "patients": out}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = build(argv[0] if argv else MANIFEST["ref_date"])
    dst = ROOT / MANIFEST["data"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(dst, dst.stat().st_size)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
