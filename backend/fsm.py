"""Journey state machine. The table lives in cases/<id>/journey.json (shared with the web app, web/app/js/fsm.js)."""
import json

from .case import CASE

SPEC = json.loads(CASE.journey.read_text(encoding="utf-8"))
STATES = SPEC["states"]
TABLE = SPEC["transitions"]
INITIAL = SPEC["initial"]
SOFT = SPEC.get("soft_decline") or {}

# Reply intents → events (from the case dialog).
INTENT_EVENT = CASE.dialog.INTENT_EVENT


def state_of(decision: dict) -> str:
    return decision.get("stage") or INITIAL


def next_state(state: str, event: str, refusals: int = 0):
    """Target state, or None when the event is not allowed in this state (it is then only recorded)."""
    target = TABLE.get(state, {}).get(event)
    if target is None:
        return None
    if SOFT and event == SOFT["event"] and refusals == 0:
        return SOFT["first_to"]
    return target


def allowed(state: str, event: str) -> bool:
    return event in TABLE.get(state, {})


def check(spec: dict | None = None) -> list:
    """Consistency of the table: every target and every state with transitions is a known state."""
    spec = spec or SPEC
    states, table, initial = spec["states"], spec["transitions"], spec["initial"]
    problems = [] if initial in states else [f"unknown initial state {initial}"]
    for s, row in table.items():
        if s not in states:
            problems.append(f"unknown source state {s}")
        for e, t in row.items():
            if t not in states:
                problems.append(f"{s} --{e}--> unknown {t}")
    for s, meta in states.items():
        if s not in table:
            problems.append(f"state {s} has no row")
        if not meta["final"] and not table.get(s):
            problems.append(f"non-final state {s} has no way out")
    soft = spec.get("soft_decline")
    if soft and soft["first_to"] not in states:
        problems.append(f"soft_decline goes to unknown {soft['first_to']}")
    reachable, todo = {initial}, [initial]
    while todo:
        for t in table.get(todo.pop(), {}).values():
            if t not in reachable:
                reachable.add(t)
                todo.append(t)
    problems += [f"state {s} is unreachable" for s in states if s not in reachable]
    return problems
