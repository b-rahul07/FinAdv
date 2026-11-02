"""Suitability and the product gate (report §4.3, Algorithm 2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from finadvisor.advisor.capacity import CapacityResult, min_level
from finadvisor.advisor.profile import Goal, Profile
from finadvisor.advisor.willingness import WillingnessResult

NEVER_GATED = {"protection", "debt_reduction"}

RISK_LABEL = {"low": "Low", "low_to_moderate": "Low to Moderate", "moderate": "Moderate",
              "moderately_high": "Moderately High", "high": "High", "very_high": "Very High",
              "unregulated": "Unregulated"}


def risk_rank(level: str | None, rules: dict) -> int:
    if level is None:
        return -1
    return rules["riskometer"].index(level)


def suitability(cap: CapacityResult | None, will: WillingnessResult | None) -> str:
    """suit = min(capacity level, willingness level). A switched-off stage contributes no limit."""
    levels = [x.level for x in (cap, will) if x is not None]
    if not levels:
        return "high"
    out = levels[0]
    for lv in levels[1:]:
        out = min_level(out, lv)
    return out


@dataclass
class GateDecision:
    product: dict
    allowed: bool
    after_priority: bool = False
    reasons: list[str] = field(default_factory=list)   # why it was gated out, or conditions attached

    @property
    def id(self) -> str:
        return self.product["id"]


def gate(suit: str, rule_ids: set[str], profile: Profile, shelf: dict, rules: dict) -> list[GateDecision]:
    max_risk = rules["suitability"]["max_risk"][suit]
    max_rank = risk_rank(max_risk, rules)
    index_at_medium = rules["suitability"].get("allow_index_fund_at_medium", False)
    priority = bool(rule_ids & {"R1", "R2", "R3", "R4"})
    out: list[GateDecision] = []
    for p in shelf["products"]:
        if p["kind"] in NEVER_GATED:
            out.append(GateDecision(p, True))
            continue
        reasons = []
        over = risk_rank(p.get("riskometer"), rules) > max_rank
        if over and not (index_at_medium and suit == "medium" and p.get("index_fund")):
            reasons.append(f"its risk level ({RISK_LABEL[p['riskometer']]}) is above what suits you now "
                           f"({RISK_LABEL[max_risk]} at most)")
        if "R6" in rule_ids and p.get("complex"):
            reasons.append("R6: complex products need loss capacity and investing experience")
        if "R5" in rule_ids and p["kind"] == "new_credit":
            reasons.append("R5: EMIs already exceed 40% of take-home pay")
        if p.get("requires_salaried") and not profile.salaried:
            reasons.append("available to salaried employees only")
        if reasons:
            out.append(GateDecision(p, False, reasons=reasons))
            continue
        d = GateDecision(p, True, after_priority=priority and p.get("market_linked", False))
        if d.after_priority:
            d.reasons.append("starts after the priority steps (emergency fund, cover, costly debt)")
        out.append(d)
    return out


def allowed_for_goal(p: dict, goal: Goal | None, rules: dict) -> tuple[bool, str]:
    """Per-goal checks: R7 horizon, minimum horizon, lock-ins, goal kinds."""
    horizon = goal.horizon_years if goal else None
    if goal and horizon < rules["rules"]["R7"]["min_goal_years"]:
        if risk_rank(p.get("riskometer"), rules) > risk_rank(rules["rules"]["R7"]["max_risk_for_goal"], rules):
            return False, "R7: goal is under 3 years away"
    if p.get("min_goal_years") and (horizon is None or horizon < p["min_goal_years"]):
        return False, f"needs a goal at least {p['min_goal_years']} years away"
    if p.get("lock_in_years") and (horizon is None or horizon < p["lock_in_years"]):
        return False, f"{p['lock_in_years']}-year lock-in is longer than the goal horizon"
    if p.get("goal_kinds") and (goal is None or goal.kind not in p["goal_kinds"]):
        return False, "only for " + ", ".join(p["goal_kinds"]) + " goals"
    return True, ""


def plannable(decisions: list[GateDecision]) -> list[dict]:
    return [d.product for d in decisions if d.allowed and d.product.get("plannable")]
