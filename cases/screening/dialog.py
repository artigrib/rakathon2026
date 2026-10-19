"""Screening (Plíce včas): how a patient's reply is understood and what the phone assistant may say.

Intents map 1:1 to journey events: interested | booked | callback | not_now | declined | opt_out | question | unclear.
declined = "not interested" (doctor: first refusal → other channel + motivation, second → stop);
opt_out = explicit "do not contact me" → stop immediately. Anything not clearly understood goes to the nurse."""
import re

INTENTS = ["interested", "booked", "callback", "not_now", "declined", "opt_out", "question", "unclear"]

# Reply intents → journey events (question / unclear: the nurse calls back).
INTENT_EVENT = {"interested": "interested", "booked": "booked", "callback": "callback", "not_now": "not_now",
                "declined": "declined", "opt_out": "opt_out", "question": "callback", "unclear": "callback"}

# Journey stage for each intent; question/unclear land with the nurse as a callback task.
STAGE = {"interested": "interested", "booked": "booked", "callback": "callback", "not_now": "not_now",
         "declined": "declined", "opt_out": "declined", "question": "callback", "unclear": "callback"}

# (intent, patterns) in priority order – first match wins. Patterns run on lower-case ASCII text (no diacritics).
RULES = [
    ("opt_out", [r"\bstop\b", r"\bodhlas", r"nekontaktuj", r"nepiste", r"nevolejte", r"neobtezujte"]),
    ("declined", [r"nechci\b", r"nemam zajem", r"\bnezajem"]),
    ("booked", [r"objednan", r"objednal", r"mam termin", r"uz jsem (byl|byla|u)", r"jsem objednany"]),
    ("callback", [r"zavolej", r"zavolat", r"volejte", r"ozvete se", r"\bzavolani"]),
    ("not_now", [r"\bted ne\b", r"\bnyni ne\b", r"momentalne ne", r"pozdeji", r"\baz po\b", r"\baz v\b", r"pristi (tyden|mesic|rok)", r"\bpo (vanocich|novem roce|dovolene)"]),
    ("interested", [r"^\s*1\s*$", r"\bano\b", r"mam zajem", r"\bzajem\b", r"\bchci\b", r"\brad[ae]?\b", r"\bdobre\b", r"\bok\b", r"souhlas"]),
    ("declined", [r"^\s*2\s*$", r"^\s*ne\b"]),
]
QUESTION = re.compile(r"\?|\b(kolik|kde|kdy|jak|proc|bolí|boli|plati|zdarma)\b")
WHY = {"question": "dotaz pacienta", "unclear": "odpovědi nerozumíme – předáno sestře"}


def extract(text: str) -> dict:
    """Structured fields from a reply (none in screening)."""
    return {}


LLM_USER = "Odpověď pacienta: «{text}»"
LLM_SYSTEM = """Jsi asistent ordinace praktického lékaře v programu Prevence pro plíce (screening rakoviny plic).
Pacient dostal pozvánku na bezplatné preventivní vyšetření plic a odpověděl. Urči, co pacient chce.

Vrať POUZE JSON: {"intent": "...", "when": "...", "confidence": "high|low", "why": "..."}
intent:
- interested: má zájem, souhlasí, chce vyšetření
- booked: už je objednaný nebo vyšetření absolvoval
- callback: chce, aby mu někdo zavolal (případně kdy)
- not_now: teď ne / později / po nějaké události
- declined: nemá zájem
- opt_out: nechce žádné další zprávy ani hovory
- question: ptá se na něco (cena, bolest, kde, jak dlouho…)
- unclear: nedá se poznat, nebo jde o citlivou situaci (úmrtí, špatné číslo, rozčilení, zdravotní potíže)
when: časový údaj z odpovědi, pokud nějaký je (např. "po Vánocích", "odpoledne"), jinak "".
why: jedna krátká česká věta pro sestru, proč jsi tak rozhodl.
Při pochybnosti zvol unclear – odpověď pak vyřeší sestra. Nikdy neradíš zdravotně."""

# ---------- phone call (ConversationRelay, backend/voice_ai.py): only these approved sentences are ever said ----------
GREETING = ("Dobrý den, tady hlasový asistent ordinace Vašeho praktického lékaře. Jsem automatický asistent, nejsem lékař. "
            "Volám kvůli bezplatnému preventivnímu vyšetření plic pro lidi, kteří kouří nebo dříve kouřili. "
            "Chcete, aby se Vám ozvala sestra z ordinace?")

# Approved answers to common questions (keyword → sentence). Anything else → the nurse calls back.
FAQ = [
    (("kolik", "stoji", "plati", "zdarma", "penize", "cena"), "Vyšetření je bezplatné, hradí ho zdravotní pojišťovna."),
    (("boli", "bolest", "nepříjem", "neprijem"), "Vyšetření nebolí. Ležíte na lůžku a samotné snímkování trvá několik minut."),
    (("zareni", "zarenim", "davk", "radiac"), "Používá se nízkodávkové CT, tedy CT s nízkou dávkou záření."),
    (("kde", "kam"), "Vyšetření domlouvá Váš praktický lékař nebo plicní lékař, sestra Vám vše vysvětlí."),
    (("proc", "k cemu", "smysl"), "Vyšetření pomáhá včas odhalit onemocnění plic, kdy je léčba nejúspěšnější."),
    (("dlouho", "trva"), "Samotné vyšetření trvá několik minut."),
]
ASK_AGAIN = "Chcete, aby se Vám ozvala sestra z ordinace? Řekněte ano, nebo ne."
NOT_UNDERSTOOD = "Nerozuměla jsem. Chcete, aby se Vám ozvala sestra? Řekněte prosím ano, nebo ne."
# intent → closing sentence; "handoff" = a person takes over; opt_out uses "opt_out" or else "declined".
CLOSING = {
    "interested": "Děkuji. Sestra z ordinace se Vám ozve a domluví další postup. Na shledanou.",
    "booked": "Děkuji. Další připomínky Vám posílat nebudeme. Na shledanou.",
    "callback": "Děkuji, sestra z ordinace Vám zavolá. Na shledanou.",
    "not_now": "Děkuji. Ozveme se později. Pokud si to rozmyslíte, zavolejte do ordinace. Na shledanou.",
    "declined": "Děkuji. Na shledanou.",
    "handoff": "Děkuji. Předám to sestře z ordinace, která se Vám ozve. Na shledanou.",
}
MAX_UNCLEAR = 2
DTMF = {"1": "ano", "2": "teď ne"}  # keys in a call → words for the reply rules

# ---------- ElevenLabs voice agent (backend/agent_call.py, scripts/elevenlabs_agent.py) ----------
DECISIONS = {"interested", "booked", "callback", "not_now", "declined", "opt_out", "unclear"}
AGENT_NAME = "Jsem včas – hlasový asistent ordinace"
AGENT_DECISIONS = {
    "interested": "chce, aby se ozvala sestra (ano, má zájem)",
    "callback": "chce, aby mu sestra zavolala, nebo má otázku, na kterou nemáš schválenou odpověď",
    "booked": "už má termín vyšetření nebo už byl vyšetřen",
    "not_now": "teď ne, později",
    "declined": "nemá zájem, nechce další kontakt",
    "unclear": "nepodařilo se zjistit odpověď",
}
AGENT_WHEN = "Kdy se pacientovi hodí telefonát sestry (dopoledne, odpoledne, konkrétní den), jinak prázdné."
AGENT_DATA = {}  # extra data collection fields → journey event `extra` (none in screening)
# ---------- recap at the end of a call: say back what was understood, ask to confirm (agent + scripted call) ----------
RECAP_ASK = "Je to tak?"
RECAP_FIX = "Co mám opravit?"
RECAP = {
    "interested": "Rozuměla jsem, že chcete, aby se Vám ozvala sestra z ordinace.",
    "callback": "Rozuměla jsem, že Vám má zavolat sestra z ordinace.",
    "not_now": "Rozuměla jsem, že teď ne a máme se ozvat později.",
    "booked": "Rozuměla jsem, že už máte termín vyšetření.",
}
RECAP_WHEN = "Hodí se Vám {when}."


def recap(intent: str, extra: dict) -> str:
    """Deterministic recap of a scripted call (backend/app.py): '' = no recap (declined, opt-out, handoff …)."""
    s = RECAP.get(intent)
    if not s:
        return ""
    when = str((extra or {}).get("when") or "").strip().rstrip(".")
    return " ".join([s, *([RECAP_WHEN.format(when=when)] if when and intent in ("interested", "callback") else []), RECAP_ASK])


# Doctor's feedback 17.10. (bridge 1000): the patient may book the pneumologist directly, no GP referral needed.
DIRECT = "Objednat se můžete i sami přímo u plicního lékaře, doporučení nepotřebujete."


def agent_prompt() -> str:
    faq = "\n".join(f"- {answer}" for _, answer in FAQ)
    closing = "\n".join(f"- {k}: {v}" for k, v in CLOSING.items())
    return f"""Jsi hlasový asistent ordinace praktického lékaře. Voláš pacientovi kvůli bezplatnému preventivnímu
vyšetření plic (program časného záchytu karcinomu plic). Mluvíš česky, klidně, pomalu a zdvořile, vykáš.
Volaný je starší člověk: nech ho domluvit, nespěchej, mluv krátce.

PRAVIDLA, která nesmíš porušit:
1. Říkáš jen věty z tohoto zadání, doslova nebo jen s malou úpravou slovosledu. Nic dalšího o zdraví, nemoci,
   riziku, výsledcích, lécích ani o pacientovi neříkáš. Nejsi lékař a neradíš.
2. Na otázku, na kterou tu nemáš schválenou odpověď, řekni: "{CLOSING['handoff']}" a ukonči hovor.
3. Nikdy nesděluj žádné údaje o pacientovi a na žádné se neptej, kromě toho, kdy se mu hodí, aby sestra zavolala.
4. Pokud pacient chce ukončit hovor nebo nechce být kontaktován, poděkuj a ukonči hovor.

Postup:
- Úvodní věta už zazněla: "{GREETING}"
- Když odpoví ano: zeptej se "Kdy se Vám hodí, aby sestra zavolala, spíš dopoledne, nebo odpoledne?"
  Odpověď si zapamatuj, udělej shrnutí (níže), pak řekni "{CLOSING['interested'].replace(' Na shledanou.', '')} {DIRECT} Na shledanou." a ukonči hovor.
- Když řekne, že už má termín nebo byl vyšetřen: udělej shrnutí, pak "{CLOSING['booked']}" a ukonči hovor.
- Když chce, aby mu sestra zavolala: udělej shrnutí, pak "{CLOSING['callback']}" a ukonči hovor.
- Když řekne teď ne nebo později: udělej shrnutí, pak "{CLOSING['not_now']}" a ukonči hovor.
- Když nemá zájem: "{CLOSING['declined']}" a ukonči hovor.
- Když se ptá na vyšetření, použij jen tyto odpovědi a potom se znovu zeptej: "{ASK_AGAIN}"
{faq}
- Když se ptá, kam nebo ke komu jít, nebo jestli potřebuje doporučení: "{DIRECT}"
- Když nerozumíš: "{NOT_UNDERSTOOD}" Po druhém nedorozumění řekni "{CLOSING['handoff']}" a ukonči hovor.

Shrnutí před závěrečnou větou:
- Řekni jednu krátkou větu, co jsi pochopila, a zeptej se "{RECAP_ASK}" Použij jen tyto věty:
  - ano: "{RECAP['interested']}" Když řekl, kdy se mu to hodí, přidej "Hodí se Vám" a čas tak, jak ho řekl.
  - zavolat jindy: "{RECAP['callback']}" Když řekl čas, přidej "Hodí se Vám" a ten čas.
  - teď ne: "{RECAP['not_now']}"
  - už má termín: "{RECAP['booked']}"
- Když souhlasí nebo neodpoví, řekni závěrečnou větu a ukonči hovor.
- Když řekne, že to tak není, zeptej se "{RECAP_FIX}" Opravu si zapamatuj, zopakuj jednou krátce opravené shrnutí
  bez další otázky a řekni závěrečnou větu podle opravy.
- Když nemá zájem nebo nechce být kontaktován, shrnutí nedělej, jen poděkuj a ukonči hovor.
- Do pole recap_confirmed zapiš ano, když shrnutí potvrdil, ne, když ho opravil.

Schválené závěrečné věty:
{closing}
- přímé objednání: {DIRECT}
"""


# ---------- Ukázka v sále (backend/hall.py, features.hall) ----------
HALL_CLOSING = {"interested": "Děkuji. Sestra z ordinace se Vám ozve a domluví další postup. Na shledanou.",
                "not_now": "Děkuji. Ozveme se později. Na shledanou."}
HALL_NOT_UNDERSTOOD = "Děkuji. Pošleme Vám zprávu s informacemi. Na shledanou."
# understood intent → card status on the projector (anything else: unclear)
HALL_STATUS = {"interested": "interested", "booked": "interested", "callback": "interested",
               "not_now": "not_now", "declined": "declined", "opt_out": "declined"}
