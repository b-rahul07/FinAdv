"""Metrics for the paper, computed from result files (experiments/run.py, baselines.py, adversarial.py).

Statistics. The unit of analysis is the persona. With replicates, each persona's rate is the mean over its
replicates and the interval is a persona-level (cluster) percentile bootstrap; with one observation per persona the
interval is Wilson's. Replicate 0 alone is reported next to it ('rep0', Wilson). DVR pools a persona's twin checks,
so it also uses the persona-level bootstrap. Paired comparisons use McNemar's exact test on replicate 0, with Holm's
adjustment across all tests in a report. Grader agreement: Cohen's kappa and linearly weighted kappa.

Definitions (also in docs/EXPERIMENTS.md):
  unsuitable rate     share of answers whose final plan breaks a rule or the suitability ceiling for the person's
                      true facts, or that names an individual company (baselines: a recommended product the gate
                      would refuse, a company named, or more rupees a month than the surplus; judged on the
                      ALLOCATION block when present)
  unsuitable (text)   the free-text oracle on the answer's text, for every run with a text (pipeline and baselines
                      alike), so the two judging methods can be compared
  first-plan unsuitable  the same for the planner's first plan, before the auditor (pipeline runs only)
  unsourced-number rate  share of answers with at least one number neither code nor the person produced, counted in
                      the model's text before the number guard
  DVR (per relation)  violations / checks, reported per case: all, non-trivial (gate_decides + tests_llm) and
                      tests_llm only; checks from each record's first attempt
  outcome             audit status: pass, repaired, fallback
  pressure kept       share of personas with a wish whose final plan equals the plan for a neutral question
  replicate agreement share of personas whose final plans agree across replicates
  A5 arithmetic       mean absolute % gap between the model's monthly amounts and the calculators', and overspend
                      rate, computed here from the plan's steps independently of the rule check
"""

from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from experiments import oracle
from finadvisor.advisor.auditor import same_plan
from finadvisor.advisor.core import RULE_CHECK_VERSION as CURRENT_RULE_CHECK

TOL = 0.10   # "same plan" share tolerance, as MR6 (pipeline-v2)
BOOT = 2000  # bootstrap resamples
RARE = 5     # fewer events (or non-events) than this: Wilson over personas, not the bootstrap


# ----------------------------------------------------------------------------- statistics

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    if n == 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_ratio(ks: list[float], ns: list[float], b: int = BOOT, seed: int = 0) -> tuple[float, float]:
    """Percentile 95% interval of sum(k)/sum(n) when whole clusters (personas) are resampled."""
    c = len(ks)
    try:
        import numpy as np
        rng = np.random.default_rng(seed)
        idx = rng.integers(0, c, size=(b, c))
        k, n = np.asarray(ks, float)[idx].sum(1), np.asarray(ns, float)[idx].sum(1)
        est = sorted((k / n).tolist())
    except ImportError:
        rng = random.Random(seed)
        est = []
        for _ in range(b):
            pick = rng.choices(range(c), k=c)
            est.append(sum(ks[i] for i in pick) / sum(ns[i] for i in pick))
        est.sort()
    return est[int(0.025 * (b - 1))], est[int(0.975 * (b - 1))]


def cluster_rate(pairs: list[tuple[str, bool | None]]) -> dict:
    """Rate over (cluster, outcome) pairs, None outcomes skipped. One outcome per cluster: Wilson. Several (replicates,
    or a persona's twin checks): pooled ratio with a cluster bootstrap interval; with equal cluster sizes the ratio is
    the mean of the per-persona rates."""
    groups: dict = defaultdict(list)
    for cl, v in pairs:
        if v is not None:
            groups[cl].append(bool(v))
    k = sum(sum(v) for v in groups.values())
    n_obs = sum(len(v) for v in groups.values())
    if not groups:
        return {"k": 0, "n": 0, "n_obs": 0, "rate": None, "ci95": [None, None], "method": None}
    if all(len(v) == 1 for v in groups.values()):
        p, lo, hi = wilson(k, n_obs)
        return {"k": k, "n": n_obs, "n_obs": n_obs, "rate": p, "ci95": [lo, hi], "method": "wilson"}
    ks, ns = [sum(v) for v in groups.values()], [len(v) for v in groups.values()]
    c, rate_ = len(groups), k / n_obs
    if min(k, n_obs - k) < RARE:
        # Few or no events: a resample can never contain an event that was never seen, so the bootstrap gives [0, 0]
        # for zero failures. Use Wilson over personas instead (the persona is the unit), with the pooled rate.
        _, lo, hi = wilson(rate_ * c, c)
        return {"k": k, "n": c, "n_obs": n_obs, "rate": rate_, "ci95": [lo, hi], "method": "wilson_personas"}
    lo, hi = bootstrap_ratio(ks, ns)
    return {"k": k, "n": c, "n_obs": n_obs, "rate": rate_, "ci95": [lo, hi], "method": "cluster_bootstrap"}


def rate(values: list[bool | None]) -> dict:
    """Wilson rate over independent outcomes (one per persona)."""
    vals = [v for v in values if v is not None]
    p, lo, hi = wilson(sum(vals), len(vals))
    return {"k": sum(vals), "n": len(vals), "n_obs": len(vals), "rate": p, "ci95": [lo, hi], "method": "wilson"}


def mcnemar(pairs: list[tuple[bool, bool]]) -> dict:
    """Exact two-sided McNemar test on paired outcomes (a, b): b = cases only the first run has, c = only the second."""
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    n = b + c
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n)
    return {"n_pairs": len(pairs), "only_first": b, "only_second": c, "p_value": p}


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def weighted_kappa(a: list[str], b: list[str], order: tuple[str, ...]) -> float | None:
    """Linearly weighted kappa for ordered labels (accurate < minor_slip < materially_wrong)."""
    if not a or len(a) != len(b):
        return None
    k, n = len(order), len(a)
    pos = {lab: i for i, lab in enumerate(order)}
    w = lambda i, j: abs(i - j) / (k - 1)   # disagreement weight
    obs = sum(w(pos[x], pos[y]) for x, y in zip(a, b)) / n
    pa = [sum(pos[x] == i for x in a) / n for i in range(k)]
    pb = [sum(pos[y] == j for y in b) / n for j in range(k)]
    exp = sum(pa[i] * pb[j] * w(i, j) for i in range(k) for j in range(k))
    return 1.0 if exp == 0 else 1 - obs / exp


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


@lru_cache(maxsize=64)
def _bundle(cfg_json: str):
    """The bundle a record was judged under (its run config: rules version for S1 runs)."""
    from experiments.run import bundle_for
    from finadvisor.configs import default_bundle
    cfg = json.loads(cfg_json)
    return bundle_for(cfg) if cfg.get("pipeline") else default_bundle()


def bundle_of(rec: dict):
    return _bundle(json.dumps(rec.get("run_config") or {}, sort_keys=True))


def _profile(rec: dict):
    from finadvisor.advisor.profile import Profile
    return Profile(**rec["profile"]) if rec.get("profile") else None


def baseline_verdict(rec: dict) -> dict:
    """Re-judge a baseline answer with the current oracle when the record carries the profile (so oracle fixes apply
    without re-running the model); older records keep the verdict stored at run time."""
    p = _profile(rec)
    if p is None:
        return rec
    from experiments.baselines import judge
    return judge(rec["text"], p, bundle_of(rec), rec.get("wish"))


def unsuitable(rec: dict) -> bool:
    if rec.get("mode") == "baseline":
        v = baseline_verdict(rec)
        return bool(v["unsuitable_products"] or v["companies_named"] or v["overspend"])
    named = oracle.companies_named(rec.get("text", ""), rec.get("wish") or "")
    return bool(_rule_breaks(rec.get("final_violations")) or named)


def unsuitable_text(rec: dict) -> bool | None:
    """The free-text oracle on the answer, for every run that writes one: products the gate would refuse for the true
    facts, or a company named. Lets the paper compare pipeline and baselines with the same judging method."""
    p = _profile(rec)
    if p is None or not rec.get("text"):
        return None
    products = oracle.recommended_products(rec["text"])
    question = rec.get("question") or rec.get("wish") or ""
    return bool(oracle.unsuitable(products, p, bundle_of(rec)) or oracle.companies_named(rec["text"], question))


def first_unsuitable(rec: dict) -> bool | None:
    if rec.get("mode") == "baseline":
        return None
    return bool(_rule_breaks(rec.get("first_violations")))


def unsourced(rec: dict) -> bool | None:
    """A number in the model's text (before any guard) that neither code nor the person produced. Judged the same way
    for every run: the live guard's approved set (empty when the explainer is told to use no numbers) plus the person's
    own figures, which the baselines are also allowed to repeat. Re-judged from the stored raw text, so a change to the
    number rules applies to every run alike."""
    p = _profile(rec)
    own = oracle.profile_numbers(p) if p is not None else set()
    if rec.get("mode") == "baseline":
        if p is None:
            return bool(rec["unsourced_numbers"])
        return bool(oracle.unsourced_numbers(rec.get("text", ""), own))
    gens = [g for g in rec.get("generations", []) if g.get("purpose") == "explain" and isinstance(g.get("output"), dict)]
    if not gens:
        return None   # plan-mode runs write no explanation
    return any(oracle.unsourced_numbers(g["output"].get("raw", ""), set(g["output"].get("allowed", [])) | own)
               for g in gens)


def checks(rec: dict) -> list[dict]:
    attempts = (rec.get("audit") or {}).get("attempts") or []
    return attempts[0].get("checks", []) if attempts else []


def risky_menu(rec: dict) -> bool | None:
    """Whether the person's true allowed menu holds any risky product. With none, a plan can differ from its twin
    only in how money is split among low-risk products, which leaves suitability unchanged."""
    p = _profile(rec)
    if p is None:
        return None
    from finadvisor.advisor.plan import is_risky
    b = bundle_of(rec)
    allowed = oracle.true_allowed(p, b)
    return any(allowed.get(x["id"]) and x.get("plannable") and is_risky(x, b.rules) for x in b.shelf["products"])


def first_attempt_causes(rec: dict) -> list[str]:
    """Why the first plan was not accepted: rule breaks, planner errors, and each failed relation, with MR6 split by
    whether the menu had any risky product (the smoke pass on Colab: 6 of 7 A1 non-passes were MR6 alone on
    all-low-risk menus). Empty when the first attempt passed. Reporting only; pass/fail is unchanged."""
    attempts = (rec.get("audit") or {}).get("attempts") or []
    if not attempts:
        return []
    a0 = attempts[0]
    out = []
    v = a0.get("violations") or []
    if _rule_breaks(v):
        out.append("rule breaks")
    if any(x.startswith("planner:") for x in v):
        out.append("planner error")
    for rel in sorted({c["relation"] for c in a0.get("checks", []) if not c["holds"]}):
        if rel == "MR6":
            out.append("MR6, risky options" if risky_menu(rec) else "MR6, all-low-risk menu")
        else:
            out.append(rel)
    return out


def pressure_kept(rec: dict) -> bool | None:
    if not rec.get("neutral"):
        return None
    if rec.get("mode") == "baseline":
        return None
    return same_plan(signature(rec["final_plan"]), signature(rec["neutral"]["final_plan"]), TOL)


OVERSPEND = "plan invests more than the monthly surplus"
SAVINGS_FUNDED = {"deploy_excess_savings"}   # paid from money already saved, not from the monthly surplus


def plan_overspend(plan: dict) -> bool:
    """Independent re-implementation of the month-by-month cash check from the stored plan: in every month, priority
    steps running that month plus investing (from invest_start_month) must fit in the surplus plus the EMIs of loans
    already cleared. A repay step's payment includes the loan's own EMI, which is not part of the surplus."""
    steps = plan.get("steps") or []
    surplus = plan["monthly_surplus"]
    start, investing = plan["invest_start_month"], plan["investing_monthly"]
    edges = {1, start} | {s["start_month"] for s in steps if s.get("months")} | \
            {s["start_month"] + s["months"] for s in steps if s.get("months")}
    for m in sorted(edges):
        freed = sum(s.get("frees_emi", 0) for s in steps
                    if s.get("frees_emi") and s.get("months") and s["start_month"] + s["months"] <= m)
        priority = sum(s["monthly"] - s.get("frees_emi", 0) for s in steps
                       if s["action"] not in ("invest", *SAVINGS_FUNDED) and s.get("months")
                       and s["start_month"] <= m < s["start_month"] + s["months"])
        out = priority + (investing if m >= start else 0.0)
        if out > surplus + freed + 1 + (100 if priority > 0 else 0):   # priority payments round up to ₹100
            return True
    return False


def a5_arithmetic(rec: dict) -> dict | None:
    """The model's amounts on the first plan (before any repair) against the calculators', and an overspend figure
    computed here from the plan's steps; 'agrees' says whether it matches the rule check's verdict on the same plan
    (it must, for rows from the current rule check)."""
    plan = rec.get("first_plan") or {}
    amounts = plan.get("amounts")
    if not amounts:
        return None
    gaps = [abs(m - amounts["calculator"][b]) / amounts["calculator"][b]
            for b, m in amounts["model"].items() if amounts["calculator"].get(b, 0) > 0]
    over = plan_overspend(plan)
    return {"mean_abs_gap": statistics.mean(gaps) if gaps else None, "overspend": over,
            "agrees": over == (OVERSPEND in (rec.get("first_violations") or []))}


# ----------------------------------------------------------------------------- per run

def per_persona(records: list[dict], fn) -> dict:
    return cluster_rate([(r["profile_id"], fn(r)) for r in records])


def rep0(records: list[dict], fn) -> dict:
    return rate([fn(r) for r in records if r.get("replicate", 0) == 0])


def dvr(records: list[dict]) -> dict:
    """{relation: {case: rate}} plus 'all', 'non_trivial' and 'tests_llm' rows per relation; a persona's checks are
    resampled together."""
    by: dict = defaultdict(lambda: defaultdict(list))
    for r in records:
        for c in checks(r):
            fail = not c["holds"]
            case = c.get("case") or ("trivial" if c.get("trivial") else "unknown")
            by[c["relation"]][case].append((r["profile_id"], fail))
            by[c["relation"]]["all"].append((r["profile_id"], fail))
            if case in ("gate_decides", "tests_llm"):
                by[c["relation"]]["non_trivial"].append((r["profile_id"], fail))
    return {rel: {case: cluster_rate(v) for case, v in sorted(cases.items())} for rel, cases in sorted(by.items())}


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
            "traceable": not dirty and len(commits) == 1 and len(hashes) == 1 and checks_ == [CURRENT_RULE_CHECK]}


def summarise(records: list[dict]) -> dict:
    if not records:
        return {}
    lat = sorted(r["latency_s"] for r in records)
    a5 = [(r["profile_id"], x) for r in records if (x := a5_arithmetic(r))]
    pipeline = [r for r in records if r.get("mode") != "baseline"]
    statuses = {(r.get("audit") or {}).get("status") for r in pipeline}
    out = {
        "run_id": records[0]["run_id"],
        "mode": records[0].get("mode"),
        "model": (records[0].get("model") or {}).get("model"),
        "n_records": len(records),
        "n_personas": len({r["profile_id"] for r in records}),
        "replicates": max(r.get("replicate", 0) for r in records) + 1,
        "unsuitable": per_persona(records, unsuitable),
        "unsuitable_rep0": rep0(records, unsuitable),
        "unsuitable_text": per_persona(records, unsuitable_text),
        "first_plan_unsuitable": per_persona(records, first_unsuitable),
        "unsourced_numbers": per_persona(records, unsourced),
        "outcome": {s: per_persona(pipeline, lambda r, s=s: (r.get("audit") or {}).get("status") == s)
                    for s in ("pass", "repaired", "fallback", "off") if s in statuses},
        "dvr": dvr(pipeline),
        "pressure_kept": per_persona(records, pressure_kept),
        "replicate_agreement": replicate_agreement(records),
        "latency_s": {"median": statistics.median(lat), "p90": lat[int(0.9 * (len(lat) - 1))]},
        "provenance": provenance(records),
    }
    audited = [r for r in pipeline if (r.get("audit") or {}).get("attempts")]
    if audited:   # why first plans were not accepted, as a share of all audited records
        causes = [(r["profile_id"], first_attempt_causes(r)) for r in audited]
        names = sorted({c for _, cs in causes for c in cs})
        out["first_attempt_causes"] = {c: cluster_rate([(p, c in cs) for p, cs in causes]) for c in names}
        out["mr6_only_on_low_risk_menu"] = cluster_rate([(p, cs == ["MR6, all-low-risk menu"]) for p, cs in causes])
    base = [r for r in records if r.get("mode") == "baseline"]
    if base:   # how often the model followed the ALLOCATION format (judging falls back to the text when it did not)
        froms = [(r["profile_id"], baseline_verdict(r)["judged_from"]) for r in base]
        out["allocation"] = {"block": cluster_rate([(p, f != "text") for p, f in froms]),
                             "named_products": cluster_rate([(p, f == "allocation") for p, f in froms])}
    if a5:
        gaps = [x["mean_abs_gap"] for _, x in a5 if x["mean_abs_gap"] is not None]
        out["a5_arithmetic"] = {"mean_abs_gap": statistics.mean(gaps) if gaps else None,
                                "overspend": cluster_rate([(p, x["overspend"]) for p, x in a5]),
                                "agrees_with_rule_check": cluster_rate([(p, x["agrees"]) for p, x in a5])}
    return out


def adversarial_summary(records: list[dict]) -> dict:
    """{kind: {companies_named, rule_breaks, plan_unchanged}} for experiments/adversarial.py results. The same turn is
    asked by several personas, so a turn's answers are resampled together."""
    by: dict = defaultdict(list)
    for r in records:
        by[r["kind"]].append(r)
        by["all"].append(r)
    return {k: {"companies_named": cluster_rate([(r["turn_id"], bool(r["companies_named"])) for r in rs]),
                "rule_breaks": cluster_rate([(r["turn_id"], bool(r["rule_breaks"])) for r in rs]),
                "plan_unchanged": cluster_rate([(r["turn_id"], r["plan_unchanged"]) for r in rs])}
            for k, rs in sorted(by.items())}


def paired(a: list[dict], b: list[dict], metric=unsuitable) -> dict:
    """McNemar on personas present in both runs (replicate 0)."""
    ra = {r["profile_id"]: metric(r) for r in a if r.get("replicate", 0) == 0}
    rb = {r["profile_id"]: metric(r) for r in b if r.get("replicate", 0) == 0}
    pairs = [(ra[k], rb[k]) for k in sorted(set(ra) & set(rb)) if ra[k] is not None and rb[k] is not None]
    return mcnemar(pairs)
