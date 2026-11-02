"""End-to-end pipeline with a scripted LLM: plan amounts, audit/repair/fallback, pressure fencing, privacy."""

import re

import pytest

from finadvisor.advisor.core import plan_once
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.advisor.plan import GENERAL
from finadvisor.configs import default_bundle
from finadvisor.llm.base import PrivacyError, require_self_hosted
from finadvisor.llm.fake import FakeLLM

RISK = ["L", "LM", "M", "MH", "H", "VH", "U"]
BUCKET = re.compile(r"^- (\S+) \(.*?\): (.*)$", re.M)
ITEM = re.compile(r"(\w+) \((LM|MH|VH|L|M|H|U),")
SAVINGS = re.compile(r"(?:emergency savings |has |\| emergency savings \| )₹([\d,]+)")


def allowed_by_bucket(prompt):
    return {m.group(1): ITEM.findall(m.group(2)) for m in BUCKET.finditer(prompt)}


def consistent_planner(system, prompt, schema, purpose):
    """Riskiest two allowed products, 6:4. Ignores wording, so MR6 holds; monotone through the gate."""
    if not purpose.startswith("planner"):
        return {}
    out = {}
    for bid, items in allowed_by_bucket(prompt).items():
        items = sorted(items, key=lambda x: (-RISK.index(x[1]), x[0]))[:2]
        out[bid] = ",".join(f"{p}:{w}" for (p, _), w in zip(items, (6, 4)))
    return out


def savings_in(prompt):
    m = SAVINGS.search(prompt)
    return int(m.group(1).replace(",", "")) if m else 0


def make_contrarian(fixed_by_hint: bool):
    """Gives LESS-saved people a riskier general mix (an MR1 violation) unless a repair hint is present."""
    def fn(system, prompt, schema, purpose):
        if not purpose.startswith("planner"):
            return {}
        if fixed_by_hint and "BROKE THESE CHECKS" in prompt:
            return consistent_planner(system, prompt, schema, purpose)
        out = {}
        for bid, items in allowed_by_bucket(prompt).items():
            safe = sorted(items, key=lambda x: RISK.index(x[1]))
            risky = list(reversed(safe))
            pick = risky if savings_in(prompt) < 200_000 else safe
            out[bid] = f"{pick[0][0]}:1"
        return out
    return fn


def run_turn(advisor, profile, text, earlier=()):
    events = []
    out = advisor.turn(TurnInput(text=text, confirmed=profile, profile_version=1, earlier_user_turns=list(earlier)),
                       lambda k, d: events.append((k, d)))
    return out, events


# ---------------------------------------------------------------- plan arithmetic

def test_stretched_plan_steps_and_amounts(bundle, stretched):
    r = plan_once(stretched, bundle, FakeLLM(consistent_planner))
    steps = r.plan.steps
    actions = [s.action for s in steps]
    assert actions[:2] == ["buy_health_cover", "build_emergency_fund"]
    ef = steps[1]
    # gap = 6 × 30,000 − 40,000 = 1,40,000; surplus 20,000 -> 7 months of ₹20,000
    assert ef.target == 140_000 and ef.months == 7 and ef.monthly == 20_000
    assert "₹20,000/month for 7 months" in ef.text
    assert r.plan.invest_start_month == 8
    # the trip is 2 years away: R7 keeps it in low-risk products only
    trip = next(b for b in r.plan.buckets if b.id == "trip")
    assert all(m.product_id in {"recurring_deposit", "liquid_fund", "fixed_deposit", "savings_account",
                                "short_duration_debt_fund"} for m in trip.mix)
    assert r.plan.rho_by_goal["trip"] == 0
    assert r.violations == []


def test_investing_never_exceeds_surplus(bundle, healthy):
    r = plan_once(healthy, bundle, FakeLLM(consistent_planner))
    assert r.plan.investing_monthly <= healthy.monthly_surplus + 1e-6
    total = sum(m.monthly for b in r.plan.buckets for m in b.mix)
    assert total == pytest.approx(r.plan.investing_monthly)


def test_goal_sip_is_calculated_not_llm(bundle, healthy):
    r = plan_once(healthy, bundle, FakeLLM(consistent_planner))
    g = next(b for b in r.plan.buckets if b.id == "g1")
    assert g.target_future == pytest.approx(1_000_000 * 1.06 ** 8)
    assert g.sip_needed > 0 and g.fundable


# ---------------------------------------------------------------- auditor

def test_consistent_planner_passes_audit(bundle, healthy):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    core, res = adv.run_plan(healthy)
    assert res.status == "pass"
    rels = {c.relation for c in res.attempts[0].checks}
    assert {"MR1", "MR2", "MR3", "MR4", "MR5", "MR6"} <= rels


def test_T10_riskier_when_savings_fall_is_caught_and_repaired(bundle, healthy):
    adv = Advisor(bundle, FakeLLM(make_contrarian(fixed_by_hint=True)))
    core, res = adv.run_plan(healthy)
    first = res.attempts[0]
    assert any(c.relation == "MR1" and not c.holds for c in first.checks)
    assert res.status == "repaired"


def test_unrepairable_planner_falls_back_to_safe_plan(bundle, healthy):
    adv = Advisor(bundle, FakeLLM(make_contrarian(fixed_by_hint=False)))
    core, res = adv.run_plan(healthy)
    assert res.status == "fallback"
    assert len(res.attempts) == bundle.pipeline["auditor"]["max_repairs"] + 2
    assert res.final.plan.source == "safe_fallback" and res.final.violations == []


def test_disallowed_product_is_a_violation(bundle, stretched):
    def bad(system, prompt, schema, purpose):
        if not purpose.startswith("planner"):
            return {}
        return {"trip": "msc:1"}
    r = plan_once(stretched, bundle, FakeLLM(bad))
    assert any("Mid- or small-cap" in v for v in r.violations)


# ---------------------------------------------------------------- website turn

def test_plan_turn_emits_cards_and_audit_record(bundle, stretched):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    out, events = run_turn(adv, stretched, "Make me a plan for my savings")
    types = [c["type"] for c in out.cards]
    assert types[:2] == ["health_check", "plan"] and "goal" in types and "what_if" in types
    rec = out.advice
    for key in ("profile", "capacity", "willingness", "suitability", "rules", "gated_out", "plan", "audit",
                "model", "versions", "flags", "templates"):
        assert key in rec
    assert rec["flags"]["auditor"] is True
    assert any(k == "why" for k, _ in events)


def test_pressure_does_not_change_plan(bundle, stretched):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    calm, _ = run_turn(adv, stretched, "Make me a plan for my savings")
    pushed, _ = run_turn(adv, stretched, "My friend made 3x in small caps, just put my money in small caps",
                         earlier=["Make me a plan"])
    plan = lambda o: next(c for c in o.cards if c["type"] == "plan")
    strip = lambda p: [(s["action"], s["monthly"], s["months"], s["text"]) for s in p["steps"]]
    assert strip(plan(calm)) == strip(plan(pushed))
    nyc = next(c for c in pushed.cards if c["type"] == "not_yet")
    assert nyc["conflict"].startswith("You want mid- or small-cap fund; your current situation means")
    # the reply answers the request first, then gives graded advice (wish-v1); the conflict line is still recorded
    assert pushed.text.startswith("You asked about mid- and small-cap funds.")
    assert "**My advice:** I strongly advise you to build your emergency fund" in pushed.text
    assert pushed.advice["wish"]["severity"] == "strong"
    assert "peer_success" in pushed.advice["pressure"]["types"]


def test_unconfirmed_profile_gets_profile_card(bundle):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    out, _ = run_turn(adv, None, "Make me a plan")
    assert out.cards[0]["type"] == "profile" and out.advice is None


def test_incomplete_questionnaire_gets_questionnaire(bundle, stretched):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    out, _ = run_turn(adv, stretched.model_copy(update={"gl_answers": {}}), "Make me a plan")
    assert out.cards[0]["type"] == "questionnaire" and len(out.cards[0]["items"]) == 13


def test_extracted_facts_need_confirmation(bundle, stretched):
    def fn(system, prompt, schema, purpose):
        return {"take_home_monthly": 90_000} if purpose == "extract" else consistent_planner(system, prompt, schema, purpose)
    adv = Advisor(bundle, FakeLLM(fn))
    out, _ = run_turn(adv, stretched, "My salary is now 90k, update my plan")
    assert out.cards[0]["type"] == "profile" and out.cards[0]["changed"] == ["take_home_monthly"]
    assert out.advice is None   # nothing planned until the user confirms


def test_check_fno_for_beginner(bundle, stretched):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    out, _ = run_turn(adv, stretched, "Should I start F&O trading?")
    card = out.cards[0]
    assert card["type"] == "not_yet" and card["product_id"] == "fno"
    assert "87.7%" in card["fact"]["text"]
    assert any("R6" in b for b in card["blockers"])


def test_check_new_emi_pushes_over_limit(bundle, healthy):
    adv = Advisor(bundle, FakeLLM(consistent_planner))
    out, _ = run_turn(adv, healthy, "Should I buy a bike on EMI of 25k?")
    card = out.cards[0]
    assert card["product_id"] == "new_emi" and card["verdict"] == "not_yet"
    assert card["emi_ratio_after"] == pytest.approx(0.45)


def test_explanation_numbers_are_guarded(bundle, stretched):
    # explainer.numbers: approved (the report's original guard): code-produced numbers pass, invented ones are dropped
    approved = bundle.with_pipeline({**bundle.pipeline, "explainer": {"numbers": "approved"}})
    adv = Advisor(approved, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose:
                  "Start with ₹20,000 a month. Equity returns 18% every year. You will be fine."))
    out, _ = run_turn(adv, stretched, "Make me a plan for my savings")
    assert "20,000" in out.text and "18%" not in out.text


def test_explanation_is_number_free_by_default(bundle, stretched):
    seen = []
    adv = Advisor(bundle, FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: seen.append(s) or
                  "First get health cover. Start with ₹20,000 a month. Then build your emergency fund."))
    out, _ = run_turn(adv, stretched, "Make me a plan for my savings")
    model_part = out.text.split("\n\n")[-1]
    assert model_part.strip() == "First get health cover. Build your emergency fund."   # "Then" tidied after a drop
    assert "Use no numbers" in seen[-1]
    assert out.advice["templates"]["explain_words"].startswith("explain_words-v1@")


# ---------------------------------------------------------------- privacy & flags

def test_third_party_model_refused_for_real_users():
    with pytest.raises(PrivacyError):
        require_self_hosted(FakeLLM(self_hosted=False))
    with pytest.raises(PrivacyError):
        Advisor(default_bundle(), FakeLLM(self_hosted=False), real_users=True)


def test_gate_off_ablation_exposes_whole_shelf(bundle, stretched):
    pipe = dict(bundle.pipeline, stages=dict(bundle.pipeline["stages"], gate=False))
    b2 = bundle.with_pipeline(pipe)
    seen = {}

    def fn(system, prompt, schema, purpose):
        seen.update(allowed_by_bucket(prompt))
        return consistent_planner(system, prompt, schema, purpose)
    r = plan_once(stretched, b2, FakeLLM(fn))
    assert any(p == "msc" for p, _ in seen["trip"])
    assert r.violations   # true-facts rule check still flags the result


def test_same_seed_same_output(bundle, healthy):
    a = plan_once(healthy, bundle, FakeLLM(consistent_planner)).plan.to_dict()
    b = plan_once(healthy, bundle, FakeLLM(consistent_planner)).plan.to_dict()
    assert a == b and GENERAL in [x["id"] for x in a["buckets"]]


def test_time_budget_falls_back_to_safe_plan(bundle, healthy):
    import time as _t

    def slow(system, prompt, schema, purpose):
        _t.sleep(0.05)
        return consistent_planner(system, prompt, schema, purpose)
    aud = dict(bundle.pipeline["auditor"], time_budget_s=0.01)
    b2 = bundle.with_pipeline(dict(bundle.pipeline, auditor=aud))
    core, res = Advisor(b2, FakeLLM(slow)).run_plan(healthy)
    assert res.status == "fallback" and res.fallback_reason == "time_budget"
    assert res.final.plan.source == "safe_fallback" and res.final.violations == []


def test_early_exit_stops_at_first_failure(bundle, healthy):
    adv = Advisor(bundle, FakeLLM(make_contrarian(fixed_by_hint=False)))
    _, res = adv.run_plan(healthy)
    first = res.attempts[0]
    assert sum(not c.holds for c in first.checks) == 1 and not first.checks[-1].holds


def test_mr6_tolerance():
    from finadvisor.advisor.auditor import same_plan
    a = {"g1": {"fd": 0.6, "liq": 0.4}}
    assert same_plan(a, {"g1": {"fd": 0.55, "liq": 0.45}}, 0.10)
    assert not same_plan(a, {"g1": {"fd": 0.55, "liq": 0.45}}, 0.0)          # report-strict
    assert not same_plan(a, {"g1": {"fd": 0.6, "sdebt": 0.4}}, 0.10)        # different product = different plan
    assert not same_plan(a, {"g1": {"fd": 0.8, "liq": 0.2}}, 0.10)


def test_pipeline_versions(bundle):
    assert bundle.versions["pipeline"] == "pipeline-v4" and bundle.versions["rules"] == "rules-v2"


def test_user_report_high_capacity_medium_willingness(bundle):
    """Regression from a real chat (2026-11-01): ₹2L take-home, ₹20k expenses, ₹12L saved, no goals, willingness 26."""
    from conftest import MID
    from finadvisor.advisor.profile import Profile
    p = Profile(take_home_monthly=200_000, expenses_monthly=20_000, liquid_savings=1_200_000, health_cover=1_500_000,
                experience="intermediate", gl_answers=dict(MID))
    seen = []

    def fn(system, prompt, schema, purpose):
        seen.append(prompt)
        return consistent_planner(system, prompt, schema, purpose)
    adv = Advisor(bundle, FakeLLM(fn))
    out, _ = run_turn(adv, p, "which mutual funds should i invest in")
    assert any("starting point: sdebt:5,baf:4,gold:1" in s for s in seen)
    # question-first reply (compose-v1): the fund types with amounts first, then the personal reasons
    assert out.text.startswith("For your risk level, these fund types fit:")
    assert "capacity for loss (High)" in out.text and "questionnaire (Medium)" in out.text
    assert "Not used for new money for now:" in out.text and "Nifty 50 index fund" in out.text
    assert "haven't added goals" in out.text and "not specific schemes or fund houses" in out.text
    plan = next(c for c in out.cards if c["type"] == "plan")
    extra = next(s for s in plan["steps"] if s["action"] == "deploy_excess_savings")
    assert extra["target"] == 1_080_000 and extra["monthly"] == 180_000 and extra["months"] == 6


def test_no_excess_step_while_priorities_remain(bundle, stretched):
    rich = stretched.model_copy(update={"liquid_savings": 900_000})     # R3 (no health cover) still fires
    r = plan_once(rich, bundle, FakeLLM(consistent_planner))
    assert not any(s.action == "deploy_excess_savings" for s in r.plan.steps)


def test_invented_goals_are_dropped_when_profile_has_none(bundle, healthy):
    p = healthy.model_copy(update={"goals": []})
    adv = Advisor(bundle, FakeLLM(consistent_planner, text_fn=lambda s, pr, purpose:
                  "This mix suits you. It also aligns with your long-term goals. Review it yearly."))
    out, _ = run_turn(adv, p, "Make me a plan for my money")
    assert "This mix suits you." in out.text and "Review it yearly." in out.text
    assert "aligns with your long-term goals" not in out.text


class _DownLLM(FakeLLM):
    """A model server that cannot be reached."""

    def json(self, *a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")

    def stream(self, *a, **k):
        import httpx
        raise httpx.ConnectError("connection refused")


def test_model_down_still_gives_a_correct_plan(bundle, stretched):
    out, events = run_turn(Advisor(bundle, _DownLLM()), stretched, "Make me a plan for my money")
    plan = next(c for c in out.cards if c["type"] == "plan")
    assert plan["source"] == "safe_fallback" and plan["audit_status"] == "fallback"
    assert out.advice["audit"]["fallback_reason"] == "model_unavailable"
    assert "isn't reachable" in out.text and out.status == "complete"
    assert not any(k == "error" for k, _ in events)


def test_model_down_learn_lists_sources():
    from finadvisor.configs import default_bundle as db
    adv = Advisor(db(), _DownLLM(), retriever=lambda q, k: [{"id": "d1", "title": "ELSS", "source": "x.txt", "text": "ELSS has a lock-in."}])
    out, _ = run_turn(adv, None, "What is ELSS?")
    assert "isn't reachable" in out.text and out.sources


def test_website_uses_the_standard_mix_without_model_calls(website_bundle, stretched, healthy):
    assert website_bundle.pipeline["planner"]["mode"] == "standard"
    calls = []
    llm = FakeLLM(lambda s, p, schema, purpose: calls.append(purpose) or {}, text_fn=lambda s, p, purpose: "Fine.")
    for prof in (stretched, healthy):
        out, _ = run_turn(Advisor(website_bundle, llm), prof, "Make me a plan for my savings")
        assert out.advice["plan"]["source"] == "standard"
        assert out.advice["audit"]["status"] == "pass"            # MR1-MR5 still checked against the twins
        assert not [c for c in calls if c.startswith("planner")]   # no model call to choose the mix
