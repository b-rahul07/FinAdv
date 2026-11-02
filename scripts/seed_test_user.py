"""Seed a long-history test account: a regular user who has invested since 2021 and changed over time.

    python scripts/seed_test_user.py          # dev database; sign in at the dev web app as arjun@finadvisor.example

Arjun (fictional) starts a Nifty 50 index-fund SIP in April 2021 at 26 and steps it up with each raise, adds a
flexi-cap SIP (paused for three months when he buys a car), makes March ELSS top-ups for 80C, buys a small-cap fund
on a friend's tip and sells half after the fall, parks a bonus in a liquid fund, and from 2024 buys a few shares:
Reliance (1:1 bonus in Oct 2024) and HDFC Bank (1:1 bonus in Aug 2025) are held through their bonuses, TCS and
Asian Paints are sold. His profile is saved in four dated versions (2021, 2023, 2025, now) with a health check each.

Every trade price is the real closing price or NAV on that date, loaded the same way the app loads them (NSE
bhavcopy from Jan 2024, MFapi NAV history, NSE index closes for the benchmark). The account is marked as example data
(banner on every screen, excluded from research exports). First run downloads about 2,000 daily files at 1 per second
(NSE asks for polite spacing), so it takes 30-40 minutes; later runs reuse the disk cache.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from finadvisor.advisor.capacity import assess
from finadvisor.advisor.health import health_card
from finadvisor.advisor.profile import Debt, Goal, Profile
from finadvisor.configs import default_bundle
from finadvisor.db.base import Base, make_engine, make_sessionmaker
from finadvisor.db.models import (FinancialProfile, HealthSnapshot, Instrument, InstrumentNote, InsurancePolicy,
                                  Liability, OtherAsset, PriceDaily, Transaction, User, UserSettings, WatchItem)
from finadvisor.market import jobs
from finadvisor.settings import get_settings

EMAIL = "arjun@finadvisor.example"
NAME = "Arjun (test account)"
MID = {i: k for i, k in zip(range(1, 14), "c b b b b b b b a b b b b".split())}
START = date(2021, 4, 1)
STOCKS_FROM = date(2024, 1, 1)        # first date of NSE's UDiFF bhavcopy, the app's stock price source
TODAY = jobs.today_ist()

FUNDS = {"nifty": "120716", "ppfas": "122639", "elss": "135781", "smallcap": "118778", "liquid": "119091"}
LISTED = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ASIANPAINT", "GOLDBEES", "TITAN", "LT"]


def monthly(first: date, last: date, day: int):
    y, m = first.year, first.month
    while True:
        d = date(y, m, day)
        if d > last:
            return
        if d >= first:
            yield d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def sip_amount(d: date) -> float:
    return 5_000 if d < date(2023, 4, 1) else 7_500 if d < date(2025, 4, 1) else 10_000


def ppfas_amount(d: date) -> float:
    if date(2023, 6, 1) <= d < date(2023, 9, 1):
        return 0                       # paused for three months after buying the car
    return 3_000 if d < date(2024, 4, 1) else 5_000


def price_on(s, inst: Instrument, d: date) -> tuple[date, float]:
    """The first close/NAV on or after `d` (a SIP date on a holiday executes on the next working day)."""
    row = s.execute(select(PriceDaily.date, PriceDaily.close).where(PriceDaily.instrument_id == inst.id,
                    PriceDaily.date >= d, PriceDaily.date <= d + timedelta(days=10))
                    .order_by(PriceDaily.date).limit(1)).first()
    if row is None:
        raise SystemExit(f"no price for {inst.symbol or inst.name} near {d}; the backfill did not reach it")
    return row[0], float(row[1])


def load_prices(s) -> dict[str, Instrument]:
    insts: dict[str, Instrument] = {}
    for k, code in FUNDS.items():
        insts[k] = s.scalar(select(Instrument).where(Instrument.kind == "mf", Instrument.key == code))
    for sym in LISTED:
        insts[sym] = s.scalar(select(Instrument).where(Instrument.symbol == sym, Instrument.exchange == "NSE"))
    missing = [k for k, v in insts.items() if v is None]
    if missing:
        raise SystemExit(f"instruments not found: {missing}; run: python -m finadvisor.market.jobs masters")
    for inst in insts.values():
        inst.tracked = True
    s.commit()
    for k in FUNDS:
        print(f"NAV history: {insts[k].name}", flush=True)
        jobs.backfill_fund(s, insts[k])
        s.commit()
    days = (TODAY - STOCKS_FROM).days + 5
    print(f"stock prices since {STOCKS_FROM} ({days} days of NSE files; cached days are read from disk)", flush=True)
    jobs.backfill_listed(s, [insts[x] for x in LISTED], days=days)
    print(f"Nifty 50 closes since {START} for the benchmark", flush=True)
    jobs.backfill_index(s, days=(TODAY - START).days + 5)
    s.commit()
    return insts


def profiles() -> list[tuple[datetime, Profile]]:
    car = Debt(kind="car", label="Car loan", outstanding=600_000, rate_pa=8.9, emi_monthly=15_600)
    home = Goal(id="g1", name="Home down payment", kind="home", target_today=3_000_000, horizon_years=4)
    ret = Goal(id="g2", name="Retirement", kind="retirement", target_today=30_000_000, horizon_years=29)
    at = lambda d: datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)
    return [
        (at(date(2021, 4, 1)), Profile(age=26, take_home_monthly=65_000, expenses_monthly=30_000, liquid_savings=80_000,
                                       health_cover=300_000, experience="none", gl_answers=MID)),
        (at(date(2023, 5, 15)), Profile(age=28, take_home_monthly=105_000, expenses_monthly=50_000, liquid_savings=220_000,
                                        dependants=1, life_cover=10_000_000, health_cover=500_000, debts=[car],
                                        experience="beginner", gl_answers=MID,
                                        goals=[home.model_copy(update={"horizon_years": 7})])),
        (at(date(2025, 4, 1)), Profile(age=30, take_home_monthly=130_000, expenses_monthly=58_000, liquid_savings=330_000,
                                       dependants=1, life_cover=27_500_000, health_cover=1_000_000,
                                       debts=[car.model_copy(update={"outstanding": 420_000})], experience="intermediate",
                                       gl_answers=MID, goals=[home.model_copy(update={"horizon_years": 5}),
                                                              ret.model_copy(update={"horizon_years": 30})])),
        (at(TODAY), Profile(age=31, take_home_monthly=145_000, expenses_monthly=62_000, liquid_savings=400_000,
                            dependants=1, life_cover=27_500_000, health_cover=1_000_000,
                            debts=[car.model_copy(update={"outstanding": 320_000})], experience="intermediate",
                            gl_answers=MID, goals=[home, ret])),
    ]


def main() -> None:
    url = get_settings().database_url
    engine = make_engine(url)
    if url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    bundle = default_bundle()
    with make_sessionmaker(engine)() as s:
        insts = load_prices(s)
        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"finadvisor-dev:{EMAIL}"))   # the id dev sign-in issues
        old = s.get(User, uid)
        if old:
            s.delete(old)
            s.commit()
        s.add(User(id=uid, email=EMAIL, name=NAME, auth_provider="dev", is_demo=True,
                   created_at=datetime(2021, 4, 1, 9, 0, tzinfo=timezone.utc)))
        s.add(UserSettings(user_id=uid))
        s.flush()

        for v, (at, p) in enumerate(profiles(), start=1):
            s.add(FinancialProfile(user_id=uid, version=v, data=p.model_dump(mode="json"), sources={"*": "test account"},
                                   created_at=at))
            hc = health_card(p, assess(p, bundle.rules), bundle.rules)
            s.add(HealthSnapshot(user_id=uid, profile_version=v, score=hc["score"], out_of=hc["out_of"],
                                 capacity_level=hc["capacity_level"], checks=hc["checks"], created_at=at))

        txs: list[tuple[str, str, date, float | None, float | None, str]] = []   # key, kind, date, rupees, qty, note
        for d in monthly(date(2021, 4, 5), TODAY, 5):
            txs.append(("nifty", "buy", d, sip_amount(d), None, "SIP"))
        for d in monthly(date(2022, 1, 10), TODAY, 10):
            if ppfas_amount(d):
                txs.append(("ppfas", "buy", d, ppfas_amount(d), None, "SIP"))
        for d in (date(2022, 3, 15), date(2023, 3, 14), date(2024, 3, 12), date(2025, 3, 11), date(2026, 3, 10)):
            txs.append(("elss", "buy", d, 50_000, None, "80C top-up"))
        txs += [("smallcap", "buy", date(2023, 6, 20), 40_000, None, "friend's tip"),
                ("smallcap", "buy", date(2024, 9, 16), 25_000, None, "added after a strong year"),
                ("liquid", "buy", date(2024, 8, 1), 100_000, None, "annual bonus parked")]
        stock_trades = [("RELIANCE", "buy", date(2024, 1, 15), 15), ("INFY", "buy", date(2024, 2, 12), 20),
                        ("TCS", "buy", date(2024, 2, 12), 8), ("HDFCBANK", "buy", date(2024, 3, 18), 20),
                        ("ASIANPAINT", "buy", date(2024, 6, 10), 10), ("GOLDBEES", "buy", date(2024, 9, 2), 200),
                        ("ASIANPAINT", "sell", date(2025, 3, 24), 10), ("INFY", "buy", date(2025, 4, 7), 10),
                        ("GOLDBEES", "buy", date(2025, 4, 21), 150), ("TCS", "sell", date(2025, 8, 18), 8)]

        units: dict[str, float] = {}
        for key, kind, d, rupees, _, note in sorted(txs, key=lambda t: t[2]):
            inst = insts[key]
            traded, nav = price_on(s, inst, d)
            qty = round(rupees / nav, 3)
            units[key] = units.get(key, 0) + qty
            s.add(Transaction(user_id=uid, instrument_id=inst.id, kind=kind, trade_date=traded, quantity=qty, price=nav,
                              note=note))
        # sells measured in units: half the small-cap holding after the fall; most of the liquid fund for a holiday
        for key, d, share, note in (("smallcap", date(2025, 3, 3), 0.5, "sold half after the fall"),
                                    ("liquid", date(2025, 11, 20), 0.55, "family holiday")):
            traded, nav = price_on(s, insts[key], d)
            s.add(Transaction(user_id=uid, instrument_id=insts[key].id, kind="sell", trade_date=traded,
                              quantity=round(units[key] * share, 3), price=nav, note=note))
        for sym, kind, d, qty in stock_trades:
            traded, close = price_on(s, insts[sym], d)
            s.add(Transaction(user_id=uid, instrument_id=insts[sym].id, kind=kind, trade_date=traded, quantity=qty,
                              price=close, charges=20.0))

        s.add_all([WatchItem(user_id=uid, instrument_id=insts["TITAN"].id, added_on=date(2025, 1, 6)),
                   WatchItem(user_id=uid, instrument_id=insts["LT"].id, added_on=date(2025, 7, 1)),
                   InstrumentNote(user_id=uid, instrument_id=insts["smallcap"].id,
                                  text="Bought on Rohan's tip in 2023. Sold half in March 2025 after the fall."),
                   InstrumentNote(user_id=uid, instrument_id=insts["RELIANCE"].id,
                                  text="1:1 bonus in Oct 2024, so 15 shares became 30.")])
        s.add_all([
            OtherAsset(user_id=uid, kind="savings", name="Salary account", account_last4="4471",
                       data={"balance": 185_000, "as_of": TODAY.isoformat()}),
            OtherAsset(user_id=uid, kind="fd", name="Bank FD", data={"principal": 150_000, "rate_pa": 7.1,
                       "start": "2025-05-02", "maturity": "2027-05-02"}),
            OtherAsset(user_id=uid, kind="rd", name="Recurring deposit", data={"instalment": 5_000, "rate_pa": 6.8,
                       "start": "2025-01-10", "maturity": "2027-01-10"}),
            OtherAsset(user_id=uid, kind="epf", name="EPF", data={"balance": 640_000, "as_of": "2026-09-30"}),
            OtherAsset(user_id=uid, kind="ppf", name="PPF (opened 2021)", data={"balance": 310_000, "as_of": "2026-03-31"}),
            OtherAsset(user_id=uid, kind="gold_physical", name="Wedding jewellery", data={"grams": 30, "purity": 916}),
            Liability(user_id=uid, kind="car", lender="Example Bank", outstanding=320_000, rate_pa=8.9, emi_monthly=15_600,
                      end_date=date(2028, 7, 5), as_of=TODAY, account_last4="0932"),
            InsurancePolicy(user_id=uid, kind="term", insurer="Example Life", sum_assured=25_000_000, premium_yearly=21_000),
            InsurancePolicy(user_id=uid, kind="term", insurer="Employer group cover", sum_assured=2_500_000,
                            employer_provided=True),
            InsurancePolicy(user_id=uid, kind="health", insurer="Example Health (family floater)", sum_assured=1_000_000,
                            premium_yearly=24_500),
        ])
        s.commit()
        n = s.query(Transaction).filter(Transaction.user_id == uid).count()
        print(f"test account ready: {n} transactions since {START:%d %b %Y}. Sign in at the dev web app as {EMAIL}.")


if __name__ == "__main__":
    main()
