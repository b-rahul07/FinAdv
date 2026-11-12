"""LaTeX tables for the paper, generated from the report's JSON so no number is ever typed by hand.

    python -m experiments.report results/paper/*.jsonl --reference A1_full --out results/paper/report.md
    python -m experiments.paper_tables results/paper/report.json --out results/paper/tables

Writes one .tex file per table (booktabs; \\input them). Rates are "p [lo, hi]" in percent; n is personas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

NAMES = {
    "B1_plain_llm": "B1 plain model", "B2_llm_rag": "B2 model + RAG", "B3_rules_in_prompt": "B3 rules in the prompt",
    "A1_full": "FinAdvisor (full)", "A2_no_gate": "A2 no gate", "A3_no_auditor": "A3 no auditor",
    "A4_no_number_guard": "A4 no number guard", "A5_no_calculators": "A5 no calculators",
    "A6_no_pressure_fence": "A6 no pressure fence", "A1T_full_turn": "FinAdvisor (full reply)",
    "S1_rules_v1": "S1 capacity formula v1", "S1_emergency_3m": "S1 emergency fund 3 months",
    "S2_mr6_risk": "S2 MR6 by risky share", "M1_qwen2.5-1.5b": "M1 qwen2.5 1.5B", "M1_qwen2.5-7b": "M1 qwen2.5 7B",
    "M1_phi4-mini": "M1 phi4-mini", "M1_llama3.2-3b": "M1 llama3.2 3B",
}
MAIN = ["B1_plain_llm", "B2_llm_rag", "B3_rules_in_prompt", "A1_full", "A1T_full_turn"]
ABLATIONS = ["A1_full", "A2_no_gate", "A3_no_auditor", "A5_no_calculators", "A6_no_pressure_fence", "A1T_full_turn",
             "A4_no_number_guard", "S1_rules_v1", "S1_emergency_3m", "S2_mr6_risk"]
MODELS = ["A1_full", "M1_qwen2.5-1.5b", "M1_qwen2.5-7b", "M1_phi4-mini", "M1_llama3.2-3b"]


def esc(s: str) -> str:
    return s.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_")


def pct(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "--"
    lo, hi = r["ci95"]
    return f"{100 * r['rate']:.1f} [{100 * lo:.1f}, {100 * hi:.1f}]"


def name(rid: str) -> str:
    return esc(NAMES.get(rid, rid))


def table(caption: str, label: str, header: list[str], rows: list[list[str]], note: str = "") -> str:
    cols = "l" + "r" * (len(header) - 1)
    out = ["\\begin{table*}[t]", "\\centering", "\\small", f"\\caption{{{caption}}}", f"\\label{{{label}}}",
           f"\\begin{{tabular}}{{{cols}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule"]
    out += [" & ".join(r) + " \\\\" for r in rows]
    out += ["\\bottomrule", "\\end{tabular}"]
    if note:
        out.append(f"\\par\\smallskip\\footnotesize {note}")
    out.append("\\end{table*}")
    return "\n".join(out) + "\n"


def main_table(runs: dict, ids: list[str], caption: str, label: str) -> str:
    rows = []
    for rid in ids:
        s = runs.get(rid)
        if not s:
            continue
        o = s["outcome"]
        rows.append([name(rid), str(s["n_personas"]), pct(s["unsuitable"]), pct(s["unsuitable_text"]),
                     pct(s["unsourced_numbers"]), pct(o.get("fallback")), pct(s["pressure_kept"]),
                     f"{s['latency_s']['median']:.1f}"])
    return table(caption, label,
                 ["System", "$n$", "Unsuitable (\\%)", "Unsuitable, text oracle (\\%)", "Unsourced numbers (\\%)",
                  "Fallback (\\%)", "Pressure kept (\\%)", "Median s"], rows,
                 "95\\% intervals: Wilson with one observation per persona, persona-level cluster bootstrap with "
                 "replicates. Unsuitable: the final plan breaks a rule or the suitability ceiling for the true facts, or "
                 "a company is named; baselines are judged on their ALLOCATION block. Fallback: the deterministic safe "
                 "plan was shown. Pressure kept: personas with a wish whose plan equals their neutral plan.")


def dvr_table(runs: dict, ids: list[str]) -> str:
    rows = []
    for rid in ids:
        s = runs.get(rid)
        if not s:
            continue
        for rel, cases in s["dvr"].items():
            rows.append([name(rid), rel, pct(cases.get("all")), pct(cases.get("non_trivial")), pct(cases.get("tests_llm")),
                         str((cases.get("trivial") or {}).get("n", 0))])
    return table("Direction-violation rate per relation on the first attempt, by what could make a check fail",
                 "tab:dvr", ["System", "Relation", "All (\\%)", "Non-trivial (\\%)", "Tests the model (\\%)", "Trivial checks"],
                 rows, "Trivial: no risky product is allowed for the twin, so the relation holds by construction. "
                       "Non-trivial: the gate decides part of the check or only the model's choice can fail it.")


def causes_table(runs: dict, ids: list[str]) -> str:
    rows = []
    for rid in ids:
        s = runs.get(rid)
        if not s or not s.get("first_attempt_causes"):
            continue
        for i, (cause, r) in enumerate(s["first_attempt_causes"].items()):
            rows.append([name(rid) if i == 0 else "", esc(cause), pct(r),
                         pct(s["mr6_only_on_low_risk_menu"]) if i == 0 else ""])
    return table("Why first plans were not accepted (share of audited records; a record can have several causes)",
                 "tab:causes", ["System", "Cause", "Share (\\%)", "MR6 only, all-low-risk menu (\\%)"], rows)


def personalisation_table(runs: dict, ids: list[str]) -> str:
    rows = []
    f = lambda v: "--" if v is None else f"{v:.2f}"
    for rid in ids:
        s = runs.get(rid)
        if not s:
            continue
        p, g = s["personalisation"], s["surrogate"]
        sim = "--" if p["mean"] is None else f"{p['mean']:.2f}" + (
            f" [{p['ci95'][0]:.2f}, {p['ci95'][1]:.2f}]" if p["ci95"][0] is not None else "")
        rows.append([name(rid), sim, f(g["r2"]), f(g["capacity_share"]), f(g["willingness_share"]), f(g["fc"])])
    return table("Personalisation and what drives the risky share of the advice", "tab:personalisation",
                 ["System", "Plan similarity", "Surrogate $R^2$", "Capacity share", "Willingness share", "FC"], rows,
                 "Plan similarity: mean pairwise weighted Jaccard of the plans different personas received (1 = the "
                 "same plan for everyone). Surrogate: ridge regression of the risky share on the persona's features; "
                 "shares are the normalised importance on capacity features (savings, EMIs, cover, card dues, costly "
                 "loans) and willingness features (questionnaire score, experience). FC: feature concentration.")


def adversarial_table(adv: dict) -> str:
    rows = []
    for rid, kinds in adv.items():
        for kind, x in kinds.items():
            rows.append([esc(kind), pct(x["companies_named"]), pct(x["rule_breaks"]), pct(x["plan_unchanged"])])
    return table("Adversarial turns through the full reply (intervals resample by turn)", "tab:adversarial",
                 ["Kind", "Companies named (\\%)", "Rules broken (\\%)", "Plan unchanged (\\%)"], rows)


def paired_table(paired: list[dict]) -> str:
    rows = [[name(t["run"]), esc(t["metric"]), str(t["n_pairs"]), str(t["only_first"]), str(t["only_second"]),
             f"{t['p_value']:.3g}", f"{t['p_holm']:.3g}"] for t in paired]
    return table("Paired comparisons with the full system (exact McNemar on replicate 0, Holm-adjusted over the table)",
                 "tab:paired", ["System", "Metric", "Pairs", "Only FinAdvisor", "Only this system", "$p$", "$p$ (Holm)"], rows)


def write_all(report_json: Path, out: Path) -> list[Path]:
    data = json.loads(report_json.read_text(encoding="utf-8"))
    runs, adv, paired = data["runs"], data.get("adversarial", {}), data.get("paired", [])
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "main.tex": main_table(runs, MAIN, "Main result: the same model plain, with retrieval, with the rules in its "
                               "prompt, and inside FinAdvisor", "tab:main"),
        "ablations.tex": main_table(runs, ABLATIONS, "Ablations and sensitivity (FinAdvisor with one component off or "
                                    "one definition changed)", "tab:ablations"),
        "models.tex": main_table(runs, MODELS, "Model size and family (FinAdvisor settings of A1)", "tab:models"),
        "dvr.tex": dvr_table(runs, ["A1_full", "A2_no_gate", "S2_mr6_risk"]),
        "causes.tex": causes_table(runs, ["A1_full", "S2_mr6_risk", "A2_no_gate"]),
        "personalisation.tex": personalisation_table(runs, MAIN + ["A2_no_gate", "A3_no_auditor"]),
    }
    if adv:
        files["adversarial.tex"] = adversarial_table(adv)
    if paired:
        files["paired.tex"] = paired_table(paired)
    written = []
    for fname, text in files.items():
        p = out / fname
        p.write_text(text, encoding="utf-8")
        written.append(p)
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report_json")
    ap.add_argument("--out", default="results/paper/tables")
    args = ap.parse_args()
    for p in write_all(Path(args.report_json), Path(args.out)):
        print("wrote", p)


if __name__ == "__main__":
    main()
