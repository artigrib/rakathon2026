"""Reply understanding of Jsem v pořádku: Czech sentences → intent, mood, needs (rules only, no AI)."""
import pytest

from backend.replies import classify, understand
from cases.seniors import dialog


@pytest.mark.parametrize("text,intent", [
    ("Dobře, děkuji, všechno v pořádku.", "ok"),
    ("V pořádku, nic nepotřebuji.", "ok"),
    ("1", "ok"),
    ("Došly mi léky a potřebovala bych nakoupit.", "need_items"),
    ("Jinak dobře, jen nám netopí topení.", "need_items"),
    ("2", "need_items"),
    ("Ale nic moc, jsem pořád sama a je mi smutno.", "low_mood"),
    ("Chtěla bych si s někým popovídat.", "low_mood"),
    ("Od včera mě bolí koleno a točí se mi hlava.", "health_problem"),
    ("Upadla jsem v koupelně, ale nic vážného.", "health_problem"),
    ("Upadla jsem a nemůžu vstát.", "emergency"),
    ("Nemůžu dýchat", "emergency"),
    ("Bolí mě na hrudi", "emergency"),
    ("Už se mi nechce žít.", "emergency"),
    ("Pomoc", "emergency"),
    ("Teď nemůžu, zavolejte mi odpoledne.", "callback"),
    ("Už mi prosím nevolejte.", "opt_out"),
    ("STOP", "opt_out"),
    ("Kdo jste?", "question"),
    ("brambory", "unclear"),
])
def test_classify(text, intent):
    assert classify(text)["intent"] == intent


def test_emergency_wins_over_opt_out():
    """Safety: someone who fell and also says 'do not call' is still an emergency for a person."""
    assert classify("Nevolejte, upadla jsem a nemůžu vstát")["intent"] == "emergency"


def test_extract_items_mood_health():
    x = dialog.extract("Ale nic moc, došly mi léky, potřebovala bych nakoupit a nějak netopí topení.")
    assert x["items"] == ["nakup", "leky", "otop"]
    assert x["mood"] == 3
    assert "health_flag" not in x
    assert dialog.extract("Je mi smutno a bolí mě záda")["mood"] == 2
    assert dialog.extract("Je mi smutno a bolí mě záda")["health_flag"] is True
    assert dialog.extract("Výborně, děkuji")["mood"] == 5
    assert dialog.extract("") == {}
    assert dialog.extract("brambory") == {}


def test_understand_carries_extra():
    r = understand("Došly mi léky a potřebovala bych nakoupit.")
    assert r["intent"] == "need_items" and r["extra"]["items"] == ["nakup", "leky"]


def test_voice_closing_for_emergency_says_155():
    from backend.voice_ai import Conversation
    say, done, intent = Conversation().feed("Upadla jsem a nemůžu vstát", understand("Upadla jsem a nemůžu vstát"))
    assert "155" in say and done and intent == "emergency"
    assert dialog.CLOSING["handoff"] in dialog.agent_prompt()
    assert "155" in dialog.agent_prompt()


def test_no_exclamation_or_dash_in_sentences():
    said = [dialog.GREETING, dialog.ASK_AGAIN, dialog.NOT_UNDERSTOOD, *dialog.CLOSING.values(), *(a for _, a in dialog.FAQ)]
    for s in said:
        assert "!" not in s and " – " not in s and " - " not in s, s
