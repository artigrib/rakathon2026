"""AI phone conversation over Twilio ConversationRelay (Twilio does Czech speech-to-text and text-to-speech).

Safety by design: the model only *understands* what was said (replies.understand). Everything the assistant
*says* comes from fixed, reviewed sentences of the case dialog – it never improvises.
"""
import unicodedata

from .case import CASE

D = CASE.dialog
GREETING = D.GREETING
FAQ = D.FAQ
ASK_AGAIN = D.ASK_AGAIN
NOT_UNDERSTOOD = D.NOT_UNDERSTOOD
CLOSING = D.CLOSING
MAX_UNCLEAR = getattr(D, "MAX_UNCLEAR", 2)
CORE = {"opt_out", "question", "unclear", "handoff"}


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
            return CLOSING.get("opt_out") or CLOSING["declined"], True, "opt_out"
        if intent in CLOSING and intent not in CORE:  # every intent with its own closing sentence ends the call
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
