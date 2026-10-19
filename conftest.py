import importlib
import os

import pytest

os.environ["PLICE_SKIP_ENV_FILE"] = "1"  # a VPS has a real backend/.env next to the code; tests must not use it
os.environ.setdefault("STATE_FILE", "/tmp/plice-test-state.json")
for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "PUBLIC_URL", "DEMO_TO"):
    os.environ[k] = ""


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import backend.app as m
    importlib.reload(m)
    m.store.reset()
    return TestClient(m.app), m.store
