"""Guided demo ("Spustit celou ukázku"): the whole case runs on the signed-in visitor's own phone and e-mail.

The case declares it in cases/<id>/scenario.json (contract in cases/README.md): a persona record bound to the visitor's
contacts (id PID, it exists only in that visitor's demo) and ordered steps. A step does something (a real send to the
visitor, a staff event, the demo clock), then waits for the visitor (a reply by SMS, a key or words in a call, a click on
the personal page, a case field such as `verified`) or for `timeout` seconds; then its `fallback` runs, so the demo
never stalls. The web app polls /api/state, which moves the scenario on (poll); "Další krok" forces the current step.

A step's live call (Twilio) is followed through the outbox entry it created: while the call rings, runs or is being
analysed (ElevenLabs agent outcome) the wait does not time out (up to HARD_WAIT); when the call ends without a
conversation (no answer, busy, failed, hung up without a word) the fallback runs at once.

A step may also carry presentation hints for the web app (PRESENT): "view" (switch to this view of the case),
"card" (true = open the persona's card, false = close it, "other" = the record the step acted on), "text" (extra
paragraph), "while_waiting" ({text, bullets} shown while the step waits). A reply action may target another record of
the visitor's set: {"reply": "…", "who": "other" | "<record id>"} (the persona's story stays clean).

The core runs the actions through `ops` (backend/app.py): send, event, allowed, reply, tick, patch, stage, today,
other, call."""
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
PRESENT = ("view", "card", "text", "while_waiting")   # step keys passed through to the web app as they are
DEFAULT_TIMEOUT = 60
HARD_WAIT = 300          # a live call in progress suspends the timeout, but never longer than this
CALL_FINAL = ("completed", "no-answer", "busy", "failed", "canceled")
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
    """Remove the persona and everything that happened to it (scenario reset), and what the scenario did to other
    records of the visitor's set ("who": "other")."""
    sc = st.data.pop("scenario", None) or {}
    st.data.pop("personas", None)
    st.data["decisions"].pop(PID, None)
    for pid in sc.get("others", []):
        st.data["decisions"].pop(pid, None)
    st.data["tokens"] = {t: p for t, p in st.data.get("tokens", {}).items() if p != PID}
    st.data["outbox"] = [m for m in st.data["outbox"] if m.get("patient") != PID]


def start(st, visitor: dict, ops):
    with _lock(st):
        clear(st)
        now = time.time()
        st.data["personas"] = {PID: persona(visitor)}
        st.data["scenario"] = {"at": now, "step": 0, "others": [],
                               "steps": [{"id": s["id"], "status": "pending", "since": now} for s in STEPS]}
        st._save()
    poll(st, ops)


def reset(st):
    with _lock(st):
        clear(st)
        st._save()


def _replies(st, mark: int, vias=None) -> list:
    """Replies of the persona since `mark`. A call that connected but nobody said a word (empty text of a voice reply)
    is not an answer: the step falls back as if the call was not answered."""
    new = st.get(PID).get("journey", [])[mark:]
    return [e for e in new if e.get("intent") and not e.get("ignored") and (vias is None or e.get("via") in vias)
            and (e.get("text") or not str(e.get("via") or "").startswith("voice"))]


def _met(wait: dict, s: dict, st) -> bool:
    d = st.get(PID)
    r = wait.get("reply")
    if r and _replies(st, s.get("mark", 0), r if isinstance(r, list) else None):
        return True
    if d.get("stage") in wait.get("stages", ()):
        return True
    return bool(wait.get("field") and d.get(wait["field"]))


def _call(s: dict, ops) -> dict | None:
    """The outbox entry of the step's live call ({status, analysing, …}) or None."""
    sid = s.get("sid")
    return ops.call(sid) if sid else None


def call_state(entry: dict | None) -> str | None:
    """dialing | in_progress | analysing | over | None (no live call)."""
    if not entry:
        return None
    if entry.get("analysing"):
        return "analysing"
    st = entry.get("status")
    if st in CALL_FINAL:
        return "over"
    if st == "in-progress":
        return "in_progress"
    return "dialing"


def _act(a: dict, s: dict, sc: dict, ops) -> bool:
    """One action; False = the state machine does not allow it now (the step is skipped)."""
    if "send" in a:
        r = ops.send(PID, a["send"], a.get("variant", "FIRST_INVITE"), live=not a.get("simulate"), delivery=a.get("delivery"))
        s["live"] = bool(r.get("live")) or s.get("live", False)
        if r.get("status") in ("daily_limit", "failed"):
            s["note"] = r["status"]
        if r.get("live") and r.get("sid") and a["send"] == "voice":
            s["sid"] = r["sid"]  # the call is followed through its outbox entry (call_state)
        return r.get("status") != "not_allowed"
    if "event" in a:
        if not ops.allowed(PID, a["event"]):
            return False
        ops.event(PID, a["event"], **{k: v for k, v in a.items() if k != "event"})
        return True
    if "reply" in a:
        pid = PID
        if a.get("who"):
            pid = ops.other(PID, a["who"])
            if not pid:
                return False
            s["who"] = pid
            if pid not in sc.setdefault("others", []):
                sc["others"].append(pid)
        ops.reply(pid, a["reply"])
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


def _begin(spec: dict, s: dict, sc: dict, st, ops, now: float):
    s.update(at=now, mark=len(st.get(PID).get("journey", [])), status="active")
    if "if_stage" in spec and ops.stage(PID) not in spec["if_stage"]:
        s["status"] = "skipped"
        return
    st._save()  # marked active before anything goes out: a step never runs twice
    for a in spec.get("do", []):
        if not _act(a, s, sc, ops):
            s["status"] = "skipped"
            return
    s["status"] = "waiting" if spec.get("wait") else "done"


def _fallback(spec: dict, s: dict, sc: dict, ops) -> str:
    fb = spec.get("fallback")
    if not fb:  # nobody answered in time; "optional": only something to look at, not a question
        return "done" if spec.get("optional") else "noreply"
    for a in fb if isinstance(fb, list) else [fb]:
        _act(a, s, sc, ops)
    return "simulated"


def _give_up(spec: dict, s: dict, ops, now: float) -> bool:
    """Stop waiting: the step's call ended without an answer, or the timeout passed (suspended while the call rings,
    runs or is analysed, never beyond HARD_WAIT)."""
    waited = now - s["at"]
    if waited >= HARD_WAIT:
        return True
    state = call_state(_call(s, ops))
    if state == "over" and spec["wait"].get("reply"):
        return True
    if state in ("dialing", "in_progress", "analysing"):
        return False
    return waited >= spec.get("timeout", DEFAULT_TIMEOUT)


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
                    _begin(spec, s, sc, st, ops, now)
                except Exception:  # a failing step must not stop the demo
                    _log.exception("scenario step %s failed", spec["id"])
                    s["status"] = "skipped"
            if s["status"] == "waiting":
                if _met(spec["wait"], s, st):
                    s["status"] = "done"
                elif force or _give_up(spec, s, ops, now):
                    force = False
                    try:
                        s["status"] = _fallback(spec, s, sc, ops)
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


def _public_step(spec: dict, s: dict, ops) -> dict:
    out = {k: s[k] for k in ("id", "status", "note", "live", "who") if k in s}
    out.update({k: spec[k] for k in PRESENT if k in spec})
    if s.get("sid"):
        out["call"] = call_state(_call(s, ops))
    return out


def public(st, available: bool, ops=None) -> dict:
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
        if s["status"] == "pending":
            left = spec.get("after", 0) - (now - s["since"])
        elif ops and call_state(_call(s, ops)) in ("dialing", "in_progress", "analysing"):
            left = HARD_WAIT - (now - s.get("at", now))
        else:
            left = spec.get("timeout", DEFAULT_TIMEOUT) - (now - s.get("at", now))
        left = max(0, round(left))
    steps = [_public_step(spec, s, ops) if ops else {k: s[k] for k in ("id", "status", "note", "live") if k in s}
             for spec, s in zip(STEPS, sc["steps"])]
    return {**out, "running": not sc.get("finished"), "finished": bool(sc.get("finished")), "step": i, "left": left,
            "steps": steps}
