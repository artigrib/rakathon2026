from datetime import date

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
            assert "{" not in t and "VPL-0142" in t or ch == "voice"
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
