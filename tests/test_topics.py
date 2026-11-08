"""Direct answers to common questions that the general plan reply used to answer with a generic template."""

import pytest

from finadvisor.advisor import compose, topics
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.advisor.profile import Debt
from finadvisor.calc import goals as G
from finadvisor.llm.fake import FakeLLM
from finadvisor.portfolio.shelf_map import summarise
from test_pipeline import consistent_planner


def ask(bundle, profile, q, held=None, snap=None):
    adv = Advisor(bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: ""),
                  funds=(lambda: snap) if snap else None)
    out = adv.turn(TurnInput(text=q, confirmed=profile, profile_version=1, holdings=(lambda: held) if held else None),
                   lambda k, d: None)
    return out, (out.advice or {}).get("compose", {}).get("intent")


@pytest.mark.parametrize("q, intent", [
    ("How can I save tax this year?", "tax"),
    ("Old or new tax regime for me?", "tax"),
    ("My mutual funds are in regular plans, should I switch?", "switch_direct"),
    ("Markets are falling, should I stop my SIP?", "market_fall"),
    ("I have 2 lakh lying in my savings account, what should I do?", "lumpsum"),
    ("Should I invest a lump sum or do SIP?", "lumpsum"),
    ("How is my portfolio doing?", "portfolio"),
    ("Is my portfolio diversified enough?", "portfolio"),
    ("What returns can I expect from my plan?", "returns"),
    ("I got a 20% salary hike, what should I do?", "raise"),
    ("When can I retire?", "retire_when"),
    ("How do I save for my child's education?", "goal"),
    ("Should I buy a house or keep renting?", "goal"),
    ("PPF or ELSS, which is better for me?", "compare"),
])
def test_topic_intents(q, intent):
    assert topics.intent_of(q) == intent


def test_loan_and_insurance_questions_keep_their_own_answers(website_bundle, healthy):
    _, intent = ask(website_bundle, healthy, "Should I prepay my home loan or invest?")
    assert intent == "debt"                       # "home" must not turn it into a goal question
    _, intent = ask(website_bundle, healthy, "Which health insurance should I buy?")
    assert intent == "insurance"


def test_months_to_target_grows_the_target_with_inflation():
    # Return equal to inflation: a target worth 12 months of savings in today's money takes exactly 12 months
    assert G.months_to_target(10_000, 0, 120_000, 0) == 12
    n = G.months_to_target(10_000, 10, 1_000_000, 6)
    assert n is not None and n < G.months_to_target(10_000, 7, 1_000_000, 6)
    assert G.months_to_target(1_000, 6, 10_000_000, 6) is None          # never within 60 years
    assert G.months_to_target(10_000, 0, 120_000, 0, start_month=4) == 15  # three months' delay


def test_summarise_flags_regular_plans():
    items = [
        {"instrument": {"kind": "mf", "name": "X Flexi Cap Fund", "category": "Equity Scheme - Flexi Cap Fund",
                        "plan": "Regular", "scheme_code": "1"}, "value": 100_000, "invested": 80_000},
        {"instrument": {"kind": "mf", "name": "Y Flexi Cap Fund", "category": "Equity Scheme - Flexi Cap Fund",
                        "plan": "Direct", "scheme_code": "2"}, "value": 50_000, "invested": 40_000},
        {"instrument": {"kind": "stock", "name": "ACME"}, "value": 30_000, "invested": 35_000},
    ]
    s = summarise(items)
    assert [p["product_id"] for p in s] == ["flexi_cap_fund", "direct_equity"]
    assert s[0]["funds"] == 2 and s[0]["invested"] == 120_000
    assert s[0]["regular"] == [{"name": "X Flexi Cap Fund", "value": 100_000, "code": "1"}]


def test_switch_to_direct_works_out_the_yearly_saving(website_bundle, healthy):
    held = [{"product_id": "flexi_cap_fund", "value": 200_000, "invested": 150_000, "funds": 1,
             "regular": [{"name": "X Flexi Cap Fund", "value": 200_000, "code": "1"}]}]
    snap = {"ter": {"x flexi cap fund": {"regular": 1.6, "direct": 0.6, "date": "2026-11-05"}}, "products": {},
            "built_at": "2026-11-08T00:00:00+00:00", "version": "fundfinder-v1", "sources": {}}
    out, intent = ask(website_bundle, healthy, "My funds are in regular plans, should I switch to direct?", held, snap)
    assert intent == "switch_direct"
    assert "about ₹2,000 a year less" in out.text                 # 2,00,000 x (1.6 - 0.6)%
    assert "₹1,25,000 of long-term gains each year is tax-free" in out.text
    assert "mfcentral.com" in out.text


def test_portfolio_review_reports_gain_split_and_concentration(website_bundle, healthy):
    held = [{"product_id": "direct_equity", "value": 400_000, "invested": 300_000, "funds": 0, "regular": []},
            {"product_id": "fixed_deposit", "value": 100_000, "invested": 100_000, "funds": 0, "regular": []}]
    out, intent = ask(website_bundle, healthy, "How is my portfolio doing?", held)
    assert intent == "portfolio"
    assert out.text.startswith("Your investments are worth ₹5,00,000; you put in ₹4,00,000, so they are up ₹1,00,000 (+25.0%).")
    assert "80% equity and 20% debt and deposits" in out.text
    assert "80% is in individual shares" in out.text
    out, _ = ask(website_bundle, healthy, "How is my portfolio doing?")
    assert out.text.startswith("I can't see any holdings yet")


def test_prepay_compares_the_loan_rate_with_the_plans_expected_return(website_bundle, healthy):
    out, _ = ask(website_bundle, healthy, "Should I prepay my home loan?")
    assert "Your home loan costs 8.5% a year" in out.text and "expected to earn about" in out.text
    costly = healthy.model_copy(update={"debts": [Debt(kind="personal", outstanding=300_000, rate_pa=16, emi_monthly=10_000)]})
    out, _ = ask(website_bundle, costly, "Should I prepay my personal loan or invest?")
    assert "prepaying part of the loan is the better use of spare money" in out.text
    assert "prepayment penalty" in out.text


def test_card_question_without_card_debt_says_so(website_bundle, healthy):
    out, _ = ask(website_bundle, healthy, "How do I clear my credit card debt?")
    assert out.text.startswith("You have no unpaid credit-card balance")


def test_card_debt_answer_shows_the_monthly_interest(website_bundle, stretched):
    p = stretched.model_copy(update={"debts": [Debt(kind="credit_card", outstanding=60_000, rate_pa=40, emi_monthly=0)],
                                     "card_dues_paid_in_full": False})
    out, _ = ask(website_bundle, p, "How do I pay off my credit card dues?")
    assert out.text.startswith("Clear it first. At 40% a year, your ₹60,000 balance costs about ₹2,000 a month in interest.")


def test_emi_check_without_an_amount_gives_the_room(website_bundle, healthy):
    out, _ = ask(website_bundle, healthy, "Can I afford a car on EMI?")
    # 40% of ₹1,00,000 minus the ₹20,000 home-loan EMI
    assert "a new EMI can be at most ₹20,000 a month" in out.text
    out, _ = ask(website_bundle, healthy, "Can I afford a phone on EMI of ₹5,000?")
    assert "would take your EMIs from 20% to 25% of take-home pay" in out.text


def test_compare_answers_every_product_named(website_bundle, stretched):
    out, intent = ask(website_bundle, stretched, "PPF or ELSS, which is better for me?")
    assert intent == "compare"
    assert out.text.startswith("Public Provident Fund (PPF) suits you now. ELSS (tax-saving) fund doesn't yet")
    assert "**Side by side**" in out.text and "locked for 15 years" in out.text and "locked for 3 years" in out.text
    assert any(c["type"] == "not_yet" for c in out.cards)          # the card for the blocked product stays


def test_lumpsum_keeps_the_emergency_fund_and_flags_a_different_amount(website_bundle, healthy, stretched):
    out, _ = ask(website_bundle, healthy, "I have 2 lakh lying in my savings account, what should I do?")
    assert out.text.startswith("Keep your ₹2,40,000 where it is: it is exactly your emergency fund")   # 6 x ₹40,000
    assert "If you now have ₹2,00,000, update your profile" in out.text
    richer = healthy.model_copy(update={"liquid_savings": 400_000})
    out, _ = ask(website_bundle, richer, "Should I invest a lump sum or do SIP?")
    assert out.text.startswith("Keep ₹2,40,000 (6 months of expenses) as your emergency fund")
    assert "Invest the other ₹1,60,000" in out.text
    out, _ = ask(website_bundle, stretched, "Should I invest a lump sum or do SIP?")
    assert out.text.startswith("Keep your savings as your emergency fund for now. Your ₹40,000 covers 1.3 months")


def test_tax_answer_is_honest_and_points_to_the_official_calculator(website_bundle, healthy):
    out, intent = ask(website_bundle, healthy, "Old or new tax regime for me?")
    assert intent == "tax"
    assert out.text.startswith("FinAdvisor doesn't calculate income tax yet")
    assert "incometax.gov.in" in out.text
    assert "your home loan's interest and principal repayment" in out.text   # personal to the profile


def test_returns_uses_the_plans_assumed_return_and_the_calculator(website_bundle, healthy):
    out, intent = ask(website_bundle, healthy, "What returns can I expect from my plan?")
    assert intent == "returns" and "not a promise" in out.text and "**Assumptions used**" in out.text
    plan = out.advice["plan"]
    bs = [b for b in plan["buckets"] if b["monthly"] > 0]
    r = sum(b["monthly"] * b["assumed_return_pa"] for b in bs) / sum(b["monthly"] for b in bs)
    assert f"About {r:.1f}% a year" in out.text
    from finadvisor.calc.money import inr
    assert inr(G.fv_sip(plan["investing_monthly"], r, 120)) in out.text


def test_retire_when_gives_a_date_or_says_why_not(website_bundle, stretched):
    out, intent = ask(website_bundle, stretched, "When can I retire?")
    assert intent in ("retire_when", "retirement")
    assert "retire" in out.text.lower()


def test_raise_works_out_the_new_surplus(website_bundle, healthy):
    out, _ = ask(website_bundle, healthy, "I got a 20% salary hike, what should I do?")
    assert "rises 20% to about ₹1,20,000" in out.text and "₹60,000 a month to plan with instead of ₹40,000" in out.text


def test_goal_question_uses_the_matching_goal(website_bundle, healthy):
    out, intent = ask(website_bundle, healthy, "How much should I save for my house down payment?")
    assert intent == "goal" and "'House down payment'" in out.text


def test_answers_carry_the_template_id_of_both_files():
    assert compose.template_id().startswith("compose-v1@")
