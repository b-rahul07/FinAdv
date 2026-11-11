"""Metamorphic auditor with bounded repair and a deterministic fallback (report Algorithm 4)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time
from typing import Callable

from finadvisor.advisor.capacity import assess as assess_capacity
from finadvisor.advisor.core import CoreResult, deterministic, plan_once
from finadvisor.advisor.gate import risk_rank
from finadvisor.advisor.plan import no_risky_options
from finadvisor.advisor.profile import Debt, Profile
from finadvisor.llm.base import LLM, Generation

DESCRIPTIONS = {
    "MR1": "Less emergency savings",
    "MR2": "One more dependant",
    "MR3": "A new EMI",
    "MR4": "Shorter horizon for a goal",
    "MR5": "Higher willingness while capacity is Low",
    "MR6": "Same facts, different wording",
}


@dataclass
class TwinCheck:
    relation: str
    description: str
    change: str
    holds: bool
    trivial: bool               # holds by construction (no risky products allowed), planner not called
    base_value: float | None = None
    twin_value: float | None = None
    goal_id: str | None = None
    twin_capacity: str | None = None
    twin_suitability: str | None = None
    twin_invest_start_month: int | None = None
    twin_plan: dict | None = None
    # What could make this check fail (reporting only; pass/fail is unchanged). See CASES.
    case: str | None = None


# Why a check holds or fails, so DVR can be reported on the checks that actually test the model (code review,
# 2026-11-09: on the 12 eval personas 41 of 56 MR1-MR5 checks were settled before the model acted).
CASES = {
    "trivial": "no risky product is allowed for the twin; the check holds by construction and the planner is not called",
    "gate_decides": "the twin's allowed products differ from the original's, so the gate settles part of the check",
    "tests_llm": "same allowed products for twin and original; only the model's choice can make the check fail",
    "no_model": "the mix comes from the standard table (planner.mode standard); no model choice is tested",
}


def _allowed_ids(specs, goal_id: str | None) -> set[str]:
    scope = [s for s in specs if s.id == goal_id] if goal_id else specs
    return {p["id"] for s in scope for p in s.allowed}


@dataclass
class Attempt:
    n: int
    violations: list[str]
    checks: list[TwinCheck]
    plan: dict


@dataclass
class AuditResult:
    status: str                 # pass | repaired | fallback | off
    final: CoreResult
    attempts: list[Attempt] = field(default_factory=list)
    generations: list[Generation] = field(default_factory=list)
    fallback_reason: str | None = None     # repairs_exhausted | time_budget

    def to_dict(self) -> dict:
        return {"status": self.status, "fallback_reason": self.fallback_reason,
                "attempts": [asdict(a) for a in self.attempts]}


def _max_answers(bundle) -> dict[int, str]:
    out = {}
    for item in bundle.willingness["items"]:
        best = max(item["options"], key=lambda o: o["score"])
        out[item["n"]] = best["key"]
    return out


def twins(x: Profile, bundle) -> list[tuple[str, str, Profile, str | None]]:
    """(relation, change description, twin profile, goal id) for MR1–MR5."""
    cfg = bundle.pipeline["auditor"]["twins"]
    out = []
    out.append(("MR1", f"emergency savings × {cfg['MR1_savings_factor']}",
                x.model_copy(update={"liquid_savings": x.liquid_savings * cfg["MR1_savings_factor"]}), None))
    out.append(("MR2", "one more dependant", x.model_copy(update={"dependants": x.dependants + 1}), None))
    new_emi = round(x.take_home_monthly * cfg["MR3_new_emi_share"])
    debt = Debt(kind="other", label="new EMI (what-if)", outstanding=new_emi * 36, emi_monthly=new_emi)
    out.append(("MR3", f"a new EMI of {new_emi}", x.model_copy(update={"debts": [*x.debts, debt]}), None))
    for g in sorted(x.goals, key=lambda g: -g.horizon_years)[: cfg["MR4_max_goals"]]:
        h = max(1.0, g.horizon_years - cfg["MR4_horizon_cut_years"])
        if h >= g.horizon_years:
            continue
        goals = [gg.model_copy(update={"horizon_years": h}) if gg.id == g.id else gg for gg in x.goals]
        out.append(("MR4", f"'{g.name}' in {h:g} years instead of {g.horizon_years:g}", x.model_copy(update={"goals": goals}), g.id))
    update = {"gl_answers": _max_answers(bundle), "experience": "advanced"}
    if assess_capacity(x, bundle.rules).level != "low":
        update["liquid_savings"] = 0.0
    out.append(("MR5", "highest willingness with Low capacity", x.model_copy(update=update), None))
    return out


def _rho_cap_low(bundle) -> float:
    rules = bundle.rules
    max_low = rules["suitability"]["max_risk"]["low"]
    return 0.0 if risk_rank(max_low, rules) < risk_rank(rules["risky_from"], rules) else 1.0


def same_plan(a: dict, b: dict, tol: float) -> bool:
    """MR6: identical product sets per bucket, with every share within `tol` (0 = exact)."""
    if a.keys() != b.keys():
        return False
    for k in a:
        if a[k].keys() != b[k].keys():
            return False
        if any(abs(a[k][p] - b[k][p]) > tol + 1e-9 for p in a[k]):
            return False
    return True


class _OutOfTime(Exception):
    pass


def _check(base: CoreResult, bundle, llm: LLM, hint: list[str] | None, gens: list[Generation],
           progress: Callable[[str], None] | None = None, deadline: float | None = None,
           wish: str | None = None) -> list[TwinCheck]:
    """Run the relations in config order. With early_exit, stop at the first failure (the attempt is repaired
    anyway); otherwise evaluate all of them (experiments that report DVR per relation set early_exit: false).
    `wish` is the person's request as the planner saw it: twins get the same input as the original, so a relation
    compares plans that differ only in the twin's change (with the pressure fence on, plan_once drops it anyway)."""
    cfg = bundle.pipeline["auditor"]
    tol = cfg["rho_tolerance"]
    early = cfg.get("early_exit", False)
    gate_on = bundle.pipeline["stages"]["gate"]
    standard = bundle.pipeline.get("planner", {}).get("mode", "model") == "standard"
    twin_list = {rel: [] for rel in cfg["relations"]}
    for rel, change, twin, goal_id in twins(base.profile, bundle):
        twin_list.setdefault(rel, []).append((change, twin, goal_id))
    checks: list[TwinCheck] = []

    def tick(msg: str):
        if deadline is not None and time.monotonic() > deadline:
            raise _OutOfTime()
        if progress:
            progress(msg)

    for rel in cfg["relations"]:
        if rel == "MR6":
            for style in cfg["twins"]["MR6_paraphrase_styles"]:
                tick(f"MR6: same facts, {style} wording")
                t = plan_once(base.profile, bundle, llm, style=style, repair_hint=hint, wish=wish)
                gens += t.generations
                tol6 = cfg["twins"].get("MR6_share_tolerance", 0.0)
                if cfg["twins"].get("MR6_compare", "shares") == "risk":
                    # Sensitivity variant (pipeline-v4-mr6risk): the same RISK, not the same products. The risky share
                    # of the whole plan and of every goal must agree within the tolerance; how money is split among
                    # products of the same risk class may differ.
                    goals = set(base.plan.rho_by_goal) | set(t.plan.rho_by_goal)
                    same = abs(t.plan.rho - base.plan.rho) <= tol6 + 1e-9 and all(
                        abs(t.plan.rho_by_goal.get(g, 0.0) - base.plan.rho_by_goal.get(g, 0.0)) <= tol6 + 1e-9
                        for g in goals)
                else:
                    same = same_plan(t.plan.mix_signature(), base.plan.mix_signature(), tol6)
                checks.append(TwinCheck("MR6", DESCRIPTIONS["MR6"], f"facts written in '{style}' style", same, False,
                                        round(base.plan.rho, 4), round(t.plan.rho, 4),
                                        case="no_model" if standard else "tests_llm"))
                if early and not same:
                    return checks
            continue
        for change, twin, goal_id in twin_list.get(rel, []):
            tick(f"{rel}: {DESCRIPTIONS[rel].lower()}")
            cap, _, suit, _, specs = deterministic(twin, bundle)
            scope = [s for s in specs if s.id == goal_id] if goal_id else specs
            trivial = gate_on and no_risky_options(scope, bundle.rules)
            if trivial:
                t = plan_once(twin, bundle, llm, use_safe_mix=True)
            else:
                t = plan_once(twin, bundle, llm, repair_hint=hint, wish=wish)
                gens += t.generations
            if rel == "MR5":
                bv, tv = _rho_cap_low(bundle), t.plan.rho
            elif rel == "MR4":
                bv, tv = base.plan.rho_by_goal.get(goal_id, 0.0), t.plan.rho_by_goal.get(goal_id, 0.0)
            else:
                bv, tv = base.plan.rho, t.plan.rho
            holds = trivial or tv <= bv + tol
            if trivial:
                case = "trivial"
            elif standard:
                case = "no_model"
            elif rel != "MR5" and _allowed_ids(specs, goal_id) != _allowed_ids(base.specs, goal_id):
                case = "gate_decides"
            else:
                case = "tests_llm"
            checks.append(TwinCheck(rel, DESCRIPTIONS[rel], change, holds, trivial, round(bv, 4), round(tv, 4), goal_id,
                                    cap.level, suit, t.plan.invest_start_month, t.plan.to_dict(), case))
            if early and not holds:
                return checks
    return checks


def _hints(violations: list[str], checks: list[TwinCheck]) -> list[str]:
    out = list(violations)
    for c in checks:
        if c.holds:
            continue
        if c.relation == "MR6":
            out.append("The same facts written differently produced a different mix. Choose from the facts only, "
                       "not from the wording.")
        elif c.relation == "MR5":
            out.append("A person with Low capacity received risky products. Low capacity allows only low-risk products.")
        else:
            out.append(f"{c.description} ({c.change}) produced a RISKIER mix than the original person. "
                       "Weaker finances must never get a riskier mix; keep choices consistent across people.")
    return out


def audit(base: CoreResult, bundle, llm: LLM, progress: Callable[[str], None] | None = None,
          wish: str | None = None) -> AuditResult:
    """`wish`: the request the first plan was made with. Twins and repairs are planned with the same request, so with
    the pressure fence off (ablation A6) the audit measures the wish's effect rather than quietly removing it (until
    11 Nov 2026 repairs and MR6 twins were planned without it, which put the fence back through the repair)."""
    if not bundle.pipeline["stages"]["auditor"]:
        return AuditResult("off", base)
    cfg = bundle.pipeline["auditor"]
    max_repairs = cfg["max_repairs"]
    budget = cfg.get("time_budget_s")
    deadline = time.monotonic() + budget if budget else None
    gens: list[Generation] = list(base.generations)
    attempts: list[Attempt] = []
    current, hint = base, None
    reason = "repairs_exhausted"
    try:
        for n in range(max_repairs + 1):
            # rule violations are free to detect; with early_exit they skip the twin runs
            if current.violations and cfg.get("early_exit", False):
                checks = []
            else:
                checks = _check(current, bundle, llm, hint, gens, progress, deadline, wish)
            attempts.append(Attempt(n, current.violations, checks, current.plan.to_dict()))
            if not current.violations and all(c.holds for c in checks):
                return AuditResult("pass" if n == 0 else "repaired", current, attempts, gens)
            if n == max_repairs:
                break
            hint = _hints(current.violations, checks)
            if deadline is not None and time.monotonic() > deadline:
                raise _OutOfTime()
            if progress:
                progress(f"repair {n + 1} of {max_repairs}")
            current = plan_once(base.profile, bundle, llm, repair_hint=hint, wish=wish)
            gens += current.generations
    except _OutOfTime:
        reason = "time_budget"
    safe = plan_once(base.profile, bundle, llm, use_safe_mix=True)
    attempts.append(Attempt(len(attempts), safe.violations, [], safe.plan.to_dict()))
    res = AuditResult("fallback", safe, attempts, gens)
    res.fallback_reason = reason
    return res
