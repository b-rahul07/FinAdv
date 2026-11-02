"""Summarise one or more advice-evaluation files (experiments/eval_advice.py output).

    python -m experiments.eval_summary results/eval/advice-a.jsonl [results/eval/advice-b.jsonl ...]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

CATEGORIES = ("engine", "route", "gate", "order", "numbers", "names", "framing", "promises", "evidence", "error")


def summarise(path: Path) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fails = Counter(f.split(":")[0] for r in rows for f in r["fails"])
    by_route = Counter(r["route"] for r in rows)
    plans = [r for r in rows if r["route"] == "plan"]
    audit = Counter(f"{r['audit']}" + (f" ({r['fallback']})" if r["fallback"] else "") for r in plans)
    print(f"\n== {path.name}: {len(rows)} turns, {len({r['persona'] for r in rows})} personas, routes {dict(by_route)}")
    clean = sum(1 for r in rows if not r["fails"])
    print(f"turns passing every check: {clean}/{len(rows)}")
    for c in CATEGORIES:
        if fails[c]:
            print(f"  {c:9} {fails[c]} failure(s)")
    print(f"plan audit outcomes: {dict(audit)}")
    for route in ("plan", "check", "learn"):
        secs = [r["seconds"] for r in rows if r["route"] == route]
        if secs:
            print(f"latency {route:5}: median {statistics.median(secs):.1f}s, max {max(secs):.1f}s (n={len(secs)})")
    for r in rows:
        if r["fails"]:
            print(f"  {r['persona']} t{r['turn']} {r['question'][:50]!r}: {r['fails']}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        summarise(Path(p))
