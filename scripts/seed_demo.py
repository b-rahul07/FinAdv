"""Seed the clearly labelled demo account used for reviews and report screenshots (brief §8).

    python scripts/seed_demo.py            # needs instrument lists (python -m finadvisor.market.jobs masters)

Sign in locally as demo@finadvisor.example (dev sign-in). Every screen shows an "Example data" banner for this
account, and it is excluded from research exports. The person and amounts are fictional; prices are real.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from finadvisor.advisor.profile import Debt, Goal, Profile
from finadvisor.api.store import save_profile
from finadvisor.db.base import Base, make_engine, make_sessionmaker
from finadvisor.db.models import (Instrument, InsurancePolicy, Liability, OtherAsset, Transaction, User, UserSettings, WatchItem)
from finadvisor.settings import get_settings

EMAIL = "demo@finadvisor.example"
MID = {i: k for i, k in zip(range(1, 14), "b b b b b c b b b b b b b".split())}


def find(s, kind_in, **kw):
    q = select(Instrument).where(Instrument.kind.in_(kind_in))
    for k, v in kw.items():
        q = q.where(getattr(Instrument, k) == v)
    inst = s.scalar(q.limit(1))
    if inst is None:
        raise SystemExit(f"instrument {kw} not found; run: python -m finadvisor.market.jobs masters")
    return inst


def main() -> None:
    engine = make_engine(get_settings().database_url)
    if get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with make_sessionmaker(engine)() as s:
        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"finadvisor-dev:{EMAIL}"))   # same id the dev sign-in issues
        old = s.get(User, uid)
        if old:
            s.delete(old)
            s.commit()
        s.add(User(id=uid, email=EMAIL, name="Meera (example)", auth_provider="dev", is_demo=True))
        s.add(UserSettings(user_id=uid))
        s.flush()
        p = Profile(age=28, take_home_monthly=85_000, expenses_monthly=42_000, liquid_savings=150_000, dependants=1,
                    life_cover=5_000_000, health_cover=500_000, card_dues_paid_in_full=True, experience="beginner",
                    debts=[Debt(kind="car", label="Car loan", outstanding=380_000, rate_pa=9.1, emi_monthly=11_800)],
                    goals=[Goal(id="g1", name="Home down payment", kind="home", target_today=1_500_000, horizon_years=5),
                           Goal(id="g2", name="Retirement", kind="retirement", target_today=20_000_000, horizon_years=32)],
                    gl_answers=MID)
        save_profile(s, uid, p, {"*": "demo"})
        rel = find(s, ("stock",), symbol="RELIANCE", exchange="NSE")
        infy = find(s, ("stock",), symbol="INFY", exchange="NSE")
        bees = find(s, ("etf",), symbol="GOLDBEES", exchange="NSE")
        ppfas = s.scalar(select(Instrument).where(Instrument.kind == "mf", Instrument.name.like("Parag Parikh Flexi Cap%"),
                                                  Instrument.plan == "Direct", Instrument.option == "Growth"))
        txs = [(rel, date(2025, 11, 3), 15, 1488.0), (infy, date(2026, 1, 12), 20, 1590.0), (bees, date(2025, 12, 1), 150, 96.0)]
        if ppfas:
            txs += [(ppfas, date(2025, 11, 5), 120, 84.0), (ppfas, date(2026, 3, 5), 60, 86.5), (ppfas, date(2026, 7, 6), 55, 90.1)]
        for inst, d, q, pr in txs:
            inst.tracked = True
            s.add(Transaction(user_id=uid, instrument_id=inst.id, kind="buy", trade_date=d, quantity=q, price=pr, note="example"))
        tcs = find(s, ("stock",), symbol="TCS", exchange="NSE")
        tcs.tracked = True
        s.add(WatchItem(user_id=uid, instrument_id=tcs.id, added_on=date(2026, 6, 1)))
        s.add_all([
            OtherAsset(user_id=uid, kind="savings", name="Savings account", data={"balance": 90_000, "as_of": "2026-10-30"}, account_last4="2914"),
            OtherAsset(user_id=uid, kind="fd", name="Bank FD", data={"principal": 60_000, "rate_pa": 6.9, "start": "2026-02-01", "maturity": "2027-02-01"}),
            OtherAsset(user_id=uid, kind="epf", name="EPF", data={"balance": 310_000, "as_of": "2026-09-30"}),
            OtherAsset(user_id=uid, kind="gold_physical", name="Gold bangles", data={"grams": 20, "purity": 916}),
            Liability(user_id=uid, kind="car", lender="Example Bank", outstanding=380_000, rate_pa=9.1, emi_monthly=11_800,
                      end_date=date(2029, 6, 5), as_of=date(2026, 10, 30), account_last4="0417"),
            InsurancePolicy(user_id=uid, kind="term", insurer="Example Life", sum_assured=5_000_000, premium_yearly=9_800),
            InsurancePolicy(user_id=uid, kind="health", insurer="Example Health", sum_assured=500_000, premium_yearly=13_500),
        ])
        s.commit()
        print(f"demo account ready: sign in as {EMAIL} (dev sign-in). Run the daily job to load prices.")


if __name__ == "__main__":
    main()
