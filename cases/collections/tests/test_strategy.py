"""Segmentation (strategy.py): deterministic rules, not AI. The data file must match them."""
import json
from pathlib import Path

import pytest

from cases.collections import build, strategy

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads((ROOT / "cases/collections/case.json").read_text(encoding="utf-8"))


def rec(**kw):
    base = {"dpd": 10, "income": "stable", "otherLoans": 0, "promises": [], "history": [], "vulnerable": None, "dispute": None}
    return {**base, **kw}


BROKEN = {"date": "2026-08-01", "amount": 1000, "kept": False}
KEPT = {"date": "2026-08-01", "amount": 1000, "kept": True}
SILENT = {"date": "2026-08-01", "channel": "sms", "response": "no_response"}


@pytest.mark.parametrize("r,segment,strat,rule", [
    (rec(dpd=12), "forgetful", "reminder", "R6"),
    (rec(dpd=30, promises=[KEPT]), "forgetful", "reminder", "R6"),
    (rec(dpd=31), "temporary", "plan", "R5"),
    (rec(dpd=8, income="reduced"), "temporary", "plan", "R5"),
    (rec(dpd=8, income="lost"), "temporary", "plan", "R5"),
    (rec(dpd=8, promises=[BROKEN]), "temporary", "plan", "R5"),
    (rec(dpd=61), "long_term", "refi", "R4"),
    (rec(dpd=45, otherLoans=2), "long_term", "refi", "R4"),
    (rec(dpd=20, otherLoans=3), "forgetful", "reminder", "R6"),
    (rec(dpd=40, promises=[BROKEN, BROKEN]), "uncooperative", "supervisor", "R3"),
    (rec(dpd=120, history=[SILENT] * 4), "uncooperative", "supervisor", "R3"),
    (rec(dpd=120, history=[SILENT] * 3), "long_term", "refi", "R4"),
    (rec(dpd=10, vulnerable={"note": "nemoc"}), "vulnerable", "human", "R2"),
    (rec(dpd=150, promises=[BROKEN] * 3, dispute={"note": "nesjednal"}), "dispute", "human", "R1"),
    (rec(dpd=5, dispute={"note": "x"}, vulnerable={"note": "y"}), "dispute", "human", "R1"),
])
def test_segment_table(r, segment, strat, rule):
    s = strategy.segment(r)
    assert (s["segment"], s["strategy"], s["rule"]) == (segment, strat, rule)
    assert s["automation"] == (strat in ("reminder", "plan", "refi"))
    assert s["reason"]


def test_people_strategies_never_automated():
    for seg in ("uncooperative", "dispute", "vulnerable"):
        assert strategy.STRATEGY[seg] not in strategy.AUTOMATED


def test_build_is_deterministic_and_committed():
    a = build.build()
    assert a == build.build()
    committed = json.loads((ROOT / MANIFEST["data"]).read_text(encoding="utf-8"))
    assert committed == a, "run: python -m cases.collections.build"


def test_data_matches_rules_and_is_synthetic():
    d = json.loads((ROOT / MANIFEST["data"]).read_text(encoding="utf-8"))
    P = d["patients"]
    assert 90 <= len(P) <= 110
    segs = {p["segment"] for p in P}
    assert segs == set(strategy.SEGMENTS)
    for p in P:
        s = strategy.segment(p)
        assert (p["segment"], p["strategy"], p["automation"], p["rule"]) == (s["segment"], s["strategy"], s["automation"], s["rule"])
        assert p["phone"].startswith("+420 000 "), "fake numbers only"
        assert p["email"].endswith("@example.com")
        assert 5 <= p["dpd"] <= 180
        assert p["product"] in ("loan", "card", "bnpl", "phone")
        assert p["outstanding"] > 0 and p["portfolio"]
    assert sum(1 for p in P if p["vulnerable"]) >= 3 and sum(1 for p in P if p["dispute"]) >= 2


def test_plan_options():
    opts = strategy.plan_options(12000)
    assert [(o["n"], o["monthly"]) for o in opts] == [(3, 4000), (6, 2000), (12, 1000)]
    assert [o["n"] for o in strategy.plan_options(1500)] == [3]  # 6 × 250 Kč is below the minimum instalment
    for amount in (999, 1001, 15400, 77777):
        for o in strategy.plan_options(amount):
            assert o["monthly"] * (o["n"] - 1) + o["last"] == amount and 0 < o["last"] <= o["monthly"]
    sch = strategy.schedule(15400, 6, "2026-10-26")
    assert len(sch) == 6 and sum(i["amount"] for i in sch) == 15400 and sch[1]["due"] == "2026-11-25"


def test_refi_example_is_consistent():
    e = strategy.refi_example(100_000)
    assert e["months"] in strategy.REFI_TERMS and e["total"] == e["monthly"] * e["months"] > 100_000
    assert e["rpsn"] == 10.4 and e["rate"] == 9.9
