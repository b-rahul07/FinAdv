"""Agreement of the gate with the hand-worked answers: the independent check on the suitability oracle.

The suitability oracle used in every metric (oracle.true_allowed, core.rule_violations) calls gate(), the same code
that builds the plans, so a bug in the gate would not show in the unsuitable rates. handcheck_v1.csv holds 45 of the
personas for two people to work out by hand from the written rules (docs/EXPERIMENTS.md section 5). This script
reports how often the two agree with each other and how often the engine agrees with them.

    python -m experiments.handcheck results/handcheck/grader_a.csv results/handcheck/grader_b.csv

Fields: capacity, rules fired (as a set), willingness, suitability. Engine answers come from engine_oracle in
experiments/data/personas_v1.jsonl, recomputed from the current engines so a stale file cannot hide a change.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from experiments import metrics, personas
from experiments.run import ROOT
from finadvisor.advisor.profile import Profile
from finadvisor.configs import default_bundle

FIELDS = {"capacity": "capacity", "rules": "rules fired", "willingness": "willingness", "suitability": "suitability"}
PERSONAS = ROOT / "experiments" / "data" / "personas_v1.jsonl"


def read(path: Path) -> dict[str, dict]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for row in rows:
        vals = {}
        for field, prefix in FIELDS.items():
            col = next(c for c in row if c.startswith(prefix))
            v = (row[col] or "").strip().lower()
            if not v:
                continue
            vals[field] = " ".join(sorted(set(re.findall(r"r\d", v)))).upper() if field == "rules" else v
        if vals:
            out[row["id"]] = vals
    return out


def engine() -> dict[str, dict]:
    bundle = default_bundle()
    out = {}
    for line in PERSONAS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        lab = personas.label(Profile(**row["profile"]), bundle)
        out[row["id"]] = {"capacity": lab["capacity"], "rules": " ".join(sorted(lab["rules"])),
                          "willingness": lab["willingness"], "suitability": lab["suitability"]}
    return out


def agreement(x: dict, y: dict, field: str) -> dict:
    ids = sorted(i for i in set(x) & set(y) if field in x[i] and field in y[i])
    a, b = [x[i][field] for i in ids], [y[i][field] for i in ids]
    return {"n": len(ids), "agreement": sum(p == q for p, q in zip(a, b)) / len(ids) if ids else None,
            "kappa": metrics.cohen_kappa(a, b), "disagree": [i for i, p, q in zip(ids, a, b) if p != q]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    args = ap.parse_args()
    eng = engine()
    a = read(Path(args.a))
    res = {"engine_vs_a": {f: agreement(eng, a, f) for f in FIELDS}}
    if args.b:
        b = read(Path(args.b))
        consensus = {i: {f: a[i][f] for f in FIELDS if f in a[i] and b.get(i, {}).get(f) == a[i][f]}
                     for i in set(a) & set(b)}
        res["a_vs_b"] = {f: agreement(a, b, f) for f in FIELDS}
        res["engine_vs_b"] = {f: agreement(eng, b, f) for f in FIELDS}
        res["engine_vs_consensus"] = {f: agreement(eng, consensus, f) for f in FIELDS}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
