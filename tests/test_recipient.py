"""Demo recipient set in the demo panel: validation, masking, used by the channels, daily limit."""
import pytest


@pytest.fixture()
def rec(tmp_path, monkeypatch):
    from backend import recipient
    monkeypatch.setattr(recipient, "_file", lambda: tmp_path / "recipient.json")
    return recipient


def test_validation_and_normalisation(rec):
    assert rec.save("601 234 567", "")["phone"] == "+420601234567"          # Czech number without the prefix
    assert rec.save("00420 601-234-567", "a@b.cz")["email"] == "a@b.cz"
    for bad in ("+44 7700 900123", "+4206", "abc"):
        with pytest.raises(ValueError):
            rec.save(bad, "")
    with pytest.raises(ValueError):
        rec.save("", "not-an-email")


def test_default_is_masked_and_empty_resets(rec, monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr(rec, "settings", replace(rec.settings, demo_to="+420602000879", demo_email="artem@example.com"))
    p = rec.public()
    assert p["phone"] == "+420 *** *** 879" and p["email"] == "a***@example.com" and not p["customPhone"]
    rec.save("+420601234567", "x@y.cz")
    assert rec.phone() == "+420601234567" and rec.email() == "x@y.cz" and rec.public()["customPhone"]
    rec.save("", "")
    assert rec.phone() == "+420602000879"


def test_live_send_goes_to_the_panel_number_and_stops_at_the_daily_limit(client, rec, monkeypatch):
    c, store = client
    import backend.app as m
    from dataclasses import replace
    monkeypatch.setattr(m, "settings", replace(m.settings, account_sid="AC1", auth_token="t", from_number="+1",
                                               demo_to="+420602000879", public_url="https://x"))
    monkeypatch.setenv("DEMO_DAILY_LIMIT", "2")
    sent = []
    monkeypatch.setattr(m.channels, "send_sms", lambda body, live: sent.append(rec.phone()) or
                        {"sid": f"SM{len(sent)}", "live": live, "to": rec.phone(), "status": "queued"})
    c.post("/api/recipient", json={"phone": "+420 601 234 567", "email": ""})
    for pid in ("R1", "R2", "R3"):
        c.post("/api/send", json={"items": [{"id": pid, "channel": "sms", "text": "x"}], "date": "2026-10-17"})
    assert sent == ["+420601234567", "+420601234567"]          # third one blocked by the daily limit
    assert c.post("/api/recipient", json={"phone": "+1 900 555 0100"}).status_code == 400
