"""Understand a free-text patient reply (Czech). Deterministic rules first – predictable and testable;
an LLM can be plugged in via `classify(..., llm=fn)` for replies the rules do not understand.

Intents map 1:1 to journey stages used by the web app:
  interested | booked | callback | not_now | declined | opt_out | question | unclear
declined = "not interested" (doctor: first refusal → other channel + motivation, second → stop);
opt_out = explicit "do not contact me" → stop immediately.
Anything not clearly understood goes to the nurse (never auto-answered)."""
import re
import unicodedata


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


# (intent, patterns) in priority order – first match wins.
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


def classify(text: str, llm=None) -> dict:
    """Return {intent, confidence, why}. `llm(text) -> dict` is consulted only when rules say unclear."""
    t = _norm(text)
    for intent, patterns in RULES:
        for p in patterns:
            if re.search(p, t):
                return {"intent": intent, "confidence": "high", "why": f"pravidlo: {p}"}
    if QUESTION.search(t):
        return {"intent": "question", "confidence": "high", "why": "dotaz pacienta"}
    if llm:
        try:
            r = llm(text)
            if r.get("intent") in {"interested", "booked", "callback", "not_now", "declined", "opt_out", "question"}:
                return {**r, "why": "AI: " + r.get("why", "")}
        except Exception as e:  # never break the webhook because of the LLM
            return {"intent": "unclear", "confidence": "low", "why": f"AI nedostupná: {e}"}
    return {"intent": "unclear", "confidence": "low", "why": "odpovědi nerozumíme – předáno sestře"}


# Journey stage for each intent; question/unclear land with the nurse as a callback task.
STAGE = {"interested": "interested", "booked": "booked", "callback": "callback", "not_now": "not_now",
         "declined": "declined", "opt_out": "declined", "question": "callback", "unclear": "callback"}


def understand(text: str) -> dict:
    """What the backend actually uses: rules for hard safety (opt-out always wins), the LLM for everything else
    when configured, rules again as the fallback. Low-confidence AI answers go to the nurse."""
    from . import llm
    rules = classify(text)
    if rules["intent"] == "opt_out" or not llm.enabled():
        return {**rules, "source": "rules"}
    try:
        ai = llm.classify(text)
    except Exception as e:  # never fail a webhook because of the model
        return {**rules, "source": "rules", "why": f"{rules['why']} (AI nedostupná: {type(e).__name__})"}
    if ai["intent"] == "opt_out":
        return {**ai, "source": "ai"}
    if ai["confidence"] != "high" and ai["intent"] not in ("unclear", "question"):
        return {**ai, "intent": "unclear", "source": "ai", "why": f"nejistá AI ({ai['intent']}): {ai['why']}"}
    return {**ai, "source": "ai"}
