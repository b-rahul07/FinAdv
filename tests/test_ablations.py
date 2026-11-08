"""Ablations for the paper: calculators off (A5), number guard off (A4), and the explanation trace."""

import json
import re
from pathlib import Path

import pytest

from conftest import MAX
from experiments import metrics
from experiments.metrics import OVERSPEND
from finadvisor.advisor.core import plan_once
from finadvisor.advisor.plan import cash_available
from finadvisor.advisor.profile import Debt, Profile
from finadvisor.advisor.pipeline import Advisor, TurnInput
from finadvisor.llm.fake import FakeLLM
from test_pipeline import consistent_planner

BUCKET = re.compile(r"^- (\w+) \(.*?\): (.+)$", re.M)


def amounts_writer(each: float):
    """A model that writes `each` rupees for every allowed product of every bucket."""
    def fn(system, prompt, schema, purpose):
        if not purpose.startswith("planner_amounts"):
            return consistent_planner(system, prompt, schema, purpose)
        return {bid: ",".join(f"{c.split(' ')[0]}:{each:,.0f}" for c in items.split(", "))
                for bid, items in BUCKET.findall(prompt)}
    return fn


def no_calculators(bundle):
    return bundle.with_pipeline({**bundle.pipeline, "stages": {**bundle.pipeline["stages"], "calculators": False}})


def test_calculators_off_keeps_the_models_amounts_and_the_calculators_beside_them(bundle, healthy):
    r = plan_once(healthy, no_calculators(bundle), FakeLLM(amounts_writer(1_000)))
    assert r.plan.source == "model_amounts"
    a = r.plan.amounts
    assert set(a["model"]) == set(a["calculator"]) and a["surplus"] == healthy.monthly_surplus
    assert all(v == 1_000 * len([m for m in b.mix]) for b in r.plan.buckets for k, v in a["model"].items() if k == b.id)
    assert r.plan.investing_monthly == sum(a["model"].values())


def test_calculators_off_catches_overspending(bundle, healthy):
    r = plan_once(healthy, no_calculators(bundle), FakeLLM(amounts_writer(5_00_000)))   # far more than the surplus
    assert "plan invests more than the monthly surplus" in r.violations


def test_number_guard_off_shows_unapproved_sentences_but_records_them(website_bundle, healthy):
    bad = "Equity funds return 12% a year. Keep going."
    llm = FakeLLM(consistent_planner, text_fn=lambda s, p, purpose: bad if purpose == "explain" else "")
    on, off = website_bundle, website_bundle.with_pipeline(
        {**website_bundle.pipeline, "explainer": {**website_bundle.pipeline["explainer"], "number_guard": False}})
    texts, gens = [], []
    for b in (on, off):
        out = Advisor(b, llm).turn(TurnInput(text="Make me a money plan", confirmed=healthy), lambda k, d: None)
        texts.append(out.text)
        gens.append(next(g for g in out.generations if g.purpose == "explain"))
    assert "12%" not in texts[0] and "12%" in texts[1]
    for g in gens:
        assert g.output["raw"].startswith("Equity funds return 12% a year.")   # the model's text before any guard
        assert any(d["numbers"] for d in g.output["dropped_sentences"])
    assert gens[1].output["number_guard"] is False and gens[1].output["dropped_sentences"][0]["shown"]


# ----------------------------------------------------------------------------- rule-check-v2: month by month

def first_product_writer(per_bucket: dict[str, float]):
    """A model that puts the given rupees a month on the first allowed product of each bucket."""
    def fn(system, prompt, schema, purpose):
        if not purpose.startswith("planner_amounts"):
            return consistent_planner(system, prompt, schema, purpose)
        return {bid: f"{items.split(', ')[0].split(' ')[0]}:{per_bucket.get(bid, 0):,.0f}"
                for bid, items in BUCKET.findall(prompt)}
    return fn


def persona(pid: str) -> Profile:
    for line in Path("experiments/data/personas_v1.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["id"] == pid:
            return Profile(**row["profile"])
    raise KeyError(pid)


def test_uncleared_emis_are_not_spendable_the_live_a5_case(bundle):
    """S7-002: surplus ₹4,000, a ₹28,000 car-loan EMI the plan never clears (not costly). qwen2.5:3b wrote ₹5,000
    for the goal and ₹5,000 long-term. rule-check-v1 allowed surplus + every EMI (₹32,000) and passed it."""
    p = persona("S7-002")
    assert p.monthly_surplus == 4_000 and sum(d.emi_monthly for d in p.debts) == 28_000
    r = plan_once(p, no_calculators(bundle), FakeLLM(first_product_writer({"g1": 5_000, "general": 5_000})))
    assert r.plan.investing_monthly == 10_000 and r.plan.amounts["available"] == 4_000
    assert OVERSPEND in r.violations
    rec = {"first_plan": r.plan.to_dict(), "first_violations": r.violations}
    assert metrics.a5_arithmetic(rec) == {**metrics.a5_arithmetic(rec), "overspend": True, "agrees": True}


def test_a_cleared_loans_emi_is_spendable_only_after_it_is_cleared(bundle):
    """A costly personal loan is repaid first; its EMI joins the surplus from the month after it is cleared."""
    p = Profile(age=28, take_home_monthly=60_000, expenses_monthly=30_000, liquid_savings=200_000,
                debts=[Debt(kind="personal", outstanding=60_000, rate_pa=16, emi_monthly=6_000)],
                dependants=0, life_cover=0, health_cover=1_000_000, card_dues_paid_in_full=True, goals=[],
                experience="intermediate", gl_answers=dict(MAX))
    calc = plan_once(p, bundle, FakeLLM(consistent_planner))
    repay = next(s for s in calc.plan.steps if s.action == "repay_costly_loan")
    cleared = repay.start_month + repay.months
    assert repay.frees_emi == 6_000 and calc.plan.invest_start_month == cleared
    assert cash_available(calc.plan, cleared - 1) == p.monthly_surplus
    assert cash_available(calc.plan, cleared) == p.monthly_surplus + 6_000
    # the calculators invest exactly what is free once the loan is gone: no violation
    assert calc.plan.investing_monthly == pytest.approx(p.monthly_surplus + 6_000) and OVERSPEND not in calc.violations
    # the model may use the freed EMI, but not a rupee more
    ok = plan_once(p, no_calculators(bundle), FakeLLM(first_product_writer({"general": p.monthly_surplus + 6_000})))
    over = plan_once(p, no_calculators(bundle), FakeLLM(first_product_writer({"general": p.monthly_surplus + 6_500})))
    assert OVERSPEND not in ok.violations and OVERSPEND in over.violations
    for r in (ok, over):
        a5 = metrics.a5_arithmetic({"first_plan": r.plan.to_dict(), "first_violations": r.violations})
        assert a5["agrees"] and a5["overspend"] == (r is over)
