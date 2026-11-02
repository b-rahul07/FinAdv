"""Check route: does a product or purchase suit this person now? Produces a 'Not yet' or 'Fits' card."""

from __future__ import annotations

import re

from finadvisor.advisor import capacity as capacity_mod
from finadvisor.advisor import willingness as willingness_mod
from finadvisor.advisor.capacity import LEVELS, CapacityResult, required_health_cover
from finadvisor.advisor.gate import gate, risk_rank, suitability
from finadvisor.advisor.pressure import conflict_line
from finadvisor.advisor.profile import Profile
from finadvisor.calc.goals import months_to_save
from finadvisor.calc.money import inr, round_up_to

EMI_AMOUNT = re.compile(r"(?:₹|rs\.?\s?)?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|thousand)?\s*(?:/|per|a|each)?\s*(?:month|mo)?\s*(?:emi)"
                        r"|emi (?:of|is|would be|around|about)?\s*(?:₹|rs\.?\s?)?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|thousand)?", re.I)


def parse_new_emi(text: str) -> float | None:
    m = EMI_AMOUNT.search(text)
    if not m:
        return None
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    v = float(num.replace(",", ""))
    if unit:
        v *= 1000
    return v if v > 0 else None


def _needed_level(product: dict, rules: dict) -> str | None:
    r = risk_rank(product.get("riskometer"), rules)
    for lv in LEVELS:
        if risk_rank(rules["suitability"]["max_risk"][lv], rules) >= r:
            return lv
    return None  # above every level (unregulated)


def _changes(p: Profile, cap: CapacityResult, rules: dict) -> list[dict]:
    """Concrete fact changes that would clear each triggered priority rule."""
    c = rules["capacity"]
    out = []
    ids = cap.rule_ids
    if "R1" in ids:
        gap = c["emergency_months"] * p.expenses_monthly - p.liquid_savings
        m = months_to_save(gap, p.monthly_surplus) if p.monthly_surplus > 0 else None
        out.append({"rule": "R1", "text": f"Build your emergency fund by {inr(gap)}"
                    + (f" (about {m} months at your current surplus)" if m else "") + "."})
    if "R2" in ids:
        out.append({"rule": "R2", "text": f"Raise term life cover to {inr(c['life_cover_multiple'] * cap.Y)}."})
    if "R3" in ids:
        out.append({"rule": "R3", "text": f"Raise health cover to {inr(required_health_cover(cap.Y, rules))}."})
    if "R4" in ids:
        out.append({"rule": "R4", "text": "Clear credit-card dues and costly personal or BNPL loans."})
    if "R5" in ids:
        excess = (cap.D - c["emi_cap"]) * p.take_home_monthly
        out.append({"rule": "R5", "text": f"Bring EMIs down by about {inr(round_up_to(excess, 100))}/month."})
    return out


def check(p: Profile, bundle, product_ids: list[str], text: str) -> dict:
    rules, shelf = bundle.rules, bundle.shelf
    cap = capacity_mod.assess(p, rules)
    will = willingness_mod.assess(p, bundle.willingness)
    suit = suitability(cap, will)
    decisions = {d.id: d for d in gate(suit, cap.rule_ids, p, shelf, rules)}
    pid = product_ids[0] if product_ids else "new_emi"
    d = decisions[pid]
    product = d.product
    blockers: list[str] = list(d.reasons) if not d.allowed else []
    extra: dict = {}

    if pid == "new_emi":
        emi = parse_new_emi(text)
        if emi:
            new_d = (p.total_emi + emi) / p.take_home_monthly if p.take_home_monthly else float("inf")
            extra = {"new_emi": emi, "emi_ratio_now": cap.D, "emi_ratio_after": new_d}
            if new_d > rules["capacity"]["emi_cap"] and "R5" not in cap.rule_ids:
                blockers.append(f"R5: with this EMI, EMIs would take {new_d * 100:.1f}% of take-home pay "
                                f"(limit {rules['capacity']['emi_cap'] * 100:.0f}%)")
        if {"R1", "R4"} & cap.rule_ids:
            blockers.append("a new EMI would slow down the priority steps (emergency fund, costly debt)")

    changes = _changes(p, cap, rules)
    need = _needed_level(product, rules) if product.get("riskometer") else None
    if need and LEVELS.index(suit) < LEVELS.index(need):
        if LEVELS.index(cap.level) < LEVELS.index(need):
            weak = [k for k in ("s_E", "s_D", "s_L", "s_H", "s_C")
                    if getattr(cap, k) < (1.0 if need == "high" else rules["capacity"]["levels"]["low_below"])]
            changes.append({"rule": "capacity", "text": f"Capacity for loss needs to be {need.capitalize()}; "
                            f"weakest parts now: {', '.join(LABELS[k] for k in weak)}."})
        if will.level and LEVELS.index(will.level) < LEVELS.index(need):
            changes.append({"rule": "willingness", "text": f"Your questionnaire shows {will.level} willingness to take risk. "
                            "That is a valid preference; FinAdvisor will not push you past it."})
    if product.get("riskometer") == "unregulated":
        changes = [{"rule": "shelf", "text": "Cryptocurrency is unregulated in India, so FinAdvisor never plans it."}]
    if "R6" in cap.rule_ids and product.get("complex") and p.experience == "none":
        changes.append({"rule": "R6", "text": "Gain experience with simpler regulated products first."})

    after_priority = d.allowed and d.after_priority
    verdict = "not_yet" if blockers else ("after_priorities" if after_priority else "fits")
    first = changes[0]["text"].rstrip(".").lower() if changes else "the priority steps"
    because = blockers[0].split(": ", 1)[-1] if blockers else "the priority steps protect you first"
    card = {
        "type": "not_yet" if verdict != "fits" else "check_ok",
        "verdict": verdict,
        "product_id": pid,
        "product_name": product["name"],
        "conflict": conflict_line(product["name"].lower(), first, because) if verdict != "fits" else None,
        "blockers": blockers,
        "changes": changes,
        "suitability": suit,
        "capacity_level": cap.level,
        "willingness_level": will.level,
        **extra,
    }
    if pid == "fno":
        card["fact"] = bundle.assumptions["facts"]["fno_losses"]
    return card


LABELS = {"s_E": "emergency fund", "s_D": "EMI load", "s_L": "life cover", "s_H": "health cover", "s_C": "card dues / costly loans"}
