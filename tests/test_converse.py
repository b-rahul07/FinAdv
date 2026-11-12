"""The website's conversation stage: what it answers, what it leaves to the pipeline, and that experiments never run it."""

from datetime import date

import pytest

from conftest import MID
from finadvisor.advisor import converse, overview
from finadvisor.advisor.numbers import collect, unapproved
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.advisor.profile import Debt, Goal, Profile, TaxFacts
from finadvisor.configs import default_bundle, load_bundle
from finadvisor.db import models  # noqa: F401  (registers the tables before the client fixture builds the database)
from finadvisor.llm.fake import FakeLLM
from test_api import PROFILE, client, events, login  # noqa: F401  (fixture)
from test_pipeline import consistent_planner

WEB = load_bundle("pipeline/pipeline-v5-website.yaml")
SECTIONS = "80C 80D 80CCD(1B)"          # section names are not amounts; every other number must come from code
TODAY = date(2026, 11, 12)


def person(**kw) -> Profile:
    base = dict(age=28, take_home_monthly=70_000, expenses_monthly=32_000, liquid_savings=60_000, dependants=1,
                debts=[Debt(kind="two_wheeler", outstanding=45_000, rate_pa=11, emi_monthly=3_500)],
                goals=[Goal(id="g1", name="Europe trip", kind="travel", target_today=250_000, horizon_years=2, saved_so_far=40_000)],
                experience="beginner", gl_answers=dict(MID))
    return Profile(**{**base, **kw})


PLAN = {"steps": [
    {"order": 1, "action": "buy_health_cover", "text": "Buy health cover of ₹5,00,000.", "rule": "R3", "monthly": 0, "months": 0, "start_month": 1},
    {"order": 2, "action": "build_emergency_fund", "text": "Build the emergency fund.", "rule": "R1", "monthly": 30_000, "months": 5, "start_month": 1},
    {"order": 3, "action": "invest", "text": "Invest for Europe trip.", "rule": None, "monthly": 11_000, "months": 0, "start_month": 6, "goal_id": "g1"}],
    "buckets": [{"id": "g1", "name": "Europe trip", "monthly": 11_000, "sip_needed": 9_000, "fundable": True, "shortfall": 0}],
    "monthly_surplus": 34_500, "investing_monthly": 34_500, "invest_start_month": 6, "notes": []}


def home(p: Profile, made=date(2026, 9, 3), recs=None, stale=False) -> dict:
    plan = {**overview.plan_overview(PLAN, made, recs or {}), "made_at": made.isoformat(), "stale": stale}
    return {"plan": plan, "goals": overview.goal_progress(p, PLAN["buckets"]),
            "health": {"score": 3, "out_of": 7}, "health_history": [{"at": "2026-09-03", "score": 2, "out_of": 7, "profile_version": 1},
                                                                     {"at": "2026-11-01", "score": 3, "out_of": 7, "profile_version": 2}]}


def ask(text: str, p: Profile | None = None, with_plan=True, earlier=(), **home_kw):
    p = p or person()
    ctx = {"home": home(p, **home_kw) if with_plan else {"plan": None}, "today": TODAY}
    return converse.reply(TurnInput(text=text, confirmed=p, earlier_user_turns=list(earlier), context=lambda: ctx), WEB)


# ----------------------------------------------------------------------------- follow-up what-ifs

@pytest.mark.parametrize("text, change", [
    ("And if I add a car loan EMI of 12k?", {"new_emi": 12_000}),
    ("what if I take a bike loan of 4,500 a month", {"new_emi": 4_500}),
    ("What if I have two dependants?", {"dependants": 2}),
    ("with 2 more kids?", {"dependants": 3}),
    ("suppose we have a baby next year", {"dependants": 2}),
    ("if I save 5k more each month?", {"expenses_monthly": 27_000}),
    ("what if I cut my expenses by ₹4,000", {"expenses_monthly": 28_000}),
    ("what if my rent goes up by 6000", {"expenses_monthly": 38_000}),
    ("How about if I get a raise of 10k?", {"take_home_monthly": 80_000}),
    ("what if my salary becomes 90,000", {"take_home_monthly": 90_000}),
])
def test_follow_ups_run_the_what_if_engine(text, change):
    r = ask(text)
    assert r is not None and r.route == "whatif"
    card = r.cards[0]
    assert card["type"] == "what_if_answer" and card["changes"] == change
    assert r.record["what_if"]["before"]["monthly_surplus"] == 34_500
    assert (card["apply"] is None) == ("new_emi" in change)              # a new loan is added with its real details
    if card["apply"]:
        assert Profile(**card["apply"]).model_dump() == person().model_copy(update=change).model_dump()
    # every number in the sentence comes from the engines or from the person's own message
    allowed = collect([card, person().model_dump(), text])
    assert not unapproved(r.text, allowed), r.text


@pytest.mark.parametrize("text", [
    "what if I put 5k more in crypto every month",        # names a product the plan never holds: the pipeline
    "what if I buy Reliance shares with 10k",
    "what if I take a home loan of 40 lakh",              # a loan's size, not its EMI: not guessed at
    "what if my salary becomes 18 lakh",                  # a yearly figure: not guessed at
    "what if the market crashes",                         # no change to the facts
    "My salary is now 80k",                               # a fact, not a hypothetical: extraction handles it
])
def test_unclear_or_risky_follow_ups_go_to_the_pipeline(text):
    assert ask(text) is None


def test_a_follow_up_needs_a_plan_and_a_complete_profile():
    assert ask("And if I add a car loan EMI of 12k?", with_plan=False) is None
    assert ask("And if I add a car loan EMI of 12k?", person(gl_answers={})) is None
    assert converse.reply(TurnInput(text="what if I have two dependants?", confirmed=None), WEB) is None


# ----------------------------------------------------------------------------- tax

def test_tax_asks_for_the_salary_once_then_answers_from_the_calculator():
    r = ask("How much tax will I pay this year?")
    assert r.route == "ask" and r.record is None
    card = r.cards[0]
    assert (card["type"], card["field"], card["then"]) == ("ask", "gross_salary_annual", "How much tax will I pay this year?")
    p = converse.apply_answers(person(), {"gross_salary_annual": 1_500_000}, WEB)
    assert p.tax.gross_salary_annual == 1_500_000 and p.model_dump()["tax"]["deductions_80c"] is None
    r = ask(card["then"], p)
    # old regime, nothing claimed: 15,00,000 - 50,000 = 14,50,000; 12,500 + 1,00,000 + 30% of 4.5L = 2,47,500; cess 9,900
    assert r.route == "tax" and "₹97,500 under the new regime" in r.text and "₹2,57,400 under the old regime" in r.text
    assert "new regime is cheaper by ₹1,59,900" in r.text and "Estimated, not tax advice" in r.text
    assert r.cards[0]["type"] == "tax" and r.cards[0]["deductions_known"] is False
    assert r.record["tax"]["better"] == "new" and r.record["tax"]["version"] == "income-tax-fy2026-27"
    assert not unapproved(r.text, collect([r.record["tax"], r.cards[0]["source"], SECTIONS])), r.text


@pytest.mark.parametrize("text, has", [
    ("Which regime is better for me, old or new?", ["new regime is cheaper"]),
    ("Would ELSS, PPF or NPS cut my tax?", ["only under the old regime", "Under the new regime none of them reduces tax"]),
    ("Should I invest in 80C to save tax?", ["Using all of 80C (₹1,50,000)"]),
    ("Is an FD or a debt fund better for me after tax?", ["FD against debt fund", "which are not guaranteed"]),
])
def test_tax_questions_people_ask(text, has):
    p = person(tax=TaxFacts(gross_salary_annual=1_800_000, deductions_80c=60_000, deductions_80d=18_000))
    r = ask(text, p)
    assert r is not None and r.route == "tax", text
    for piece in has:
        assert piece in r.text, (piece, r.text)
    assert "80C ₹60,000" in r.text and "80D ₹18,000" in r.text
    assert not unapproved(r.text, collect([r.record["tax"], WEB.assumptions, r.cards[0]["source"], SECTIONS,
                                           converse.income_tax.rules(), converse.config()])), r.text


@pytest.mark.parametrize("text", ["What is section 80C?", "Explain the new tax regime", "How does income tax work in India?"])
def test_general_tax_questions_stay_with_the_library(text):
    assert ask(text, person(tax=TaxFacts(gross_salary_annual=1_800_000))) is None


def test_deductions_form_and_bad_answers():
    p = converse.apply_answers(person(tax=TaxFacts(gross_salary_annual=1_200_000)),
                               {"deductions_80c": 150_000, "deductions_80d": 20_000, "hra_exemption_annual": 96_000}, WEB)
    assert (p.tax.gross_salary_annual, p.tax.deductions_80c, p.tax.hra_exemption_annual) == (1_200_000, 150_000, 96_000)
    assert p.goals == person().goals and p.take_home_monthly == 70_000          # nothing else moves
    for bad in ({"gross_salary_annual": -5}, {"age": 7}, {"take_home_monthly": 1}, {"age": "old"}):
        with pytest.raises(ValueError):
            converse.apply_answers(person(), bad, WEB)


# ----------------------------------------------------------------------------- retirement without a goal

def test_retirement_without_a_goal_asks_one_number_and_makes_the_goal():
    r = ask("How much do I need to save for retirement?")
    assert r.route == "ask" and r.cards[0]["field"] == "retirement_spend_monthly" and "₹32,000" in r.cards[0]["hint"]
    assert ask("How much do I need to save for retirement?", person(age=None)).cards[0]["field"] == "age"
    p = converse.apply_answers(person(), {"retirement_spend_monthly": 50_000}, WEB)
    goal = p.goals[-1]
    assert (goal.id, goal.kind, goal.horizon_years) == ("g2", "retirement", 32)          # 60 - 28
    assert goal.target_today == round(converse.goal_calc.retirement_corpus_today(50_000, 25, 7.0, 6.0))
    assert ask("How much do I need to save for retirement?", p) is None                   # now the plan answers
    both = converse.apply_answers(person(age=None), {"age": 30, "retirement_spend_monthly": 40_000}, WEB)
    assert both.age == 30 and both.goals[-1].horizon_years == 30
    with pytest.raises(ValueError, match="planning retirement age"):
        converse.apply_answers(person(age=61), {"retirement_spend_monthly": 40_000}, WEB)
    assert ask("What is a pension plan?") is None


# ----------------------------------------------------------------------------- "am I on track?"

def test_on_track_reads_the_plan_goals_and_health():
    r = ask("Am I on track?", recs={"buy_health_cover": {"id": "a", "status": "done"}})
    assert r.route == "track"
    # the emergency-fund step ran Sep 2026 to Jan 2027, so in Nov 2026 nothing is overdue
    assert r.text.startswith("Yes, so far: nothing in your plan is overdue.")
    assert "You have done 1 of 3 steps of the plan made on 3 Sep 2026." in r.text
    assert "Next is step 2 (Sep 2026 to Jan 2027): Build the emergency fund." in r.text
    assert "Europe trip: 16% saved (₹40,000 of ₹2,50,000 in today's rupees); it needs ₹9,000 a month and your plan gives ₹11,000." in r.text
    assert "Your health check passes 3 of 7, up from 2 on 3 Sep 2026." in r.text
    assert r.record["track"]["overdue"] == []


def test_on_track_says_what_is_overdue_or_stale():
    late = ask("how am I doing?", made=date(2026, 3, 10))
    # made in March: the one-off cover step (March) and the fund step (ending July) are both past and open
    assert late.text.startswith("Not quite: step 1 was due by Mar 2026 and is still open, along with 2 more.")
    assert late.record["track"]["overdue"] == [1, 2, 3]
    stale = ask("am I on track with my plan?", stale=True)
    assert stale.text.startswith("Your facts changed after this plan was made") and stale.cards[0]["items"][0].startswith("Update my money plan")
    done = ask("on track?", recs={k: {"id": k, "status": "done"} for k in ("buy_health_cover", "build_emergency_fund", "invest:g1")})
    assert done.text.startswith("Yes: every step of your plan is done or skipped.")
    assert ask("Am I on track?", with_plan=False) is None                    # no plan yet: the pipeline makes one


# ----------------------------------------------------------------------------- the plan-change line

def test_plan_changes_between_two_plans():
    new = {**PLAN, "monthly_surplus": 40_000, "investing_monthly": 40_000, "invest_start_month": 4,
           "steps": [s for s in PLAN["steps"] if s["action"] != "buy_health_cover"]
           + [{"order": 4, "action": "invest", "text": "x", "monthly": 5_000, "months": 0, "start_month": 4, "goal_id": "g9"}],
           "buckets": PLAN["buckets"] + [{"id": "g9", "name": "Retirement"}]}
    assert overview.plan_changes(PLAN, new, date(2026, 9, 3)) == [
        "Money left each month: ₹34,500 → ₹40,000.", "No longer in the plan: buy health cover.",
        "New in the plan: invest for Retirement.", "Investing starts in month 4 instead of month 6.",
        "Investing: ₹34,500 → ₹40,000 a month."]
    assert overview.plan_changes(PLAN, PLAN, date(2026, 9, 3)) == ["Same plan as on 3 Sep 2026: nothing changed."]


# ----------------------------------------------------------------------------- the stage in the pipeline and the API

def test_experiments_never_run_the_conversation_stage():
    """default.yaml has no conversation flag: the same turn goes to the routes exactly as before."""
    assert "conversation" not in default_bundle().pipeline["stages"]
    seen = []
    llm = FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: "ok")
    p = person(tax=TaxFacts(gross_salary_annual=1_500_000))
    ctx = lambda: {"home": home(p), "today": TODAY}  # noqa: E731
    for bundle, expect in ((default_bundle(), "plan"), (WEB, "tax")):
        out = Advisor(bundle, llm).turn(TurnInput(text="How much tax will I pay on my salary?", confirmed=p, context=ctx),
                                        lambda k, d: seen.append((k, d)))
        assert out.route == expect
    web = Advisor(WEB, llm).turn(TurnInput(text="How much tax will I pay on my salary?", confirmed=p, context=ctx), lambda k, d: None)
    assert web.advice["route"] == "tax" and web.advice["flags"]["conversation"] is True and web.advice["versions"]
    forced = Advisor(WEB, llm).turn(TurnInput(text="How much tax will I pay on my salary?", confirmed=p, forced_route="learn"),
                                    lambda k, d: None)
    assert forced.route == "learn"                                          # an explicit route is respected
    plain = Advisor(WEB, llm).turn(TurnInput(text="Make me a money plan", confirmed=p, context=ctx), lambda k, d: None)
    assert plain.route == "plan" and plain.advice["plan"]


def test_api_ask_answer_follow_up_and_the_change_line(client):
    h = login(client)
    client.put("/api/profile", json={"data": {**PROFILE, "age": 30}}, headers=h)
    chat = client.post("/api/chats", json={}, headers=h).json()

    def say(text):
        return events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": text}, headers=h))

    ev = say("How much tax will I pay this year?")
    card = next(d for k, d in ev if k == "card")
    assert ("route", {"route": "ask"}) in ev and card["field"] == "gross_salary_annual" and ev[-1][1]["advice_run_id"] is None
    assert client.post("/api/profile/answer", json={"answers": {"gross_salary_annual": -1}}, headers=h).status_code == 422
    v = client.post("/api/profile/answer", json={"answers": {"gross_salary_annual": 900000}}, headers=h).json()
    assert v["version"] == 2 and v["data"]["tax"]["gross_salary_annual"] == 900000 and v["sources"]["gross_salary_annual"] == "asked"
    ev = say(card["then"])
    assert ("route", {"route": "tax"}) in ev and ev[-1][1]["advice_run_id"]
    run = client.get(f"/api/advice/{ev[-1][1]['advice_run_id']}", headers=h).json()
    assert run["route"] == "tax" and run["flags"]["conversation"] is True

    ev = say("And if I add a car loan EMI of 5k?")                                      # no plan yet: the pipeline answers
    assert ("route", {"route": "check"}) in ev and not any(d.get("type") == "what_if_answer" for k, d in ev if k == "card")
    ev = say("Make me a plan for my money")
    assert not any(d.get("type") == "plan_change" for k, d in ev if k == "card")          # the first plan changes nothing
    ev = say("And if I add a car loan EMI of 5k?")
    wi = next(d for k, d in ev if k == "card" and d["type"] == "what_if_answer")
    assert ("route", {"route": "whatif"}) in ev and wi["after"]["monthly_surplus"] == 15_000
    assert client.get("/api/home", headers=h).json()["plan"]["total"] > 0                  # the saved plan is untouched
    assert ("route", {"route": "track"}) in say("Am I on track?")

    client.put("/api/profile", json={"data": {**v["data"], "take_home_monthly": 60000}}, headers=h)
    ev = say("Make me a plan for my money")
    change = next(d for k, d in ev if k == "card" and d["type"] == "plan_change")
    assert change["lines"][0] == "Money left each month: ₹20,000 → ₹30,000."
    saved = client.get(f"/api/chats/{chat['id']}", headers=h).json()["messages"][-1]
    assert saved["cards"][0]["type"] == "plan_change"                                       # stored first, shown on top

    ev = say("How much should I save for retirement?")                                      # PROFILE has a retirement goal
    assert ("route", {"route": "plan"}) in ev
