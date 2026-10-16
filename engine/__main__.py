import argparse, json, sys
from .rules import run, Config

ap = argparse.ArgumentParser(description="Plíce včas eligibility engine")
ap.add_argument("data_dir"); ap.add_argument("--ref-date", default=None); ap.add_argument("-o", "--out")
ap.add_argument("--policy", default="2026", help="program rules: 2026 (55–74) or 2027 (50–80)")
a = ap.parse_args()
res = run(a.data_dir, a.ref_date, Config.policy(a.policy))
s = json.dumps(res, ensure_ascii=False, indent=2)
(open(a.out, "w", encoding="utf-8").write(s) if a.out else sys.stdout.write(s))
print(json.dumps(res["summary"], ensure_ascii=False, indent=1), file=sys.stderr)
