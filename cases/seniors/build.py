"""Build the Jsem v pořádku demo data (case.json "data"): 80 synthetic lonely seniors in four Brno districts with
30 days of check-in calls (mood, needs, notes). Deterministic: a fixed seed, the same file every time.

  python -m cases.seniors.build [ref-date]

Every name, address and phone number is made up. Phone numbers use the clearly fake range +420 000 …
Answers are generated as Czech sentences and understood with the same rules as live answers (dialog.RULES, extract),
so the history and the live demo agree."""
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((Path(__file__).with_name("case.json")).read_text(encoding="utf-8"))
SEED = 2049
DAYS = 30

# district → (social workers, streets)
DISTRICTS = {
    "Brno-střed": (["Bc. Petra Malá", "Mgr. Ondřej Sýkora"], ["Údolní", "Pekařská", "Husova", "Křížová", "Kounicova", "Hybešova"]),
    "Brno-sever": (["Mgr. Lucie Horká"], ["Lesnická", "Merhautova", "Tomkova", "Provazníkova", "Jugoslávská"]),
    "Brno-Královo Pole": (["Bc. Tomáš Krejčí"], ["Palackého", "Štefánikova", "Božetěchova", "Purkyňova", "Kolejní"]),
    "Brno-Židenice": (["Bc. Eva Šimková"], ["Gajdošova", "Bubeníčkova", "Táborská", "Kuldova", "Stará osada"]),
}
PER_DISTRICT = 20

# (male, female, male vocative)
SURNAMES = [
    ("Novák", "Nováková", "Nováku"), ("Svoboda", "Svobodová", "Svobodo"), ("Novotný", "Novotná", "Novotný"),
    ("Dvořák", "Dvořáková", "Dvořáku"), ("Černý", "Černá", "Černý"), ("Procházka", "Procházková", "Procházko"),
    ("Kučera", "Kučerová", "Kučero"), ("Veselý", "Veselá", "Veselý"), ("Horák", "Horáková", "Horáku"),
    ("Němec", "Němcová", "Němče"), ("Pokorný", "Pokorná", "Pokorný"), ("Marek", "Marková", "Marku"),
    ("Pospíšil", "Pospíšilová", "Pospíšile"), ("Hájek", "Hájková", "Hájku"), ("Jelínek", "Jelínková", "Jelínku"),
    ("Král", "Králová", "Krále"), ("Růžička", "Růžičková", "Růžičko"), ("Beneš", "Benešová", "Beneši"),
    ("Fiala", "Fialová", "Fialo"), ("Sedláček", "Sedláčková", "Sedláčku"), ("Doležal", "Doležalová", "Doležale"),
    ("Zeman", "Zemanová", "Zemane"), ("Kolář", "Kolářová", "Koláři"), ("Navrátil", "Navrátilová", "Navrátile"),
    ("Čermák", "Čermáková", "Čermáku"), ("Urban", "Urbanová", "Urbane"), ("Vaněk", "Vaňková", "Vaňku"),
    ("Blažek", "Blažková", "Blažku"), ("Kříž", "Křížová", "Kříži"), ("Kovář", "Kovářová", "Kováři"),
    ("Bartoš", "Bartošová", "Bartoši"), ("Vlček", "Vlčková", "Vlčku"), ("Polák", "Poláková", "Poláku"),
    ("Musil", "Musilová", "Musile"), ("Šimek", "Šimková", "Šimku"), ("Konečný", "Konečná", "Konečný"),
]
WOMEN = ["Marie", "Jana", "Anna", "Věra", "Jaroslava", "Zdeňka", "Ludmila", "Božena", "Libuše", "Miroslava", "Eva",
         "Hana", "Vlasta", "Milada", "Jiřina", "Helena", "Alena", "Dagmar", "Olga", "Růžena", "Emilie", "Drahomíra"]
MEN = ["Josef", "Jan", "Jiří", "František", "Karel", "Václav", "Miroslav", "Zdeněk", "Jaroslav", "Antonín", "Vladimír",
       "Ladislav", "Stanislav", "Oldřich", "Bohumil", "Milan"]
RELATIVES = [("dcera", "F"), ("syn", "M"), ("neteř", "F"), ("vnučka", "F"), ("vnuk", "M"), ("sousedka", "F"), ("synovec", "M")]
YOUNG_W = ["Petra", "Lenka", "Martina", "Kateřina", "Ivana", "Lucie", "Monika", "Jitka"]
YOUNG_M = ["Petr", "Martin", "Tomáš", "Pavel", "Michal", "Lukáš", "David", "Jakub"]
MOBILITY = ["independent", "independent", "cane", "cane", "walker", "wheelchair", "homebound"]
SCHEDULES = [  # weekdays 0 = Monday
    ("daily", [0, 1, 2, 3, 4, 5, 6]), ("daily", [0, 1, 2, 3, 4, 5, 6]), ("weekdays", [0, 1, 2, 3, 4]),
    ("weekdays", [0, 1, 2, 3, 4]), ("mwf", [0, 2, 4]), ("mwf", [0, 2, 4]), ("tt", [1, 3]),
]
WINDOWS = [("8:30", "9:30"), ("9:00", "10:00"), ("10:00", "11:00"), ("13:00", "14:00"), ("16:00", "17:00")]
FLAGS = ["Nedoslýchá, mluvte pomalu a nahlas.", "Hůře vidí, SMS čte soused.", "Klíče od bytu má sousedka z 2. patra.",
         "Má psa, při návštěvě zazvonit dvakrát.", "Večer po 19. hodině nevolat."]

# Answers by intent; {a} = "a" for women ("byla jsem"). Mood and items come from dialog.extract over the sentence.
OK = {
    5: ["Výborně, děkuji. Byl{a} jsem dnes venku.", "Skvěle, vnučka mi přinesla koláč.", "Výborně, těším se na neděli."],
    4: ["Dobře, děkuji, všechno v pořádku.", "V pořádku, nic nepotřebuji.", "Dobře, dívám se na televizi.",
        "Fajn, dcera tu byla včera.", "Dobře, děkuji za zavolání."],
    3: ["Ujde to, nic nepotřebuji.", "Jde to, jen jsem trochu unaven{a}.", "Dá se to, nic nepotřebuji."],
}
ITEM_SAY = {
    "nakup": "potřeboval{a} bych nakoupit", "leky": "potřebuji vyzvednout léky v lékárně",
    "obed": "chtěl{a} bych zase dovážet obědy", "doprava": "potřebuji odvézt na poštu", "uklid": "nezvládám úklid",
    "otop": "nějak mi netopí topení", "pradlo": "potřebuji vyprat prádlo", "oprava": "kape mi kohoutek v kuchyni",
}
ITEM_W = {"nakup": 30, "leky": 22, "obed": 10, "doprava": 10, "uklid": 9, "otop": 7, "pradlo": 6, "oprava": 6}
NEED_PREFIX = {4: "Jinak dobře, jen", 3: "Ujde to, ale"}
LOW = ["Nic moc, jsem pořád sam{a} doma.", "Je mi smutno, nikdo za mnou nechodí.", "Ani nevím, je mi těžko.",
       "Nic moc, chtěl{a} bych si s někým popovídat.", "Smutno, chybí mi manžel."]
HEALTH = ["Bolí mě záda, špatně se mi chodí.", "Točí se mi hlava, ale už je to lepší.",
          "Upadl{a} jsem v koupelně, ale nic vážného.", "Mám teplotu od včerejška."]
EMERGENCY = ["Upadl{a} jsem a nemůžu vstát."]
CALLBACK = ["Teď nemůžu, zavolejte mi odpoledne.", "Teď nemám čas, jsem u lékaře."]
OPT_OUT = "Už mi prosím nevolejte, dcera se o mě stará."


def understand(text):
    """Intent by the dialog rules (the same as backend/replies.classify without the AI)."""
    from . import dialog
    t = dialog.norm(text)
    for intent, patterns in dialog.RULES:
        if any(re.search(p, t) for p in patterns):
            return intent
    return "question" if dialog.QUESTION.search(t) else "unclear"


def phone(rng):
    return f"+420 000 {rng.randint(100, 999)} {rng.randint(100, 999)}"


def say(rng, intent, mood, sex, items=()):
    a = "a" if sex == "F" else ""
    if intent == "ok":
        t = rng.choice(OK[max(3, min(5, mood))])
    elif intent == "need_items":
        parts = [ITEM_SAY[i] for i in items]
        t = f"{NEED_PREFIX[4 if mood >= 4 else 3]} {' a '.join(parts)}."
    elif intent == "low_mood":
        t = rng.choice(LOW)
    elif intent == "health_problem":
        t = rng.choice(HEALTH)
    elif intent == "emergency":
        t = rng.choice(EMERGENCY)
    elif intent == "callback":
        t = rng.choice(CALLBACK)
    else:
        t = OPT_OUT
    return t.replace("{a}", a)


def pick_items(rng):
    keys, w = zip(*ITEM_W.items())
    first = rng.choices(keys, w)[0]
    if rng.random() < 0.3:
        second = rng.choices(keys, w)[0]
        return [first] if second == first else [first, second]
    return [first]


def call(rng, day, window, sex, intent, mood, items=(), answered=True, minute=None):
    h, m = map(int, window[0].split(":"))
    mins = h * 60 + m + (minute if minute is not None else rng.randint(0, 50))
    c = {"date": day.isoformat(), "time": f"{mins // 60}:{mins % 60:02d}", "answered": answered}
    if not answered:
        return c
    from . import dialog
    text = say(rng, intent, mood, sex, items)
    got = understand(text)
    assert got == intent, (text, got, intent)  # generated sentences must mean what we planned
    ex = dialog.extract(text)
    c.update(text=text, intent=intent)
    if ex.get("mood"):
        c["mood"] = ex["mood"]
    if ex.get("items"):
        c["items"] = ex["items"]
    if ex.get("health_flag"):
        c["health"] = True
    return c


# Forced situations per district (index of the senior in the district) so that every district shows each case.
FORCED = {0: "health_problem", 1: "low_mood", 2: "need_items", 3: "need_items", 4: "no_answer", 5: "callback",
          17: "enrolled", 18: "paused", 19: "declined"}


def senior(rng, n, district, idx, used, ref):
    workers, streets = DISTRICTS[district]
    sex = "F" if rng.random() < 0.68 else "M"
    while True:
        sur = rng.choice(SURNAMES)
        first = rng.choice(WOMEN if sex == "F" else MEN)
        if (first, sur) not in used:
            used.add((first, sur))
            break
    surname = sur[1] if sex == "F" else sur[0]
    name = f"{first} {surname}"
    rel, rsex = rng.choice(RELATIVES)
    rsur = sur[1] if rsex == "F" else sur[0]
    if rel in ("sousedka",):
        o = rng.choice(SURNAMES)
        rsur = o[1]
    rname = f"{rng.choice(YOUNG_W if rsex == 'F' else YOUNG_M)} {rsur}"
    kind, days = rng.choice(SCHEDULES)
    window = rng.choice(WINDOWS)
    age = rng.randint(70, 95)
    mobility = rng.choice(MOBILITY) if age < 88 else rng.choice(MOBILITY[2:])
    p = {
        "id": f"S-{n:03d}", "district": district, "worker": workers[idx % len(workers)],
        "name": name, "sex": sex, "age": age,
        "title": f"{'paní' if sex == 'F' else 'pan'} {name}",
        "vocative": f"paní {surname}" if sex == "F" else f"pane {sur[2]}",
        "address": f"{rng.choice(streets)} {rng.randint(1, 120)}, {district}",
        "phone": phone(rng), "alone": True, "mobility": mobility,
        "schedule": {"kind": kind, "days": days, "from": window[0], "to": window[1]},
        "channel": "voice",
        "relative": {"name": rname, "rel": rel, "phone": phone(rng)},
        "since": (ref - timedelta(days=rng.randint(40, 700))).isoformat(),
        "flags": [],
        "history": [],
    }
    if rng.random() < 0.22:
        f = rng.choice(FLAGS)
        p["flags"].append({"sev": "warning", "text": f})
        if f.startswith("Nedoslýchá"):
            p["channel"] = "sms"
    forced = FORCED.get(idx)
    if forced == "declined" and district not in ("Brno-střed", "Brno-Židenice"):
        forced = None
    # personal tendencies
    answer = rng.uniform(0.82, 0.98)
    base = rng.uniform(3.0, 4.6)
    need_rate = rng.uniform(0.04, 0.16)
    low_rate = 0.25 if base < 3.4 else 0.05
    mood = base
    calls = []
    start = ref - timedelta(days=DAYS)
    stop = ref  # exclusive
    if forced == "enrolled":
        p["since"] = (ref - timedelta(days=1)).isoformat()
        stop = start
    if forced == "paused":
        pause_from = ref - timedelta(days=rng.randint(3, 8))
        stop = pause_from
        p["pause"] = {"reason": rng.choice(["V nemocnici", "U dcery na chalupě", "V lázních", "Respitní pobyt"]),
                      "from": pause_from.isoformat(), "until": (ref + timedelta(days=rng.randint(4, 12))).isoformat()}
    if forced == "declined":
        stop = ref - timedelta(days=rng.randint(6, 12))
    scheduled = [start + timedelta(days=i) for i in range((stop - start).days) if (start + timedelta(days=i)).weekday() in days]
    for i, day in enumerate(scheduled):
        last = i == len(scheduled) - 1
        mood = max(1.6, min(5.0, mood + rng.uniform(-0.6, 0.6) + (base - mood) * 0.3))
        m = round(mood)
        if last and forced:
            if forced == "no_answer":
                calls += [call(rng, day, window, sex, None, m, answered=False, minute=5),
                          call(rng, day, window, sex, None, m, answered=False, minute=125)]
                calls[-1]["relative"] = True  # 2x no answer: SMS to the relative
                continue
            if forced in ("health_problem", "low_mood", "need_items", "callback"):
                items = pick_items(rng) if forced == "need_items" else ()
                calls.append(call(rng, day, window, sex, forced, 2 if forced == "low_mood" else max(3, m), items))
                continue
            if forced == "declined":
                c = call(rng, day, window, sex, "opt_out", m)
                c.pop("mood", None)
                calls.append(c)
                continue
        if rng.random() > answer:
            calls.append(call(rng, day, window, sex, None, m, answered=False))
            if rng.random() < 0.6:  # the retry 2 hours later got through
                calls.append(call(rng, day, window, sex, "ok", max(3, m), minute=rng.randint(110, 140)))
            continue
        r = rng.random()
        if m <= 2 or r < low_rate * 0.4:
            intent = "low_mood"
        elif r < low_rate * 0.4 + need_rate:
            intent = "need_items"
        elif r < low_rate * 0.4 + need_rate + 0.02:
            intent = "health_problem"
        elif r < low_rate * 0.4 + need_rate + 0.028:
            intent = "callback"
        else:
            intent = "ok"
        calls.append(call(rng, day, window, sex, intent, max(3, m) if intent != "low_mood" else 2,
                          pick_items(rng) if intent == "need_items" else ()))
    # one historical emergency in the whole data set, long resolved
    if n == 23 and len(calls) > 10:
        k = len(calls) // 3
        calls[k] = call(rng, date.fromisoformat(calls[k]["date"]), window, sex, "emergency", 3)
        calls[k].pop("mood", None)
        calls[k]["note"] = "Sousedka přivolala záchrannou službu, druhý den doma. Vyřešeno."
    p["calls"] = calls
    p["needs"] = needs_of(p["id"], calls, ref)
    p["stage"], extra = stage_of(calls, forced, p["needs"], ref)
    p.update(extra)
    return p


def needs_of(pid, calls, ref):
    """Basket entries from the calls of the last 14 days; older ones are done, recent ones ordered or new."""
    out = []
    for c in calls:
        age = (ref - date.fromisoformat(c["date"])).days
        if age > 14:
            continue
        for it in c.get("items", []):
            if it == "navsteva":
                continue
            status = "new" if age <= 2 else "ordered" if age <= 6 else "done"
            out.append({"id": f"{pid}-{c['date']}-{it}", "item": it, "date": c["date"], "status": status})
    return out


def stage_of(calls, forced, needs, ref):
    if forced == "enrolled":
        return "enrolled", {}
    if forced == "paused":
        return "paused", {}
    if forced == "declined":
        return "declined", {}
    if not calls:
        return "enrolled", {}
    last = calls[-1]
    if not last["answered"]:
        missed = 0
        for c in reversed(calls):
            if c["answered"] or c["date"] != last["date"]:
                break
            missed += 1
        return "no_answer", {"missed": missed}
    age = (ref - date.fromisoformat(last["date"])).days
    intent = last["intent"]
    if intent in ("health_problem", "emergency"):
        return ("escalated" if age <= 2 or forced == "health_problem" else "resolved"), {}
    if intent == "need_items":
        open_ = [n for n in needs if n["date"] == last["date"] and n["status"] != "done"]
        return ("needs_help" if open_ else "resolved"), {}
    if intent == "low_mood":
        return ("low_mood" if age <= 3 else "ok"), {}
    if intent == "callback":
        return "callback", {}
    return "ok", {}


def build(ref: str = MANIFEST["ref_date"]) -> dict:
    rng = random.Random(SEED)
    refd = date.fromisoformat(ref)
    used, out, n = set(), [], 0
    for district in DISTRICTS:
        for idx in range(PER_DISTRICT):
            n += 1
            out.append(senior(rng, n, district, idx, used, refd))
    return {"refDate": ref, "issues": [], "patients": out}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = build(argv[0] if argv else MANIFEST["ref_date"])
    dst = ROOT / MANIFEST["data"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(dst, dst.stat().st_size)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
