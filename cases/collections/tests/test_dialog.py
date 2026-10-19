"""Reply understanding (rules) and deterministic extraction of the promised date and amount."""
import pytest

from backend.replies import classify, understand
from cases.collections import dialog

MON = "2026-10-19"  # demo start, a Monday


@pytest.mark.parametrize("text,intent", [
    ("Zaplatím v pátek 5000", "will_pay"),
    ("Dobrý den, zaplatím zítra celou částku.", "will_pay"),
    ("Pošlu to do 15. 11.", "will_pay"),
    ("1", "will_pay"),
    ("Nezaplatím, nemám peníze", "cannot_pay"),
    ("Přišel jsem o práci", "cannot_pay"),
    ("Nemůžu zaplatit všechno najednou, šlo by to rozložit do splátek?", "need_plan"),
    ("Potřebuji odklad o měsíc", "need_plan"),
    ("2", "need_plan"),
    ("Mám víc půjček, šlo by je sloučit do jedné?", "want_refi"),
    ("Zajímá mě refinancování", "want_refi"),
    ("Nic vám nedlužím, už jsem to zaplatil.", "dispute"),
    ("Tu smlouvu jsem nepodepsal, je to podvod", "dispute"),
    ("Jsem v nemocnici, teď to opravdu nezvládnu.", "vulnerable"),
    ("Manžel minulý měsíc zemřel", "vulnerable"),
    ("Přišla jsem o práci a nevím co dál", "vulnerable"),
    ("To nejsem já, máte špatné číslo.", "wrong_person"),
    ("Omyl", "wrong_person"),
    ("9", "wrong_person"),
    ("Nevolejte mi prosím, pište jen SMS.", "channel_opt_out"),
    ("STOP SMS", "channel_opt_out"),
    ("0", "opt_out"),
    ("STOP", "opt_out"),
    ("Už mi nevolejte ani nepište", "opt_out"),
    ("Nekontaktujte mě", "opt_out"),
    ("Zavolejte mi prosím odpoledne", "callback"),
    ("3", "callback"),
    ("Kolik vám dlužím?", "question"),
    ("ehm", "unclear"),
])
def test_classify(text, intent):
    assert classify(text)["intent"] == intent


def test_opt_out_wins_over_payment():
    assert classify("STOP, zaplatím v pátek")["intent"] == "opt_out"
    assert understand("STOP")["source"] == "rules"


def test_opt_out_wins_over_ai(monkeypatch):
    from backend import llm
    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "classify", lambda t: {"intent": "opt_out", "confidence": "low", "why": "x"})
    assert understand("Zaplatím v pátek")["intent"] == "opt_out"  # AI opt-out wins even over a rule's will_pay
    monkeypatch.setattr(llm, "classify", lambda t: {"intent": "will_pay", "confidence": "low", "why": "x"})
    assert understand("hmm možná")["intent"] == "unclear"  # low-confidence AI → a person


@pytest.mark.parametrize("text,date,amount", [
    ("Zaplatím v pátek 5000", "2026-10-23", 5000),
    ("zaplatím v pondělí 2 500 Kč", "2026-10-26", 2500),
    ("Zaplatím zítra 1500,-", "2026-10-20", 1500),
    ("zaplatím dnes", "2026-10-19", None),
    ("Pošlu 3 tisíce do 15. 11.", "2026-11-15", 3000),
    ("Zaplatím pět tisíc 30. října", "2026-10-30", 5000),
    ("zaplatím za týden 12000 korun", "2026-10-26", 12000),
    ("Uhradím za 3 dny", "2026-10-22", None),
    ("zaplatím do konce měsíce", "2026-10-31", None),
    ("zaplatím 2,5 tisíce příští týden", "2026-10-26", 2500),
    ("Zaplatím 4.500 Kč 2.11.2026", "2026-11-02", 4500),
    ("zaplatím po výplatě", "2026-11-15", None),
])
def test_extract_promise(text, date, amount):
    x = dialog.extract(text)
    assert dialog.resolve(x.get("promise_when", ""), MON) == date
    assert x.get("promise_amount") == amount


def test_extract_nothing_without_a_promise():
    assert dialog.extract("") == {}
    assert "promise_amount" not in dialog.extract("Mám 3 děti a 2 psy")


def test_extract_channels():
    assert dialog.extract("Nevolejte mi prosím, pište jen SMS.")["channels"] == ["voice"]
    assert dialog.extract("Nepište mi SMS")["channels"] == ["sms"]
    assert dialog.extract("nechci e-maily")["channels"] == ["email"]


def test_weekday_said_on_that_day_means_next_week():
    assert dialog.resolve("wd:4", "2026-10-23") == "2026-10-30"


def test_understand_carries_extra():
    r = understand("Zaplatím v pátek 5000")
    assert r["intent"] == "will_pay" and r["extra"] == {"promise_when": "wd:4", "promise_amount": 5000}
