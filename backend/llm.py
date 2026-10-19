"""LLM understanding of free-text replies (Czech); intents and prompt come from the case dialog. Provider chosen by env, no SDKs needed:

  LLM_PROVIDER=anthropic  ANTHROPIC_API_KEY=…  [ANTHROPIC_MODEL=claude-haiku-5-5]
  LLM_PROVIDER=openai     OPENAI_API_KEY=…     [OPENAI_MODEL=gpt-4o-mini]
  LLM_PROVIDER=azure      AZURE_OPENAI_ENDPOINT=https://….openai.azure.com  AZURE_OPENAI_KEY=…  AZURE_OPENAI_DEPLOYMENT=…

The model only classifies. It never writes to the patient and never decides to contact anyone.
"""
import json
import os
import urllib.request

from .case import CASE

D = CASE.dialog
INTENTS = D.INTENTS
SYSTEM = D.LLM_SYSTEM  # the case asks for JSON {intent, when, confidence, why[, extra]}
USER = getattr(D, "LLM_USER", "Odpověď: «{text}»")


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "").lower()


def enabled() -> bool:
    p = provider()
    return (p == "anthropic" and bool(os.getenv("ANTHROPIC_API_KEY"))) or \
           (p == "openai" and bool(os.getenv("OPENAI_API_KEY"))) or \
           (p == "azure" and bool(os.getenv("AZURE_OPENAI_KEY")))


def _post(url, headers, body, timeout=8):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # Twilio waits max 15 s for the webhook
        return json.loads(r.read())


def _complete(text: str) -> str:
    p = provider()
    user = USER.format(text=text)
    if p == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                  {"model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"), "max_tokens": 200, "system": SYSTEM,
                   "messages": [{"role": "user", "content": user}]})
        return r["content"][0]["text"]
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    if p == "openai":
        r = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                  {"model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"), "messages": msgs, "response_format": {"type": "json_object"}})
    elif p == "azure":
        base = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        url = f"{base}/openai/deployments/{os.environ['AZURE_OPENAI_DEPLOYMENT']}/chat/completions?api-version=2024-10-21"
        r = _post(url, {"api-key": os.environ["AZURE_OPENAI_KEY"]}, {"messages": msgs, "response_format": {"type": "json_object"}})
    else:
        raise RuntimeError("LLM_PROVIDER not set")
    return r["choices"][0]["message"]["content"]


def classify(text: str) -> dict:
    raw = _complete(text).strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    out = json.loads(raw)
    if out.get("intent") not in INTENTS:
        raise ValueError(f"unexpected intent {out.get('intent')!r}")
    r = {"intent": out["intent"], "when": out.get("when", ""), "confidence": out.get("confidence", "low"),
         "why": out.get("why", "")}
    if isinstance(out.get("extra"), dict) and out["extra"]:  # structured fields the case asked for (mood, amount …)
        r["extra"] = out["extra"]
    return r
