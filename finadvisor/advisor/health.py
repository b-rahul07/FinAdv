"""Money health check: 7 checks built from the capacity engine (SEBI Financial Health Check thresholds)."""

from __future__ import annotations

from finadvisor.advisor.capacity import CapacityResult, costly_debts, required_health_cover
from finadvisor.advisor.profile import Profile
from finadvisor.calc.money import inr


def health_card(p: Profile, cap: CapacityResult, rules: dict) -> dict:
    c = rules["capacity"]
    ids = cap.rule_ids
    checks = []

    def add(key, title, passed, reason, rule):
        checks.append({"key": key, "title": title, "status": "pass" if passed else "fail", "reason": reason, "rule": rule})

    need_ef = c["emergency_months"] * p.expenses_monthly
    add("emergency_fund", "Emergency fund", "R1" not in ids,
        f"{inr(p.liquid_savings)} saved; {c['emergency_months']} months of expenses is {inr(need_ef)}.", "R1")
    if p.dependants:
        need_life = c["life_cover_multiple"] * cap.Y
        add("life_cover", "Life cover", "R2" not in ids,
            f"{inr(p.life_cover)} cover; with dependants the target is {inr(need_life)}.", "R2")
    else:
        add("life_cover", "Life cover", True, "No one depends on your income, so term cover is optional for now.", "R2")
    need_h = required_health_cover(cap.Y, rules)
    add("health_cover", "Health cover", "R3" not in ids, f"{inr(p.health_cover)} cover; the target is {inr(need_h)}.", "R3")
    costly = costly_debts(p, rules)
    if not p.card_dues_paid_in_full:
        reason = "The card bill is not paid in full each month."
    elif costly:
        reason = f"{len(costly)} costly unsecured loan(s) outstanding."
    else:
        reason = "Card bill paid in full and no costly unsecured loans."
    add("card_and_costly_debt", "Card dues and costly loans", "R4" not in ids, reason, "R4")
    add("emi_load", "EMI load", "R5" not in ids,
        f"EMIs are {cap.D * 100:.1f}% of take-home pay; the limit is {c['emi_cap'] * 100:.0f}%." if cap.D != float("inf")
        else "EMIs exceed take-home pay.", "R5")
    add("complex_products", "Complex products", "R6" not in ids,
        "F&O, crypto and leverage are not suitable for you yet." if "R6" in ids
        else "Your capacity and experience would allow complex products, though they remain high-risk.", "R6")
    short = [h for h in cap.triggered if h.rule == "R7"]
    add("short_goals", "Short-horizon goals", not short,
        ("Money for " + ", ".join(f"'{g.name}'" for g in p.goals if g.horizon_years < rules["rules"]["R7"]["min_goal_years"])
         + " should stay in low-risk products.") if short else "No goal is less than 3 years away.", "R7")
    passed = sum(1 for x in checks if x["status"] == "pass")
    return {"type": "health_check", "score": passed, "out_of": len(checks), "checks": checks,
            "capacity_level": cap.level}
