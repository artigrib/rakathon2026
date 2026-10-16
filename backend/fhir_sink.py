"""Write the journey back to the FHIR server: every invitation and reply as Communication, the practice task as Task.

Best effort and asynchronous: a slow or unavailable FHIR server never blocks sending or a webhook.
"""
import base64
import json
import queue
import threading
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from .fhir import LOCAL

TASK_STATUS = {"new": "requested", "sent": "in-progress", "not_now": "on-hold", "nurse_call": "in-progress", "callback": "in-progress",
               "interested": "in-progress", "booked": "in-progress", "ldct": "in-progress", "result": "completed",
               "declined": "rejected", "excluded": "cancelled"}
_q: "queue.Queue" = queue.Queue()
state = {"sent": 0, "errors": 0, "last_error": None, "last": None}


def _put(base, user, password, res):
    url = f"{base.rstrip('/')}/{res['resourceType']}/{res['id']}"
    req = urllib.request.Request(url, data=json.dumps(res).encode(), method="PUT", headers={"Content-Type": "application/fhir+json"})
    if user:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def _worker(cfg):
    while True:
        res = _q.get()
        try:
            _put(cfg.fhir_base, cfg.fhir_user, cfg.fhir_password, res)
            state["sent"] += 1
            state["last"] = f"{res['resourceType']}/{res['id']}"
        except Exception as e:  # noqa: BLE001 – recorded, shown in /api/health
            state["errors"] += 1
            state["last_error"] = f"{res['resourceType']}/{res['id']}: {str(e)[:120]}"


_started = False


def start(cfg):
    global _started
    if cfg.fhir_base and not _started:
        threading.Thread(target=_worker, args=(cfg,), daemon=True).start()
        _started = True


def resources(pid, n, event, decision, gp=None, text=None):
    """FHIR resources for one journey event (n = index in the patient's journey)."""
    now = datetime.now(ZoneInfo("Europe/Prague")).isoformat(timespec="seconds")
    stage = decision.get("stage") or "new"
    out = [{
        "resourceType": "Task", "id": f"task-{pid}", "status": TASK_STATUS.get(stage, "in-progress"), "intent": "order",
        "code": {"coding": [{"system": f"{LOCAL}/task", "code": "invite"}], "text": "Oslovit pacienta – Prevence pro plíce"},
        "businessStatus": {"coding": [{"system": f"{LOCAL}/journey", "code": stage}]},
        "for": {"reference": f"Patient/{pid}"}, "lastModified": now,
        **({"owner": {"reference": f"Organization/{gp}"}} if gp else {}),
    }]
    e = decision["journey"][-1]
    if event == "send":
        out.append({
            "resourceType": "Communication", "id": f"pv-{pid}-{n}", "status": "completed", "sent": now,
            "subject": {"reference": f"Patient/{pid}"}, "recipient": [{"reference": f"Patient/{pid}"}],
            "medium": [{"coding": [{"system": f"{LOCAL}/channel", "code": e.get("channel") or "sms"}]}],
            "category": [{"coding": [{"system": f"{LOCAL}/message-type", "code": "lung_screening_information"}]}],
            "note": [{"text": "automaticky dle plánu kontaktů" if e.get("auto") else "schváleno ordinací"}],
        })
    elif e.get("text"):
        out.append({
            "resourceType": "Communication", "id": f"pv-{pid}-{n}", "status": "completed", "received": now,
            "subject": {"reference": f"Patient/{pid}"}, "sender": {"reference": f"Patient/{pid}"},
            "category": [{"coding": [{"system": f"{LOCAL}/message-type", "code": "patient_reply"}]}],
            "payload": [{"contentString": e["text"]}],
            "note": [{"text": f"rozpoznáno: {e.get('intent')}" + (" (bez změny stavu)" if e.get("ignored") else "")}],
        })
    return out


def push(cfg, pid, event, decision, gp=None):
    if not cfg.fhir_base:
        return
    start(cfg)
    for r in resources(pid, len(decision.get("journey", [])) - 1, event, decision, gp):
        _q.put(r)
