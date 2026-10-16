"""Print the patient journey state machine (web/app/content/journey.json) as a Mermaid diagram for SPEC.md."""
import json
from collections import defaultdict
from pathlib import Path

J = json.loads((Path(__file__).resolve().parent.parent / "web/app/content/journey.json").read_text(encoding="utf-8"))
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
