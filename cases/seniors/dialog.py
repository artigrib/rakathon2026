"""Jsem v pořádku: how a senior's answer to the check-in call is understood and what the assistant may say.

Intents map to journey events: ok | need_items | low_mood | health_problem | emergency | callback | opt_out | question | unclear.
Safety first: emergency (fall, cannot breathe, chest pain, thoughts of not wanting to live) is checked before
anything else, the assistant tells the senior to call 155 and a person takes over at once. The assistant never
gives medical advice. Anything not clearly understood goes to a person (operator calls back)."""
import json
import re
import unicodedata
from pathlib import Path

INTENTS = ["ok", "need_items", "low_mood", "health_problem", "emergency", "callback", "opt_out", "question", "unclear"]

# Reply intents → journey events (question / unclear: the operator calls back).
INTENT_EVENT = {"ok": "ok", "need_items": "need_items", "low_mood": "low_mood", "health_problem": "health_problem",
                "emergency": "emergency", "callback": "callback", "opt_out": "opt_out", "question": "callback",
                "unclear": "callback"}

# Journey stage for each intent.
STAGE = {"ok": "ok", "need_items": "needs_help", "low_mood": "low_mood", "health_problem": "escalated",
         "emergency": "escalated", "callback": "callback", "opt_out": "declined", "question": "callback",
         "unclear": "callback"}

# Needs vocabulary (shared with the web app: items.json is served as /app/content/items.json).
ITEMS = json.loads(Path(__file__).with_name("items.json").read_text(encoding="utf-8"))["items"]  # key → {label, patterns}
_ITEM_RE = {k: [re.compile(p) for p in v["patterns"]] for k, v in ITEMS.items()}

# (intent, patterns) in priority order, first match wins. Patterns run on lower-case ASCII text (no diacritics).
RULES = [
    ("emergency", [r"\b155\b", r"zachrank", r"sanitk", r"nemuzu (vstat|vstavat|dychat|se zvednout|se hnout)", r"nemohu (vstat|dychat)",
                   r"lezim na (zemi|podlaze)", r"upadl[a]? jsem a nemuzu", r"bolest na hrudi", r"boli me na hrudi", r"svira me na hrudi",
                   r"nemuzu popadnout dech", r"\bhori\b", r"krvacim", r"omdlel", r"nechce se mi zit", r"nechce (se mi )?zit", r"skoncit se zivotem",
                   r"zabit se", r"^\s*pomoc\b", r"pomozte mi rychle"]),
    ("opt_out", [r"\bstop\b", r"nevolejte", r"\bodhlas", r"nekontaktuj", r"neobtezujte", r"nechci (uz )?(zadne )?hovory",
                 r"nechci, ?abyste mi volal", r"nechci abyste mi volal"]),
    ("health_problem", [r"\bboli\b", r"\bbolest", r"nemocn", r"horeck", r"teplot", r"zavrat", r"toci se mi hlava", r"\bupadl",
                        r"kasl", r"nevolno", r"zvracim", r"otekl", r"je mi zle", r"neni mi dobre", r"hur se mi dycha",
                        r"spatne se mi dycha", r"\bprujem"]),
    ("callback", [r"ted nemuzu", r"ted nemohu", r"nehodi se", r"zavolejte (mi )?(pozdeji|zitra|odpoledne|vecer|rano|jindy|za)",
                  r"volejte (az|pozdeji)", r"pozdeji", r"jsem u (lekare|doktora)", r"nemam ted cas"]),
    ("need_items", [r"^\s*2\s*$", r"potreb(uji|uju|ovala bych|oval bych) (pomoc|pomoct)", r"dosl[ay]? mi", r"dosel mi"]
     + [p for k in ITEMS for p in ITEMS[k]["patterns"] if k != "navsteva"]),
    ("low_mood", [r"smutn", r"smutno", r"osamel", r"sam[a]? doma", r"nikdo (mi|me|za mnou)", r"nikoho nemam", r"nic moc",
                  r"nema to smysl", r"nechce se mi", r"spatna nalada", r"stysk", r"brecim", r"deprese", r"nemam (na nic )?silu",
                  r"nic me nebavi", r"je mi tezko", r"\bnavstev", r"popovidat"]),
    ("ok", [r"^\s*1\s*$", r"v poradku", r"\bdobre\b", r"\bfajn\b", r"\bok\b", r"nic nepotrebuj", r"\bano\b", r"jde to",
            r"ujde to", r"vyborn", r"skvel", r"da se to", r"\bcajk"]),
]
QUESTION = re.compile(r"\?|\b(kdo jste|kdo vola|odkud|proc|kolik|kdy zase|jak dlouho)\b")
WHY = {"question": "dotaz seniora", "unclear": "odpovědi nerozumíme, předáno operátorovi"}

# Mood words → 1 (very bad) … 5 (very good), the lowest match wins (a careful reading); health words → health_flag.
VOCAB = json.loads(Path(__file__).with_name("items.json").read_text(encoding="utf-8"))
MOOD = sorted((int(k), v) for k, v in VOCAB["mood"].items())
HEALTH = VOCAB["health"]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def items_of(text: str) -> list:
    """Item keys (items.json) named in a free text, in vocabulary order."""
    t = norm(text)
    return [k for k, pats in _ITEM_RE.items() if any(p.search(t) for p in pats)]


def mood_of(text: str):
    t = norm(text)
    found = [m for m, pats in MOOD if any(re.search(p, t) for p in pats)]
    return min(found) if found else None


def extract(text: str) -> dict:
    """Deterministic fields from a reply: mood 1–5, items [keys of items.json], health_flag. {} = nothing found."""
    if not text or not text.strip():
        return {}
    out = {}
    mood = mood_of(text)
    if mood:
        out["mood"] = mood
    items = items_of(text)
    if items:
        out["items"] = items
    if any(re.search(p, norm(text)) for p in HEALTH):
        out["health_flag"] = True
    return out


LLM_USER = "Odpověď seniora: «{text}»"
LLM_SYSTEM = """Jsi asistent služby Jsem v pořádku. Osamělému seniorovi pravidelně voláme, abychom věděli, že je v pořádku,
jakou má náladu a zda něco nepotřebuje. Senior odpověděl. Urči, co odpověď znamená.

Vrať POUZE JSON: {"intent": "...", "when": "...", "confidence": "high|low", "why": "...", "extra": {"mood": 1-5 nebo null, "items": [...], "health_flag": true|false}}
intent:
- ok: je v pořádku, nic nepotřebuje
- need_items: potřebuje praktickou pomoc (nákup, léky z lékárny, obědy, dopravu, úklid, topení, prádlo, opravu)
- low_mood: je smutný, osamělý, bez nálady, chybí mu společnost
- health_problem: zmiňuje zdravotní potíž (bolest, pád, nevolnost, horečku), ale nejde o akutní ohrožení
- emergency: akutní ohrožení života nebo zdraví (leží na zemi a nemůže vstát, nemůže dýchat, bolest na hrudi, krvácí, hoří, nechce žít)
- callback: teď nemůže mluvit, chce zavolat jindy
- opt_out: nechce žádné další hovory ani zprávy
- question: ptá se na něco (kdo volá, proč, kolik to stojí)
- unclear: nedá se poznat
when: časový údaj, pokud nějaký je (např. "odpoledne", "zítra"), jinak "".
extra.mood: nálada 1 (velmi špatná) až 5 (výborná), null když se nedá poznat.
extra.items: seznam klíčů z: nakup, leky, obed, doprava, uklid, otop, pradlo, oprava, navsteva, jine. Prázdný seznam, když nic.
extra.health_flag: true, když zmínil jakoukoli zdravotní potíž.
why: jedna krátká česká věta pro sociálního pracovníka.
Při jakékoli známce ohrožení zvol emergency. Při pochybnosti zvol unclear, odpověď pak vyřeší člověk. Nikdy neradíš zdravotně."""

# ---------- phone call (ConversationRelay, backend/voice_ai.py): only these approved sentences are ever said ----------
GREETING = ("Dobrý den, tady Jsem v pořádku, pravidelný hovor od Vaší sociální služby. Jsem automatický asistent. "
            "Jak se dnes máte? Je všechno v pořádku, nebo něco potřebujete?")

FAQ = [
    (("kdo jste", "kdo vola", "odkud", "kdo to je"), "Volám ze služby Jsem v pořádku, kterou pro Vás zajišťuje Vaše sociální služba. Jsem automatický asistent."),
    (("kolik", "stoji", "plati", "zdarma", "penize"), "Hovory jsou pro Vás zdarma."),
    (("proc", "k cemu"), "Voláme pravidelně, abychom věděli, že jste v pořádku a jestli něco nepotřebujete."),
    (("kdy zase", "pristi", "zase zavolate"), "Zavoláme Vám znovu podle domluveného rozvrhu."),
]
ASK_AGAIN = "Jak se dnes máte? Je všechno v pořádku, nebo něco potřebujete?"
NOT_UNDERSTOOD = "Promiňte, nerozuměla jsem. Je u Vás všechno v pořádku, nebo něco potřebujete?"
EMERGENCY = "Prosím zavěste a hned volejte 155. Zároveň to předávám pracovníkovi, který se Vám ozve."
# intent → closing sentence; "handoff" = a person takes over.
CLOSING = {
    "ok": "To ráda slyším. Zavolám zase příště. Na shledanou.",
    "need_items": "Děkuji. Předám to sociální službě a ozveme se Vám. Na shledanou.",
    "low_mood": "Děkuji, že jste mi to řekli. Brzy se Vám ozve někdo z naší služby. Na shledanou.",
    "health_problem": "Děkuji. Předám to pracovníkovi, který se Vám ozve. Pokud se Vám přitíží, volejte hned 155. Na shledanou.",
    "emergency": EMERGENCY,
    "callback": "Dobře, zavolám Vám později. Na shledanou.",
    "opt_out": "Rozumím, další hovory Vám volat nebudeme. Na shledanou.",
    "handoff": "Děkuji. Předám to pracovníkovi naší služby, který se Vám ozve. Na shledanou.",
}
MAX_UNCLEAR = 2
DTMF = {"1": "v pořádku", "2": "potřebuji pomoc"}  # keys in a call → words for the reply rules

# ---------- ElevenLabs voice agent (backend/agent_call.py, scripts/elevenlabs_agent.py) ----------
DECISIONS = {"ok", "need_items", "low_mood", "health_problem", "emergency", "callback", "opt_out", "unclear"}
AGENT_NAME = "Jsem v pořádku, pravidelný hovor se seniorem"
AGENT_DECISIONS = {
    "ok": "je v pořádku a nic nepotřebuje",
    "need_items": "potřebuje praktickou pomoc (nákup, léky, obědy, dopravu, úklid, topení, prádlo, opravu)",
    "low_mood": "je smutný nebo osamělý, chce, aby se někdo ozval",
    "health_problem": "zmínil zdravotní potíž bez akutního ohrožení",
    "emergency": "akutní ohrožení (leží na zemi, nemůže dýchat, bolest na hrudi, krvácí, nechce žít)",
    "callback": "teď nemůže mluvit, máme zavolat jindy",
    "opt_out": "nechce další hovory",
    "unclear": "nepodařilo se zjistit, jak na tom je",
}
AGENT_WHEN = "Kdy se seniorovi hodí zavolat znovu (dopoledne, odpoledne, konkrétní den), jinak prázdné."
AGENT_DATA = {
    "mood": "Nálada seniora jako číslo 1 (velmi špatná) až 5 (výborná). Prázdné, když se nedá poznat.",
    "items": "Co senior potřebuje, klíče oddělené čárkou: nakup, leky, obed, doprava, uklid, otop, pradlo, oprava, navsteva, jine.",
    "health_flag": "ano, pokud senior zmínil jakoukoli zdravotní potíž, jinak ne.",
}

# ---------- recap at the end of a call: say back what was understood, ask to confirm (agent + scripted call) ----------
# Never after an emergency (155 + a person at once), an opt-out or "call me later".
RECAP_ASK = "Je to tak?"
RECAP_FIX = "Co mám opravit?"
RECAP = {
    "ok": "Rozuměla jsem, že jste v pořádku a nic nepotřebujete.",
    "need_items": "Rozuměla jsem, že potřebujete {items}.",
    "need_help": "Rozuměla jsem, že potřebujete pomoc.",
    "low_mood": "Rozuměla jsem, že je Vám smutno a chcete, aby se Vám někdo ozval.",
    "health_problem": "Rozuměla jsem, že Vám není dobře a má se Vám ozvat pracovník.",
}
RECAP_ALSO = "Potřebujete také {items}."


def _and(words: list) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " a " + words[-1]


def recap(intent: str, extra: dict) -> str:
    """Deterministic recap of a scripted call (backend/app.py), e.g. "Rozuměla jsem, že potřebujete nákup a léky
    z lékárny. Je to tak?"; '' = no recap (emergency, opt-out, callback, unclear …)."""
    extra = extra or {}
    items = extra.get("items") or []
    if isinstance(items, str):
        items = [x.strip() for x in items.split(",")]
    labels = [ITEMS[k]["label"] for k in items if k in ITEMS and k != "navsteva"]
    if intent == "need_items":
        s = RECAP["need_items"].format(items=_and(labels)) if labels else RECAP["need_help"]
    elif intent == "ok":
        s = RECAP["ok"]
    elif intent in ("low_mood", "health_problem"):
        s = RECAP[intent] + (" " + RECAP_ALSO.format(items=_and(labels)) if labels else "")
    else:
        return ""
    return f"{s} {RECAP_ASK}"


def agent_prompt() -> str:
    faq = "\n".join(f"- {answer}" for _, answer in FAQ)
    closing = "\n".join(f"- {k}: {v}" for k, v in CLOSING.items())
    return f"""Jsi hlasový asistent služby Jsem v pořádku. Voláš osamělému seniorovi v pravidelném hovoru, který mu
zajišťuje jeho sociální služba. Chceš vědět, jestli je v pořádku, jakou má náladu a jestli něco nepotřebuje.
Mluvíš česky, vlídně, pomalu a krátce, vykáš. Nech seniora domluvit a nespěchej.

PRAVIDLA, která nesmíš porušit:
1. Říkáš jen věty z tohoto zadání, doslova nebo jen s malou úpravou slovosledu. Nikdy neradíš zdravotně,
   nedoporučuješ léky ani léčbu a nehodnotíš zdravotní stav.
2. Když senior popíše ohrožení (leží na zemi a nemůže vstát, nemůže dýchat, bolí ho na hrudi, krvácí, hoří,
   nechce žít), řekni hned: "{EMERGENCY}" a ukonči hovor.
3. Na otázku, na kterou tu nemáš schválenou odpověď, řekni: "{CLOSING['handoff']}" a ukonči hovor.
4. Nesděluj žádné údaje o seniorovi a na nic osobního se neptej.
5. Pokud senior nechce další hovory, řekni "{CLOSING['opt_out']}" a ukonči hovor.

Postup:
- Úvodní věta už zazněla: "{GREETING}"
- Když je v pořádku: udělej shrnutí (níže), pak "{CLOSING['ok']}" a ukonči hovor.
- Když něco potřebuje: zeptej se "Co přesně potřebujete? Nákup, léky z lékárny, obědy, dopravu, nebo něco jiného?"
  Pak udělej shrnutí, řekni "{CLOSING['need_items']}" a ukonči hovor.
- Když je smutný nebo osamělý: udělej shrnutí, pak "{CLOSING['low_mood']}" a ukonči hovor.
- Když zmíní zdravotní potíž bez ohrožení: udělej shrnutí, pak "{CLOSING['health_problem']}" a ukonči hovor.
- Když teď nemůže mluvit: "{CLOSING['callback']}" a ukonči hovor.
- Když se na něco ptá, použij jen tyto odpovědi a potom se znovu zeptej: "{ASK_AGAIN}"
{faq}
- Když nerozumíš: "{NOT_UNDERSTOOD}" Po druhém nedorozumění řekni "{CLOSING['handoff']}" a ukonči hovor.

Shrnutí před závěrečnou větou:
- Jednou nebo dvěma krátkými větami řekni, co jsi pochopila: jak se má, jakou má náladu, co přesně potřebuje
  a jestli zmínil zdravotní potíž. Začni "Rozuměla jsem, že" a řekni jen to, co senior sám řekl, nic nepřidávej
  a nic nehodnoť. Pak se zeptej "{RECAP_ASK}" Příklady:
  - "{RECAP['ok']} {RECAP_ASK}"
  - "{RECAP['need_items'].format(items='nákup a léky z lékárny')} {RECAP_ASK}"
  - "{RECAP['low_mood']} {RECAP_ASK}"
  - "{RECAP['health_problem']} {RECAP_ASK}"
- Když souhlasí nebo neodpoví, řekni závěrečnou větu a ukonči hovor.
- Když řekne, že to tak není, zeptej se "{RECAP_FIX}" Opravu si zapamatuj, zopakuj jednou krátce opravené shrnutí
  bez další otázky a řekni závěrečnou větu podle opravy.
- Při ohrožení shrnutí nikdy nedělej: hned "{EMERGENCY}" a ukonči hovor. Ani když nechce další hovory nebo teď
  nemůže mluvit, shrnutí nedělej.
- Do pole recap_confirmed zapiš ano, když shrnutí potvrdil, ne, když ho opravil.

Schválené závěrečné věty:
{closing}
"""
