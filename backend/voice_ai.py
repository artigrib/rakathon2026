"""AI phone conversation over Twilio ConversationRelay (Twilio does Czech speech-to-text and text-to-speech).

Safety by design: the model only *understands* what the patient said (replies.understand). Everything the
assistant *says* comes from fixed, reviewed sentences below – it never improvises medical content.
"""
import unicodedata

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
CLOSING = {
    "interested": "Děkuji. Sestra z ordinace se Vám ozve a domluví další postup. Na shledanou.",
    "booked": "Děkuji. Další připomínky Vám posílat nebudeme. Na shledanou.",
    "callback": "Děkuji, sestra z ordinace Vám zavolá. Na shledanou.",
    "not_now": "Děkuji. Ozveme se později. Pokud si to rozmyslíte, zavolejte do ordinace. Na shledanou.",
    "declined": "Děkuji. Na shledanou.",
    "handoff": "Děkuji. Předám to sestře z ordinace, která se Vám ozve. Na shledanou.",
}
MAX_UNCLEAR = 2


def _norm(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def faq_answer(text: str):
    t = _norm(text)
    for keys, answer in FAQ:
        if any(_norm(k) in t for k in keys):
            return answer
    return None


class Conversation:
    """One call. feed(text) → (what to say, finished?, recorded intent or None)."""

    def __init__(self):
        self.unclear = 0

    def feed(self, text: str, understood: dict):
        intent = understood["intent"]
        if intent == "opt_out":
            return CLOSING["declined"], True, "opt_out"
        if intent in ("interested", "booked", "callback", "not_now", "declined"):
            return CLOSING[intent], True, intent
        if intent == "question":
            answer = faq_answer(text)
            if answer:
                return f"{answer} {ASK_AGAIN}", False, None
            return CLOSING["handoff"], True, "question"
        self.unclear += 1
        if self.unclear >= MAX_UNCLEAR:
            return CLOSING["handoff"], True, "unclear"
        return NOT_UNDERSTOOD, False, None
