from datetime import date, timedelta

from backend.cadence import next_touch
from backend.messages import render, with_link, MARKER

D = "2026-10-16"


def sent(day, ch="sms"):
    return {"stage": "sent", "date": day, "channel": ch}


def test_no_invitation_no_plan():
    assert next_touch([]) is None


def test_ladder_after_first_sms():
    n = next_touch([sent(D)])
    assert (n["due"], n["channel"], n["step"]) == (date(2026, 10, 19), "voice", 1)


def test_full_ladder_ends_with_nurse():
    j = [sent("2026-10-16"), sent("2026-10-19", "voice"), sent("2026-10-21", "voice"), sent("2026-10-24", "whatsapp")]
    n = next_touch(j)
    assert (n["due"], n["channel"]) == (date(2026, 10, 28), "nurse")
    assert next_touch(j + [{"stage": "nurse_call", "date": "2026-10-28"}]) is None


def test_any_reply_stops_the_plan():
    for stage in ("interested", "callback", "booked", "declined"):
        assert next_touch([sent(D), {"stage": stage, "date": "2026-10-17"}]) is None


def test_not_now_pauses_then_restarts_with_motivation():
    j = [sent(D), {"stage": "not_now", "date": "2026-10-17"}]
    n = next_touch(j)
    assert (n["due"], n["channel"], n["variant"]) == (date(2027, 1, 15), "sms", "MOTIVATION")
    j2 = j + [sent("2027-01-15")]
    assert next_touch(j2)["due"] == date(2027, 1, 18)


def test_delivery_events_do_not_break_plan():
    j = [sent(D), {"stage": None, "date": D, "delivery": "delivered"}]
    assert next_touch(j)["channel"] == "voice"


def test_shared_templates_render_without_placeholders():
    p = {"gp": "VPL-0142", "pneu": "PNEU-1"}
    for ch in ("sms", "voice", "email", "whatsapp", "letter"):
        for v in ("FIRST_INVITE", "REMINDER", "MOTIVATION"):
            t = render(p, ch, v)
            assert "{" not in t and "VPL-" not in t  # no placeholders, no internal codes in patient texts
            assert not any(c in t for c in "–—→·!")
    assert "bezplatné" in render(p, "sms")
    assert "https://x/p/abc" in render(p, "sms", url="https://x/p/abc")


def test_marker_from_web_app_is_replaced_or_dropped():
    p = {"gp": "VPL-0142"}
    import backend.messages as m
    text = render(p, "sms", url=MARKER)
    assert "https://y/p/1" in with_link(text, "https://y/p/1")
    assert MARKER not in with_link(text, "") and "Odpověď" not in with_link(text, "")


def test_never_three_same_channels_in_a_row():
    j = [sent("2026-10-16", "voice"), sent("2026-10-19", "voice")]
    assert next_touch(j)["channel"] == "sms"


def test_trial_sms_fits_one_segment():
    from backend.messages import sms_trial
    t = sms_trial()
    assert t.isascii() and 38 + len(t) <= 160


def test_link_is_appended_for_text_channels_not_for_calls():
    assert with_link("Dobrý den.", "https://y/p/1", "sms").endswith("https://y/p/1")
    assert "https://y/p/1" in with_link("Dobrý den.", "https://y/p/1", "email")
    assert with_link("Dobrý den.", "https://y/p/1", "voice") == "Dobrý den."
    assert with_link("Dobrý den.", "", "sms") == "Dobrý den."


# --- case adjust hook: record argument and skipped steps (screening has no adjust; patched in) ---------------------

def test_two_arg_adjust_is_called_without_record(monkeypatch):
    import backend.cadence as c
    calls = []

    def adjust(touch, journey):
        calls.append(touch["step"])
        return touch
    monkeypatch.setattr(c, "ADJUST", adjust)
    monkeypatch.setattr(c, "_ADJ_RECORD", False)
    assert c.next_touch([sent(D)], record={"relative": None})["step"] == 1
    assert calls == [0, 1]  # the past step is probed (was it skipped?), the current one returned


def test_three_arg_adjust_gets_the_record_and_may_skip(monkeypatch):
    import backend.cadence as c
    seen = []

    def adjust(touch, journey, record=None):
        seen.append((touch["step"], record))
        return {"skip": True} if touch["step"] == 1 else touch
    monkeypatch.setattr(c, "ADJUST", adjust)
    monkeypatch.setattr(c, "_ADJ_RECORD", True)
    n = c.next_touch([sent(D)], record={"id": "P1"})
    assert (n["step"], n["channel"], n["due"]) == (2, c.PLAN.steps[2].channel, date(2026, 10, 16) + timedelta(days=c.PLAN.steps[2].day))
    assert seen == [(0, {"id": "P1"}), (1, {"id": "P1"}), (2, {"id": "P1"})]


def test_skipping_every_step_to_the_last_returns_none(monkeypatch):
    import backend.cadence as c
    monkeypatch.setattr(c, "ADJUST", lambda touch, journey, record=None: {"skip": True})
    monkeypatch.setattr(c, "_ADJ_RECORD", True)
    assert c.next_touch([sent(D)]) is None
    monkeypatch.setattr(c, "ADJUST", lambda touch, journey: None)
    monkeypatch.setattr(c, "_ADJ_RECORD", False)
    assert c.next_touch([sent(D)]) is None
