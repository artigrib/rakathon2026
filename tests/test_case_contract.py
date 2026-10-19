"""The case package contract (cases/README.md), checked for every cases/<id>/ with a case.json – a new case is
validated automatically. Runs under any CASE: it reads each package directly, it does not need it to be active."""
import importlib
import json
import re
from pathlib import Path

import pytest

from backend import fsm
from backend.case import REQUIRED
from backend.messages import render_with
from backend.plan import Plan

ROOT = Path(__file__).resolve().parents[1]
IDS = sorted(p.parent.name for p in (ROOT / "cases").glob("*/case.json"))
CORE_INTENTS = {"opt_out", "question", "unclear"}


def load(cid):
    d = ROOT / "cases" / cid
    rd = lambda n: json.loads((d / n).read_text(encoding="utf-8"))  # noqa: E731
    return d, rd("case.json"), rd("journey.json"), rd("messages.cs.json")


def events(journey):
    return {e for row in journey["transitions"].values() for e in row}


def test_there_is_a_case():
    assert "screening" in IDS


@pytest.mark.parametrize("cid", IDS)
def test_manifest(cid):
    d, m, j, _ = load(cid)
    assert not [k for k in REQUIRED if k not in m], "missing manifest fields"
    assert m["id"] == cid and m["lang"] == "cs"
    assert isinstance(m["storage_key"], str) and m["storage_key"]
    assert isinstance(m["features"], dict) and set(m["features"]) <= {"fhir", "hall"}
    assert {m["initial_stage"], m["sent_stage"]} <= set(j["states"]) and m["initial_stage"] == j["initial"]
    assert set(m["terminal_reply_stages"]) <= set(j["states"])
    if m.get("result_stage"):
        assert m["result_stage"] in j["states"]
    assert set(m["voice"]) >= {"mode", "lang"} and m["voice"]["mode"] in ("gather", "relay", "agent")
    if m.get("group"):
        assert set(m["group"]) >= {"field", "label"}
    for path in m.get("redirects", {}):
        assert path.startswith("/") and path.count("/") == 1
    assert m["views"] and len({v["id"] for v in m["views"]}) == len(m["views"])


@pytest.mark.parametrize("cid", IDS)
def test_web_modules(cid):
    d, m, _, _ = load(cid)
    web = d / "web"

    def exports(path, names):
        src = path.read_text(encoding="utf-8")
        found = set(re.findall(r"export\s+(?:async\s+)?(?:const|let|function)\s+(\w+)", src))
        found |= {b or a for block in re.findall(r"export\s*\{([^}]*)\}", src)
                  for a, b in re.findall(r"(\w+)(?:\s+as\s+(\w+))?", block)}
        missing = set(names) - found
        assert not missing, f"{path.relative_to(ROOT)} does not export {sorted(missing)}"
        return src

    exports(web / "i18n.js", ["T"])
    exports(web / "config.js", ["CHANNELS", "REPLIES", "JOURNEY", "FILTERS"])
    exports(web / "domain.js", ["stageOf", "ownerOf", "lostOf", "plannedContact", "batchOf"] + (["groups"] if m.get("group") else []))
    exports(web / "row.js", ["describe", "actions"])
    for v in m["views"]:
        path = ROOT / "web/app/js" / v["module"][5:] if v["module"].startswith("core/") else web / v["module"]
        assert path.is_file(), f"view {v['id']}: {path} does not exist"
        exports(path, ["render"])
    for opt, names in (("card.js", ["blocks"]), ("actions.js", ["actions"])):
        if (web / opt).exists():
            exports(web / opt, names)
    for js in web.rglob("*.js"):  # the core only through the import map ("core/…"): relative paths differ per mode
        assert "/js/" not in "".join(re.findall(r"""from\s+["']([^"']+)["']""", js.read_text(encoding="utf-8"))), js


@pytest.mark.parametrize("cid", IDS)
def test_journey(cid):
    _, m, j, _ = load(cid)
    assert fsm.check(j) == []
    t = j["transitions"]
    assert "send" in t[j["initial"]], "the initial state must allow 'send'"
    for s, meta in j["states"].items():
        assert set(meta) >= {"final"}
        if meta["final"]:
            assert "send" not in t.get(s, {}), f"final state {s} must never be contacted"
    if j.get("soft_decline"):
        assert j["soft_decline"]["event"] in events(j)


@pytest.mark.parametrize("cid", IDS)
def test_dialog(cid):
    _, m, j, _ = load(cid)
    D = importlib.import_module(f"cases.{cid}.dialog")
    assert CORE_INTENTS <= set(D.INTENTS)
    assert set(D.INTENT_EVENT) == set(D.INTENTS) and set(D.INTENT_EVENT.values()) <= events(j)
    assert set(D.STAGE) >= set(D.INTENTS)
    for intent, patterns in D.RULES:
        assert intent in D.INTENTS
        for p in patterns:
            re.compile(p)
    assert hasattr(D.QUESTION, "search")
    assert "intent" in D.LLM_SYSTEM and "{text}" in getattr(D, "LLM_USER", "{text}")
    for name in ("GREETING", "ASK_AGAIN", "NOT_UNDERSTOOD", "AGENT_NAME", "AGENT_WHEN"):
        assert isinstance(getattr(D, name), str) and getattr(D, name), name
    assert all(isinstance(keys, tuple) and isinstance(a, str) for keys, a in D.FAQ)
    assert "handoff" in D.CLOSING and ("opt_out" in D.CLOSING or "declined" in D.CLOSING)
    assert set(D.CLOSING) - {"handoff"} <= set(D.INTENTS)
    assert isinstance(D.DTMF, dict)
    assert set(D.DECISIONS) <= set(D.INTENTS) and "unclear" in D.DECISIONS
    assert set(D.AGENT_DECISIONS) <= set(D.DECISIONS)
    assert isinstance(getattr(D, "AGENT_DATA", {}), dict)
    assert isinstance(D.agent_prompt(), str) and D.CLOSING["handoff"] in D.agent_prompt()
    assert D.extract("") == {} or isinstance(D.extract(""), dict)
    if m["features"].get("hall"):
        assert D.HALL_CLOSING and D.HALL_NOT_UNDERSTOOD and set(D.HALL_STATUS) <= set(D.INTENTS)


@pytest.mark.parametrize("cid", IDS)
def test_cadence_and_hooks(cid):
    _, m, j, M = load(cid)
    C = importlib.import_module(f"cases.{cid}.cadence")
    H = importlib.import_module(f"cases.{cid}.hooks")
    B = importlib.import_module(f"cases.{cid}.build")
    assert isinstance(C.PLAN, Plan) and C.PLAN.steps
    assert not C.PLAN.pause_stage or C.PLAN.pause_stage in j["states"]
    assert set(C.PLAN.stop_stages) <= set(j["states"])
    for st in C.PLAN.steps:
        if st.channel == C.PLAN.human:
            assert C.PLAN.human in events(j), f"human step fires event {C.PLAN.human!r}, not in journey"
            continue
        kind = M["channel_template"][st.channel]
        assert st.variant in M[kind], f"{st.channel}/{st.variant} has no text"
    assert callable(H.extra_placeholders) and callable(H.on_reply)
    assert callable(getattr(B, "main", None)) and callable(getattr(B, "build", None))


def _sample(m):
    path = ROOT / m["data"]
    if path.exists():
        recs = json.loads(path.read_text(encoding="utf-8"))["patients"]
        return recs[:5] or [{}]
    return [{}]


@pytest.mark.parametrize("cid", IDS)
def test_messages_render(cid):
    _, m, j, M = load(cid)
    H = importlib.import_module(f"cases.{cid}.hooks")
    assert {"link", "link_short", "link_marker", "call_us"} <= set(M["parts"])
    assert {"sms", "voice", "email"} <= set(M["channel_template"])
    assert "callback" in M["sms_reply"]  # fallback of backend/messages.sms_reply
    assert {"no_answer", "no_digit", "thanks"} <= set(M["voice_ui"])
    page = M["page"]
    assert {"invalid", "head", "foot", "thanks_title", "answers"} <= set(page)
    for a in page["answers"]:
        assert {"value", "label", "event", "intent", "thanks"} <= set(a) and a["event"] in events(j)
    kinds = set(M["channel_template"].values())
    for rec in _sample(m):
        for channel, kind in M["channel_template"].items():
            for variant in M[kind]:
                if variant.startswith("_"):
                    continue
                t = render_with(M, H, rec, channel, variant, "https://x/p/abc")
                assert not re.search(r"\{\w+\}", t), f"{channel}/{variant}: unfilled placeholder in {t[:80]!r}"
    assert kinds <= set(M)


@pytest.mark.parametrize("cid", IDS)
def test_data_shape(cid):
    _, m, _, _ = load(cid)
    path = ROOT / m["data"]
    if not path.exists():
        pytest.skip(f"no data yet: python -m cases.{cid}.build")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", d["refDate"])
    ids = [p["id"] for p in d["patients"]]
    assert ids and len(ids) == len(set(ids))
    if m.get("group"):
        assert all(m["group"]["field"] in p for p in d["patients"])
