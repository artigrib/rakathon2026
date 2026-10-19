"""Reply understanding of Jsem v pořádku: Czech sentences → intent, mood, needs (rules only, no AI)."""
import re

import pytest

from backend.replies import classify, understand
from cases.seniors import dialog

# The research table: sentence → intent (and what extract must find).
TABLE = [
    # ok, colloquial and negations
    ("Dobře, děkuji, všechno v pořádku.", "ok"), ("V pořádku, nic nepotřebuji.", "ok"), ("1", "ok"),
    ("jo", "ok"), ("dobrý", "ok"), ("jak kdy", "ok"), ("nic nového", "ok"), ("ujde to", "ok"), ("Nic mi není", "ok"),
    ("Mám se dobře", "ok"), ("Spíš dobře", "ok"), ("Jako vždycky", "ok"), ("Byla jsem v nemocnici, už jsem doma", "ok"),
    # chronic / mild complaint: the call goes on (health_note)
    ("Nic nepotřebuju, jen ta kolena", "ok"), ("Bolí mě kolena", "ok"), ("Jen ta záda", "ok"),
    # needs
    ("Došly mi léky a potřebovala bych nakoupit.", "need_items"), ("Jinak dobře, jen nám netopí topení.", "need_items"), ("2", "need_items"),
    ("Pomoc s nákupem bych potřebovala", "need_items"), ("Pes potřebuje k veterináři", "need_items"), ("Nejde mi plyn v kuchyni", "need_items"),
    ("Nemám na léky", "need_items"), ("Přišel mi dopis z úřadu", "need_items"), ("Nerozumím tomu dopisu", "need_items"),
    ("Potřebovala bych doprovod k lékaři", "need_items"), ("Nemůžu se vykoupat", "need_items"), ("Rozbily se mi brýle", "need_items"),
    ("Ujde to, ale došly mi léky a potřebovala bych nákup", "need_items"),
    # low mood and grief
    ("Ale nic moc, jsem pořád sama a je mi smutno.", "low_mood"), ("Chtěla bych si s někým popovídat.", "low_mood"), ("Dcera nevolá", "low_mood"),
    ("Zemřel mi manžel", "low_mood"), ("Je mi smutno", "low_mood"), ("Pořád jsem sama", "low_mood"), ("Nic moc, je mi smutno.", "low_mood"),
    ("Je mi smutno, nikdo za mnou nechodí", "low_mood"), ("Spíš hůř než obvykle", "low_mood"), ("Hrozně", "low_mood"), ("Ano, je mi smutno", "low_mood"),
    # new or worsening health: a worker calls
    ("Od včera mě bolí koleno a točí se mi hlava.", "health_problem"), ("Upadla jsem v koupelně, ale nic vážného.", "health_problem"),
    ("Nejsem v pořádku", "health_problem"), ("Není mi dobře", "health_problem"), ("Mám teplotu", "health_problem"), ("Je mi hůř", "health_problem"),
    ("Zvracím", "health_problem"), ("Je mi zle", "health_problem"),
    # emergency: real markers only
    ("Upadla jsem a nemůžu vstát.", "emergency"), ("Nemůžu dýchat", "emergency"), ("Bolí mě na hrudi", "emergency"), ("Spadl jsem", "emergency"),
    ("Pomoc", "emergency"), ("Ležím na zemi a nemůžu vstát", "emergency"), ("Potřebuju sanitku", "emergency"), ("Zavolejte záchranku", "emergency"),
    ("Hoří", "emergency"), ("Cítím plyn", "emergency"),
    # crisis: not 155, a warm handover
    ("Už se mi nechce žít.", "crisis"), ("Nechce se mi žít", "crisis"), ("Už to nemá cenu", "crisis"), ("Chci umřít", "crisis"),
    # pause / schedule / human / callback / opt-out
    ("Jsem v nemocnici", "pause"), ("Jsem u dcery do neděle", "pause"), ("Jedu do lázní", "pause"),
    ("Stačí jednou týdně", "schedule_change"), ("Volejte raději odpoledne", "schedule_change"), ("Ne tak často", "schedule_change"), ("Nevolejte mi ráno", "schedule_change"),
    ("Nechci s robotem mluvit", "human"), ("Chci mluvit s člověkem", "human"), ("Dejte mi paní Malou", "human"),
    ("Teď nemůžu, zavolejte mi odpoledne.", "callback"),
    ("Už mi prosím nevolejte.", "opt_out"), ("STOP", "opt_out"), ("Zrušte to", "opt_out"), ("Nevolejte mi už vůbec", "opt_out"),
    ("Kdo jste?", "question"), ("Mluvím s robotem?", "question"), ("brambory", "unclear"),
]


@pytest.mark.parametrize("text,intent", TABLE)
def test_classify(text, intent):
    assert classify(text)["intent"] == intent


def test_table_passes_completely():
    missed = [(t, i, classify(t)["intent"]) for t, i in TABLE if classify(t)["intent"] != i]
    assert missed == []


def test_rules_order_is_deterministic():
    order = [intent for intent, _ in dialog.RULES]
    assert order == ["crisis", "emergency", "opt_out", "human", "pause", "schedule_change", "callback", "need_items",
                     "health_problem", "low_mood", "ok"]
    assert set(order) <= set(dialog.INTENTS)


def test_intents_and_mapping():
    assert set(dialog.INTENT_EVENT) == set(dialog.INTENTS)
    assert dialog.INTENT_EVENT["crisis"] == "emergency" and dialog.STAGE["crisis"] == "escalated"
    assert dialog.INTENT_EVENT["pause"] == "pause" and dialog.STAGE["pause"] == "paused"
    assert dialog.INTENT_EVENT["human"] == "escalate" and dialog.STAGE["human"] == "escalated"
    assert dialog.INTENT_EVENT["schedule_change"] == "ok"  # a wish for the worker, the senior is fine
    assert dialog.DECISIONS >= {"crisis", "pause", "schedule_change", "human"}


def test_emergency_wins_over_opt_out():
    """Safety: someone who fell and also says 'do not call' is still an emergency for a person."""
    assert classify("Nevolejte, upadla jsem a nemůžu vstát")["intent"] == "emergency"


def test_emergency_needs_real_markers():
    assert classify("Včera pro mě jela sanitka")["intent"] != "emergency"
    assert classify("Pomoc s nákupem bych potřebovala")["intent"] == "need_items"
    assert classify("Nejde mi plyn v kuchyni")["intent"] == "need_items"
    assert dialog.emergency_kind("Hoří u souseda") == "fire" and dialog.emergency_kind("Cítím plyn") == "fire"
    assert dialog.emergency_kind("Upadla jsem a nemůžu vstát") == "medical" and dialog.emergency_kind("Bolí mě kolena") is None


def test_schedule_change_is_not_opt_out():
    for t in ("Stačí jednou týdně", "Nevolejte mi tak často", "Nevolejte mi dopoledne", "Volejte raději odpoledne"):
        assert classify(t)["intent"] == "schedule_change", t
    assert dialog.extract("Stačí jednou týdně")["schedule"] == "jednou týdně"
    assert dialog.extract("Nevolejte mi tak často")["schedule"] == "méně často"
    assert dialog.extract("Volejte raději v pondělí")["schedule"] == "v pondělí"


def test_pause_until():
    assert dialog.extract("Jsem u dcery do neděle")["pause_until"] == "do neděle"
    assert dialog.extract("Jedu do lázní na čtrnáct dní")["pause_until"] == "na čtrnáct dní"
    assert "pause_until" not in dialog.extract("Jsem v nemocnici")


def test_extract_items_mood_health():
    x = dialog.extract("Ale nic moc, došly mi léky, potřebovala bych nakoupit a nějak netopí topení.")
    assert x["items"] == ["nakup", "leky", "otop"]
    assert x["mood"] == 3
    assert "health_flag" not in x
    x = dialog.extract("Je mi smutno a bolí mě záda")
    assert x["mood"] == 2 and x["health_flag"] is True and x["health_note"] is True and "health_acute" not in x
    assert dialog.extract("Výborně, děkuji")["mood"] == 5
    assert dialog.extract("") == {}
    assert dialog.extract("brambory") == {}


def test_health_note_versus_problem():
    note = dialog.extract("Nic nepotřebuju, jen ta kolena")
    assert note["health_note"] is True and "health_acute" not in note
    acute = dialog.extract("Od včera mě bolí koleno")
    assert acute["health_acute"] is True and "health_note" not in acute
    assert "health_flag" not in dialog.extract("Pes potřebuje k veterináři")  # the animal, not the senior
    assert dialog.extract("Pes potřebuje k veterináři")["items"] == ["pet"]
    assert "health_flag" not in dialog.extract("Jsem v nemocnici")


def test_mood_words_two_step():
    assert dialog.mood_of("Výborně") == 5 and dialog.mood_of("Skvěle") == 5
    assert dialog.mood_of("Dobře") == 4 and dialog.mood_of("Fajn") == 4
    assert dialog.mood_of("Ujde to") == 3 and dialog.mood_of("Jak kdy") == 3 and dialog.mood_of("Nic moc") == 3
    assert dialog.mood_of("Špatně") == 2 and dialog.mood_of("Je mi smutno") == 2 and dialog.mood_of("Hůř") == 2
    assert dialog.mood_of("Hrozně") == 1 and dialog.mood_of("Nechce se mi žít") == 1
    # relative answers to "Spíš dobře, nebo spíš hůř než obvykle?" set mood_delta, not an absolute mood
    assert dialog.extract("Spíš hůř než obvykle") == {"mood_delta": -1}
    assert dialog.extract("Jako vždycky") == {"mood_delta": 0}
    assert dialog.extract("Dnes trochu lépe") == {"mood_delta": 1}
    assert dialog.ASK_AGAIN == "Jak se dnes cítíte?" and dialog.ASK_MOOD_2 == "Spíš dobře, nebo spíš hůř než obvykle?"
    assert dialog.ASK_AGAIN in dialog.agent_prompt() and dialog.ASK_MOOD_2 in dialog.agent_prompt()


def test_company_wish_is_low_mood_with_a_basket_item():
    r = understand("Chtěla bych si s někým popovídat")
    assert r["intent"] == "low_mood" and r["extra"]["items"] == ["spolecnost"]
    assert "spolecnost" not in [p for i, pats in dialog.RULES if i == "need_items" for p in pats]
    assert dialog.ITEMS["spolecnost"]["label"] and dialog.ITEMS["finance"]["label"] and dialog.ITEMS["pet"]["label"]


def test_understand_carries_extra():
    r = understand("Došly mi léky a potřebovala bych nakoupit.")
    assert r["intent"] == "need_items" and r["extra"]["items"] == ["nakup", "leky"]


def test_emergency_keeps_the_line_open():
    """Tísňová péče: never 'zavěste a volejte 155' to a person who may be on the floor."""
    from backend.voice_ai import Conversation
    say, done, intent = Conversation().feed("Upadla jsem a nemůžu vstát", understand("Upadla jsem a nemůžu vstát"))
    assert done and intent == "emergency"
    assert "nezavěšujte" in say and "Zůstaňte prosím na telefonu" in say and "zavěste" not in say.lower()
    assert "záchrannou službu" in say
    for s in (dialog.EMERGENCY, dialog.EMERGENCY_FIRE_SAY, dialog.CRISIS_SAY, dialog.CLOSING["emergency"], dialog.CLOSING["crisis"]):
        assert "zavěste" not in s.lower() and "na telefonu" in s, s
    assert "150" in dialog.EMERGENCY_FIRE_SAY and "112" in dialog.EMERGENCY_FIRE_SAY
    assert "155" not in dialog.CRISIS_SAY


def test_crisis_is_warm_and_goes_to_a_person():
    from backend.voice_ai import Conversation
    u = understand("Už se mi nechce žít")
    say, done, intent = Conversation().feed("Už se mi nechce žít", u)
    assert intent == "crisis" and done and say == dialog.CRISIS_SAY
    assert "800 200 007" in dialog.CRISIS_LINES and "800 157 157" in dialog.CRISIS_LINES
    assert dialog.recap("crisis", {}) == "" and dialog.recap("emergency", {"emergency_kind": "fire"}) == ""


def test_human_pause_schedule_closings_end_the_call():
    from backend.voice_ai import Conversation
    for text, intent in (("Nechci s robotem mluvit", "human"), ("Jsem v nemocnici", "pause"), ("Stačí jednou týdně", "schedule_change")):
        say, done, got = Conversation().feed(text, understand(text))
        assert done and got == intent and say == dialog.CLOSING[intent], text


def test_not_understood_repeats_with_keys_then_a_person():
    from backend.voice_ai import Conversation
    assert "jedničku" in dialog.NOT_UNDERSTOOD and "dvojku" in dialog.NOT_UNDERSTOOD and "pomaleji" in dialog.NOT_UNDERSTOOD
    assert "sms" not in dialog.NOT_UNDERSTOOD.lower() and dialog.MAX_UNCLEAR == 2
    c = Conversation()
    say, done, _ = c.feed("brambory", understand("brambory"))
    assert say == dialog.NOT_UNDERSTOOD and not done
    say, done, intent = c.feed("brambory", understand("brambory"))
    assert done and intent == "unclear" and say == dialog.CLOSING["handoff"]


def test_agent_prompt_rules():
    p = dialog.agent_prompt()
    assert dialog.CLOSING["handoff"] in p and dialog.EMERGENCY in p and dialog.EMERGENCY_FIRE_SAY in p and dialog.CRISIS_SAY in p
    assert "nejdřív ověř" in p.lower() or "Nejdřív ověř" in p
    assert "zavěste" not in p.lower() and "neříkej mu, ať zavěsí" in p
    assert "Nikdy neradíš zdravotně" in p and "jedna otázka" in p.lower()
    assert dialog.RECAP["opt_out"] in p  # the opt-out is confirmed before the service ends
    assert "!" not in p


def test_greeting_is_short_one_question_no_brand():
    g = dialog.GREETING
    assert g.count("?") == 1 and "pečovatelská služba" in g and "Jsem v pořádku" not in g
    assert "{" not in g  # the agent's first message gets no placeholders
    assert len(g) < 200


def test_no_exclamation_or_dash_in_sentences():
    said = [dialog.GREETING, dialog.ASK_AGAIN, dialog.ASK_MOOD_2, dialog.NOT_UNDERSTOOD, dialog.EMERGENCY, dialog.EMERGENCY_FIRE_SAY,
            dialog.CRISIS_SAY, dialog.WRONG_PERSON, *dialog.CLOSING.values(), *(a for _, a in dialog.FAQ), *dialog.RECAP.values()]
    for s in said:
        assert "!" not in s and not re.search(r"\s[–—-]\s", s), s
        assert "{" not in s or s in dialog.RECAP.values()
    for s in dialog.CLOSING.values():
        assert "155" not in s  # the worker calls, the senior is never sent away from the phone


class _Store:
    """Minimal store for hooks.on_reply: one record, patch merges fields."""

    def __init__(self, **d):
        self.d = {"journey": [{"stage": "ok", "event": "ok", "date": "2026-10-19", "text": "x"}], **d}

    def get(self, pid):
        return self.d

    def patch(self, pid, **fields):
        self.d.update(fields)


def test_hooks_store_mood_delta_notes_and_alerts():
    from cases.seniors import hooks
    s = _Store(mood=4)
    hooks.on_reply("S", "ok", {"mood_delta": -1}, s)
    assert s.d["mood"] == 3 and s.d["moodDate"] == "2026-10-19"
    hooks.on_reply("S", "ok", {"mood_delta": 0}, s)
    assert s.d["mood"] == 3
    hooks.on_reply("S", "ok", {"mood_delta": 1}, s)
    assert s.d["mood"] == 4
    s = _Store()
    hooks.on_reply("S", "ok", {"mood_delta": -1}, s)
    assert s.d["mood"] == 2  # no mood yet: from the middle
    # a chronic complaint is a note, not an alert; a real problem is an alert
    s = _Store()
    s.d["journey"][-1]["text"] = "Nic nepotřebuju, jen ta kolena"
    hooks.on_reply("S", "ok", {"health_flag": True, "health_note": True}, s)
    assert "health" not in s.d and s.d["health_note"] == {"date": "2026-10-19", "text": "Nic nepotřebuju, jen ta kolena"} and s.d["mood"] == 4
    hooks.on_reply("S", "health_problem", {"health_flag": True, "health_acute": True}, s)
    assert s.d["health"] == {"date": "2026-10-19", "intent": "health_problem"}
    s = _Store()
    hooks.on_reply("S", "crisis", {}, s)
    assert s.d["health"]["intent"] == "crisis" and s.d["mood"] == 1 and s.d["crisis"]["sms"] == "CRISIS"
    s = _Store()
    hooks.on_reply("S", "emergency", {"emergency_kind": "fire"}, s)
    assert s.d["emergency"] == {"date": "2026-10-19", "kind": "fire", "sms": "EMERGENCY_RELATIVE"}
    s = _Store()
    hooks.on_reply("S", "schedule_change", {"schedule": "raději odpoledne", "when": "odpoledne"}, s)
    assert s.d["schedule_note"] == {"date": "2026-10-19", "note": "raději odpoledne", "when": "odpoledne"}
    hooks.on_reply("S", "human", {}, s)
    assert s.d["human_request"] == {"date": "2026-10-19"}
    s = _Store()
    s.d["journey"][-1]["text"] = "Chtěla bych si s někým popovídat"
    hooks.on_reply("S", "low_mood", {"items": ["spolecnost"]}, s)
    assert [n["item"] for n in s.d["needs"]] == ["spolecnost"] and s.d["mood"] == 2
