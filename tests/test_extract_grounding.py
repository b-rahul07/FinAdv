"""Extraction grounding: facts the model invents are dropped; facts the message states are kept.
The fake model replays outputs qwen2.5:3b produced in the 2026-11-01 evaluation."""

from finadvisor.advisor.extract import extract
from finadvisor.advisor.profile import Profile
from finadvisor.llm.fake import FakeLLM


def run(text, raw, purchase=False, base=None):
    llm = FakeLLM(lambda s, p, schema, purpose: raw)
    base = base or Profile(take_home_monthly=80000, expenses_monthly=30000)
    proposed, changed, _ = extract(llm, text, base, exclude_purchase=purchase)
    return proposed, changed


def test_invented_facts_on_a_purchase_question_are_dropped():
    _, changed = run("should I buy a phone on EMI of 6000 a month",
                     {"age": 25, "expenses_monthly": 6000, "experience": "intermediate",
                      "debts": [{"kind": "other", "emi_monthly": 6000}]}, purchase=True)
    assert changed == []


def test_stated_facts_are_kept():
    p, changed = run("I earn 80k a month take-home and spend 45k, I have 2 lakh saved",
                     {"take_home_monthly": 80000, "expenses_monthly": 45000, "liquid_savings": 200000},
                     base=Profile(take_home_monthly=70000, expenses_monthly=30000))
    assert set(changed) == {"take_home_monthly", "expenses_monthly", "liquid_savings"}
    assert p["liquid_savings"] == 200000


def test_wrong_conversions_are_dropped():
    # 10 lakh read as 1 lakh; 50 lakh read as 5 lakh
    _, changed = run("I have health insurance of 10 lakh", {"health_cover": 100000})
    assert changed == []
    _, changed = run("I want to buy a house in 5 years, it costs 50 lakh",
                     {"goals": [{"name": "Buy House", "target_today": 500000, "horizon_years": 5}]})
    assert changed == []


def test_never_invested_means_no_experience():
    p, changed = run("I have never invested before", {"experience": "intermediate"},
                     base=Profile(take_home_monthly=80000, expenses_monthly=30000, experience="beginner"))
    assert p["experience"] == "none" and changed == ["experience"]


def test_insurance_is_not_a_goal_and_dependants_may_be_implied():
    _, changed = run("I have a term plan of 1 crore", {"goals": [{"name": "Term Plan", "target_today": 10000000,
                                                                  "horizon_years": 1}]})
    assert "goals" not in changed
    p, changed = run("I am 28 and my wife and two kids depend on me", {"age": 28, "dependants": 3})
    assert p["dependants"] == 3 and p["age"] == 28


def test_existing_debt_is_kept_but_needs_an_amount_in_the_message():
    p, changed = run("I have a car loan with 9000 EMI", {"debts": [{"kind": "car", "emi_monthly": 9000}]})
    assert changed == ["debts"] and p["debts"][-1]["emi_monthly"] == 9000
    _, changed = run("I have a car loan", {"debts": [{"kind": "car", "emi_monthly": 9000}]})
    assert changed == []
