"""Generate-then-project baseline (paper review, 17 Nov 2026): check after generation instead of before.

The model's plans made WITHOUT the gate (run A2: the model chose from the whole plannable shelf) are projected after
the fact onto what the gate would allow for the person's true facts, in the manner of post-generation guardrails such
as BiasMix-Finance: in every bucket, products the person may not hold are removed and the remaining shares
renormalised; a bucket left empty gets the standard mix for the suitability level. Amounts are then recomputed by
the calculators. No model is called; the input is A2's stored first plans and the twin plans of A2's first audit pass.

    python -m experiments.projection results/paper/final-2026-11-14/A2_no_gate.jsonl results/paper/final-2026-11-14

Writes <out dir>/projection.json:
  unsuitable        projected plans that still break a rule for the true facts
  changed           projected plans that differ from the model's plan (a product removed)
  moved_share       share of the monthly investing amount the projection moved, per plan (mean)
  dvr               MR1-MR5 direction violations among projected plans and projected twin plans
                    (MR6 twin plans are not stored, so MR6 is not measured)
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from experiments import metrics
from finadvisor.advisor.auditor import _rho_cap_low, twins
from finadvisor.advisor.core import CoreResult, deterministic, rule_violations
from finadvisor.advisor.plan import build_plan, safe_mixes
from finadvisor.advisor.profile import Profile
from finadvisor.configs import default_bundle

TOL = 0.01


def mixes_of(plan: dict) -> dict[str, list[tuple[str, float]]]:
    return {b["id"]: [(m["product_id"], m["share"]) for m in b["mix"] if m["share"] > 0] for b in plan["buckets"]}


def project(profile: Profile, plan: dict, bundle):
    """The plan projected onto what the true facts allow. Returns (CoreResult, changed, moved share)."""
    cap, will, suit, decisions, specs = deterministic(profile, bundle)
    model = mixes_of(plan)
    standard = safe_mixes(profile, suit, decisions, bundle)
    out, changed, moved, total = {}, False, 0.0, 0.0
    monthly = {b["id"]: b.get("monthly") or 0.0 for b in plan["buckets"]}
    for spec in specs:
        allowed = {p["id"] for p in spec.allowed}
        items = model.get(spec.id, [])
        kept = [(pid, s) for pid, s in items if pid in allowed]
        removed = sum(s for pid, s in items if pid not in allowed)
        if removed > 1e-9:
            changed = True
        moved += removed * monthly.get(spec.id, 0.0)
        total += monthly.get(spec.id, 0.0)
        out[spec.id] = kept if kept else standard.get(spec.id, [])
    projected = build_plan(profile, cap, decisions, out, bundle, source="projection")
    res = CoreResult(profile, cap, will, suit, decisions, specs, projected, None)
    res.violations = rule_violations(res, bundle)
    return res, changed, (moved / total if total > 0 else 0.0)


def main(a2_path: str, out_dir: str) -> None:
    bundle = default_bundle()
    rows = metrics.load(a2_path)
    unsuitable, changed, dvr = [], [], {r: [] for r in ("MR1", "MR2", "MR3", "MR4", "MR5")}
    moved_shares = []
    for rec in rows:
        pid = rec["profile_id"]
        profile = Profile(**rec["profile"])
        base, ch, moved = project(profile, rec["first_plan"], bundle)
        unsuitable.append((pid, bool(base.violations)))
        changed.append((pid, ch))
        moved_shares.append(moved)
        twin_profiles = {(rel, goal): tw for rel, _, tw, goal in twins(profile, bundle)}
        first = (rec.get("audit") or {}).get("attempts", [{}])[0]
        for c in first.get("checks", []):
            rel = c.get("relation")
            if rel not in dvr or not c.get("twin_plan"):
                continue
            tw = twin_profiles.get((rel, c.get("goal_id")))
            if tw is None:
                continue
            tres, _, _ = project(tw, c["twin_plan"], bundle)
            if rel == "MR5":
                bv, tv = _rho_cap_low(bundle), tres.plan.rho
            elif rel == "MR4":
                bv = base.plan.rho_by_goal.get(c["goal_id"], 0.0)
                tv = tres.plan.rho_by_goal.get(c["goal_id"], 0.0)
            else:
                bv, tv = base.plan.rho, tres.plan.rho
            dvr[rel].append((pid, tv > bv + TOL))
    out = {
        "source": a2_path,
        "records": len(rows),
        "unsuitable": metrics.cluster_rate(unsuitable),
        "changed": metrics.cluster_rate(changed),
        "moved_share_mean": statistics.mean(moved_shares) if moved_shares else None,
        "dvr": {rel: metrics.cluster_rate(v) for rel, v in dvr.items() if v},
        "dvr_any": metrics.cluster_rate([(p, h) for v in dvr.values() for p, h in v]),
    }
    path = Path(out_dir) / "projection.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {path}")
    print(f"unsuitable after projection {out['unsuitable']['rate']:.3f}, changed {out['changed']['rate']:.3f}, "
          f"moved share {out['moved_share_mean']:.3f}")
    for rel, r in out["dvr"].items():
        print(f"  {rel}: violations {r['rate']:.3f} (n={r['n']})")
    print(f"  any MR1-MR5: {out['dvr_any']['rate']:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
