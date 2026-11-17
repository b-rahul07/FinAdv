"""Summary of the fact-extraction runs (X1_extract_*: prompt v1, X2_extract_*: prompt v2; experiments/extract_eval.py).

    python -m experiments.extract_report results/paper/followup-2026-11-15

Writes <dir>/extraction.json, per model:
  raw_recall           fields the model read correctly / all fields (the model's own reading)
  accepted_recall      fields the confirmation card would show correctly / all fields (after grounding)
  accepted_precision   correct values / values the card would show (how often a shown value is right)
  by_field, by_wording the same rates per field and per wording
Rates are persona-level (metrics.cluster_rate).
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

from experiments import metrics
from experiments.extract_eval import FIELDS, WORDINGS


def summarise(rows: list[dict]) -> dict:
    raw, acc, prec = [], [], []
    by_field = {f: {"raw": [], "acc": [], "prec": []} for f in FIELDS}
    by_wording = {w: {"raw": [], "acc": [], "prec": []} for w in WORDINGS}
    for r in rows:
        pid = r["profile_id"]
        for w, v in r["wordings"].items():
            for f in FIELDS:
                rc, ac = v["raw_correct"][f], v["accepted_correct"][f]
                shown = v["accepted"][f] is not None
                for bucket in (by_field[f], by_wording[w]):
                    bucket["raw"].append((pid, rc))
                    bucket["acc"].append((pid, ac))
                    if shown:
                        bucket["prec"].append((pid, ac))
                raw.append((pid, rc))
                acc.append((pid, ac))
                if shown:
                    prec.append((pid, ac))

    def rates(d):
        return {"raw_recall": metrics.cluster_rate(d["raw"]), "accepted_recall": metrics.cluster_rate(d["acc"]),
                "accepted_precision": metrics.cluster_rate(d["prec"]) if d["prec"] else None}

    return {"model": rows[0]["model"]["model"], "personas": len({r["profile_id"] for r in rows}),
            "raw_recall": metrics.cluster_rate(raw), "accepted_recall": metrics.cluster_rate(acc),
            "accepted_precision": metrics.cluster_rate(prec),
            "by_field": {f: rates(d) for f, d in by_field.items()},
            "by_wording": {w: rates(d) for w, d in by_wording.items()}}


def main(run_dir: str) -> None:
    out = {}
    for f in sorted(glob.glob(str(Path(run_dir) / "X[0-9]_extract_*.jsonl"))):
        rid = Path(f).stem
        out[rid] = summarise(metrics.load(f))
        s = out[rid]
        print(f"{rid:26s} {s['model']:14s} raw recall {s['raw_recall']['rate']:.3f}  shown recall "
              f"{s['accepted_recall']['rate']:.3f}  shown precision {s['accepted_precision']['rate']:.3f}")
        for w, d in s["by_wording"].items():
            print(f"   {w:7s} raw {d['raw_recall']['rate']:.3f}  shown precision "
                  f"{(d['accepted_precision'] or {}).get('rate', float('nan')):.3f}")
    path = Path(run_dir) / "extraction.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1])
