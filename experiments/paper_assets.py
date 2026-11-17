"""Everything the 6-page paper shows, generated from the report's JSON and the checks' outputs, so no number in the
paper is typed by hand.

    python -m experiments.paper_assets results/paper/final-2026-11-14 --out <paper folder>/generated

Reads <run dir>/report.json and <run dir>/checks/{sebi_check.md, sebi_check_unsecured.md, rules_rework.txt}. Writes:
  numbers.tex       \\val{RUN}{metric} -> "89.3", \\vci{RUN}{metric} -> "89.3% [85.7, 92.6]", plus named counts;
                    an unknown name stops LaTeX with an error instead of printing nothing
  tab_results.tex   one compact table: baselines, FinAdvisor, ablations, sensitivity, models
  tab_checks.tex    rule-by-rule agreement with SEBI's tool; written rules against the engines
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABEL = {
    "B1_plain_llm": "B1 plain model", "B2_llm_rag": "B2 model + RAG", "B3_rules_in_prompt": "B3 rules in prompt",
    "A1_full": "FinAdvisor (A1)", "STD_standard_mix": "Standard mix only, no model", "A1T_full_turn": "A1T full reply", "A2_no_gate": "A2 no gate",
    "A3_no_auditor": "A3 no auditor", "A4_no_number_guard": "A4 no number guard",
    "A5_no_calculators": "A5 no calculators", "A6_no_pressure_fence": "A6 no pressure fence",
    "S1_rules_v1": "S1 capacity formula v1", "S1_emergency_3m": "S1 3-month emergency fund",
    "S2_mr6_risk": "S2 MR6 by risky share", "M1_qwen2.5-1.5b": "M1 qwen2.5 1.5B", "M1_qwen2.5-7b": "M1 qwen2.5 7B",
    "M1_phi4-mini": "M1 phi4-mini 3.8B", "M1_llama3.2-3b": "M1 llama3.2 3B",
}
GROUPS = [
    ("Baselines (qwen2.5 3B)", ["B1_plain_llm", "B2_llm_rag", "B3_rules_in_prompt"]),
    ("FinAdvisor (qwen2.5 3B)", ["A1_full", "A1T_full_turn", "STD_standard_mix"]),
    ("Ablations", ["A2_no_gate", "A3_no_auditor", "A4_no_number_guard", "A5_no_calculators", "A6_no_pressure_fence"]),
    ("Sensitivity", ["S1_rules_v1", "S1_emergency_3m", "S2_mr6_risk"]),
    ("Other models", ["M1_qwen2.5-1.5b", "M1_llama3.2-3b", "M1_phi4-mini", "M1_qwen2.5-7b"]),
]


def rate(r: dict | None):
    return None if not r or r.get("rate") is None else r


def p1(x: float) -> str:
    return f"{100 * x:.1f}"


def cell(r: dict | None, ci: bool = True) -> str:
    r = rate(r)
    if r is None:
        return "--"
    lo, hi = r["ci95"]
    return f"{p1(r['rate'])}" + (f" {{\\tiny[{p1(lo)}, {p1(hi)}]}}" if ci else "")


def metrics(s: dict) -> dict[str, dict | None]:
    out = s.get("outcome") or {}
    return {"unsuitable": s.get("unsuitable"), "first": s.get("first_plan_unsuitable"),
            "text": s.get("unsuitable_text"), "unsourced": s.get("unsourced_numbers"),
            "pass": out.get("pass"), "repaired": out.get("repaired"), "fallback": out.get("fallback"),
            "pressure": s.get("pressure_kept"), "agreement": s.get("replicate_agreement")}


# --------------------------------------------------------------------------- numbers.tex

def tex_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s)


def numbers_tex(report: dict, checks: dict) -> str:
    defs: list[tuple[str, str]] = []
    runs = report["runs"]
    for rid, s in runs.items():
        for m, r in metrics(s).items():
            r = rate(r)
            if r is None:
                continue
            lo, hi = r["ci95"]
            defs.append((f"v@{rid}@{m}", p1(r["rate"])))
            defs.append((f"ci@{rid}@{m}", f"{p1(r['rate'])}\\,\\% [{p1(lo)}, {p1(hi)}]"))
            defs.append((f"n@{rid}@{m}", str(r["n"])))
        lat = s.get("latency_s") or {}
        if lat.get("median") is not None:
            defs.append((f"v@{rid}@latency", f"{lat['median']:.1f}"))
        for rel, cases in (s.get("dvr") or {}).items():
            for case, r in cases.items():
                r = rate(r) if isinstance(r, dict) else None
                if r is not None:
                    defs.append((f"v@{rid}@dvr{rel}{case}", p1(r["rate"])))
                    defs.append((f"n@{rid}@dvr{rel}{case}", str(r["n"])))
        for cause, r in (s.get("first_attempt_causes") or {}).items():
            if rate(r):
                defs.append((f"v@{rid}@cause{tex_name(cause)}", p1(r["rate"])))
        if rate(s.get("mr6_only_on_low_risk_menu")):
            defs.append((f"v@{rid}@mrsixlowonly", p1(s["mr6_only_on_low_risk_menu"]["rate"])))
        pers = s.get("personalisation") or {}
        if pers.get("mean") is not None:
            defs.append((f"v@{rid}@similarity", f"{pers['mean']:.2f}"))
        sur = s.get("surrogate") or {}
        if sur.get("r2") is not None:
            defs.append((f"v@{rid}@surrogateRtwo", f"{sur['r2']:.2f}"))
            defs.append((f"v@{rid}@capacityshare", f"{100 * sur['capacity_share']:.0f}"))
            defs.append((f"v@{rid}@willingnessshare", f"{100 * sur['willingness_share']:.0f}"))
        a5 = s.get("a5_arithmetic")
        if a5:
            defs.append((f"v@{rid}@gapmedian", f"{100 * a5['median_abs_gap']:.0f}"))
            defs.append((f"v@{rid}@gaplo", f"{100 * a5['gap_quartiles'][0]:.0f}"))
            defs.append((f"v@{rid}@gaphi", f"{100 * a5['gap_quartiles'][1]:.0f}"))
            defs.append((f"v@{rid}@gapn", str(a5["rows_with_gap"])))
            defs.append((f"v@{rid}@overspend", p1(a5["overspend"]["rate"])))
        block = s.get("allocation") or {}
        for k, r in block.items():
            if isinstance(r, dict) and rate(r):
                defs.append((f"v@{rid}@block{tex_name(k)}", p1(r["rate"])))
    for row in report.get("paired") or []:
        rid = row["run"]
        defs.append((f"v@{rid}@pairedonly", str(row["only_second"])))
        defs.append((f"v@{rid}@pairedholm", sci(row["p_holm"])))
    adv = report.get("adversarial") or {}
    for rid, kinds in adv.items():
        a = kinds.get("all") or {}
        for m, r in a.items():
            if rate(r):
                defs.append((f"v@{rid}@{m}", p1(r["rate"])))
                defs.append((f"n@{rid}@{m}", str(r["n"])))
    for k, v in checks.items():
        defs.append((f"c@{k}", v))
    an = report.get("_analysis") or {}
    std = an.get("standard_mix") or {}
    if std:
        defs.append(("v@STD@similarity", f"{std['personalisation']['mean']:.2f}"))
        lo, hi = std["personalisation"]["ci95"]
        defs.append(("v@STD@similarityci", f"{lo:.2f}--{hi:.2f}"))
        defs.append(("v@STD@unsuitable", p1(std["unsuitable"]["rate"])))
        defs.append(("v@STD@latencyms", f"{1000 * std['median_latency_s']:.0f}"))
    summ = an.get("standard_mix_summary") or {}
    fb = ((summ.get("outcome") or {}).get("fallback")) or {}
    if fb:
        defs.append(("v@STD@fallbackk", str(fb["k"])))
        defs.append(("v@STD@n", str(fb["n"])))
    for rid, x in (an.get("vs_standard") or {}).items():
        for k in ("identical", "lower_risk", "higher_risk", "identical_when_not_fallback"):
            if rate(x.get(k)):
                defs.append((f"v@{rid}@{tex_name(k)}std", p1(x[k]["rate"])))
                defs.append((f"ci@{rid}@{tex_name(k)}std", ci_text(x[k])))
    for rid, x in (an.get("baselines") or {}).items():
        for k in ("product_or_company", "overspend", "loops", "no_surplus", "robust_subset"):
            if rate(x.get(k)):
                defs.append((f"v@{rid}@{tex_name(k)}", p1(x[k]["rate"])))
                defs.append((f"ci@{rid}@{tex_name(k)}", ci_text(x[k])))
        defs.append((f"n@{rid}@robustrows", str(x["robust_rows"])))
    lines = ["% Generated by experiments/paper_assets.py from report.json; do not edit.",
             "\\newcommand{\\fetch}[1]{\\ifcsname #1\\endcsname\\csname #1\\endcsname\\else"
             "\\errmessage{paper number #1 is not in numbers.tex}\\fi}",
             "\\newcommand{\\val}[2]{\\fetch{v@#1@#2}}",
             "\\newcommand{\\vci}[2]{\\fetch{ci@#1@#2}}",
             "\\newcommand{\\nof}[2]{\\fetch{n@#1@#2}}",
             "\\newcommand{\\chk}[1]{\\fetch{c@#1}}"]
    lines += [f"\\expandafter\\def\\csname {k}\\endcsname{{{v}}}" for k, v in defs]
    return "\n".join(lines) + "\n"


def ci_text(r: dict) -> str:
    lo, hi = r["ci95"]
    return f"{p1(r['rate'])}\\,\\% [{p1(lo)}, {p1(hi)}]"


def sci(p: float) -> str:
    if p >= 0.001:
        return f"{p:.3f}"
    mant, exp = f"{p:.1e}".split("e")
    return f"{mant}\\times10^{{{int(exp)}}}"


def find_paired(report: dict) -> list[dict]:
    return report.get("paired") or []


# --------------------------------------------------------------------------- checks

def parse_checks(run_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, key in (("sebi_check.md", "v2"), ("sebi_check_unsecured.md", "unsec")):
        text = (run_dir / "checks" / name).read_text(encoding="utf-8")
        for m in re.finditer(r"^\| (R\d) \| .*? \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| ([\d.]+)% \|$", text, re.M):
            rule, both, neither, eng, tool, agree = m.groups()
            out[f"sebi{key}{rule}agree"] = f"{float(agree):.0f}"
            out[f"sebi{key}{rule}both"], out[f"sebi{key}{rule}neither"] = both, neither
            out[f"sebi{key}{rule}engine"], out[f"sebi{key}{rule}tool"] = eng, tool
        m = re.search(r"suitability for (\d+) \{'medium -> low': (\d+), 'high -> low': (\d+)\}", text)
        if m:
            out["unsecsuitchanged"], out["unsecmedlow"], out["unsechighlow"] = m.groups()
        m = re.search(r"capacity level changes for (\d+)", text)
        if m:
            out["unseccapchanged"] = m.group(1)
        m = re.search(r"read (\d{4}-\d{2}-\d{2})", text)
        if m:
            out["sebidate"] = m.group(1)
    rework = (run_dir / "checks" / "rules_rework.txt").read_text(encoding="utf-8")
    for field, k, n in re.findall(r"^(\w+): (\d+) of (\d+) agree", rework, re.M):
        out[f"rework{field}"] = k
        out["reworkn"] = n
    return out


def tab_checks(c: dict[str, str]) -> str:
    rows = [("R1", "emergency fund $<$ 6 months"), ("R2", "life cover $<15\\times$ income"),
            ("R3", "health cover too low"), ("R4", "card dues or costly loan"), ("R5", "EMIs $>$ 40\\% of pay")]
    body = "\n".join(f"{r} & {what} & {c[f'sebiv2{r}both']} & {c[f'sebiv2{r}neither']} & {c[f'sebiv2{r}engine']} & "
                     f"{c[f'sebiv2{r}tool']} & {c[f'sebiv2{r}agree']} \\\\" for r, what in rows)
    return ("\\begin{table}[t]\n\\centering\n\\caption{Rule-by-Rule Agreement With SEBI's Financial Health Check "
            f"\\cite{{sebi2023healthcheck}} on the {c['reworkn']} Personas}}\n\\label{{tab:checks}}\n\\footnotesize\n\\setlength{{\\tabcolsep}}{{2.5pt}}\n"
            "\\begin{tabular}{@{}llrrrrr@{}}\n\\toprule\n"
            "\\textbf{Rule} & \\textbf{Fires when} & \\textbf{Both} & \\textbf{Neither} & \\textbf{Engine} & "
            "\\textbf{Tool} & \\textbf{Agree} \\\\\n"
            " & & \\textbf{flag} & \\textbf{flags} & \\textbf{only} & \\textbf{only} & \\textbf{(\\%)} \\\\\n\\midrule\n"
            f"{body}\n\\bottomrule\n\\end{{tabular}}\n\\end{{table}}\n")


# --------------------------------------------------------------------------- results table

def tab_results(report: dict) -> str:
    runs = report["runs"]
    head = " & ".join(f"\\textbf{{{h}}}" for h in ("System", "Unsuitable, final", "Unsuitable, first plan",
                                                   "Unsourced numbers", "Pass", "Fallback", "Pressure kept",
                                                   "Median s")) + " \\\\"
    rows = []
    std = (report.get("_analysis") or {}).get("standard_mix_summary")
    if std:   # the pipeline with no model choice (experiments/analysis.py), shown with FinAdvisor
        runs = {**runs, "STD_standard_mix": std}
    for title, ids in GROUPS:
        rows.append(f"\\multicolumn{{8}}{{@{{}}l}}{{\\textit{{{title}}}}} \\\\")
        for rid in ids:
            if rid not in runs:
                continue
            m, s = metrics(runs[rid]), runs[rid]
            lat = (s.get("latency_s") or {}).get("median")
            rows.append(" & ".join([LABEL[rid], cell(m["unsuitable"]), cell(m["first"]), cell(m["unsourced"]),
                                    cell(m["pass"]), cell(m["fallback"]), cell(m["pressure"]),
                                    f"{lat:.1f}" if lat is not None else "--"]) + " \\\\")
    return ("\\begin{table*}[t]\n\\centering\n\\caption{Results on 240 Personas With Three Replicates (Rates in \\%, With "
            "95\\% Persona-Level Intervals)}\n\\label{tab:results}\n\\scriptsize\n\\setlength{\\tabcolsep}{4pt}\n"
            "\\begin{tabular}{@{}lrrrrrrr@{}}\n\\toprule\n" + head + "\n\\midrule\n" + "\n".join(rows) +
            "\n\\bottomrule\n\\end{tabular}\n\\par\\smallskip\\parbox{\\textwidth}{\\scriptsize Definitions in "
            "Section~\\ref{sec:metrics}. Pass: first plan accepted; fallback: standard mix shown (the rest repaired). "
            "Median latency on one T4 GPU. --: not applicable.}"
            "\n\\end{table*}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--followup", help="a follow-up run directory (report.json, analysis.json) for text macros")
    ap.add_argument("--site-eval", help="the website's advice-evaluation records (jsonl) for text macros")
    a = ap.parse_args()
    run_dir, out = Path(a.run_dir), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    if (run_dir / "analysis.json").exists():          # experiments/analysis.py (review of 15 Nov 2026)
        report["_analysis"] = json.loads((run_dir / "analysis.json").read_text(encoding="utf-8"))
    checks = parse_checks(run_dir)
    table_report = json.loads(json.dumps(report))     # the tables and figures show the reported runs only
    if a.followup:
        # Follow-up runs (docs/PAPER_PLAN.md §9): their numbers become macros for the text; runs already in the main
        # report keep the main report's values.
        fdir = Path(a.followup)
        fr = json.loads((fdir / "report.json").read_text(encoding="utf-8"))
        for rid, s in fr["runs"].items():
            report["runs"].setdefault(rid, s)
        have = {r["run"] for r in report.get("paired") or []}
        report["paired"] = (report.get("paired") or []) + [r for r in fr.get("paired") or [] if r["run"] not in have]
        if (fdir / "analysis.json").exists():
            fa = json.loads((fdir / "analysis.json").read_text(encoding="utf-8"))
            an = report.setdefault("_analysis", {})
            for key in ("vs_standard", "baselines"):
                for rid, x in (fa.get(key) or {}).items():
                    an.setdefault(key, {}).setdefault(rid, x)
    if a.site_eval:
        # The website's own advice evaluation (experiments/eval_advice.py: its pipeline file and model on its CPU host)
        import statistics
        rows = [json.loads(x) for x in Path(a.site_eval).read_text(encoding="utf-8").splitlines() if x.strip()]
        by: dict[str, list[float]] = {}
        for r in rows:
            by.setdefault(r["route"], []).append(r["seconds"])
        site = {"turns": str(len(rows)), "passed": str(sum(1 for r in rows if not r["fails"])),
                "personas": str(len({r["persona"] for r in rows})), "model": rows[0]["model"]["model"]}
        for route, secs in by.items():
            site[f"{route}median"] = f"{statistics.median(secs):.1f}"
            site[f"{route}n"] = str(len(secs))
        checks = {**checks, **{f"site{k}": v for k, v in site.items()}}
    (out / "numbers.tex").write_text(numbers_tex(report, checks), encoding="utf-8")
    (out / "tab_results.tex").write_text(tab_results(table_report), encoding="utf-8")
    (out / "tab_checks.tex").write_text(tab_checks(checks), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
