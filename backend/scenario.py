"""Guided demo ("Spustit celou ukázku"): the whole case runs on the signed-in visitor's own phone and e-mail.

The case declares it in cases/<id>/scenario.json (contract in cases/README.md): a persona record bound to the visitor's
contacts (id PID, it exists only in that visitor's demo) and ordered steps. A step does something (a real send to the
visitor, a staff event, the demo clock), then waits for the visitor (a reply by SMS, a key or words in a call, a click on
the personal page, a case field such as `verified`) or for `timeout` seconds; then its `fallback` runs, so the demo
never stalls. The web app polls /api/state, which moves the scenario on (poll); "Další krok" forces the current step.

The core runs the actions through `ops` (backend/app.py): send, event, allowed, reply, tick, patch, stage, today."""
import json
import logging
import threading
import time

from .case import CASE

PID = "demo-you"
_FILE = CASE.dir / "scenario.json"
SPEC = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else None
STEPS = SPEC["steps"] if SPEC else []
ACTIONS = ("send", "event", "reply", "tick", "tick_until", "patch")
WAITS = ("reply", "stages", "field")
DEFAULT_TIMEOUT = 60
_locks: dict = {}
_log = logging.getLogger("uvicorn.error")


def _fill(v, vars: dict):
    if isinstance(v, str):
        for k, x in vars.items():
            v = v.replace("{" + k + "}", x)
        return v
    if isinstance(v, dict):
        return {k: _fill(x, vars) for k, x in v.items()}
    if isinstance(v, list):
        return [_fill(x, vars) for x in v]
    return v


def persona(visitor: dict) -> dict:
    """The case's persona with {phone} / {email} of the visitor; in the case's default group so the app shows it."""
    rec = _fill(SPEC["persona"], {"phone": visitor.get("phone", ""), "email": visitor.get("email", "")})
    rec.update(id=PID, demo=True)
    g = CASE.manifest.get("group")
    if g:
        rec.setdefault(g["field"], g.get("default"))
    return rec


def _lock(st) -> threading.Lock:
    return _locks.setdefault(str(st.path), threading.Lock())


def clear(st):
    """Remove the persona and everything that happened to it (scenario reset)."""
    st.data.pop("scenario", None)
    st.data.pop("personas", None)
    st.data["decisions"].pop(PID, None)
    st.data["tokens"] = {t: p for t, p in st.data.get("tokens", {}).items() if p != PID}
    st.data["outbox"] = [m for m in st.data["outbox"] if m.get("patient") != PID]


def start(st, visitor: dict, ops):
    with _lock(st):
        clear(st)
        now = time.time()
        st.data["personas"] = {PID: persona(visitor)}
        st.data["scenario"] = {"at": now, "step": 0, "steps": [{"id": s["id"], "status": "pending", "since": now} for s in STEPS]}
        st._save()
    poll(st, ops)


def reset(st):
    with _lock(st):
        clear(st)
        st._save()


def _replies(st, mark: int, vias=None) -> list:
    new = st.get(PID).get("journey", [])[mark:]
    return [e for e in new if e.get("intent") and not e.get("ignored") and (vias is None or e.get("via") in vias)]


def _met(wait: dict, s: dict, st) -> bool:
    d = st.get(PID)
    r = wait.get("reply")
    if r and _replies(st, s.get("mark", 0), r if isinstance(r, list) else None):
        return True
    if d.get("stage") in wait.get("stages", ()):
        return True
    return bool(wait.get("field") and d.get(wait["field"]))


def _act(a: dict, s: dict, ops) -> bool:
    """One action; False = the state machine does not allow it now (the step is skipped)."""
    if "send" in a:
        r = ops.send(PID, a["send"], a.get("variant", "FIRST_INVITE"), live=not a.get("simulate"), delivery=a.get("delivery"))
        s["live"] = bool(r.get("live")) or s.get("live", False)
        if r.get("status") in ("daily_limit", "failed"):
            s["note"] = r["status"]
        return r.get("status") != "not_allowed"
    if "event" in a:
        if not ops.allowed(PID, a["event"]):
            return False
        ops.event(PID, a["event"], **{k: v for k, v in a.items() if k != "event"})
        return True
    if "reply" in a:
        ops.reply(PID, a["reply"])
        return True
    if "tick" in a:
        ops.tick(int(a["tick"]))
        return True
    if "tick_until" in a:
        for _ in range(int(a.get("max", 14))):
            if ops.stage(PID) in a["tick_until"]:
                break
            ops.tick(1)
        return True
    if "patch" in a:
        ops.patch(PID, _fill(a["patch"], {"today": ops.today()}))
        return True
    raise ValueError(f"unknown scenario action {a}")


def _begin(spec: dict, s: dict, st, ops, now: float):
    s.update(at=now, mark=len(st.get(PID).get("journey", [])), status="active")
    if "if_stage" in spec and ops.stage(PID) not in spec["if_stage"]:
        s["status"] = "skipped"
        return
    st._save()  # marked active before anything goes out: a step never runs twice
    for a in spec.get("do", []):
        if not _act(a, s, ops):
            s["status"] = "skipped"
            return
    s["status"] = "waiting" if spec.get("wait") else "done"


def _fallback(spec: dict, s: dict, ops) -> str:
    fb = spec.get("fallback")
    if not fb:  # nobody answered in time; "optional": only something to look at, not a question
        return "done" if spec.get("optional") else "noreply"
    for a in fb if isinstance(fb, list) else [fb]:
        _act(a, s, ops)
    return "simulated"


def poll(st, ops, force: bool = False):
    """Move the scenario on: start due steps, finish met or timed-out waits. force = "Další krok" (one step)."""
    sc = st.data.get("scenario")
    if not sc or sc.get("finished"):
        return
    lock = _lock(st)
    if not lock.acquire(blocking=False):  # another poll of the same visitor is running it
        return
    try:
        now = time.time()
        before = json.dumps(sc)
        while sc["step"] < len(STEPS):
            spec, s = STEPS[sc["step"]], sc["steps"][sc["step"]]
            if s["status"] == "active":  # an earlier run failed half-way: never repeat its sends
                s["status"] = "skipped"
            if s["status"] == "pending":
                if not force and now - s["since"] < spec.get("after", 0):
                    break
                force = False
                try:
                    _begin(spec, s, st, ops, now)
                except Exception:  # a failing step must not stop the demo
                    _log.exception("scenario step %s failed", spec["id"])
                    s["status"] = "skipped"
            if s["status"] == "waiting":
                if _met(spec["wait"], s, st):
                    s["status"] = "done"
                elif force or now - s["at"] >= spec.get("timeout", DEFAULT_TIMEOUT):
                    force = False
                    try:
                        s["status"] = _fallback(spec, s, ops)
                    except Exception:
                        _log.exception("scenario fallback %s failed", spec["id"])
                        s["status"] = "skipped"
                else:
                    break
            sc["step"] += 1
            if sc["step"] < len(STEPS):
                sc["steps"][sc["step"]]["since"] = now
        if sc["step"] >= len(STEPS):
            sc["finished"] = now
        if json.dumps(sc) != before:  # an unchanged poll keeps the store version (the web app does not re-render)
            st._save()
    finally:
        lock.release()


def public(st, available: bool) -> dict:
    """Progress for the demo panel (texts are in messages.cs.json "scenario", the web app has them)."""
    out = {"available": bool(available and SPEC), "pid": PID}
    sc = st.data.get("scenario")
    if not sc:
        return out
    now = time.time()
    i = sc["step"]
    left = None
    if i < len(STEPS):
        s, spec = sc["steps"][i], STEPS[i]
        left = (spec.get("after", 0) - (now - s["since"]) if s["status"] == "pending"
                else spec.get("timeout", DEFAULT_TIMEOUT) - (now - s.get("at", now)))
        left = max(0, round(left))
    return {**out, "running": not sc.get("finished"), "finished": bool(sc.get("finished")), "step": i, "left": left,
            "steps": [{k: s[k] for k in ("id", "status", "note", "live") if k in s} for s in sc["steps"]]}
