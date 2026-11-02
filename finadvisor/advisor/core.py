"""One pass of the deterministic stages plus the planner, honouring stage flags (report §7.2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from finadvisor.advisor import capacity as capacity_mod
from finadvisor.advisor import willingness as willingness_mod
from finadvisor.advisor.capacity import CapacityResult
from finadvisor.advisor.gate import GateDecision, allowed_for_goal, gate, suitability
from finadvisor.advisor.plan import BucketSpec, Plan, bucket_specs, build_plan, safe_mixes
from finadvisor.advisor.planner import PlannerOutput, choose_mixes
from finadvisor.advisor.profile import Profile
from finadvisor.advisor.willingness import WillingnessResult
from finadvisor.llm.base import LLM, Generation


@dataclass
class CoreResult:
    profile: Profile
    capacity: CapacityResult | None
    willingness: WillingnessResult | None
    suitability: str
    decisions: list[GateDecision]
    specs: list[BucketSpec]
    plan: Plan
    planner: PlannerOutput | None
    violations: list[str] = field(default_factory=list)

    @property
    def generations(self) -> list[Generation]:
        return [self.planner.generation] if self.planner and self.planner.generation else []


def _no_capacity(profile: Profile, rules: dict) -> CapacityResult:
    """Stand-in when the capacity stage is switched off: no rules fire, nothing limits suitability."""
    cap = capacity_mod.assess(profile, rules)
    return CapacityResult(cap.E, cap.D, cap.Y, 1, 1, 1, 1, 1, 1.0, "high", [])


def deterministic(profile: Profile, bundle) -> tuple[CapacityResult, WillingnessResult | None, str, list[GateDecision], list[BucketSpec]]:
    st = bundle.pipeline["stages"]
    rules, shelf = bundle.rules, bundle.shelf
    cap = capacity_mod.assess(profile, rules) if st["capacity"] else _no_capacity(profile, rules)
    will = willingness_mod.assess(profile, bundle.willingness) if st["willingness"] else None
    suit = suitability(cap if st["capacity"] else None, will)
    if st["gate"]:
        decisions = gate(suit, cap.rule_ids, profile, shelf, rules)
        specs = bucket_specs(profile, decisions, rules)
    else:
        decisions = [GateDecision(p, True) for p in shelf["products"]]
        specs = [BucketSpec(s.id, s.name, s.goal, [p for p in shelf["products"] if p.get("plannable")])
                 for s in bucket_specs(profile, decisions, rules)]
    return cap, will, suit, decisions, specs


def plan_once(profile: Profile, bundle, llm: LLM, *, style: str = "plain", repair_hint: list[str] | None = None,
              wish: str | None = None, use_safe_mix: bool = False) -> CoreResult:
    st = bundle.pipeline["stages"]
    if not st["calculators"]:
        raise NotImplementedError("The calculators-off ablation is built with the experiment runner (Phase 4).")
    cap, will, suit, decisions, specs = deterministic(profile, bundle)
    standard = bundle.pipeline.get("planner", {}).get("mode", "model") == "standard"
    if use_safe_mix or standard:
        # planner.mode standard (the website since 2026-11-02): the tested mix for the suitability level, no model
        # call. The auditor still checks it against its twins (MR1-MR5; MR6 holds by construction).
        out = None
        mixes = safe_mixes(profile, suit, decisions, bundle)
        source = "standard" if standard and not use_safe_mix else "safe_fallback"
    else:
        anchors = None
        if bundle.pipeline.get("planner", {}).get("anchor_mix", False):
            # Small models copy list order; a suitability-matched starting point gives them a sensible base to adjust.
            code_of = {p["id"]: p.get("code", p["id"]) for p in bundle.shelf["products"]}
            anchors = {bid: ",".join(f"{code_of[pid]}:{max(1, round(share * 10))}" for pid, share in mix)
                       for bid, mix in safe_mixes(profile, suit, decisions, bundle).items() if mix}
        out = choose_mixes(llm, profile, suit, specs, style=style, repair_hint=repair_hint, anchors=anchors,
                           wish=None if st["pressure_fence"] else wish,
                           codes={p.get("code", p["id"]): p["id"] for p in bundle.shelf["products"]})
        mixes = out.mixes
        source = "repair" if repair_hint else "planner"
    plan = build_plan(profile, cap, decisions, mixes, bundle, source=source)
    res = CoreResult(profile, cap if st["capacity"] else None, will, suit, decisions, specs, plan, out)
    res.violations = rule_violations(res, bundle)
    return res


def rule_violations(res: CoreResult, bundle) -> list[str]:
    """What a plan may never do (R1–R7 and the shelf), checked against the TRUE facts, not stage flags."""
    rules, shelf = bundle.rules, bundle.shelf
    true_cap = capacity_mod.assess(res.profile, rules)
    true_will = willingness_mod.assess(res.profile, bundle.willingness)
    true_suit = suitability(true_cap, true_will)
    true_decisions = {d.id: d for d in gate(true_suit, true_cap.rule_ids, res.profile, shelf, rules)}
    goals = {g.id: g for g in res.profile.goals}
    out: list[str] = []
    if res.planner:
        out += [f"planner: {p}" for p in res.planner.problems]
    for b in res.plan.buckets:
        for m in b.mix:
            d = true_decisions.get(m.product_id)
            if d is None:
                out.append(f"{m.product_id} is not on the shelf")
                continue
            if not d.allowed:
                out.append(f"{d.product['name']} in '{b.name}': " + "; ".join(d.reasons))
                continue
            ok, why = allowed_for_goal(d.product, goals.get(b.id), rules)
            if not ok:
                out.append(f"{d.product['name']} in '{b.name}': {why}")
    if res.plan.investing_monthly > res.profile.monthly_surplus + sum(
            x.emi_monthly for x in res.profile.debts) + 1:
        out.append("plan invests more than the monthly surplus")
    return sorted(set(out))
