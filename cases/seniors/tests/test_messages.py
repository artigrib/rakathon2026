"""Texts for seniors and relatives: every variant renders for real records, no exclamation marks, no dashes, no threats,
155 only where the senior reads it (SMS, e-mail, page); on the phone the line stays open and a worker calls."""
import json
import re
from pathlib import Path

from backend import messages
from cases.seniors import dialog, hooks

ROOT = Path(__file__).resolve().parents[3]
M = json.loads((ROOT / "cases/seniors/messages.cs.json").read_text(encoding="utf-8"))
DATA = json.loads((ROOT / "cases/seniors/synthetic/seniors.json").read_text(encoding="utf-8"))["patients"]


def texts():
    for kind in ("sms", "voice", "email"):
        for k, v in M[kind].items():
            if not k.startswith("_"):
                yield kind, k, v
    for k, v in M["sms_reply"].items():
        yield "sms_reply", k, v
    for k, v in M["voice_ui"]["thanks"].items():
        yield "voice_ui", k, v
    for k in ("no_answer", "no_digit", "follow_up"):
        yield "voice_ui", k, M["voice_ui"][k]


def test_style():
    for kind, k, v in texts():
        assert "!" not in v, (kind, k)
        assert not re.search(r"\s[–—-]\s", v), (kind, k)
        assert "zavěste" not in v.lower(), (kind, k)
        for word in ("musíte", "jinak", "ihned se dostavte", "diagn", "užívejte"):
            assert word not in v.lower() or kind == "email", (kind, k, word)  # no threats, no medical advice


def test_render_for_real_records():
    women = next(p for p in DATA if p["sex"] == "F")
    men = next(p for p in DATA if p["sex"] == "M")
    t = messages.render(women, "sms", "CHECKIN")
    assert t.startswith(f"Dobrý den, {women['vocative']},") and "155" in t and "{" not in t
    assert f", {men['vocative']}," in messages.render(men, "voice", "CHECKIN")
    rel = messages.render(women, "sms", "RELATIVE")
    assert women["title"] in rel and "{" not in rel
    assert messages.render({}, "sms", "CHECKIN").startswith("Dobrý den, tady")  # no record: no salutation
    v = messages.render(women, "voice", "CHECKIN")
    assert women["worker"] in v and "Jak se dnes cítíte?" in v and v.count("?") == 1  # one question per turn
    assert "jedničku" in v and "dvojku" in v and "155" not in v
    assert messages.render({}, "voice", "CHECKIN").count("?") == 1 and "Vaše sociální pracovnice" in messages.render({}, "voice", "CHECKIN")


def test_emergency_sms_to_relative_and_crisis_sms():
    p = DATA[0]
    rel = messages.render(p, "sms", "EMERGENCY_RELATIVE")
    assert p["title"] in rel and p["worker"] in rel and "okamžitou pomoc" in rel and "volá záchranáře" in rel and "{" not in rel
    crisis = messages.render(p, "sms", "CRISIS")
    assert "800 200 007" in crisis and "800 157 157" in crisis and "155" not in crisis and "{" not in crisis
    assert "{" not in messages.render(p, "email", "CRISIS") and "{" not in messages.render(p, "voice", "EMERGENCY_RELATIVE")
    assert "{" not in messages.render(p, "sms", "PAUSED")


def test_placeholders_hook():
    p = DATA[0]
    ph = hooks.extra_placeholders(p, M)
    assert ph["name"] == f", {p['vocative']}" and ph["senior"] == p["title"] and ph["worker"] == p["worker"]
    assert ph["relative"] == p["relative"]["name"] and ph["crisis_lines"] == dialog.CRISIS_LINES
    assert hooks.extra_placeholders({}, M)["worker"] == "Vaše sociální pracovnice"
    used = set(re.findall(r"\{(\w+)\}", json.dumps(M["sms"]) + json.dumps(M["voice"]) + json.dumps(M["email"])))
    assert used <= set(ph) | {"call_us", "link", "link_short"}


def test_trial_sms_fits():
    assert len(messages.sms_trial()) <= 122


def test_sms_reply_per_stage():
    assert "155" in messages.sms_reply("emergency", "escalated") and "800 200 007" in messages.sms_reply("crisis", "escalated")
    assert messages.sms_reply("opt_out", "declined") == ""
    assert messages.to_gsm(messages.sms_reply("pause", "paused")).startswith("Rozumime, zatim Vam volat nebudeme")
    assert messages.to_gsm(messages.sms_reply("ok", "ok")).startswith("Dekujeme")  # GSM alphabet on a trial account


def test_voice_ui_thanks_cover_every_reply_stage():
    stages = set(dialog.STAGE.values()) - {"callback"} | {"callback"}
    assert stages <= set(M["voice_ui"]["thanks"]), stages - set(M["voice_ui"]["thanks"])
    esc = M["voice_ui"]["thanks"]["escalated"]
    assert "nezavěšujte" in esc and "Zůstaňte prosím na telefonu" in esc
    assert "zavěste" not in esc.lower()
