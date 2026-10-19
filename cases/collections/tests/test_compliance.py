"""Compliance built into the product, checked on every text and every rule:

  * every message and call opens with the creditor and that it is an automated assistant;
  * nothing about the debt (amount, the word "dluh", any number) before identity verification: SMS, WhatsApp,
    e-mail and calls only point to the secure page;
  * no threats, no false or exaggerated consequences, no shaming (FORBIDDEN, over every text the assistant may say);
  * contact only on working days 8–20 h, at most WEEKLY_CAP contacts in 7 days;
  * a refused channel is never used again; dispute, vulnerability, STOP and wrong person stop the automation.
"""
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.cadence import next_touch
from backend.messages import render_with
from cases.collections import cadence, dialog, hooks, strategy

HERE = Path(__file__).resolve().parents[1]
M = json.loads((HERE / "messages.cs.json").read_text(encoding="utf-8"))
DATA = json.loads((HERE.parents[1] / json.loads((HERE / "case.json").read_text(encoding="utf-8"))["data"]).read_text(encoding="utf-8"))["patients"]
CREDITOR = M["parts"]["creditor"]

# Threats, false or exaggerated consequences, pressure and shaming (lower-case ASCII, regex). None of these may appear
# in anything the assistant sends or says. Legal steps are never mentioned by the automation at all; a person decides.
FORBIDDEN = [r"exekuc", r"exekutor", r"\bpolici", r"vezen", r"\bsoud", r"zalob", r"trestn", r"zatcen", r"zabav", r"insolvenc",
             r"registr", r"dluznik", r"neplatic", r"zamestnavatel", r"soused", r"ostud", r"hanb", r"styd", r"posledni varovani",
             r"okamzit", r"neprodlen", r"hrozi", r"nasledk", r"sankc", r"penale", r"vymah", r"inkas", r"pravni krok", r"advokat"]
# Pre-verification channels must not even say what it is about.
NO_DEBT_WORDS = [r"\bdluh", r"\bdluz", r"prodlen", r"\bdpd\b", r"\bkc\b", r"korun", r"czk", r"castk[auy] \d"]


def norm(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def texts(node, path=""):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            if not k.startswith("_"):
                yield from texts(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from texts(v, f"{path}[{i}]")


SAMPLES = [next(p for p in DATA if p["strategy"] == s) for s in ("reminder", "plan", "refi", "supervisor", "human")]
RENDERED = [(p["id"], ch, v, render_with(M, hooks, p, ch, v, "https://x.example/p/AbC123"))
            for p in SAMPLES for ch in M["channel_template"] for v in M[M["channel_template"][ch]] if not v.startswith("_")]


@pytest.mark.parametrize("pid,channel,variant,text", RENDERED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in RENDERED])
def test_opening_names_creditor_and_automated_assistant(pid, channel, variant, text):
    opening = text[:170]
    assert CREDITOR in opening and "automatick" in norm(opening), opening


def test_call_openings_and_agent():
    for t in (dialog.GREETING, *(v.replace("{creditor}", CREDITOR) for v in M["voice"].values())):
        first = t.split(". ")[0] + t.split(". ")[1]
        assert CREDITOR in first and "automatick" in norm(first)
    prompt = dialog.agent_prompt()
    assert dialog.GREETING in prompt and dialog.VERIFY_ASK in prompt and dialog.CLOSING["handoff"] in prompt


@pytest.mark.parametrize("pid,channel,variant,text", RENDERED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in RENDERED])
def test_no_debt_detail_before_verification(pid, channel, variant, text):
    p = next(x for x in DATA if x["id"] == pid)
    body = re.sub(r"https?://\S+", "", text)
    assert not re.search(r"\d{3}", body), f"a number in {channel}/{variant}: {body!r}"
    for v in (p["outstanding"], p["principal"], p["balance"], p["instalment"]):
        assert str(v) not in body and f"{v:,}".replace(",", " ") not in body
    assert p["contract"] not in body and p["name"] not in body and str(p["dpd"]) + " dn" not in body
    for w in NO_DEBT_WORDS:
        assert not re.search(w, norm(body)), f"{w} in {channel}/{variant}"


def test_placeholders_carry_nothing_from_the_debt():
    for p in SAMPLES:
        ph = hooks.extra_placeholders(p, M)
        assert set(ph) == {"creditor", "offer_sms", "offer_email", "offer_voice"}
        assert not any(re.search(r"\d", v) for v in ph.values())


def test_fixed_replies_and_call_sentences_say_nothing_about_the_debt():
    pre = [*texts(M["sms_reply"]), *texts(M["voice_ui"]), *[("dialog", s) for s in dialog.approved_sentences()]]
    for path, t in pre:
        for w in NO_DEBT_WORDS:
            assert not re.search(w, norm(t)), f"{w} in {path}: {t}"
        assert not re.search(r"\d{3}", t), path


def test_no_threats_shaming_or_pressure_anywhere():
    every = [*texts(M), *[("dialog", s) for s in dialog.approved_sentences()]]
    assert len(every) > 60
    for path, t in every:
        for w in FORBIDDEN:
            assert not re.search(w, norm(t)), f"forbidden {w!r} in {path}: {t[:120]}"


def test_agent_prompt_forbids_threats_and_disclosure():
    p = norm(dialog.agent_prompt())
    assert "nikdy nerikas castku" in p and "nevyhrozujes" in p and "overen" in p and "8 a 20" in p


def test_refi_page_has_illustrative_disclaimer():
    page = M["page"]
    assert "ilustrativni" in norm(page["refi_disclaimer"]) and "rpsn" in norm(page["refi_example"])
    assert "neni povinne" in norm(page["refi_disclaimer"]) or "nejde o nabidku" in norm(page["refi_disclaimer"])


# ---------- contact window and weekly cap (cadence.py) ----------
@pytest.mark.parametrize("when,ok", [
    (datetime(2026, 10, 19, 8, 0), True),    # Monday 8:00
    (datetime(2026, 10, 19, 7, 59), False),
    (datetime(2026, 10, 19, 19, 59), True),
    (datetime(2026, 10, 19, 20, 0), False),
    (datetime(2026, 10, 24, 10, 0), False),  # Saturday
    (datetime(2026, 10, 25, 10, 0), False),  # Sunday
    (datetime(2026, 10, 28, 10, 0), False),  # 28. 10., státní svátek
    (datetime(2026, 11, 17, 10, 0), False),
    (datetime(2026, 12, 24, 10, 0), False),
    (datetime(2027, 3, 26, 10, 0), False),   # Velký pátek 2027
    (datetime(2027, 3, 29, 10, 0), False),   # Velikonoční pondělí 2027
    (datetime(2026, 10, 27, 12, 0), True),
])
def test_calling_window(when, ok):
    assert cadence.allowed_at(when) is ok


def send(day, channel="sms"):
    return {"stage": "contacted", "date": day, "event": "send", "channel": channel}


def test_touches_fall_on_working_days_inside_the_window():
    # ladder step 1 is due 2 days after Thursday 22. 10. = Saturday → Monday
    t = next_touch([send("2026-10-22")])
    assert t["due"] == date(2026, 10, 26) and t["channel"] == "voice"
    h, m = map(int, t["at"].split(":"))
    assert cadence.allowed_at(datetime(2026, 10, 26, h, m))
    # 27. 10. + 1 = 28. 10. (holiday) → Thursday 29. 10.
    t = next_touch([send("2026-10-25"), send("2026-10-26", "voice"), {"stage": "broken_promise", "date": "2026-10-27"}])
    assert t["due"] == date(2026, 10, 29) and t["variant"] == "BROKEN_PROMISE"


def test_weekly_cap():
    # three contacts on Mon, Tue, Wed: the next one may go out only when the Monday drops out of the 7-day window
    j = [send("2026-10-19"), send("2026-10-20", "voice"), send("2026-10-21", "email")]
    t = next_touch(j)
    assert cadence.contacts_in_week(j, t["due"]) < cadence.WEEKLY_CAP
    assert t["due"] >= date(2026, 10, 26)
    # every touch of a whole ladder respects the cap
    j = [send("2026-10-19")]
    while (t := next_touch(j)) and t["channel"] != "human":
        assert cadence.is_contact_day(t["due"])
        j.append(send(t["due"].isoformat(), t["channel"]))
        assert cadence.contacts_in_week(j, t["due"]) <= cadence.WEEKLY_CAP
    assert t and t["channel"] == "human"


def test_channel_opt_out_is_respected():
    reply = {"stage": "contacted", "date": "2026-10-19", "event": "channel_opt_out", "intent": "channel_opt_out", "via": "sms",
             "extra": {"channels": ["voice"]}}
    t = next_touch([send("2026-10-19"), reply])
    assert t["channel"] != "voice"
    everything = {**reply, "extra": {"channels": ["voice", "sms", "email", "whatsapp"]}}
    assert next_touch([send("2026-10-19"), everything]) is None


@pytest.mark.parametrize("stage", ["dispute", "hardship_review", "human_handoff", "wrong_contact", "do_not_contact", "paid",
                                   "promise_to_pay", "plan_active", "plan_offered", "refi_offered"])
def test_automation_stops(stage):
    assert next_touch([send("2026-10-19"), {"stage": stage, "date": "2026-10-20"}]) is None


def test_people_segments_are_not_in_the_automation():
    for p in DATA:
        if p["dispute"] or p["vulnerable"]:
            assert not p["automation"] and p["strategy"] == "human"
    assert not strategy.segment({"dpd": 5, "vulnerable": {"note": "x"}})["automation"]


# ---------- recap at the end of a call (dialog.recap, agent prompt) ----------
def test_recap_sentences_have_no_threats_and_no_debt_detail():
    for t in dialog.recap_sentences():
        for w in FORBIDDEN:
            assert not re.search(w, norm(t)), f"forbidden {w!r} in recap: {t}"
        assert "!" not in t and not re.search(r"\d", t)
    for t in (*dialog.RECAP.values(), dialog.RECAP_WHEN, dialog.RECAP_ASK, dialog.RECAP_FIX):  # all but the person's amount
        for w in NO_DEBT_WORDS:
            assert not re.search(w, norm(t)), f"{w} in recap: {t}"


def test_recap_only_after_verification_and_never_on_protective_paths():
    full = {"verified": True, "promise_date": "v pátek", "promise_amount": 5000}
    for intent in dialog.INTENTS:
        assert dialog.recap(intent, {k: v for k, v in full.items() if k != "verified"}) == ""
        assert dialog.recap(intent, {**full, "verified": "2026-10-19"}) == ""  # only an explicit True counts
    for intent in ("wrong_person", "dispute", "vulnerable", "opt_out", "channel_opt_out", "callback", "question", "unclear"):
        assert dialog.recap(intent, full) == ""
    assert dialog.recap("will_pay", full) == \
        "Zapsal jsem si, že zaplatíte. Termín: v pátek. Částka podle Vašich slov: 5000 Kč. Souhlasí to?"
    assert dialog.recap("want_refi", full) == "Zapsal jsem si, že máte zájem o sloučení do jedné splátky. Souhlasí to?"


def test_recap_carries_only_what_the_person_said():
    for p in SAMPLES:
        t = dialog.recap("will_pay", {"verified": True, "promise_date": "zítra", "promise_amount": 1234, **p})
        for v in (p["outstanding"], p["principal"], p["balance"], p["instalment"]):
            assert str(v) not in t and f"{v:,}".replace(",", " ") not in t
        assert p["contract"] not in t and p["name"] not in t and "1234" in t


def test_agent_prompt_recap_rules():
    p = dialog.agent_prompt()
    n = norm(p)
    assert "nikdy nerikas castku" in n and "jen tehdy, kdyz v tomto hovoru probehlo overeni totoznosti" in n
    assert "nikdy jinou castku" in n and dialog.RECAP_ASK in p and dialog.RECAP_FIX in p
    for line in p.splitlines():  # the wrong person / vulnerable / dispute paths close at once, no recap
        if any(dialog.CLOSING[k] in line for k in ("wrong_person", "vulnerable", "dispute", "opt_out")):
            assert "shrnut" not in norm(line), line
    from scripts.elevenlabs_agent import config
    dc = config("collections")["platform_settings"]["data_collection"]
    assert {"summary", "recap_confirmed", "verification", "promise_amount"} <= set(dc)
    assert "nikdy neuvadej dluznou castku" in norm(dc["summary"]["description"])


def test_scripted_call_never_recaps_without_verification(client):
    """The gather fallback has no identity check: a promise is closed at once, nothing is said back."""
    c, store = client
    import backend.app as m
    pid = next(iter(m.PATIENTS))
    c.post("/api/send", json={"items": [{"id": pid, "channel": "voice", "variant": "FIRST_INVITE", "text": "x"}]})
    c.post(f"/twilio/voice/{pid}", data={"CallSid": "CC1"})
    a = c.post(f"/twilio/voice/{pid}/answer", data={"CallSid": "CC1", "Digits": "1"}).text
    assert "<Gather" not in a and "Souhlasí to?" not in a
    e = [x for x in store.get(pid)["journey"] if x.get("intent")][-1]
    assert e["intent"] == "will_pay" and "summary" not in e and "confirmed" not in e
