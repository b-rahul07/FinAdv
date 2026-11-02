"""Card payloads for the chat UI, built only from computed results."""

from __future__ import annotations

from finadvisor.advisor.auditor import AuditResult
from finadvisor.advisor.core import CoreResult, plan_once
from finadvisor.advisor.plan import GENERAL, Plan
from finadvisor.advisor.profile import Debt, Profile


def plan_card(plan: Plan, audit_status: str) -> dict:
    return {
        "type": "plan",
        "source": plan.source,
        "audit_status": audit_status,
        "monthly_surplus": plan.monthly_surplus,
        "investing_monthly": plan.investing_monthly,
        "invest_start_month": plan.invest_start_month,
        "rho": plan.rho,
        "steps": [s.__dict__ for s in plan.steps],
        "notes": plan.notes,
    }


def goal_cards(plan: Plan, profile: Profile, bundle) -> list[dict]:
    goals = {g.id: g for g in profile.goals}
    out = []
    for b in plan.buckets:
        if b.id == GENERAL or b.id not in goals:
            continue
        g = goals[b.id]
        out.append({
            "type": "goal",
            "goal_id": g.id,
            "name": g.name,
            "target_today": g.target_today,
            "target_future": b.target_future,
            "horizon_years": g.horizon_years,
            "saved_so_far": g.saved_so_far,
            "inflation_pa": bundle.assumptions["inflation_pa"]["value"],
            "assumed_return_pa": b.assumed_return_pa,
            "sip_needed": b.sip_needed,
            "monthly_assigned": b.monthly,
            "starts_month": plan.invest_start_month,
            "fundable": b.fundable,
            "shortfall": b.shortfall,
            "mix": [m.__dict__ for m in b.mix],
        })
    return out


def why_panel(core: CoreResult, audit: AuditResult, extra: dict | None = None) -> dict:
    cap = core.capacity
    gated = [{"product_id": d.id, "name": d.product["name"], "reasons": d.reasons}
             for d in core.decisions if not d.allowed]
    return {
        "capacity": cap.to_dict() if cap else None,
        "willingness": core.willingness.to_dict() if core.willingness else None,
        "suitability": core.suitability,
        "rules": [h.__dict__ for h in cap.triggered] if cap else [],
        "gated_out": gated,
        "audit": {
            "status": audit.status,
            "attempts": len(audit.attempts),
            "violations": [v for a in audit.attempts for v in a.violations],
            "failed_relations": sorted({c.relation for a in audit.attempts for c in a.checks if not c.holds}),
            "relations_checked": sorted({c.relation for a in audit.attempts for c in a.checks}),
        },
        **(extra or {}),
    }


def what_if(profile: Profile, changes: dict, bundle) -> dict:
    """Deterministic what-if: re-runs capacity, gate and calculators with the safe mix. No LLM, so sliders are instant.
    The investing mix is labelled illustrative; a full audited plan comes from asking the advisor."""
    base = plan_once(profile, bundle, None, use_safe_mix=True)
    upd = {}
    for k in ("take_home_monthly", "expenses_monthly", "liquid_savings", "dependants", "life_cover", "health_cover"):
        if k in changes and changes[k] is not None:
            upd[k] = changes[k]
    debts = list(profile.debts)
    if changes.get("new_emi"):
        emi = float(changes["new_emi"])
        debts.append(Debt(kind="other", label="new EMI (what-if)", outstanding=emi * 36, emi_monthly=emi))
    twin = profile.model_copy(update={**upd, "debts": debts})
    alt = plan_once(twin, bundle, None, use_safe_mix=True)
    return {
        "type": "what_if",
        "illustrative": True,
        "changes": changes,
        "before": _summary(base),
        "after": _summary(alt),
        "explanations": _explain_diff(base, alt),
        "after_plan": plan_card(alt.plan, "illustrative"),
    }


def _summary(r: CoreResult) -> dict:
    return {
        "capacity_level": r.capacity.level if r.capacity else None,
        "suitability": r.suitability,
        "rules": sorted(r.capacity.rule_ids) if r.capacity else [],
        "invest_start_month": r.plan.invest_start_month,
        "investing_monthly": r.plan.investing_monthly,
        "rho": r.plan.rho,
        "monthly_surplus": r.plan.monthly_surplus,
    }


RULE_NAMES = {"R1": "emergency fund", "R2": "life cover", "R3": "health cover", "R4": "card dues / costly loans",
              "R5": "EMI load", "R6": "complex products", "R7": "short-horizon goals"}


def _explain_diff(a: CoreResult, b: CoreResult) -> list[str]:
    out = []
    ra, rb = (a.capacity.rule_ids if a.capacity else set()), (b.capacity.rule_ids if b.capacity else set())
    for r in sorted(rb - ra):
        out.append(f"New priority: {RULE_NAMES[r]} ({r}) now needs attention.")
    for r in sorted(ra - rb):
        out.append(f"Cleared: {RULE_NAMES[r]} ({r}) is no longer a concern.")
    if a.suitability != b.suitability:
        out.append(f"Suitability moves from {a.suitability} to {b.suitability}, which changes the products allowed.")
    if a.plan.invest_start_month != b.plan.invest_start_month:
        out.append(f"Investing would start in month {b.plan.invest_start_month} instead of month {a.plan.invest_start_month}.")
    if not out:
        out.append("Nothing in the plan's structure changes; only the amounts move.")
    return out


def twin_whatifs(audit: AuditResult) -> list[dict]:
    """'What would change my advice' entries from the auditor's twins (report §3.3)."""
    last = audit.attempts[-1] if audit.attempts else None
    if not last:
        return []
    return [{"relation": c.relation, "description": c.description, "change": c.change,
             "capacity": c.twin_capacity, "suitability": c.twin_suitability,
             "invest_start_month": c.twin_invest_start_month, "rho": c.twin_value}
            for c in last.checks if c.relation != "MR6"]
