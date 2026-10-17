"""The public project page is reachable without the demo password."""
from fastapi.testclient import TestClient


def test_landing_open_without_password(monkeypatch):
    from backend import app as appmod
    from dataclasses import replace
    monkeypatch.setattr(appmod, "settings", replace(appmod.settings, demo_password="x"))
    c = TestClient(appmod.app)
    r = c.get("/projekt/")
    assert r.status_code == 200 and "Plíce včas" in r.text and r.text.startswith("<!doctype html>")
    assert c.get("/projekt/img/ukoly.jpg").status_code == 200
    assert c.get("/projekt/demo.mp4", headers={"Range": "bytes=0-99"}).status_code in (200, 206)
    assert c.get("/app/index.html").status_code == 401
