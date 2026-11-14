"""Analyses added after reviewing the draft (15 Nov 2026; docs/PAPER_PLAN.md §9), computed from stored records only.

    python -m experiments.run experiments/configs/analysis/STD_standard_mix.yaml      # seconds, no model
    python -m experiments.analysis results/paper/final-2026-11-14 results/analysis/STD_standard_mix.jsonl

Writes <run dir>/analysis.json, read by experiments/paper_assets.py:
  standard_mix   the pipeline with no model choice: unsuitable rate, plan similarity, latency
  vs_standard    per model run: final plans identical to the standard mix for the same persona, and plans whose risky
                 share is lower / higher than the standard mix's (what the model's choice changed)
  baselines      the unsuitable rate split into "product or company" and "overspend", the share of personas with no
                 surplus, answers that repeat a line, and the rate on a robust subset (a surplus to invest, a
                 complete ALLOCATION block, no repeated lines)
Rates are persona-level with the report's intervals (metrics.cluster_rate).
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

from experiments import metrics
from finadvisor.advisor.auditor import same_plan
from finadvisor.advisor.profile import Profile

MODEL_RUNS = ["A1_full", "M1_qwen2.5-1.5b", "M1_llama3.2-3b", "M1_phi4-mini", "M1_qwen2.5-7b", "S2_mr6_risk",
              "A1N_no_anchor", "A1N7_no_anchor_7b"]
BASELINES = ["B1_plain_llm", "B2_llm_rag", "B3_rules_in_prompt", "B1L_plain_llm_long", "B3L_rules_in_prompt_long",
             "B3L7_rules_in_prompt_7b"]
LOOP_LINES = 4          # a line of more than 15 characters repeated this often counts as a loop


def sig(plan: dict) -> dict:
    return {b["id"]: {m["product_id"]: round(m["share"], 3) for m in b["mix"] if m["share"] > 0} for b in plan["buckets"]}


def loops(text: str) -> bool:
    lines = collections.Counter(x.strip() for x in (text or "").splitlines() if len(x.strip()) > 15)
    return max(lines.values(), default=0) >= LOOP_LINES


def rate(pairs: list[tuple[str, bool]]) -> dict | None:
    return metrics.cluster_rate(pairs) if pairs else None


def standard_mix(std: list[dict]) -> dict:
    return {"unsuitable": rate([(r["profile_id"], metrics.unsuitable(r)) for r in std]),
            "personalisation": metrics.personalisation(std),
            "median_latency_s": statistics.median(r["latency_s"] for r in std)}


def vs_standard(records: list[dict], std: dict[str, dict]) -> dict:
    same, lower, higher, own = [], [], [], []
    for r in records:
        s = std[r["profile_id"]]["final_plan"]
        p = r["final_plan"]
        same.append((r["profile_id"], same_plan(sig(p), sig(s), 0.0)))
        lower.append((r["profile_id"], p["rho"] < s["rho"] - 0.01))
        higher.append((r["profile_id"], p["rho"] > s["rho"] + 0.01))
        if r["audit"].get("status") != "fallback":
            own.append((r["profile_id"], same_plan(sig(p), sig(s), 0.0)))
    return {"identical": rate(same), "lower_risk": rate(lower), "higher_risk": rate(higher),
            "identical_when_not_fallback": rate(own)}


def baselines(records: list[dict]) -> dict:
    prod, over, anyu, robust, loop, nosurplus = [], [], [], [], [], []
    for r in records:
        v = metrics.baseline_verdict(r)
        p = Profile(**r["profile"])
        pid = r["profile_id"]
        pc = bool(v["unsuitable_products"] or v["companies_named"])
        prod.append((pid, pc))
        over.append((pid, bool(v["overspend"])))
        anyu.append((pid, pc or bool(v["overspend"])))
        loop.append((pid, loops(r["text"])))
        nosurplus.append((pid, p.monthly_surplus <= 0))
        if p.monthly_surplus > 0 and v.get("judged_from") != "text" and not loops(r["text"]):
            robust.append((pid, pc or bool(v["overspend"])))
    return {"unsuitable": rate(anyu), "product_or_company": rate(prod), "overspend": rate(over),
            "loops": rate(loop), "no_surplus": rate(nosurplus), "robust_subset": rate(robust),
            "robust_rows": len(robust), "rows": len(records)}


def main(run_dir: str, std_path: str) -> None:
    run_dir = Path(run_dir)
    std = metrics.load(std_path)
    by_persona = {r["profile_id"]: r for r in std}
    out = {"standard_mix": standard_mix(std), "standard_mix_summary": metrics.summarise(std), "vs_standard": {},
           "baselines": {}}
    for rid in MODEL_RUNS:
        f = run_dir / f"{rid}.jsonl"
        if f.exists():
            out["vs_standard"][rid] = vs_standard(metrics.load(f), by_persona)
    for rid in BASELINES:
        f = run_dir / f"{rid}.jsonl"
        if f.exists():
            out["baselines"][rid] = baselines(metrics.load(f))
    (run_dir / "analysis.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {run_dir / 'analysis.json'}")
    s = out["standard_mix"]
    print(f"standard mix: unsuitable {s['unsuitable']['rate']:.3f}, similarity {s['personalisation']['mean']:.2f}")
    for rid, x in out["vs_standard"].items():
        print(f"{rid:22s} identical {x['identical']['rate']:.3f}  lower {x['lower_risk']['rate']:.3f}  "
              f"higher {x['higher_risk']['rate']:.3f}")
    for rid, x in out["baselines"].items():
        print(f"{rid:24s} any {x['unsuitable']['rate']:.3f}  product {x['product_or_company']['rate']:.3f}  "
              f"overspend {x['overspend']['rate']:.3f}  robust {x['robust_subset']['rate']:.3f} "
              f"({x['robust_rows']} rows)  loops {x['loops']['rate']:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
