"""Blind grading of explanations by two people, and their agreement (Cohen's kappa).

    python -m experiments.grading export results/paper/A1*.jsonl results/paper/B1*.jsonl --n 80 --out results/grading
    # two people fill in grader_a.csv and grader_b.csv (copies of sheet.csv) without seeing key.csv
    python -m experiments.grading kappa results/grading/grader_a.csv results/grading/grader_b.csv \
        --key results/grading/key.csv

Labels: accurate | minor_slip | materially_wrong. The sheet shows the person's facts, the plan (pipeline runs) and the
text, under a random id; which run produced it is only in key.csv. kappa reports agreement and, with the key, the
share of each label per run (only items both graders labelled the same count, plus the disagreement rate).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import secrets
from collections import Counter, defaultdict
from pathlib import Path

from experiments import metrics

LABELS = ("accurate", "minor_slip", "materially_wrong")


def plan_summary(plan: dict | None) -> str:
    if not plan:
        return ""
    return " | ".join(s.get("text", "") for s in plan.get("steps", []))


def export(files: list[str], n: int, out: Path, seed: int = 3) -> None:
    items = []
    for f in files:
        for r in metrics.load(f):
            if r.get("replicate", 0) == 0 and r.get("text"):
                items.append(r)
    random.Random(seed).shuffle(items)
    items = items[:n]
    out.mkdir(parents=True, exist_ok=True)
    with (out / "sheet.csv").open("w", newline="", encoding="utf-8") as fs, \
            (out / "key.csv").open("w", newline="", encoding="utf-8") as fk:
        ws, wk = csv.writer(fs), csv.writer(fk)
        ws.writerow(["item", "question", "plan (pipeline runs)", "answer", "label (" + " / ".join(LABELS) + ")", "notes"])
        wk.writerow(["item", "run_id", "profile_id"])
        for r in items:
            item = secrets.token_hex(4)
            ws.writerow([item, r.get("question") or r.get("wish") or "Make me a money plan",
                         plan_summary(r.get("final_plan")), r["text"], "", ""])
            wk.writerow([item, r["run_id"], r["profile_id"]])
    print(f"{len(items)} items -> {out / 'sheet.csv'} (graders) and {out / 'key.csv'} (keep hidden)")


def read_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    col = next(i for i, h in enumerate(rows[0]) if h.startswith("label"))
    return {row[0]: row[col].strip().lower() for row in rows[1:] if len(row) > col and row[col].strip()}


def kappa(a: Path, b: Path, key: Path | None) -> dict:
    la, lb = read_labels(a), read_labels(b)
    common = sorted(set(la) & set(lb))
    bad = sorted({v for v in [*la.values(), *lb.values()] if v not in LABELS})
    if bad:
        raise SystemExit(f"unknown labels {bad}; use {LABELS}")
    res = {"items_both": len(common), "kappa": metrics.cohen_kappa([la[i] for i in common], [lb[i] for i in common]),
           "agreement": sum(la[i] == lb[i] for i in common) / len(common) if common else None}
    if key:
        with key.open(encoding="utf-8") as f:
            run_of = {row["item"]: row["run_id"] for row in csv.DictReader(f)}
        per: dict = defaultdict(Counter)
        for i in common:
            per[run_of.get(i, "?")]["agreed:" + la[i] if la[i] == lb[i] else "disagreed"] += 1
        res["per_run"] = {rid: dict(c) for rid, c in sorted(per.items())}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("files", nargs="+")
    e.add_argument("--n", type=int, default=80)
    e.add_argument("--out", default="results/grading")
    k = sub.add_parser("kappa")
    k.add_argument("a")
    k.add_argument("b")
    k.add_argument("--key")
    args = ap.parse_args()
    if args.cmd == "export":
        export(args.files, args.n, Path(args.out))
    else:
        print(json.dumps(kappa(Path(args.a), Path(args.b), Path(args.key) if args.key else None), indent=1))


if __name__ == "__main__":
    main()
