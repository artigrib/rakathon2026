"""One pytest process = one case (backend modules bind the case at import time):

  .venv/bin/python -m pytest -q                      # CASE=screening (default): tests/ + cases/screening/tests/
  CASE=seniors .venv/bin/python -m pytest -q         # generic core tests + cases/seniors/tests/ + the contract of every case

tests/ belongs to screening except GENERIC; cases/<id>/tests/ run only when CASE=<id>.
At the repository root, so the environment is set before any test module imports the backend."""
import importlib
import os
from pathlib import Path

import pytest

CASE = os.environ.setdefault("CASE", "screening")
os.environ["PLICE_SKIP_ENV_FILE"] = "1"  # a VPS has a real backend/.env next to the code; tests must not use it
os.environ.setdefault("STATE_FILE", "/tmp/plice-test-state.json" if CASE == "screening" else f"/tmp/plice-test-state-{CASE}.json")
for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "PUBLIC_URL", "DEMO_TO"):
    os.environ[k] = ""

ROOT = Path(__file__).resolve().parent
GENERIC = {"test_case_contract.py", "test_agent_live.py", "test_case_live.py", "test_recipient.py", "test_sessions.py", "test_password_landing.py",
           "test_scenario.py"}  # any case


def pytest_collection_modifyitems(config, items):
    for item in items:
        p = Path(str(item.fspath)).resolve()
        rel = p.relative_to(ROOT).parts if p.is_relative_to(ROOT) else ()
        if rel[:1] == ("cases",) and len(rel) > 2 and rel[1] != CASE:
            item.add_marker(pytest.mark.skip(reason=f"test of case {rel[1]} (CASE={CASE})"))
        elif rel[:1] == ("tests",) and CASE != "screening" and p.name not in GENERIC:
            item.add_marker(pytest.mark.skip(reason=f"screening test (CASE={CASE})"))


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import backend.app as m
    importlib.reload(m)
    m.store.reset()
    return TestClient(m.app), m.store
