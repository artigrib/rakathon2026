"""Print a case's journey state machine (cases/<id>/journey.json) as a Mermaid diagram for SPEC.md.

  python scripts/fsm_diagram.py [case]        (default: env CASE or screening)
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

CASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("CASE", "screening")
J = json.loads((Path(__file__).resolve().parent.parent / "cases" / CASE / "journey.json").read_text(encoding="utf-8"))
edges = defaultdict(list)
for s, row in J["transitions"].items():
    for ev, t in row.items():
        if t != s:  # self loops (repeat send, repeat reply) are left out of the picture
            edges[(s, t)].append(ev)
print("```mermaid\nstateDiagram-v2")
print(f"  [*] --> {J['initial']}")
for (s, t), evs in sorted(edges.items()):
    print(f"  {s} --> {t}: {', '.join(evs)}")
for s, m in J["states"].items():
    if m["final"]:
        print(f"  {s} --> [*]")
print("```")
