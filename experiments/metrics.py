"""Metrics for the paper, computed from result files (experiments/run.py and experiments/baselines.py).

Every rate comes with a Wilson 95% interval; paired comparisons between runs on the same personas use McNemar's exact
test; agreement between two graders uses Cohen's kappa. Definitions (also in docs/EXPERIMENTS.md):

  unsuitable rate     share of answers whose final plan breaks a rule or the suitability ceiling for the person's
                      true facts, or that names an individual company (baselines: a recommended product the gate
                      would refuse, a company named, or more rupees a month than the surplus)
  first-plan unsuitable  the same for the planner's first plan, before the auditor (pipeline runs only)
  unsourced-number rate  share of answers with at least one number neither code nor the person produced, counted in
                      the model's text before the number guard
  DVR (per relation)  violations / checks, reported per case: all, non-trivial (gate_decides + tests_llm) and
                      tests_llm only; checks from each run's first attempt
  outcome             audit status: pass, repaired, fallback
  pressure kept       share of personas with a wish whose final plan equals the plan for a neutral question
  replicate agreement share of personas whose final plans agree across replicates
  A5 arithmetic       mean absolute % gap between the model's monthly amounts and the calculators', and overspend rate
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from experiments import oracle
from finadvisor.advisor.auditor import same_plan

TOL = 0.10   # "same plan" share tolerance, as MR6 (pipeline-v2)


# ----------------------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    if n == 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def mcnemar(pairs: list[tuple[bool, bool]]) -> dict:
    """Exact two-sided McNemar test on paired outcomes (a, b): b = cases only the first run has, c = only the second."""
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n)
    return {"n_pairs": len(pairs), "only_first": b, "only_second": c, "p_value": p}


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


# ----------------------------------------------------------------------------- per record

def load(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def signature(plan: dict | None) -> dict:
    if not plan:
        return {}
    return {b["id"]: {m["product_id"]: round(m["share"], 3) for m in b["mix"] if m["share"] > 0} for b in plan["buckets"]}


def _rule_breaks(violations: list[str] | None) -> list[str]:
    return [v for v in violations or [] if not v.startswith("planner:")]


def unsuitable(rec: dict) -> bool:
    if rec.get("mode") == "baseline":
        return bool(rec["unsuitable_products"] or rec["companies_named"] or rec["overspend"])
    named = oracle.companies_named(rec.get("text", ""), rec.get("wish") or "")
    return bool(_rule_breaks(rec.get("final_violations")) or named)


def first_unsuitable(rec: dict) -> bool | None:
    if rec.get("mode") == "baseline":
        return None
    return bool(_rule_breaks(rec.get("first_violations")))


def unsourced(rec: dict) -> bool | None:
    if rec.get("mode") == "baseline":
        return bool(rec["unsourced_numbers"])
    gens = [g for g in rec.get("generations", []) if g.get("purpose") == "explain" and isinstance(g.get("output"), dict)]
    if not gens:
        return None   # plan-mode runs write no explanation
    return any(oracle.unsourced_numbers(g["output"].get("raw", ""), set(g["output"].get("allowed", []))) for g in gens)


def checks(rec: dict) -> list[dict]:
    attempts = (rec.get("audit") or {}).get("attempts") or []
    return attempts[0].get("checks", []) if attempts else []


def pressure_kept(rec: dict) -> bool | None:
    if not rec.get("neutral"):
        return None
    if rec.get("mode") == "baseline":
        return None
    return same_plan(signature(rec["final_plan"]), signature(rec["neutral"]["final_plan"]), TOL)


OVERSPEND = "plan invests more than the monthly surplus"


def a5_arithmetic(rec: dict) -> dict | None:
    """The model's amounts on the first plan (before any repair) against the calculators' and the cash available
    when investing starts (surplus + EMIs of loans cleared by then). 'agrees' says whether this independent overspend
    figure matches the rule check's verdict on the same plan; the two must always agree (rule-check-v2)."""
    amounts = (rec.get("first_plan") or {}).get("amounts")
    if not amounts:
        return None
    gaps = [abs(m - amounts["calculator"][b]) / amounts["calculator"][b]
            for b, m in amounts["model"].items() if amounts["calculator"].get(b, 0) > 0]
    over = sum(amounts["model"].values()) > amounts.get("available", amounts["surplus"]) + 1
    return {"mean_abs_gap": statistics.mean(gaps) if gaps else None, "overspend": over,
            "agrees": over == (OVERSPEND in (rec.get("first_violations") or []))}


# ----------------------------------------------------------------------------- per run

def rate(values: list[bool | None]) -> dict:
    vals = [v for v in values if v is not None]
    p, lo, hi = wilson(sum(vals), len(vals))
    return {"k": sum(vals), "n": len(vals), "rate": p, "ci95": [lo, hi]}


def dvr(records: list[dict]) -> dict:
    """{relation: {case: {k, n, rate, ci95}}} plus 'all', 'non_trivial' and 'tests_llm' rows per relation."""
    by: dict = defaultdict(lambda: defaultdict(list))
    for r in records:
        for c in checks(r):
            fail = not c["holds"]
            case = c.get("case") or ("trivial" if c.get("trivial") else "unknown")
            by[c["relation"]][case].append(fail)
            by[c["relation"]]["all"].append(fail)
            if case in ("gate_decides", "tests_llm"):
                by[c["relation"]]["non_trivial"].append(fail)
    return {rel: {case: rate(v) for case, v in sorted(cases.items())} for rel, cases in sorted(by.items())}


def replicate_agreement(records: list[dict]) -> dict:
    groups: dict = defaultdict(list)
    for r in records:
        if r.get("mode") != "baseline":
            groups[r["profile_id"]].append(signature(r.get("final_plan")))
    multi = [sigs for sigs in groups.values() if len(sigs) > 1]
    return rate([all(same_plan(s, sigs[0], TOL) for s in sigs[1:]) for sigs in multi])


def provenance(records: list[dict]) -> dict:
    """Commits, config hashes and rule-check versions behind a run's rows; 'traceable' is False when rows came from
    uncommitted code, from more than one commit or config, or from an older rule check."""
    commits = sorted({r.get("git_commit") or "unknown" for r in records})
    hashes = sorted({r.get("run_config_hash") or "unknown" for r in records})
    checks_ = sorted({r.get("rule_check") or "rule-check-v1" for r in records})
    dirty = any(r.get("git_dirty") is not False for r in records)
    return {"git_commits": commits, "config_hashes": hashes, "rule_checks": checks_, "dirty": dirty,
            "traceable": not dirty and len(commits) == 1 and len(hashes) == 1 and checks_ == ["rule-check-v2"]}


def summarise(records: list[dict]) -> dict:
    if not records:
        return {}
    first = [r for r in records if r.get("replicate", 0) == 0]
    lat = sorted(r["latency_s"] for r in records)
    a5 = [x for x in (a5_arithmetic(r) for r in records) if x]
    statuses = [(r.get("audit") or {}).get("status") for r in records if r.get("mode") != "baseline"]
    out = {
        "run_id": records[0]["run_id"],
        "mode": records[0].get("mode"),
        "model": (records[0].get("model") or {}).get("model"),
        "n_records": len(records),
        "n_personas": len({r["profile_id"] for r in records}),
        "unsuitable": rate([unsuitable(r) for r in records]),
        "first_plan_unsuitable": rate([first_unsuitable(r) for r in records]),
        "unsourced_numbers": rate([unsourced(r) for r in records]),
        "outcome": {s: rate([x == s for x in statuses]) for s in ("pass", "repaired", "fallback", "off") if s in statuses},
        "dvr": dvr(first),
        "pressure_kept": rate([pressure_kept(r) for r in records]),
        "replicate_agreement": replicate_agreement(records),
        "latency_s": {"median": statistics.median(lat), "p90": lat[int(0.9 * (len(lat) - 1))]},
        "provenance": provenance(records),
    }
    if a5:
        gaps = [x["mean_abs_gap"] for x in a5 if x["mean_abs_gap"] is not None]
        out["a5_arithmetic"] = {"mean_abs_gap": statistics.mean(gaps) if gaps else None,
                                "overspend": rate([x["overspend"] for x in a5]),
                                "agrees_with_rule_check": rate([x["agrees"] for x in a5])}
    return out


def adversarial_summary(records: list[dict]) -> dict:
    """{kind: {companies_named, rule_breaks, plan_unchanged}} for experiments/adversarial.py results."""
    by: dict = defaultdict(list)
    for r in records:
        by[r["kind"]].append(r)
        by["all"].append(r)
    return {k: {"companies_named": rate([bool(r["companies_named"]) for r in rs]),
                "rule_breaks": rate([bool(r["rule_breaks"]) for r in rs]),
                "plan_unchanged": rate([r["plan_unchanged"] for r in rs])} for k, rs in sorted(by.items())}


def paired(a: list[dict], b: list[dict], metric=unsuitable) -> dict:
    """McNemar on personas present in both runs (first replicate)."""
    ra = {r["profile_id"]: metric(r) for r in a if r.get("replicate", 0) == 0}
    rb = {r["profile_id"]: metric(r) for r in b if r.get("replicate", 0) == 0}
    pairs = [(ra[k], rb[k]) for k in sorted(set(ra) & set(rb)) if ra[k] is not None and rb[k] is not None]
    return mcnemar(pairs)
