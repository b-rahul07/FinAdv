"""Turn result files into the paper's tables.

    python -m experiments.report results/paper/*.jsonl --reference A1 --out results/paper/report.md

Writes a markdown report (main table, DVR per relation and case, paired McNemar tests against the reference run) and
a JSON file with every number next to it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments import metrics


def pct(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "—"
    lo, hi = r["ci95"]
    star = "*" if r.get("method") == "cluster_bootstrap" else ""
    return f"{r['rate']:.1%} [{lo:.1%}, {hi:.1%}]{star} (n={r['n']})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--reference", help="run_id (or its prefix) to compare every other run with")
    ap.add_argument("--out", default="results/report.md")
    args = ap.parse_args()
    runs, adversarial = {}, {}
    for f in args.files:
        recs = metrics.load(f)
        if recs:
            (adversarial if recs[0].get("mode") == "adversarial" else runs).setdefault(recs[0]["run_id"], []).extend(recs)
    summaries = {rid: metrics.summarise(recs) for rid, recs in runs.items()}
    adv = {rid: metrics.adversarial_summary(recs) for rid, recs in adversarial.items()}

    lines = ["# FinAdvisor experiment report", "",
             "The unit is the persona: n counts personas (DVR: personas whose checks are pooled; adversarial: turns). "
             "Intervals are 95%: Wilson with one observation per persona, or a persona-level cluster bootstrap "
             "(marked *) when replicates or several checks per persona are pooled. 'Replicate 0' is the first "
             "replicate alone (Wilson). 'Text oracle' judges every run's answer text the same way as the baselines.", "",
             "| Run | Model | Personas | Reps | Unsuitable (final) | Unsuitable (replicate 0) | Unsuitable (text oracle) | "
             "Unsuitable (first plan) | Unsourced numbers | Pass | Fallback | Pressure kept | Replicate agreement | "
             "Median latency |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for rid, s in summaries.items():
        o = s["outcome"]
        lines.append(f"| {rid} | {s['model']} | {s['n_personas']} | {s['replicates']} | {pct(s['unsuitable'])} | "
                     f"{pct(s['unsuitable_rep0'])} | {pct(s['unsuitable_text'])} | {pct(s['first_plan_unsuitable'])} | "
                     f"{pct(s['unsourced_numbers'])} | {pct(o.get('pass'))} | {pct(o.get('fallback'))} | "
                     f"{pct(s['pressure_kept'])} | {pct(s['replicate_agreement'])} | {s['latency_s']['median']:.1f} s |")
    lines += ["", "## DVR per relation (first attempt)", "",
              "| Run | Relation | All | Non-trivial | Tests the LLM | Trivial checks |", "|---|---|---|---|---|---|"]
    for rid, s in summaries.items():
        for rel, cases in s["dvr"].items():
            lines.append(f"| {rid} | {rel} | {pct(cases.get('all'))} | {pct(cases.get('non_trivial'))} | "
                         f"{pct(cases.get('tests_llm'))} | {(cases.get('trivial') or {}).get('n', 0)} |")
    a5 = {rid: s["a5_arithmetic"] for rid, s in summaries.items() if "a5_arithmetic" in s}
    if a5:
        lines += ["", "## A5: the model's own arithmetic", "",
                  "| Run | Mean gap vs calculators | Overspend | Agrees with rule check |", "|---|---|---|---|"]
        for rid, x in a5.items():
            gap = f"{x['mean_abs_gap']:.1%}" if x["mean_abs_gap"] is not None else "—"
            lines.append(f"| {rid} | {gap} | {pct(x['overspend'])} | {pct(x['agrees_with_rule_check'])} |")
    causes = {rid: s for rid, s in summaries.items() if s.get("first_attempt_causes")}
    if causes:
        lines += ["", "## Why first plans were not accepted", "",
                  "Share of audited records whose first plan failed for each reason (a record can have several). "
                  "'MR6 only, low-risk menu': the only failure was a wording twin splitting money differently among "
                  "low-risk products, which leaves suitability unchanged.", "",
                  "| Run | Cause | Share | MR6 only, low-risk menu |", "|---|---|---|---|"]
        for rid, s in causes.items():
            for i, (cause, r) in enumerate(s["first_attempt_causes"].items()):
                lines.append(f"| {rid} | {cause} | {pct(r)} | {pct(s['mr6_only_on_low_risk_menu']) if i == 0 else ''} |")
    alloc = {rid: s["allocation"] for rid, s in summaries.items() if "allocation" in s}
    if alloc:
        lines += ["", "## Baseline ALLOCATION block", "",
                  "Answers that ended with a parsable block (judged on it), and blocks that named a product the oracle "
                  "recognises (otherwise products come from the text).", "",
                  "| Run | Block present | Block names products |", "|---|---|---|"]
        for rid, x in alloc.items():
            lines.append(f"| {rid} | {pct(x['block'])} | {pct(x['named_products'])} |")
    lines += ["", "## Provenance", "", "| Run | Commit | Config hash | Rule check | Traceable |", "|---|---|---|---|---|"]
    for rid, s in summaries.items():
        p = s["provenance"]
        lines.append(f"| {rid} | {', '.join(c[:10] for c in p['git_commits'])} | {', '.join(h[:10] for h in p['config_hashes'])} | "
                     f"{', '.join(p['rule_checks'])} | {'yes' if p['traceable'] else 'NO' + (' (uncommitted code)' if p['dirty'] else '')} |")
    if args.reference:
        ref = next((rid for rid in runs if rid.startswith(args.reference)), None)
        if ref:
            lines += ["", f"## Paired comparisons with {ref} (McNemar, exact, replicate 0)", "",
                      "Holm-adjusted p-values are corrected over every test in this table.", "",
                      "| Run | Metric | Personas | Only reference | Only this run | p | p (Holm) |",
                      "|---|---|---|---|---|---|---|"]
            tests = []
            for rid in runs:
                if rid == ref:
                    continue
                for name, fn in (("unsuitable", metrics.unsuitable), ("unsuitable (text oracle)", metrics.unsuitable_text),
                                 ("unsourced numbers", metrics.unsourced)):
                    m = metrics.paired(runs[ref], runs[rid], fn)
                    if m["n_pairs"]:
                        tests.append((rid, name, m))
            for (rid, name, m), adj in zip(tests, metrics.holm([m["p_value"] for _, _, m in tests])):
                m["p_holm"] = adj
                lines.append(f"| {rid} | {name} | {m['n_pairs']} | {m['only_first']} | {m['only_second']} | "
                             f"{m['p_value']:.3g} | {adj:.3g} |")
            paired_out = [{"run": rid, "metric": name, **m} for rid, name, m in tests]
    for rid, kinds in adv.items():
        lines += ["", f"## Adversarial turns: {rid}", "", "| Kind | Companies named | Rules broken | Plan unchanged |",
                  "|---|---|---|---|"]
        for kind, x in kinds.items():
            lines.append(f"| {kind} | {pct(x['companies_named'])} | {pct(x['rule_breaks'])} | {pct(x['plan_unchanged'])} |")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"runs": summaries, "adversarial": adv,
                                                    "paired": locals().get("paired_out", [])}, indent=1, default=str),
                                        encoding="utf-8")
    print(f"{len(runs)} runs -> {out} (+ .json)")


if __name__ == "__main__":
    main()
