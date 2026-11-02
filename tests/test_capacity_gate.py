"""Capacity engine, willingness and gate. T-numbers follow the report's test table (Ch. 5)."""

import math

import pytest

from conftest import MAX, MID, MIN
from finadvisor.advisor import capacity, willingness
from finadvisor.advisor.gate import gate, suitability
from finadvisor.advisor.profile import Debt, Profile
from finadvisor.configs import load_component

V1 = load_component("rules", "rules-v1")   # the report's original formulas, kept for sensitivity runs


def base(**kw) -> Profile:
    d = dict(take_home_monthly=100_000, expenses_monthly=40_000, liquid_savings=240_000,
             health_cover=600_000, experience="intermediate", gl_answers=dict(MAX))
    d.update(kw)
    return Profile(**d)


# ---- T01/T02 emergency fund boundary
def test_T01_six_months_exactly_clears_R1(bundle):
    c = capacity.assess(base(liquid_savings=6 * 40_000), bundle.rules)
    assert c.s_E == 1 and "R1" not in c.rule_ids


def test_T02_just_below_six_months_fires_R1(bundle):
    c = capacity.assess(base(liquid_savings=5.99 * 40_000), bundle.rules)
    assert "R1" in c.rule_ids
    assert c.s_E == pytest.approx(5.99 / 6)
    assert c.level == "medium"


# ---- T03 EMI load
def test_T03_emi_41_percent_fires_R5_and_gates_new_emi(bundle):
    p = base(debts=[Debt(kind="car", outstanding=500_000, rate_pa=9, emi_monthly=41_000)])
    c = capacity.assess(p, bundle.rules)
    assert "R5" in c.rule_ids
    assert c.s_D == pytest.approx(0.40 / 0.41) and c.level == "medium"   # v2: just over the limit is not Low
    decisions = {d.id: d for d in gate(suitability(c, willingness.assess(p, bundle.willingness)), c.rule_ids, p,
                                       bundle.shelf, bundle.rules)}
    assert not decisions["new_emi"].allowed
    v1 = capacity.assess(p, V1)
    assert v1.s_D == 0 and v1.level == "low"


def test_emi_exactly_40_percent_does_not_fire_R5(bundle):
    p = base(debts=[Debt(kind="home", outstanding=1, emi_monthly=40_000)])
    c = capacity.assess(p, bundle.rules)
    assert "R5" not in c.rule_ids and c.s_D == 1 and c.level == "high"
    assert capacity.assess(p, V1).s_D == 0


def test_s_D_forms(bundle):
    p = base(debts=[Debt(kind="home", outstanding=1, emi_monthly=20_000)])
    assert capacity.assess(p, bundle.rules).s_D == 1                      # v2: passes the check -> 1
    assert capacity.assess(p, V1).s_D == pytest.approx((0.40 - 0.20) / 0.40)
    heavy = base(debts=[Debt(kind="home", outstanding=1, emi_monthly=90_000)])
    assert capacity.assess(heavy, bundle.rules).s_D == pytest.approx(0.40 / 0.90)
    assert capacity.assess(heavy, bundle.rules).level == "low"


def test_every_component_is_one_exactly_when_its_check_passes(bundle):
    """v2 design rule: High capacity <=> all five SEBI checks pass."""
    c = capacity.assess(base(debts=[Debt(kind="home", outstanding=1, emi_monthly=35_000)]), bundle.rules)
    assert (c.s_E, c.s_D, c.s_L, c.s_H, c.s_C) == (1, 1, 1, 1, 1) and c.level == "high"


# ---- T04 life cover
def test_T04_no_dependants_no_life_cover_is_fine(bundle):
    c = capacity.assess(base(dependants=0, life_cover=0), bundle.rules)
    assert c.s_L == 1 and "R2" not in c.rule_ids


def test_life_cover_needed_with_dependants(bundle):
    Y = 100_000 * 12
    c = capacity.assess(base(dependants=2, life_cover=15 * Y - 1), bundle.rules)
    assert "R2" in c.rule_ids
    c = capacity.assess(base(dependants=2, life_cover=15 * Y), bundle.rules)
    assert "R2" not in c.rule_ids


# ---- health cover = max(5 lakh, 50% of income)
def test_health_cover_threshold_uses_larger_of_two(bundle):
    # Y = 12 lakh -> 50% = 6 lakh > 5 lakh
    assert "R3" in capacity.assess(base(health_cover=599_999), bundle.rules).rule_ids
    assert "R3" not in capacity.assess(base(health_cover=600_000), bundle.rules).rule_ids
    # Y = 6 lakh -> 5 lakh floor applies
    p = base(take_home_monthly=50_000, expenses_monthly=20_000, liquid_savings=120_000, health_cover=500_000)
    assert "R3" not in capacity.assess(p, bundle.rules).rule_ids


# ---- card dues and costly loans
def test_card_not_paid_in_full_zeroes_s_C(bundle):
    c = capacity.assess(base(card_dues_paid_in_full=False), bundle.rules)
    assert c.s_C == 0 and "R4" in c.rule_ids and c.level == "low"


def test_personal_loan_is_costly_home_loan_is_not(bundle):
    assert "R4" in capacity.assess(base(debts=[Debt(kind="personal", outstanding=100_000, rate_pa=11, emi_monthly=5000)]), bundle.rules).rule_ids
    assert "R4" not in capacity.assess(base(debts=[Debt(kind="home", outstanding=100_000, rate_pa=9, emi_monthly=5000)]), bundle.rules).rule_ids
    assert "R4" in capacity.assess(base(debts=[Debt(kind="other", outstanding=50_000, rate_pa=14, emi_monthly=2000)]), bundle.rules).rule_ids
    assert "R4" not in capacity.assess(base(debts=[Debt(kind="other", outstanding=50_000, rate_pa=13.99, emi_monthly=2000)]), bundle.rules).rule_ids


def test_weakest_link_levels(bundle):
    assert capacity.assess(base(), bundle.rules).level == "high"
    assert capacity.assess(base(liquid_savings=120_000), bundle.rules).level == "medium"   # s_E = 0.5
    assert capacity.assess(base(liquid_savings=119_999), bundle.rules).level == "low"


def test_zero_expenses_does_not_divide_by_zero(bundle):
    c = capacity.assess(base(expenses_monthly=0), bundle.rules)
    assert math.isinf(c.E) and c.s_E == 1


# ---- R6 / T06
def test_T06_no_experience_high_capacity_removes_fno_and_crypto(bundle):
    p = base(experience="none")
    c = capacity.assess(p, bundle.rules)
    assert c.level == "high" and "R6" in c.rule_ids
    w = willingness.assess(p, bundle.willingness)
    decisions = {d.id: d for d in gate(suitability(c, w), c.rule_ids, p, bundle.shelf, bundle.rules)}
    assert not decisions["fno"].allowed and not decisions["crypto"].allowed


def test_crypto_never_allowed(bundle):
    p = base()
    c = capacity.assess(p, bundle.rules)
    decisions = {d.id: d for d in gate("high", c.rule_ids, p, bundle.shelf, bundle.rules)}
    assert not decisions["crypto"].allowed
    assert decisions["fno"].allowed  # High capacity + experience + High willingness: R6 does not bar it


# ---- R7
def test_R7_short_goal(bundle, stretched):
    c = capacity.assess(stretched, bundle.rules)
    assert any(h.rule == "R7" and h.goal_id == "trip" for h in c.triggered)
    assert not any(h.rule == "R7" and h.goal_id == "ret" for h in c.triggered)


# ---- willingness
def test_gl_score_range(bundle):
    p = base(gl_answers=dict(MIN))
    assert willingness.assess(p, bundle.willingness).score == 13
    assert willingness.assess(base(gl_answers=dict(MAX)), bundle.willingness).score == 47


def test_gl_bands_and_experience_cap(bundle):
    w = willingness.assess(base(gl_answers=dict(MID)), bundle.willingness)
    assert w.score == 26 and w.level == "medium"   # eleven 2s + item 9 (1) + item 10 (3)
    w = willingness.assess(base(gl_answers=dict(MAX), experience="none"), bundle.willingness)
    assert w.band_level == "high" and w.level == "medium" and w.capped_by_experience


def test_band_boundaries(bundle):
    cfg = bundle.willingness
    assert willingness.band(22, cfg) == "low"
    assert willingness.band(23, cfg) == "medium"
    assert willingness.band(28, cfg) == "medium"
    assert willingness.band(29, cfg) == "high"


def test_incomplete_questionnaire_is_low(bundle):
    w = willingness.assess(base(gl_answers={1: "a"}), bundle.willingness)
    assert w.level == "low" and w.score is None


def test_suitability_is_lower_of_two(bundle):
    p = base(gl_answers=dict(MIN))
    c = capacity.assess(p, bundle.rules)
    assert c.level == "high"
    assert suitability(c, willingness.assess(p, bundle.willingness)) == "low"


def test_gate_respects_riskometer(bundle):
    p = base()
    c = capacity.assess(p, bundle.rules)
    allowed = {d.id for d in gate("medium", c.rule_ids, p, bundle.shelf, bundle.rules) if d.allowed}
    assert "hybrid_baf" in allowed and "large_cap_index_fund" not in allowed
    allowed = {d.id for d in gate("low", c.rule_ids, p, bundle.shelf, bundle.rules) if d.allowed}
    assert "liquid_fund" in allowed and "hybrid_baf" not in allowed
    assert {"term_life", "health_insurance", "loan_prepayment"} <= allowed


def test_market_linked_waits_for_priorities(bundle, stretched):
    c = capacity.assess(stretched, bundle.rules)
    d = {x.id: x for x in gate("medium", c.rule_ids, stretched, bundle.shelf, bundle.rules)}
    assert d["hybrid_baf"].after_priority and not d["liquid_fund"].after_priority
