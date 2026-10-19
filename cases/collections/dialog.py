"""AI vymáhání: how a debtor's reply is understood and what the assistant may say.

The AI only understands. It never chooses the strategy (strategy.py), never decides to contact anybody (cadence.py)
and never says anything that is not written here or in messages.cs.json. Before identity verification nothing about
the debt is said: no amount, no DPD, not even the word "dluh". The phone flows below never say an amount at all;
details are only on the secure page /p/{token} after verification.

Intents → journey events (journey.json):
  will_pay        promise to pay (+ date and amount from extract) → promise_to_pay
  need_plan       instalments / deferral                         → plan_offered
  cannot_pay      cannot pay now (no distress)                   → plan_offered (splátky, odklad)
  want_refi       refinancing / consolidation                    → refi_offered
  dispute         disputes the claim, says already paid           → dispute (person, automation stops)
  vulnerable      illness, bereavement, distress …               → hardship_review (person, automation stops)
  wrong_person    wrong number / not the debtor                  → wrong_contact (apologise, end, number invalid)
  opt_out         no more contact at all (STOP)                  → do_not_contact (final)
  channel_opt_out not this channel (e.g. "nevolejte mi")         → stage unchanged, the channel is blocked (cadence)
  callback, question, unclear                                    → human_handoff (a person calls back)
"""
import re
import unicodedata
from datetime import date, timedelta

INTENTS = ["will_pay", "need_plan", "cannot_pay", "want_refi", "dispute", "vulnerable", "wrong_person",
           "opt_out", "channel_opt_out", "callback", "question", "unclear"]

INTENT_EVENT = {"will_pay": "will_pay", "need_plan": "need_plan", "cannot_pay": "cannot_pay", "want_refi": "want_refi",
                "dispute": "dispute", "vulnerable": "vulnerable", "wrong_person": "wrong_person", "opt_out": "opt_out",
                "channel_opt_out": "channel_opt_out", "callback": "callback", "question": "callback", "unclear": "callback"}

STAGE = {"will_pay": "promise_to_pay", "need_plan": "plan_offered", "cannot_pay": "plan_offered", "want_refi": "refi_offered",
         "dispute": "dispute", "vulnerable": "hardship_review", "wrong_person": "wrong_contact", "opt_out": "do_not_contact",
         "channel_opt_out": "contacted", "callback": "human_handoff", "question": "human_handoff", "unclear": "human_handoff"}

# (intent, patterns) in priority order, first match wins. Patterns run on lower-case ASCII text (no diacritics).
# Safety first: opt-out, wrong person, vulnerability and dispute come before anything about paying.
RULES = [
    ("opt_out", [r"^\s*stop\s*$", r"\bstop\b(?!\s*(sms|whatsapp|e-?mail|hovor))", r"\bodhlas", r"nekontaktujte", r"neobtezujte",
                 r"dejte mi (uz )?pokoj", r"nechte me (uz )?(byt|na pokoji)", r"nevolejte.{0,30}nepiste|nepiste.{0,30}nevolejte",
                 r"nechci (zadne|dalsi|uz zadne) (zpravy|hovory|kontakt)", r"^\s*0\s*$"]),
    ("channel_opt_out", [r"\bstop (sms|whatsapp|e-?mail|hovor)", r"\bnevolejte\b", r"prestante (mi )?volat", r"nechci (zadne )?hovory",
                         r"(nepiste|neposilejte)( mi)? (sms|esemesky|zpravy na whatsapp|na whatsapp|whatsapp|e-?maily?)",
                         r"nechci (sms|e-?maily?|whatsapp)"]),
    ("wrong_person", [r"^\s*9\s*$", r"\bomyl", r"spatne cislo", r"spatny (kontakt|clovek|e-?mail)", r"nejsem (to )?(ja|on|ona|adresat)",
                      r"to nejsem ja", r"neznam (ho|ji|toho|tu|takov)", r"nikoho takoveho", r"spletli jste se",
                      r"to neni moje (cislo|telefon)", r"toto cislo (mam|patri)"]),
    ("vulnerable", [r"nemocnic", r"\bnemoc", r"nemocn[ya]\b", r"rakovin", r"onkolog", r"chemoterap", r"\boperac",
                    r"zemrel", r"zemrela", r"umrel", r"umrela", r"pohreb", r"ovdovel", r"\binvalid", r"deprese",
                    r"zoufal", r"nevim (co|jak) dal", r"nemam (ani )?na jidlo", r"nemam z ceho zit", r"nemam co jist",
                    r"sebevra", r"nechci (uz )?zit", r"\bpecuji o", r"tezk[aeyou] (zivotni )?situac"]),
    ("dispute", [r"nedluzim", r"neni (to )?muj (dluh|uver)", r"nikdy jsem si (nic )?nepujc", r"nesjednal", r"nepodepsal",
                 r"nesouhlasim", r"reklamac", r"rozporuj", r"uz (jsem )?(to )?(zaplatil|uhradil|splatil)", r"uz je (to )?zaplaceno",
                 r"\bpodvod", r"zneuzit", r"spatna castka", r"castka nesedi", r"\badvokat", r"\bpravnik", r"vratil(a)? jsem (to|telefon|zbozi)"]),
    ("want_refi", [r"refinanc", r"konsolid", r"\bslouc", r"\bspojit (je|vse|to|pujcky|uvery)", r"(sloucit|spojit|slouceni|spojeni).{0,20}(pujck|uver|dluh|splat)", r"jednu splatku",
                   r"jeden uver"]),
    ("need_plan", [r"^\s*2\s*$", r"splatk", r"rozlozit", r"rozdelit", r"po castech", r"\bodklad", r"odlozit", r"posunout",
                   r"pockat", r"najednou (ne|nemohu|nemuzu|to nedam)", r"(nemohu|nemuzu|nezvladnu).{0,20}najednou"]),
    ("cannot_pay", [r"nemam (ted )?(penize|na to|z ceho|prachy)", r"(nemuzu|nemohu|nedokazu) (to )?(zaplatit|platit|splacet)",
                    r"\bnezaplatim", r"nemam praci", r"prisel jsem o praci", r"prisla jsem o praci", r"nezamestnan",
                    r"jsem bez prace"]),
    ("callback", [r"^\s*3\s*$", r"\bzavolej", r"(?<!ne)volejte mi", r"ozvete se", r"(chci|muzu) mluvit s", r"\boperator",
                  r"\bclovek", r"s (nekym|clovekem)"]),
    ("will_pay", [r"^\s*1\s*$", r"(?<!ne)zaplatim", r"(?<!ne)zaplatime", r"(?<!ne)uhradim", r"(?<!ne)splatim", r"(?<!ne)doplatim",
                  r"(?<!ne)poslu (to|penize|platbu|castku|\d)", r"(?<!ne)posleme", r"platbu (poslu|odeslu|provedu)",
                  r"(?<!ne)zaplatit (dnes|zitra|v |ve |do |hned)", r"hned (to )?zaplat", r"jdu (to )?zaplatit"]),
]
QUESTION = re.compile(r"\?|\b(kolik|kde|kdy|jak|proc|kdo|odkud|cislo uctu|ucet)\b")
WHY = {"question": "dotaz dlužníka – předáno operátorovi", "unclear": "odpovědi nerozumíme – předáno operátorovi"}


# ---------- deterministic extraction: promise date and amount from Czech text ----------
def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


WEEKDAYS = {"pondel": 0, "uter": 1, "stred": 2, "ctvrt": 3, "patek": 4, "patk": 4, "sobot": 5, "nedel": 6}
MONTHS = {"ledn": 1, "unor": 2, "brez": 3, "dub": 4, "kvet": 5, "cervenc": 7, "cerv": 6, "srp": 8, "zar": 9,
          "rij": 10, "listopad": 11, "prosin": 12}
NUMWORDS = {"jeden": 1, "jednu": 1, "jedna": 1, "dva": 2, "dve": 2, "tri": 3, "ctyri": 4, "pet": 5, "sest": 6, "sedm": 7,
            "osm": 8, "devet": 9, "deset": 10, "patnact": 15, "dvacet": 20, "tricet": 30, "padesat": 50}

_DATE_NUM = re.compile(r"\b(\d{1,2})\s*\.\s*(\d{1,2})\s*\.(?:\s*(\d{4}))?")
_DATE_WORD = re.compile(r"\b(\d{1,2})\s*\.\s*(" + "|".join(MONTHS) + r")[a-z]*")
_IN_DAYS = re.compile(r"\bza (\d+|" + "|".join(NUMWORDS) + r") (dn[iy]|den|tyd[a-z]*|mesic[a-z]*)")
_THOUSANDS = re.compile(r"\b(\d+(?:[,.]\d+)?|" + "|".join(NUMWORDS) + r"|pul)\s*(tisic[a-z]*|tis\.?|k\b)")
_AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:[ .]\d{3})+|\d{2,7})(?:\s*(?:,-|,--|kc\b|korun\w*|czk\b))?(?![\d.]|\s*\.\s*\d)")


def _num(s: str) -> float:
    if s == "pul":
        return 0.5
    return float(NUMWORDS[s]) if s in NUMWORDS else float(s.replace(",", "."))


def when_of(text: str) -> str:
    """Relative description of a promised date: 'd:YYYY-MM-DD' (month-day: 'md:MM-DD'), 'wd:N', 'in:N', 'eom', or ''."""
    t = _norm(text)
    m = _DATE_NUM.search(t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"d:{int(y):04d}-{mo:02d}-{d:02d}" if y else f"md:{mo:02d}-{d:02d}"
    m = _DATE_WORD.search(t)
    if m:
        mo = next(v for k, v in MONTHS.items() if m.group(2).startswith(k))
        return f"md:{mo:02d}-{int(m.group(1)):02d}"
    if re.search(r"\bdnes\b|\bhned\b|\bihned\b", t):
        return "in:0"
    if re.search(r"\bpozitri\b", t):
        return "in:2"
    if re.search(r"\bzitra\b", t):
        return "in:1"
    if re.search(r"\bza tyden\b", t):
        return "in:7"
    if re.search(r"\bza mesic\b", t):
        return "in:30"
    m = _IN_DAYS.search(t)
    if m:
        n = int(_num(m.group(1)))
        unit = m.group(2)
        return f"in:{n * (7 if unit.startswith('tyd') else 30 if unit.startswith('mesic') else 1)}"
    if re.search(r"konce? (mesice|tohoto mesice)", t):
        return "eom"
    if re.search(r"pristi tyden", t):
        return "nextweek"
    for k, v in WEEKDAYS.items():
        if re.search(r"\b(v|ve|do|tento|tuto|pristi)?\s*" + k, t):
            return f"wd:{v}"
    if re.search(r"vyplat|vyplaty|vyplate", t):
        return "payday"
    return ""


def resolve(rel: str, today) -> str | None:
    """ISO date of a relative promise description (when_of) seen on `today`; None when unknown."""
    if not rel:
        return None
    t = today if isinstance(today, date) else date.fromisoformat(today)
    kind, _, v = rel.partition(":")
    if kind == "d":
        return v
    if kind == "md":
        mo, d = map(int, v.split("-"))
        try:
            cand = date(t.year, mo, d)
        except ValueError:
            return None
        return (cand if cand >= t else date(t.year + 1, mo, d)).isoformat()
    if kind == "in":
        return (t + timedelta(days=int(v))).isoformat()
    if kind == "wd":
        ahead = (int(v) - t.weekday()) % 7 or 7  # "v pátek" said on a Friday = next Friday
        return (t + timedelta(days=ahead)).isoformat()
    if kind == "nextweek":
        return (t + timedelta(days=7 - t.weekday())).isoformat()  # Monday of next week
    if kind == "eom":
        nxt = date(t.year + (t.month == 12), t.month % 12 + 1, 1)
        return (nxt - timedelta(days=1)).isoformat()
    if kind == "payday":  # Czech payday is usually around the 15th
        cand = date(t.year, t.month, 15)
        return (cand if cand > t else date(t.year + (t.month == 12), t.month % 12 + 1, 15)).isoformat()
    return None


def amount_of(text: str) -> int | None:
    """Amount in Kč mentioned in the reply: '5000', '5 000 Kč', '5.000,-', '2,5 tisíce', 'pět tisíc'; None if none."""
    t = _norm(text)
    t = _DATE_NUM.sub(" ", t)
    t = _DATE_WORD.sub(" ", t)
    t = _IN_DAYS.sub(" ", t)
    m = _THOUSANDS.search(t)
    if m:
        return int(round(_num(m.group(1)) * 1000))
    for m in _AMOUNT.finditer(t):
        n = int(re.sub(r"[ .]", "", m.group(1)))
        if n >= 50:
            return n
    return None


_NEG = r"(nepiste|neposilejte|nechci|stop|prestante|zadne)( mi)?( uz)?( zadne)?( zpravy)?( posilat| psat)?( na| pres)?\s*"
CHANNEL_WORDS = [("voice", r"nevolejte|prestante (mi )?volat|nechci (zadne )?(hovory|telefonaty)|stop hovor"),
                 ("sms", _NEG + r"(sms|esemes)"), ("whatsapp", _NEG + r"whatsapp"), ("email", _NEG + r"e-?mail")]


def channels_of(text: str) -> list:
    """Channels the person refuses ("nevolejte mi, pište SMS" → ["voice"])."""
    t = _norm(text)
    return [c for c, p in CHANNEL_WORDS if re.search(p, t)]


def extract(text: str) -> dict:
    """Structured fields from a reply ({} = none): promise_when (relative, see when_of), promise_amount (Kč),
    channels (for a channel opt-out), verification (birth date or 4 digits said for identity verification)."""
    if not text:
        return {}
    t = _norm(text)
    out = {}
    if re.search(r"(?<!ne)(zaplat|uhrad|splat|doplat|poslu|posleme|plat)", t):
        when = when_of(text)
        if when:
            out["promise_when"] = when
        amount = amount_of(text)
        if amount:
            out["promise_amount"] = amount
    ch = channels_of(text)
    if ch:
        out["channels"] = ch
    m = re.search(r"narozen[aey]?\s*(\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{4})", t)
    if m:
        out["verification"] = re.sub(r"\s", "", m.group(1))
    return out


LLM_USER = "Odpověď dlužníka: «{text}»"
LLM_SYSTEM = """Jsi asistent zákaznického týmu věřitele Finance Demo a.s. Klient dostal zprávu k smlouvě po splatnosti
a odpověděl. Tvým jediným úkolem je porozumět odpovědi. Nic neodpovídáš, nic nenavrhuješ, strategii nevolíš.

Vrať POUZE JSON: {"intent": "...", "when": "...", "confidence": "high|low", "why": "...",
                  "extra": {"promise_date": "...", "promise_amount": 0, "verified": false}}
intent:
- will_pay: slibuje zaplatit (případně kdy a kolik)
- need_plan: chce splátky, rozložení nebo odklad
- cannot_pay: teď nemůže platit, bez známek tísně
- want_refi: chce refinancování nebo sloučení úvěrů
- dispute: nesouhlasí s pohledávkou, tvrdí, že už zaplatil, mluví o podvodu nebo právníkovi
- vulnerable: nemoc, úmrtí v rodině, těžká životní situace, zoufalství, ztráta práce s tísní
- wrong_person: není adresát, špatné číslo
- opt_out: nechce žádný další kontakt
- channel_opt_out: nechce jen jeden kanál (např. nevolejte mi, nepište SMS)
- callback: chce mluvit s člověkem nebo zavolat
- question: ptá se na něco
- unclear: nedá se poznat
when: časový údaj z odpovědi tak, jak zazněl (např. "v pátek", "15. 11."), jinak "".
extra.promise_date: datum slibu tak, jak zaznělo (např. "v pátek"), jinak "".
extra.promise_amount: slíbená částka v Kč jako číslo, jinak 0.
extra.verified: true jen když odpověď obsahuje datum narození nebo poslední 4 číslice smlouvy; samotné ověření
provede systém, ty ho jen označíš.
why: jedna krátká česká věta pro operátora.
Při jakékoli známce tísně, nemoci, úmrtí nebo zranitelnosti zvol vulnerable. Při pochybnosti zvol unclear;
odpověď pak vyřeší člověk."""

# ---------- phone call (ConversationRelay, backend/voice_ai.py): only these approved sentences are ever said ----------
CREDITOR = "Finance Demo a.s."
GREETING = (f"Dobrý den, tady automatický hlasový asistent společnosti {CREDITOR}, jsem automat, ne člověk. "
            "Volám ve věci Vaší smlouvy. Podrobnosti po telefonu nesděluji, najdete je po ověření totožnosti "
            "na zabezpečené stránce z naší zprávy. Řekněte prosím, jestli chcete zaplatit, potřebujete splátky, "
            "nebo chcete mluvit s kolegou. Pokud nejste adresát hovoru, řekněte omyl.")
FAQ = [
    (("kolik", "castk", "dluzim", "vyse"), "Částku po telefonu z důvodu ochrany Vašich údajů nesděluji. Najdete ji po ověření totožnosti na zabezpečené stránce z naší zprávy."),
    (("kdo jste", "kdo vola", "odkud", "jak jste", "cislo mate"), f"Jsem automatický asistent společnosti {CREDITOR}, kontakt máme z Vaší smlouvy."),
    (("ucet", "uctu", "jak zaplat", "jak mam zaplatit", "kam"), "Zaplatit můžete na zabezpečené stránce z naší zprávy, po ověření tam najdete i platební údaje."),
    (("podvod", "pravda", "overit", "skutecne"), f"Nikdy po Vás nebudeme chtít heslo ani PIN. Pravost zprávy si můžete ověřit na zákaznické lince společnosti {CREDITOR}"),
    (("co se stane", "nezaplatim", "nasledky"), "Pokud se teď nedomluvíme, ozve se Vám kolega z našeho týmu, aby s Vámi hledal řešení. Smluvní podmínky najdete ve své smlouvě."),
    (("automat", "robot", "clovek"), "Ano, jsem automatický asistent. Kdykoli Vás mohu předat kolegovi."),
]
ASK_AGAIN = "Chcete zaplatit, potřebujete splátky nebo odklad, nebo chcete mluvit s kolegou?"
NOT_UNDERSTOOD = "Omlouvám se, nerozuměl jsem. Chcete zaplatit, potřebujete splátky, nebo chcete mluvit s kolegou?"
CLOSING = {
    "will_pay": "Děkuji. Termín a způsob platby si zvolíte po ověření na zabezpečené stránce z naší zprávy. Na shledanou.",
    "need_plan": "Děkuji. Možnosti splátek a odkladu najdete po ověření na zabezpečené stránce z naší zprávy. Na shledanou.",
    "cannot_pay": "Rozumím, děkuji. Možnosti splátek a odkladu najdete po ověření na zabezpečené stránce z naší zprávy. Na shledanou.",
    "want_refi": "Děkuji. Ukázku sloučení do jedné splátky najdete po ověření na zabezpečené stránce z naší zprávy. Na shledanou.",
    "dispute": "Děkuji. Vaši námitku předám kolegovi, který ji prověří. Do té doby Vás automaticky kontaktovat nebudeme. Na shledanou.",
    "vulnerable": "Děkuji za informaci. Automatické hovory zastavím a ozve se Vám kolega, který s Vámi v klidu probere možnosti. Na shledanou.",
    "wrong_person": "Omlouvám se za obtěžování. Toto číslo si označíme a už Vám volat nebudeme. Na shledanou.",
    "opt_out": "Rozumím. Další automatické zprávy ani hovory od nás nedostanete. Na shledanou.",
    "channel_opt_out": "Rozumím. Tímto způsobem Vás už kontaktovat nebudeme. Na shledanou.",
    "callback": "Děkuji. Ozve se Vám kolega z našeho týmu v pracovní dny mezi 8 a 20 hodinou. Na shledanou.",
    "handoff": "Děkuji. Předám to kolegovi z našeho týmu, který se Vám ozve. Na shledanou.",
}
MAX_UNCLEAR = 2
DTMF = {"1": "zaplatim", "2": "potrebuji splatky", "3": "zavolejte mi", "9": "omyl, nejsem adresat", "0": "nevolejte mi"}

# ---------- ElevenLabs voice agent (backend/agent_call.py, scripts/elevenlabs_agent.py) ----------
DECISIONS = {"will_pay", "need_plan", "cannot_pay", "want_refi", "dispute", "vulnerable", "wrong_person", "opt_out",
             "channel_opt_out", "callback", "unclear"}
AGENT_NAME = "AI vymáhání – hlasový asistent Finance Demo a.s."
AGENT_DECISIONS = {
    "will_pay": "ověřený klient slíbil zaplatit",
    "need_plan": "chce splátky nebo odklad",
    "cannot_pay": "teď nemůže platit, bez známek tísně",
    "want_refi": "má zájem o sloučení nebo refinancování",
    "dispute": "nesouhlasí s pohledávkou nebo tvrdí, že už zaplatil",
    "vulnerable": "zmínil nemoc, úmrtí, tíseň nebo jinou těžkou situaci",
    "wrong_person": "volaný není adresát hovoru",
    "opt_out": "nechce žádný další kontakt",
    "channel_opt_out": "nechce jen telefonáty",
    "callback": "chce mluvit s člověkem nebo má otázku bez schválené odpovědi",
    "unclear": "nepodařilo se zjistit",
}
AGENT_WHEN = "Kdy se klientovi hodí telefonát kolegy (v pracovní dny 8 až 20 h), jinak prázdné."
AGENT_DATA = {
    "verification": "Údaj, který klient řekl pro ověření totožnosti (datum narození nebo poslední 4 číslice smlouvy), jinak prázdné. Systém ho porovná se záznamem.",
    "promise_date": "Datum slíbené platby tak, jak ho klient řekl (např. v pátek, 15. listopadu), jinak prázdné.",
    "promise_amount": "Slíbená částka v Kč jako číslo, jinak prázdné.",
}
VERIFY_ASK = "Než budeme pokračovat, potřebuji ověřit, že mluvím se správnou osobou. Řekněte mi prosím své datum narození, nebo poslední čtyři číslice čísla smlouvy."
VERIFY_THANKS = "Děkuji. Údaj ověří systém. Podrobnosti Vám pak ukáže zabezpečená stránka."
PROMISE_ASK = "Kdy a jakou částku plánujete zaplatit?"
PROMISE_THANKS = "Děkuji, zapisuji si termín a částku platby. Kdyby se něco změnilo, dejte nám prosím vědět."


def approved_sentences() -> list:
    """Every sentence the assistant may say (tests/test_compliance.py checks them for forbidden words)."""
    return [GREETING, ASK_AGAIN, NOT_UNDERSTOOD, VERIFY_ASK, VERIFY_THANKS, PROMISE_ASK, PROMISE_THANKS,
            *[a for _, a in FAQ], *CLOSING.values()]


def agent_prompt() -> str:
    faq = "\n".join(f"- {answer}" for _, answer in FAQ)
    closing = "\n".join(f"- {k}: {v}" for k, v in CLOSING.items())
    return f"""Jsi automatický hlasový asistent zákaznického týmu společnosti {CREDITOR} (fiktivní věřitel této ukázky).
Voláš klientovi ve věci jeho smlouvy, která je po splatnosti. Mluvíš česky, klidně, zdvořile a věcně, vykáš.

PRAVIDLA, která nesmíš porušit:
1. Hned na začátku se představíš: kdo volá (společnost {CREDITOR}) a že jsi automatický asistent, ne člověk.
   Úvodní věta to už říká: "{GREETING}"
2. Nikdy neříkáš částku, počet dní po splatnosti, číslo smlouvy ani jiný údaj o závazku. Neznáš je a nedomýšlíš je.
   Podrobnosti jsou jen na zabezpečené stránce po ověření totožnosti.
3. Než se klienta zeptáš na termín a částku platby, ověř totožnost: "{VERIFY_ASK}" Odpověď zapiš do pole
   verification a řekni "{VERIFY_THANKS}" Údaj sám nehodnotíš, ověří ho systém.
4. Nevyhrožuješ, nestrašíš a neuvádíš žádné následky (žádné vymáhací, soudní ani trestní kroky, žádné kontaktování
   zaměstnavatele, rodiny ani sousedů). Nikoho nezahanbuješ, netlačíš na něj a nenaléháš. Neříkáš nic nepravdivého.
5. Říkáš jen věty z tohoto zadání, doslova nebo jen s malou úpravou slovosledu. Na otázku bez schválené odpovědi
   řekni: "{CLOSING['handoff']}" a ukonči hovor.
6. Strategii ani nabídku nevybíráš. Splátky, odklad i sloučení jsou na zabezpečené stránce.
7. Volá se jen v pracovní dny mezi 8 a 20 hodinou. Pokud klient řekne, že se mu to teď nehodí, nabídni zavolání kolegy.

Postup:
- Když volaný řekne, že není adresát nebo že jde o omyl: "{CLOSING['wrong_person']}" a ukonči hovor. Nic dalšího neříkej.
- Když zmíní nemoc, úmrtí v rodině, ztrátu práce s tísní nebo jinou těžkou situaci: "{CLOSING['vulnerable']}" a ukonči hovor.
- Když nesouhlasí s pohledávkou nebo tvrdí, že už zaplatil: "{CLOSING['dispute']}" a ukonči hovor.
- Když nechce žádný další kontakt: "{CLOSING['opt_out']}" a ukonči hovor.
- Když nechce jen telefonáty: "{CLOSING['channel_opt_out']}" a ukonči hovor.
- Když chce zaplatit: ověř totožnost (pravidlo 3), pak se zeptej "{PROMISE_ASK}" Termín zapiš do promise_date,
  částku do promise_amount, řekni "{PROMISE_THANKS}" a pak "{CLOSING['will_pay']}" a ukonči hovor.
- Když potřebuje splátky nebo odklad: "{CLOSING['need_plan']}" a ukonči hovor.
- Když teď nemůže platit: "{CLOSING['cannot_pay']}" a ukonči hovor.
- Když chce sloučit úvěry nebo refinancovat: "{CLOSING['want_refi']}" a ukonči hovor.
- Když chce mluvit s člověkem: "{CLOSING['callback']}" a ukonči hovor.
- Na otázky odpovídej jen těmito větami a pak se znovu zeptej "{ASK_AGAIN}"
{faq}
- Když nerozumíš: "{NOT_UNDERSTOOD}" Po druhém nedorozumění řekni "{CLOSING['handoff']}" a ukonči hovor.

Schválené závěrečné věty:
{closing}
"""
