"""A case other than screening never sends real traffic with the shared (screening) keys unless CASE_LIVE=1."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "t", "TWILIO_FROM": "+1", "DEMO_TO": "+420600000000",
        "PUBLIC_URL": "https://example.invalid", "DEMO_EMAIL": "a@example.invalid", "SENDGRID_API_KEY": "k",
        "EMAIL_FROM": "b@example.invalid"}


def _modes(case: str, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("CASE_LIVE",)} | KEYS | {"CASE": case, "PLICE_SKIP_ENV_FILE": "1"} | extra
    code = "import json;from backend.settings import settings as s;print(json.dumps([s.live, s.email_live]))"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_screening_stays_live_with_keys():
    assert _modes("screening") == [True, True]


def test_other_cases_are_mock_without_opt_in():
    assert _modes("seniors") == [False, False]
    assert _modes("collections") == [False, False]


def test_case_live_opts_in():
    assert _modes("seniors", CASE_LIVE="1") == [True, True]


def test_env_files_read_for_case(tmp_path, monkeypatch):
    """Without CASE_LIVE a non-screening case reads only cases/<id>/.env, never backend/.env."""
    from backend import settings as st
    read = []
    monkeypatch.setattr(st, "_read", lambda p: read.append(p))
    monkeypatch.delenv("PLICE_SKIP_ENV_FILE", raising=False)
    monkeypatch.delenv("CASE_LIVE", raising=False)
    monkeypatch.setattr(st, "CASE_ID", "seniors")
    st._env_file()
    assert [p.name for p in read] == [".env"] and read[0].parent.name == "seniors"
    read.clear()
    monkeypatch.setattr(st, "CASE_ID", "screening")
    st._env_file()
    assert [p.parent.name for p in read] == ["screening", "backend"]
