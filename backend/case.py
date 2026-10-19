"""The active case: one product (screening, seniors, collections …) on the shared core. Chosen by env CASE
(default "screening"); everything domain-specific lives in the package cases/<id>/ (see cases/README.md):

  case.json          manifest (title, stages, views, features, data file, storage key …)
  journey.json       state machine (backend/fsm.py, web/app/js/fsm.js)
  messages.cs.json   every text sent to a person (backend/messages.py, web/app/js/messages.js)
  dialog.py          reply understanding and approved voice sentences
  cadence.py         contact plan
  hooks.py           side effects and per-case pages
  build.py           builds the data file
  web/               ES modules of the web app (served at /app/case/)
"""
import importlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases"
REQUIRED = ("id", "title", "brand", "lang", "entity", "owners", "views", "features", "voice", "ref_date",
            "initial_stage", "sent_stage", "terminal_reply_stages", "data", "storage_key")


def name() -> str:
    return os.getenv("CASE", "screening").strip() or "screening"


class Case:
    def __init__(self, cid: str):
        self.id = cid
        self.dir = CASES / cid
        if not (self.dir / "case.json").exists():
            raise RuntimeError(f"unknown case {cid!r}: {self.dir / 'case.json'} does not exist")
        self.manifest = json.loads((self.dir / "case.json").read_text(encoding="utf-8"))
        self.journey = self.dir / "journey.json"
        self.messages = self.dir / "messages.cs.json"
        self.web = self.dir / "web"
        self.data = ROOT / self.manifest["data"]
        self.dialog = importlib.import_module(f"cases.{cid}.dialog")
        self.cadence = importlib.import_module(f"cases.{cid}.cadence")
        self.hooks = importlib.import_module(f"cases.{cid}.hooks")

    def feature(self, key: str) -> bool:
        return bool(self.manifest.get("features", {}).get(key))

    def __repr__(self):
        return f"Case({self.id!r})"


def load(cid: str | None = None) -> Case:
    return Case(cid or name())


def all_ids() -> list:
    return sorted(p.parent.name for p in CASES.glob("*/case.json"))


CASE = load()
