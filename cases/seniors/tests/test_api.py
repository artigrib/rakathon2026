"""API smoke in mock mode: a check-in call, a simulated answer moves the stage and the needs land in the basket."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = json.loads((ROOT / "cases/seniors/data/seniors.json").read_text(encoding="utf-8"))
PID = next(p["id"] for p in DATA["patients"] if p["stage"] == "ok")


def test_case_and_health(client):
    c, _ = client
    assert c.get("/api/health").json()["case"] == "seniors"
    m = c.get("/api/case").json()
    assert m["id"] == "seniors" and m["sent_stage"] == "no_answer"
    assert c.get("/app/content/items.json").json()["items"]["nakup"]["label"] == "nákup"
    assert c.get("/app/data/patients.json").json()["refDate"] == DATA["refDate"]
    assert c.get("/app/case/views/today.js").status_code == 200


def test_call_then_answer_with_needs(client):
    c, store = client
    r = c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "Dobrý den"}], "date": "2026-10-19"})
    assert r.status_code == 200 and store.get(PID)["stage"] == "no_answer"
    d = c.post("/api/step", json={"id": PID, "text": "Došly mi léky a potřebovala bych nakoupit.", "date": "2026-10-19"}).json()
    assert d["stage"] == "needs_help"
    assert d["journey"][-1]["extra"]["items"] == ["nakup", "leky"]
    s = c.get("/api/state").json()["decisions"][PID]
    assert {n["item"] for n in s["needs"]} == {"nakup", "leky"} and all(n["status"] == "new" for n in s["needs"])
    assert PID not in c.get("/api/state").json()["plans"]  # answered: nothing automatic follows
    # the social worker orders it: the case's own mark
    nid = s["needs"][0]["id"]
    assert c.post("/api/mark", json={"id": PID, "field": "basket", "value": {nid: "ordered"}}).status_code == 200
    assert store.get(PID)["basket"] == {nid: "ordered"}


def test_emergency_escalates_and_mood(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "x"}], "date": "2026-10-19"})
    d = c.post("/api/step", json={"id": PID, "text": "Upadla jsem a nemůžu vstát.", "date": "2026-10-19"}).json()
    assert d["stage"] == "escalated" and store.get(PID)["health"]["intent"] == "emergency"
    d = c.post("/api/step", json={"id": PID, "stage": "resolve", "date": "2026-10-19"}).json()
    assert d["stage"] == "resolved"


def test_low_mood_stores_mood(client):
    c, store = client
    c.post("/api/step", json={"id": PID, "text": "Nic moc, je mi smutno.", "date": "2026-10-19"})
    assert store.get(PID)["stage"] == "low_mood" and store.get(PID)["mood"] == 2


def test_tick_runs_the_ladder_to_a_visit(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "voice", "variant": "CHECKIN", "text": "x"}], "date": DATA["refDate"]})
    for _ in range(4):
        c.post("/api/tick", json={"days": 1})
    auto = [(e.get("channel") or e["event"], e.get("variant")) for e in store.get(PID)["journey"] if e.get("auto")]
    assert auto == [("voice", "RETRY"), ("sms", "RELATIVE"), ("voice", "RETRY"), ("visit", None)]
    assert store.get(PID)["stage"] == "escalated"
    sms = [m for m in store.data["outbox"] if m["patient"] == PID and m["channel"] == "sms"][0]
    assert "nedovolali" in sms["text"] and sms["variant"] == "RELATIVE"


def test_personal_page_answer(client):
    c, store = client
    c.post("/api/send", json={"items": [{"id": PID, "channel": "sms", "variant": "CHECKIN", "text": "x"}], "date": "2026-10-19"})
    token = store.token(PID)
    assert "Jak se dnes máte" in c.get(f"/p/{token}").text
    r = c.post(f"/p/{token}", data={"answer": "help"})
    assert "155" in r.text and store.get(PID)["stage"] == "escalated"
    r = c.post(f"/p/{token}", data={"answer": "need"})  # escalated: a need is recorded, the stage stays
    assert store.get(PID)["stage"] == "escalated" and store.get(PID)["needs"][0]["item"] == "jine"
