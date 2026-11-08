"""One quick pass over every paper config before the long runs: 1 replicate, the first N personas (adversarial: one
persona per suitability level and the first N turns), then the report. Checks that no config crashes and that every
table is produced.

    python -m experiments.smoke_paper                      # the models each config names (on Colab, before the runs)
    python -m experiments.smoke_paper --model tiny-test    # plumbing only, no model needed (seconds)

Writes to results/smoke/ (never results/paper/), starting fresh each time.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

import yaml

from experiments import adversarial, baselines, report
from experiments import run as runner
from experiments.run import ROOT

PAPER = ROOT / "experiments" / "configs" / "paper"
TABLES = ("| Run | Model |", "## DVR per relation", "## A5: the model's own arithmetic", "## Provenance",
          "## Paired comparisons with", "## Adversarial")


def entry(cfg: dict):
    if "baseline" in cfg:
        return baselines.main
    if "turns" in cfg:
        return adversarial.main
    return runner.main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="use this model for every config instead of the one it names")
    ap.add_argument("--n", type=int, default=20, help="personas per config (adversarial: turns)")
    ap.add_argument("--only", nargs="*", help="run_id prefixes to run (default: all)")
    args = ap.parse_args()
    out_dir = ROOT / "results" / "smoke"
    shutil.rmtree(out_dir, ignore_errors=True)
    (out_dir / "configs").mkdir(parents=True)
    failed, outputs = [], []
    for path in sorted(PAPER.glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        if args.only and not any(cfg["run_id"].startswith(p) for p in args.only):
            continue
        cfg.update(replicates=1, limit=args.n, output=f"results/smoke/{cfg['run_id']}.jsonl")
        if "turns" in cfg:
            cfg["per_level"] = 1
        if args.model:
            cfg["model"] = args.model
        tmp = out_dir / "configs" / path.name
        tmp.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
        t0 = time.perf_counter()
        try:
            entry(cfg)(str(tmp))
            outputs.append(str(ROOT / cfg["output"]))
            print(f"OK    {cfg['run_id']}  {time.perf_counter() - t0:.0f} s", flush=True)
        except Exception:   # keep going so one pass shows every broken config
            failed.append(cfg["run_id"])
            print(f"FAIL  {cfg['run_id']}\n{traceback.format_exc()}", flush=True)
    rep = out_dir / "report.md"
    argv = sys.argv
    sys.argv = ["report", *outputs, "--reference", "A1_full", "--out", str(rep)]
    try:
        report.main()
    finally:
        sys.argv = argv
    text = rep.read_text(encoding="utf-8")
    missing = [t for t in TABLES if t not in text]
    print(f"\nreport: {rep}\nconfigs failed: {failed or 'none'}\ntables missing: {missing or 'none'}")
    if failed or missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
