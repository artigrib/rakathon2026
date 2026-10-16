"""Server-side decisions per patient, same shape as the web app's store (stage, journey, sent, result).
JSON file is enough for the demo; swap for a DB without touching callers."""
import hashlib
import json
import secrets
import threading
from datetime import date

_lock = threading.Lock()


class Store:
    def __init__(self, path):
        self.path = path
        self.data = {"decisions": {}, "outbox": []}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        self.version = 0

    def _save(self):
        self.version += 1
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def decisions(self):
        return self.data["decisions"]

    def get(self, pid):
        return self.data["decisions"].get(pid, {})

    def event(self, pid, stage, day=None, **extra):
        """Append a journey event and set the current stage (stage=None only records the event)."""
        with _lock:
            d = self.data["decisions"].setdefault(pid, {})
            e = {"stage": stage, "date": (day or date.today().isoformat()), **extra}
            d.setdefault("journey", []).append(e)
            if stage == "new":  # doctor re-included the patient: back to the start, ready to invite
                d.pop("stage", None)
            elif stage:
                d["stage"] = stage
            if stage == "result":
                d["result"] = extra.get("result")
            if stage == "sent":
                d["sent"] = {"channel": extra.get("channel"), "date": e["date"], "variant": extra.get("variant")}
                d["skipped"] = False
            self._save()
            return d

    def patch(self, pid, **fields):
        with _lock:
            self.data["decisions"].setdefault(pid, {}).update(fields)
            self._save()

    def log(self, **msg):
        """Outbox record: who we contacted, through what, Twilio SID, delivery status."""
        with _lock:
            self.data["outbox"].append(msg)
            self._save()

    def outbox_update(self, sid, **fields):
        with _lock:
            for m in self.data["outbox"]:
                if m.get("sid") == sid:
                    m.update(fields)
                    self._save()
                    return m
        return None

    def last_contacted(self, phone):
        """Inbound SMS → patient: the latest real message we sent to that number."""
        for m in reversed(self.data["outbox"]):
            if m.get("to") == phone and m.get("live"):
                return m.get("patient")
        return None

    def token(self, pid):
        """Opaque per-patient token for the personal link (no patient id in the URL)."""
        with _lock:
            tokens = self.data.setdefault("tokens", {})
            for t, p in tokens.items():
                if p == pid:
                    return t
            t = secrets.token_urlsafe(8)
            tokens[t] = pid
            self._save()
            return t

    def patient_by_token(self, token):
        return self.data.get("tokens", {}).get(token)

    def reset(self):
        with _lock:
            self.data = {"decisions": {}, "outbox": []}
            self._save()
