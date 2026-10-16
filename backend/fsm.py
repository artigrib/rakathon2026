"""Patient journey state machine. The table lives in web/app/content/journey.json (shared with the web app)."""
import json
from pathlib import Path

SPEC = json.loads((Path(__file__).resolve().parent.parent / "web/app/content/journey.json").read_text(encoding="utf-8"))
STATES = SPEC["states"]
TABLE = SPEC["transitions"]
INITIAL = SPEC["initial"]
SOFT = SPEC["soft_decline"]

# Reply intents → events (question / unclear: the nurse calls back).
INTENT_EVENT = {"interested": "interested", "booked": "booked", "callback": "callback", "not_now": "not_now",
                "declined": "declined", "opt_out": "opt_out", "question": "callback", "unclear": "callback"}


def state_of(decision: dict) -> str:
    return decision.get("stage") or INITIAL


def next_state(state: str, event: str, refusals: int = 0):
    """Target state, or None when the event is not allowed in this state (it is then only recorded)."""
    target = TABLE.get(state, {}).get(event)
    if target is None:
        return None
    if event == SOFT["event"] and refusals == 0:
        return SOFT["first_to"]
    return target


def allowed(state: str, event: str) -> bool:
    return event in TABLE.get(state, {})


def check() -> list:
    """Consistency of the table: every target and every state with transitions is a known state."""
    problems = []
    for s, row in TABLE.items():
        if s not in STATES:
            problems.append(f"unknown source state {s}")
        for e, t in row.items():
            if t not in STATES:
                problems.append(f"{s} --{e}--> unknown {t}")
    for s, meta in STATES.items():
        if s not in TABLE:
            problems.append(f"state {s} has no row")
        if not meta["final"] and not TABLE.get(s):
            problems.append(f"non-final state {s} has no way out")
    reachable, todo = {INITIAL}, [INITIAL]
    while todo:
        for t in TABLE.get(todo.pop(), {}).values():
            if t not in reachable:
                reachable.add(t)
                todo.append(t)
    problems += [f"state {s} is unreachable" for s in STATES if s not in reachable]
    return problems
