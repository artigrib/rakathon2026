"""LLM understanding of free-text replies (Czech); intents and prompt come from the case dialog. Provider chosen by env, no SDKs needed:

  LLM_PROVIDER=anthropic  ANTHROPIC_API_KEY=…  [ANTHROPIC_MODEL=claude-haiku-5-5]
  LLM_PROVIDER=openai     OPENAI_API_KEY=…     [OPENAI_MODEL=gpt-4o-mini]
  LLM_PROVIDER=azure      AZURE_OPENAI_ENDPOINT=https://….openai.azure.com  AZURE_OPENAI_KEY=…  AZURE_OPENAI_DEPLOYMENT=…

The model only classifies. It never writes to the patient and never decides to contact anyone.
"""
import json
import os
import time
import urllib.request
import uuid

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


def _capture_generation(properties: dict) -> None:
    """Send AI observability data without affecting the classifier's provider call."""
    try:
        # Import at call time: app imports replies during its own construction.
        from .app import posthog_client
        if posthog_client:
            posthog_client.capture("$ai_generation", properties=properties)
    except Exception:
        pass


def _complete(text: str, conversation_id: str | None = None) -> str:
    p = provider()
    user = USER.format(text=text)
    trace_id = str(uuid.uuid4())
    session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"rakathon:{conversation_id}")) if conversation_id else None
    started = time.monotonic()
    if p == "anthropic":
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        try:
            r = _post("https://api.anthropic.com/v1/messages",
                      {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                      {"model": model, "max_tokens": 200, "system": SYSTEM,
                       "messages": [{"role": "user", "content": user}]})
            output = r["content"][0]["text"]
        except Exception as exc:
            _capture_generation({"$ai_trace_id": trace_id, "$ai_session_id": session_id, "$ai_span_id": str(uuid.uuid4()),
                                 "$ai_span_name": "classify_reply", "$ai_model": model, "$ai_provider": p,
                                 "$ai_input": messages, "$ai_input_tokens": None, "$ai_output_choices": [],
                                 "$ai_output_tokens": None, "$ai_latency": time.monotonic() - started,
                                 "$ai_is_error": True, "$ai_error": type(exc).__name__, "$ai_max_tokens": 200})
            raise
        usage = r.get("usage") or {}
        properties = {"$ai_trace_id": trace_id, "$ai_session_id": session_id, "$ai_span_id": str(uuid.uuid4()),
                      "$ai_span_name": "classify_reply", "$ai_model": model, "$ai_provider": p,
                      "$ai_input": messages, "$ai_input_tokens": usage.get("input_tokens"),
                      "$ai_output_choices": [{"role": "assistant", "content": output}],
                      "$ai_output_tokens": usage.get("output_tokens"), "$ai_latency": time.monotonic() - started,
                      "$ai_stop_reason": r.get("stop_reason"), "$ai_max_tokens": 200}
    else:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        if p == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            try:
                r = _post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                          {"model": model, "messages": messages, "response_format": {"type": "json_object"}})
            except Exception as exc:
                _capture_generation({"$ai_trace_id": trace_id, "$ai_session_id": session_id, "$ai_span_id": str(uuid.uuid4()),
                                     "$ai_span_name": "classify_reply", "$ai_model": model, "$ai_provider": p,
                                     "$ai_input": messages, "$ai_input_tokens": None, "$ai_output_choices": [],
                                     "$ai_output_tokens": None, "$ai_latency": time.monotonic() - started,
                                     "$ai_is_error": True, "$ai_error": type(exc).__name__})
                raise
        elif p == "azure":
            model = os.environ["AZURE_OPENAI_DEPLOYMENT"]
            base = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
            url = f"{base}/openai/deployments/{model}/chat/completions?api-version=2024-10-21"
            try:
                r = _post(url, {"api-key": os.environ["AZURE_OPENAI_KEY"]}, {"messages": messages, "response_format": {"type": "json_object"}})
            except Exception as exc:
                _capture_generation({"$ai_trace_id": trace_id, "$ai_session_id": session_id, "$ai_span_id": str(uuid.uuid4()),
                                     "$ai_span_name": "classify_reply", "$ai_model": model, "$ai_provider": p,
                                     "$ai_input": messages, "$ai_input_tokens": None, "$ai_output_choices": [],
                                     "$ai_output_tokens": None, "$ai_latency": time.monotonic() - started,
                                     "$ai_is_error": True, "$ai_error": type(exc).__name__})
                raise
        else:
            raise RuntimeError("LLM_PROVIDER not set")
        output = r["choices"][0]["message"]["content"]
        usage = r.get("usage") or {}
        properties = {"$ai_trace_id": trace_id, "$ai_session_id": session_id, "$ai_span_id": str(uuid.uuid4()),
                      "$ai_span_name": "classify_reply", "$ai_model": model, "$ai_provider": p,
                      "$ai_input": messages, "$ai_input_tokens": usage.get("prompt_tokens"),
                      "$ai_output_choices": [{"role": "assistant", "content": output}],
                      "$ai_output_tokens": usage.get("completion_tokens"), "$ai_latency": time.monotonic() - started,
                      "$ai_stop_reason": (r.get("choices") or [{}])[0].get("finish_reason")}
    _capture_generation(properties)
    return output


def classify(text: str, conversation_id: str | None = None) -> dict:
    raw = _complete(text, conversation_id=conversation_id).strip()
    raw = raw[raw.find("{"): raw.rfind("}") + 1]
    out = json.loads(raw)
    if out.get("intent") not in INTENTS:
        raise ValueError(f"unexpected intent {out.get('intent')!r}")
    r = {"intent": out["intent"], "when": out.get("when", ""), "confidence": out.get("confidence", "low"),
         "why": out.get("why", "")}
    if isinstance(out.get("extra"), dict) and out["extra"]:  # structured fields the case asked for (mood, amount …)
        r["extra"] = out["extra"]
    return r
