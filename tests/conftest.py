import pytest

from finadvisor.advisor.profile import Debt, Goal, Profile
from finadvisor.configs import default_bundle

# Answers that score each option; "mid" gives 2s (score 27 -> Medium), "max" gives the top score (47 -> High).
MID = {1: "c", 2: "b", 3: "b", 4: "b", 5: "b", 6: "b", 7: "b", 8: "b", 9: "a", 10: "b", 11: "b", 12: "b", 13: "b"}
MAX = {1: "a", 2: "d", 3: "d", 4: "c", 5: "c", 6: "d", 7: "d", 8: "d", 9: "b", 10: "b", 11: "d", 12: "c", 13: "d"}
MIN = {1: "d", 2: "a", 3: "a", 4: "a", 5: "a", 6: "a", 7: "a", 8: "a", 9: "a", 10: "a", 11: "a", 12: "a", 13: "a"}


def model_bundle():
    """The report's design: the language model chooses the mix (experiments). The website config uses the standard
    mix (planner.mode: standard); `website_bundle` tests that."""
    b = default_bundle()
    return b.with_pipeline({**b.pipeline, "planner": {**b.pipeline["planner"], "mode": "model"}})


@pytest.fixture
def bundle():
    return model_bundle()


@pytest.fixture
def website_bundle():
    return default_bundle()


@pytest.fixture
def healthy() -> Profile:
    """Passes every capacity check: High capacity, experienced, High willingness."""
    return Profile(
        age=30, take_home_monthly=100_000, expenses_monthly=40_000, liquid_savings=240_000,
        debts=[Debt(kind="home", outstanding=2_000_000, rate_pa=8.5, emi_monthly=20_000)],
        dependants=0, life_cover=0, health_cover=1_000_000, card_dues_paid_in_full=True,
        goals=[Goal(id="g1", name="House down payment", kind="home", target_today=1_000_000, horizon_years=8)],
        experience="intermediate", gl_answers=dict(MAX),
    )


@pytest.fixture
def stretched() -> Profile:
    """A young earner with a thin emergency fund and no cover."""
    return Profile(
        age=25, take_home_monthly=50_000, expenses_monthly=30_000, liquid_savings=40_000,
        debts=[], dependants=0, health_cover=0, card_dues_paid_in_full=True,
        goals=[Goal(id="trip", name="Europe trip", kind="travel", target_today=200_000, horizon_years=2),
               Goal(id="ret", name="Retirement", kind="retirement", target_today=5_000_000, horizon_years=30)],
        experience="none", gl_answers=dict(MID),
    )
