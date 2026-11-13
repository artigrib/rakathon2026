"""Understand a free-text reply (Czech). Deterministic rules first – predictable and testable;
an LLM can be plugged in via `classify(..., llm=fn)` for replies the rules do not understand.

Rules, intents and stages come from the case dialog (cases/<id>/dialog.py). The safety policy stays here:
opt-out always wins, a low-confidence AI answer goes to a person, anything not understood is never auto-answered.
Core intents every case has: opt_out, question, unclear."""
import re
import unicodedata

from .case import CASE

D = CASE.dialog
RULES = D.RULES
QUESTION = D.QUESTION
STAGE = D.STAGE
WHY = {"question": "dotaz", "unclear": "odpovědi nerozumíme – předáno člověku", **getattr(D, "WHY", {})}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def classify(text: str, llm=None) -> dict:
    """Return {intent, confidence, why}. `llm(text) -> dict` is consulted only when rules say unclear."""
    t = _norm(text)
    for intent, patterns in RULES:
        for p in patterns:
            if re.search(p, t):
                return {"intent": intent, "confidence": "high", "why": f"pravidlo: {p}"}
    if QUESTION.search(t):
        return {"intent": "question", "confidence": "high", "why": WHY["question"]}
    if llm:
        try:
            r = llm(text)
            if r.get("intent") in set(D.INTENTS) - {"unclear"}:
                return {**r, "why": "AI: " + r.get("why", "")}
        except Exception as e:  # never break the webhook because of the LLM
            return {"intent": "unclear", "confidence": "low", "why": f"AI nedostupná: {e}"}
    return {"intent": "unclear", "confidence": "low", "why": WHY["unclear"]}


def _with_extra(r: dict, text: str) -> dict:
    """Structured fields of the case (dialog.extract over the text, merged over what the AI found)."""
    extra = {**(r.get("extra") or {}), **(D.extract(text) or {})}
    return {**r, "extra": extra} if extra else r


def understand(text: str, conversation_id: str | None = None) -> dict:
    """Understand one reply, grouping any configured LLM call under its conversation."""
    return _with_extra(_understand(text, conversation_id=conversation_id), text)


def _understand(text: str, conversation_id: str | None = None) -> dict:
    from . import llm
    rules = classify(text)
    if rules["intent"] == "opt_out" or not llm.enabled():
        return {**rules, "source": "rules"}
    try:
        ai = llm.classify(text, conversation_id=conversation_id)
    except Exception as e:  # never fail a webhook because of the model
        return {**rules, "source": "rules", "why": f"{rules['why']} (AI nedostupná: {type(e).__name__})"}
    if ai["intent"] == "opt_out":
        return {**ai, "source": "ai"}
    if ai["confidence"] != "high" and ai["intent"] not in ("unclear", "question"):
        return {**ai, "intent": "unclear", "source": "ai", "why": f"nejistá AI ({ai['intent']}): {ai['why']}"}
    return {**ai, "source": "ai"}
