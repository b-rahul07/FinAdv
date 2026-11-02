"""Question-first replies (compose-v1): each intent answers the question asked, with the person's numbers."""

from finadvisor.advisor import compose
from finadvisor.advisor.pipeline import Advisor
from finadvisor.llm.fake import FakeLLM
from test_pipeline import consistent_planner, run_turn


def reply(bundle, profile, q):
    out, _ = run_turn(Advisor(bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: "")), profile, q)
    return out


def test_intents():
    assert compose.intent_of("Do I have enough emergency savings?") == "emergency"
    assert compose.intent_of("How much should I save for retirement?") == "retirement"
    assert compose.intent_of("which mutual funds should I invest in") == "funds"
    assert compose.intent_of("how much should I invest every month") == "how_much"
    assert compose.intent_of("Make me a money plan for my salary and goals") == "plan"


def test_emergency_question_gets_a_yes_or_no_first(website_bundle, stretched, healthy):
    out = reply(website_bundle, stretched, "Do I have enough emergency savings?")
    assert out.text.startswith("Not yet. You have ₹40,000, which covers 1.3 months of expenses")
    assert "**What to do**\n\n1. Save ₹" in out.text
    assert next(c for c in out.cards if c["type"] == "health_check")["show"] == "main"
    out = reply(website_bundle, healthy, "Do I have enough emergency savings?")
    assert out.text.startswith("Yes.")


def test_retirement_question_sizes_the_goal(website_bundle, stretched):
    out = reply(website_bundle, stretched, "How much should I save for retirement?")
    assert out.text.startswith("Put about ₹") and "after inflation in 30 years" in out.text


def test_plan_reply_leads_with_the_answer_and_keeps_details_out_of_the_way(website_bundle, stretched):
    out = reply(website_bundle, stretched, "Make me a plan for my savings")
    assert out.text.startswith("Here is what to do with the ₹20,000 you have left each month")
    assert "Your capacity for loss is" not in out.text          # the old profile-first paragraph is gone
    show = {c["type"]: c["show"] for c in out.cards}
    assert show["plan"] == show["health_check"] == show["what_if"] == "details"
    assert show["followups"] == "main"
    assert out.advice["compose"]["intent"] == "plan" and out.advice["templates"]["compose"].startswith("compose-v1@")


def test_existing_holdings_open_the_plan(website_bundle, healthy):
    from finadvisor.advisor.pipeline import TurnInput
    held = [{"product_id": "large_cap_index_fund", "value": 550_000}, {"product_id": "direct_equity", "value": 140_000},
            {"product_id": "liquid_fund", "value": 50_000}]
    low = healthy.model_copy(update={"gl_answers": {i: "a" for i in range(1, 14)}})       # cautious questionnaire
    adv = Advisor(website_bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: ""))
    out = adv.turn(TurnInput(text="Make me a plan", confirmed=low, profile_version=1, holdings=lambda: held),
                   lambda k, d: None)
    assert "**What you already have**\n\nYou already have ₹7,40,000 invested: ₹5,50,000 in Nifty 50 index fund" in out.text
    assert "rated above your risk level" in out.text and "you don't have to sell anything" in out.text
    assert out.advice["compose"]["holdings"] == held


def test_retirement_goal_with_no_money_left_is_not_called_missing(website_bundle):
    from conftest import MID
    from finadvisor.advisor.profile import Goal, Profile
    p = Profile(take_home_monthly=100_000, expenses_monthly=40_000, liquid_savings=300_000, health_cover=800_000,
                experience="intermediate", gl_answers=dict(MID),
                goals=[Goal(id="h", name="Home", kind="home", target_today=5_000_000, horizon_years=3),
                       Goal(id="r", name="Retirement", kind="retirement", target_today=30_000_000, horizon_years=28)])
    out = reply(website_bundle, p, "How much should I save for retirement?")
    assert "no retirement goal" not in out.text
    assert out.text.startswith("Nothing goes to retirement yet") or out.text.startswith("Put about")


def test_model_recap_is_labelled_and_never_left_empty(website_bundle, stretched):
    out, _ = run_turn(Advisor(website_bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose:
                      "First get health cover. Then build the fund.")), stretched, "Make me a plan")
    assert "**In plain words**\n\nFirst get health cover." in out.text
    out, _ = run_turn(Advisor(website_bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose:
                      "Save ₹12,345 now.")), stretched, "Make me a plan")      # every sentence dropped
    assert "In plain words" not in out.text
