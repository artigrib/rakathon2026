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


def test_domain_root_is_the_landing_and_only_exact_public_paths_open(monkeypatch):
    from backend import app as appmod
    from dataclasses import replace
    monkeypatch.setattr(appmod, "settings", replace(appmod.settings, demo_password="x"))
    c = TestClient(appmod.app)
    r = c.get("/")
    assert r.status_code == 200 and "Plíce včas" in r.text
    assert c.get("/img/ukoly.jpg").status_code == 200
    assert c.get("/demo.mp4", headers={"Range": "bytes=0-9"}).status_code in (200, 206)
    assert c.get("/rakathon", follow_redirects=False).status_code in (200, 307)
    # "/" is public only as an exact path: the app and its data stay behind the password
    for path in ("/app/", "/app/index.html", "/app/data/patients.json", "/api/state"):
        assert c.get(path).status_code == 401, path
    assert c.get("/app/", auth=("plice", "x")).status_code == 200
