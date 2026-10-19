"""The public project page is reachable without the demo password."""
import pytest
from fastapi.testclient import TestClient


def test_landing_open_without_password(monkeypatch):
    from backend import app as appmod
    from dataclasses import replace
    if not appmod.LANDING_ON:
        pytest.skip("the case has no project landing (case.json landing)")
    monkeypatch.setattr(appmod, "settings", replace(appmod.settings, demo_password="x"))
    c = TestClient(appmod.app)
    r = c.get("/projekt/")
    assert r.status_code == 200 and "Plíce včas" in r.text and r.text.startswith("<!doctype html>")
    assert c.get("/projekt/img/ukoly.jpg").status_code == 200
    assert c.get("/projekt/demo.mp4", headers={"Range": "bytes=0-99"}).status_code in (200, 206)
    r = c.get("/app/index.html", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("/login")


def test_domain_root_is_the_landing_and_only_exact_public_paths_open(monkeypatch):
    from backend import app as appmod
    from dataclasses import replace
    monkeypatch.setattr(appmod, "settings", replace(appmod.settings, demo_password="x"))
    c = TestClient(appmod.app)
    r = c.get("/", follow_redirects=False)
    if appmod._case_landing():
        assert r.status_code == 200 and "<html" in r.text.lower()
    elif appmod.LANDING_ON:
        assert r.status_code == 200 and "Plíce včas" in r.text
        assert c.get("/img/ukoly.jpg").status_code == 200
        assert c.get("/demo.mp4", headers={"Range": "bytes=0-9"}).status_code in (200, 206)
        assert c.get("/rakathon", follow_redirects=False).status_code in (200, 307)
    else:  # no landing: the domain root opens the app (→ sign-in), never the lung-screening pages
        assert r.status_code == 307 and r.headers["location"] == "/app/"
        assert c.get("/projekt/", follow_redirects=False).status_code == 307
        assert c.get("/demo.mp4").status_code == 404
    # "/" is public only as an exact path: the app and its data stay behind the password
    for path in ("/app/", "/app/index.html", "/app/data/patients.json"):
        assert c.get(path, follow_redirects=False).status_code == 307, path      # → /login, no browser dialog
    r = c.get("/api/state")
    assert r.status_code == 401 and "www-authenticate" not in r.headers
    assert c.get("/app/", auth=("plice", "x")).status_code == 200


def test_case_landing_served_at_root_with_assets(monkeypatch, tmp_path):
    """cases/<id>/landing/index.html wins over the project landing; its files at /landing/…, public, nothing outside."""
    from backend import app as appmod
    from dataclasses import replace
    monkeypatch.setattr(appmod, "settings", replace(appmod.settings, demo_password="x"))
    (tmp_path / "img").mkdir()
    (tmp_path / "index.html").write_text('<!doctype html><title>L</title><a href="/login?next=/app/">Vyzkoušet</a>', encoding="utf-8")
    (tmp_path / "img" / "a.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("no", encoding="utf-8")
    monkeypatch.setattr(appmod, "CASE_LANDING", tmp_path)
    c = TestClient(appmod.app)
    r = c.get("/")
    assert r.status_code == 200 and "/login?next=/app/" in r.text
    assert c.get("/landing/img/a.svg").status_code == 200
    for path in ("/landing/../secret.txt", "/landing/%2e%2e/secret.txt", "/landing/..%2fsecret.txt"):
        assert c.get(path).text != "no", path
    assert 'href="/"' in c.get("/login").text                       # back to the landing from the sign-in page
