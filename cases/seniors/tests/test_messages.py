"""Texts for seniors and relatives: every variant renders for real records, no exclamation marks, no dashes, 155 in check-ins."""
import json
import re
from pathlib import Path

from backend import messages
from cases.seniors import hooks

ROOT = Path(__file__).resolve().parents[3]
M = json.loads((ROOT / "cases/seniors/messages.cs.json").read_text(encoding="utf-8"))
DATA = json.loads((ROOT / "cases/seniors/data/seniors.json").read_text(encoding="utf-8"))["patients"]


def texts():
    for kind in ("sms", "voice", "email"):
        for k, v in M[kind].items():
            if not k.startswith("_"):
                yield kind, k, v
    for k, v in M["sms_reply"].items():
        yield "sms_reply", k, v
    for k, v in M["voice_ui"]["thanks"].items():
        yield "voice_ui", k, v


def test_style():
    for kind, k, v in texts():
        assert "!" not in v, (kind, k)
        assert not re.search(r"\s[–—-]\s", v), (kind, k)


def test_render_for_real_records():
    women = next(p for p in DATA if p["sex"] == "F")
    men = next(p for p in DATA if p["sex"] == "M")
    t = messages.render(women, "sms", "CHECKIN")
    assert t.startswith(f"Dobrý den, {women['vocative']},") and "155" in t and "{" not in t
    assert f", {men['vocative']}," in messages.render(men, "voice", "CHECKIN")
    rel = messages.render(women, "sms", "RELATIVE")
    assert women["title"] in rel and "{" not in rel
    assert messages.render({}, "sms", "CHECKIN").startswith("Dobrý den, tady")  # no record: no salutation


def test_placeholders_hook():
    p = DATA[0]
    ph = hooks.extra_placeholders(p, M)
    assert ph["name"] == f", {p['vocative']}" and ph["senior"] == p["title"] and ph["worker"] == p["worker"]


def test_trial_sms_fits():
    assert len(messages.sms_trial()) <= 122


def test_sms_reply_per_stage():
    assert "155" in messages.sms_reply("emergency", "escalated")
    assert messages.sms_reply("opt_out", "declined") == ""
    assert messages.to_gsm(messages.sms_reply("ok", "ok")).startswith("Dekujeme")  # GSM alphabet on a trial account
