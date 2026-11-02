"""Capacity engine (report Algorithm 1). Deterministic: no LLM, no randomness."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from finadvisor.advisor.profile import Profile

LEVELS = ("low", "medium", "high")


def level_index(level: str) -> int:
    return LEVELS.index(level)


def min_level(a: str, b: str) -> str:
    return a if level_index(a) <= level_index(b) else b


@dataclass
class RuleHit:
    rule: str            # R1..R7
    detail: str
    goal_id: str | None = None


@dataclass
class CapacityResult:
    E: float             # months of expenses held in liquid savings
    D: float             # EMI-to-take-home ratio
    Y: float             # annual income
    s_E: float
    s_D: float
    s_L: float
    s_H: float
    s_C: float
    cap: float
    level: str
    triggered: list[RuleHit] = field(default_factory=list)

    @property
    def rule_ids(self) -> set[str]:
        return {h.rule for h in self.triggered}

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("E", "D"):
            if math.isinf(d[k]):
                d[k] = None
        return d


def costly_debts(p: Profile, cfg: dict) -> list:
    rule = cfg["capacity"]["costly_debt"]
    out = []
    for d in p.debts:
        if d.outstanding <= 0 and d.emi_monthly <= 0:
            continue
        if d.kind in rule["kinds"]:
            out.append(d)
        elif d.kind == "credit_card":
            continue  # revolving card dues are covered by card_dues_paid_in_full
        elif not d.secured and d.rate_pa is not None and d.rate_pa >= rule["unsecured_min_rate_pa"]:
            out.append(d)
    return out


def required_health_cover(Y: float, cfg: dict) -> float:
    c = cfg["capacity"]
    return max(c["health_cover_min_inr"], c["health_cover_income_share"] * Y)


def assess(p: Profile, cfg: dict) -> CapacityResult:
    """Score capacity from confirmed facts. `cfg` is the rules config (configs/rules/*.yaml)."""
    c = cfg["capacity"]
    Y = p.take_home_monthly * 12

    E = p.liquid_savings / p.expenses_monthly if p.expenses_monthly > 0 else math.inf
    D = p.total_emi / p.take_home_monthly if p.take_home_monthly > 0 else (0.0 if p.total_emi == 0 else math.inf)

    s_E = min(E / c["emergency_months"], 1.0)
    if math.isinf(D):
        s_D = 0.0
    elif c.get("s_D_form", "headroom") == "ratio":
        s_D = 1.0 if D <= c["emi_cap"] else c["emi_cap"] / D        # 1 while the SEBI check passes
    else:
        s_D = min(max((c["emi_cap"] - D) / c["emi_cap"], 0.0), 1.0)  # report v1: 1 only with no EMIs
    if p.dependants > 0:
        s_L = min(p.life_cover / (c["life_cover_multiple"] * Y), 1.0) if Y > 0 else (1.0 if p.life_cover > 0 else 0.0)
    else:
        s_L = 1.0
    s_H = min(p.health_cover / required_health_cover(Y, cfg), 1.0)
    costly = costly_debts(p, cfg)
    s_C = 0.0 if (not p.card_dues_paid_in_full or costly) else 1.0

    cap = min(s_E, s_D, s_L, s_H, s_C)
    lv = c["levels"]
    level = "low" if cap < lv["low_below"] else ("high" if cap >= lv["high_at"] else "medium")

    hits: list[RuleHit] = []
    if E < c["emergency_months"]:
        hits.append(RuleHit("R1", f"Emergency savings cover {_months(E)} of expenses; the target is {c['emergency_months']} months."))
    if s_L < 1:
        hits.append(RuleHit("R2", f"With {p.dependants} dependant{'' if p.dependants == 1 else 's'}, life cover should be {c['life_cover_multiple']}× annual income."))
    if s_H < 1:
        hits.append(RuleHit("R3", "Health cover is below the larger of ₹5 lakh and half of annual income."))
    if s_C == 0:
        reasons = []
        if not p.card_dues_paid_in_full:
            reasons.append("credit-card bill not paid in full")
        if costly:
            reasons.append("costly unsecured loan outstanding")
        hits.append(RuleHit("R4", "; ".join(reasons).capitalize() + "."))
    if D > c["emi_cap"]:
        hits.append(RuleHit("R5", f"EMIs take {D * 100:.1f}% of take-home pay; the limit is {c['emi_cap'] * 100:.0f}%."))
    if level == "low" or p.experience == "none":
        why = "capacity for loss is Low" if level == "low" else "no investing experience yet"
        hits.append(RuleHit("R6", f"Complex products (F&O, crypto, leverage) are off the table: {why}."))
    r7 = cfg["rules"]["R7"]["min_goal_years"]
    for g in p.goals:
        if g.horizon_years < r7:
            hits.append(RuleHit("R7", f"'{g.name}' is under {r7} years away; its money stays in low-risk products.", goal_id=g.id))

    return CapacityResult(E, D, Y, s_E, s_D, s_L, s_H, s_C, cap, level, hits)


def _months(E: float) -> str:
    if math.isinf(E):
        return "unlimited months"
    return f"{E:.1f} months"
