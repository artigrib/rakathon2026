"""NIS data → FHIR (export) → read back from the server → same engine result."""
from pathlib import Path

import pytest

from backend.fhir import bundle
from backend.fhir_source import fetch, tables_from, write
from engine.webdata import build

DATA = Path(__file__).resolve().parents[1] / "data"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="challenge data not present")


def fake_server(resources, page=50):
    """Minimal FHIR search: /Type?_count=…, paged with 'next' links."""
    by = {}
    for r in resources:
        by.setdefault(r["resourceType"], []).append(r)

    def get(url, *_):
        t = url.rsplit("/", 1)[1].split("?")[0]
        start = int(url.split("_offset=")[1]) if "_offset=" in url else 0
        items = by.get(t, [])[start:start + page]
        nxt = start + page < len(by.get(t, []))
        return {"resourceType": "Bundle", "entry": [{"resource": r} for r in items],
                "link": [{"relation": "next", "url": f"http://x/fhir/{t}?_count={page}&_offset={start + page}"}] if nxt else []}
    return get


def test_roundtrip_through_fhir_server_gives_the_same_evaluation(tmp_path):
    b = bundle(DATA, "2026-10-16")
    res = fetch("http://x/fhir", get=fake_server([e["resource"] for e in b["entry"]]))
    t = tables_from(res)
    assert len(t["patients"]) == 300 and len(t["smoking"]) == 300 and len(t["ct"]) == 140 and len(t["contacts"]) == 100
    a = build(DATA, "2026-10-16")
    c = build(write(t, tmp_path), "2026-10-16")
    key = lambda out: {p["id"]: (p["status"], p["smoking"] and p["smoking"]["packYears"], p["channel"], len(p["history"])) for p in out["patients"]}
    assert key(a) == key(c)


def test_sync_from_and_write_back_to_a_fhir_server(tmp_path, monkeypatch):
    """A tiny FHIR server over HTTP: the app loads patients from it and writes every journey step back."""
    import importlib
    import json as _json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    store_ = {}
    for e in bundle(DATA, "2026-10-16")["entry"]:
        store_[(e["resource"]["resourceType"], e["resource"]["id"])] = e["resource"]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            t = self.path.split("/")[-1].split("?")[0]
            body = {"resourceType": "Bundle", "entry": [{"resource": r} for (k, _), r in store_.items() if k == t]}
            out = _json.dumps(body).encode()
            self.send_response(200); self.send_header("Content-Type", "application/fhir+json"); self.end_headers(); self.wfile.write(out)

        def do_PUT(self):
            n = int(self.headers["Content-Length"]); r = _json.loads(self.rfile.read(n))
            store_[(r["resourceType"], r["id"])] = r
            self.send_response(200); self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("FHIR_BASE", f"http://127.0.0.1:{srv.server_port}/fhir/r4")
    patients_json = Path(__file__).resolve().parents[1] / "web/app/data/patients.json"
    backup = patients_json.read_bytes()
    try:
        import backend.settings as s
        importlib.reload(s)
        import backend.fhir_sink as sink
        importlib.reload(sink)
        import backend.app as m
        importlib.reload(m)
        m.store.reset()
        from fastapi.testclient import TestClient
        c = TestClient(m.app)
        r = c.post("/api/fhir/sync").json()
        assert r["patients"] == 300
        c.post("/api/send", json={"items": [{"id": "SYN-000001", "channel": "sms", "text": "x"}]})
        c.post("/api/step", json={"id": "SYN-000001", "text": "Ano, mám zájem"})
        for _ in range(50):
            if ("Communication", "pv-SYN-000001-1") in store_:
                break
            time.sleep(0.05)
        assert store_[("Task", "task-SYN-000001")]["businessStatus"]["coding"][0]["code"] == "interested"
        assert store_[("Communication", "pv-SYN-000001-1")]["payload"][0]["contentString"] == "Ano, mám zájem"
        assert c.get("/api/health").json()["fhir"]["errors"] == 0
    finally:
        patients_json.write_bytes(backup)
        srv.shutdown()
        monkeypatch.delenv("FHIR_BASE")
        importlib.reload(s)
