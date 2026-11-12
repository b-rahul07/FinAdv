"""SIPs found from transactions, the four nudges, and the capital-gains statement."""

from datetime import date, timedelta

import pytest

from finadvisor.advisor import nudges
from finadvisor.db import models  # noqa: F401  (registers the tables before the client fixture builds the database)
from finadvisor.portfolio import gains, sips
from test_api import PROFILE, client, events, login  # noqa: F401  (fixture)
from test_holdings_api import TODAY, last_weekday, seed

D = date(2026, 11, 12)


def monthly(start: date, n: int, amount: float) -> list[tuple[date, float]]:
    return [(start + timedelta(days=30 * k), amount) for k in range(n)]


# ----------------------------------------------------------------------------- SIP detection

def test_a_sip_is_three_or_more_monthly_buys_of_the_same_amount():
    buys = monthly(date(2026, 7, 5), 5, 4999.75)                                 # 5 Jul ... 2 Nov; stamp duty shaves paise
    f = sips.detect(buys, D)
    assert (f.amount, f.instalments, f.start, f.last, f.status) == (5000, 5, date(2026, 7, 5), date(2026, 11, 2), "active")
    assert f.next_expected == date(2026, 12, 2) and 2 <= f.day_of_month <= 5
    assert sips.detect(buys[:2], D) is None                                      # two buys are not a SIP yet
    assert sips.detect([(date(2026, 5, 1), 5000), (date(2026, 8, 1), 5000), (date(2026, 11, 1), 5000)], D) is None   # quarterly
    assert sips.detect([(date(2026, 9, 1), 5000), (date(2026, 10, 1), 6000), (date(2026, 11, 1), 7000)], D) is None  # no common amount


def test_lump_sums_step_ups_and_breaks():
    with_lump = monthly(date(2026, 7, 5), 5, 5000) + [(date(2026, 9, 20), 80_000)]
    assert sips.detect(with_lump, D).instalments == 5                            # the lump sum in between is ignored
    stepped = monthly(date(2026, 3, 7), 4, 5000) + monthly(date(2026, 7, 5), 5, 7500)
    f = sips.detect(stepped, D)
    assert (f.amount, f.instalments, f.start) == (7500, 5, date(2026, 7, 5))    # the latest run is the SIP
    broken = monthly(date(2025, 11, 5), 4, 5000) + monthly(date(2026, 8, 4), 4, 5000)   # a six-month break
    assert sips.detect(broken, D).start == date(2026, 8, 4)


def test_missed_and_stopped():
    buys = monthly(date(2026, 6, 3), 4, 3000)                                    # last on 1 Sep; next expected 1 Oct
    assert sips.detect(buys, date(2026, 10, 6)).status == "active"               # five days late: still within grace
    assert sips.detect(buys, date(2026, 10, 12)).status == "missed"
    assert sips.detect(buys, date(2026, 11, 20)).status == "stopped"
    assert sips.window_end(sips.detect(buys, D)) == date(2026, 10, 8)


# ----------------------------------------------------------------------------- nudges

def base(**kw) -> dict:
    return {**dict(today=D, prefs={}, holdings=[], plan=None, profile_confirmed_on=date(2026, 10, 1), sips=[], dismissed=set()), **kw}


PLAN = {"advice_run_id": "run1", "total": 3, "stale": False, "steps": [
    {"order": 1, "action": "buy_health_cover", "status": "done", "starts_on": "2026-11-01", "monthly": 0, "goal": None},
    {"order": 2, "action": "build_emergency_fund", "status": "suggested", "starts_on": "2026-11-01", "monthly": 20_000, "goal": None},
    {"order": 3, "action": "invest", "status": "suggested", "starts_on": "2027-06-01", "monthly": 20_000, "goal": "Retirement"}]}
SIP = {"id": "s1", "status": "missed", "amount": 5000, "next_expected": "2026-11-01", "instrument": {"name": "Test Flexi Cap Fund"}}


def test_the_four_nudges_and_nothing_else():
    assert nudges.build(**base()) == []
    got = nudges.build(**base(
        holdings=[{"stale": True, "price_date": "2026-11-03"}, {"stale": True, "price_date": "2026-10-30"}, {"stale": False, "price_date": "2026-11-11"}],
        plan=PLAN, profile_confirmed_on=date(2026, 3, 1), sips=[SIP, {**SIP, "id": "s2", "status": "active"}]))
    assert [n["kind"] for n in got] == ["prices_stale", "step_due", "profile_old", "sip_missed"]
    stale, step, old, sip = got
    assert "2 holdings still show a price from 30 Oct 2026" in stale["body"] and (stale["to"], stale["tab"]) == ("/money", "Overview")
    assert step["title"] == "This month: build the emergency fund" and "Step 2 of 3" in step["body"] and "₹20,000 a month" in step["body"]
    assert step["to"] == "/" and "1 Mar 2026" in old["body"] and old["tab"] == "Facts"
    assert "₹5,000 SIP in Test Flexi Cap Fund was expected around 1 Nov 2026" in sip["body"] and sip["id"] == "sip_missed:s1:2026-11-01"


def test_nudges_respect_switches_dismissals_and_dates():
    full = dict(holdings=[{"stale": True, "price_date": "2026-11-03"}], plan=PLAN, profile_confirmed_on=date(2026, 3, 1), sips=[SIP])
    off = nudges.build(**base(**full, prefs={"data_refresh": False, "plan_reminders": False, "profile_reminders": False, "sip_reminders": False}))
    assert off == []
    all_four = nudges.build(**base(**full))
    assert nudges.build(**base(**full, dismissed={n["id"] for n in all_four})) == []
    assert nudges.build(**base(plan={**PLAN, "stale": True})) == []                          # an out-of-date plan does not nag
    later = {**PLAN, "steps": [PLAN["steps"][0], PLAN["steps"][2]]}
    assert nudges.build(**base(plan=later)) == []                                            # the next step starts in June 2027
    assert nudges.build(**base(profile_confirmed_on=D - timedelta(days=183))) == []          # exactly six months is not yet old
    next_month = nudges.build(**base(plan=PLAN, today=date(2026, 12, 2)))[0]
    assert next_month["id"] != nudges.build(**base(plan=PLAN))[0]["id"]                      # a step still open is raised again next month


# ----------------------------------------------------------------------------- capital gains

def test_financial_years_and_tax_classes():
    assert gains.fy_of(date(2026, 3, 31)) == "2025-26" and gains.fy_of(date(2026, 4, 1)) == "2026-27"
    assert gains.fy_bounds("2026-27") == (date(2026, 4, 1), date(2027, 3, 31))
    with pytest.raises(ValueError):
        gains.fy_bounds("2026-28")
    fund = lambda cat: models.Instrument(kind="mf", key="x", name="x", category=cat)  # noqa: E731
    assert gains.tax_class(models.Instrument(kind="stock", key="s", name="s")) == "equity"
    assert gains.tax_class(fund("Equity Scheme - Flexi Cap Fund")) == "equity"
    assert gains.tax_class(fund("Other Scheme - Index Funds")) == "equity"
    assert gains.tax_class(fund("Debt Scheme - Liquid Fund")) == "slab"
    assert gains.tax_class(fund("Hybrid Scheme - Arbitrage Fund")) == "slab"                 # not guessed as equity
    assert gains.tax_class(fund(None)) == "slab"


def test_capital_gains_statement_and_csv(client):
    sid, fid, _ = seed(client)
    h = login(client)
    buy_day, sell_day = last_weekday(TODAY - timedelta(days=200)), last_weekday(TODAY - timedelta(days=10))

    def tx(iid, kind, day, qty, price):
        r = client.post("/api/transactions", json={"instrument_id": iid, "kind": kind, "trade_date": day.isoformat(),
                                                   "quantity": qty, "price": price, "charges": 0}, headers=h)
        assert r.status_code == 200, r.text
    tx(sid, "buy", buy_day, 10, 210)                    # a 1:1 bonus since then: 20 shares at 105
    tx(sid, "sell", sell_day, 5, 130)
    tx(fid, "buy", buy_day, 100, 52)
    tx(fid, "sell", sell_day, 40, 50)                   # a loss
    fy = gains.fy_of(sell_day)
    st = client.get(f"/api/tax/capital-gains?fy={fy}", headers=h).json()
    assert st["financial_year"] == fy and fy in st["years"] and len(st["rows"]) == 2
    stock = next(r for r in st["rows"] if r["name"] == "TESTCO")
    assert (stock["quantity"], stock["buy_price"], stock["term"], stock["tax_class"]) == (5, 105, "short", "equity")
    assert stock["gain"] == pytest.approx(5 * (130 - 105))
    e = st["equity"]
    assert e["short_term"] == pytest.approx(125 - 80) and e["long_term"] == 0                # the fund's loss nets within short-term
    assert e["tax"] == pytest.approx(45 * 0.20) and "Estimated, not tax advice" in st["note"]
    if sell_day.month != 4 or sell_day.day > 10:                                             # another year has no sales
        other = f"{int(fy[:4]) - 1}-{fy[2:4]}"
        assert client.get(f"/api/tax/capital-gains?fy={other}", headers=h).json()["rows"] == []
    assert client.get("/api/tax/capital-gains?fy=2026", headers=h).status_code == 422
    csv_resp = client.get(f"/api/tax/capital-gains.csv?fy={fy}", headers=h)
    assert csv_resp.headers["content-type"].startswith("text/csv") and f"capital-gains-{fy}.csv" in csv_resp.headers["content-disposition"]
    lines = csv_resp.text.splitlines()
    assert lines[1].startswith("Name,Type,Taxed as") and any(line.startswith("TESTCO,stock,equity") for line in lines)
    assert "Equity: estimated tax,9.00" in lines


# ----------------------------------------------------------------------------- the API together

def test_sips_are_found_shown_on_home_and_can_be_marked_stopped(client):
    _, fid, _ = seed(client)
    h = login(client)
    client.put("/api/profile", json={"data": PROFILE}, headers=h)
    assert client.get("/api/sips", headers=h).json()["items"] == []
    for back in (130, 100, 70, 45):                                    # last instalment 45 days ago: the next one is late
        r = client.post("/api/transactions", json={"instrument_id": fid, "kind": "buy", "quantity": 100, "price": 50,
                                                   "trade_date": (TODAY - timedelta(days=back)).isoformat()}, headers=h)
        assert r.status_code == 200
    found = client.get("/api/sips", headers=h).json()
    sip = found["items"][0]
    assert (sip["amount"], sip["instalments"], sip["status"], sip["active"]) == (5000, 4, "missed", True)
    assert found["monthly_total"] == 5000
    assert client.get("/api/sips", headers=h).json()["items"][0]["id"] == sip["id"]          # the same row, not a new one
    home = client.get("/api/home", headers=h).json()
    assert home["cash_flow"]["sips"] == 5000 and home["cash_flow"]["sips_count"] == 1
    assert home["cash_flow"]["left_over"] == 20_000                                          # the planner's surplus is untouched

    ns = client.get("/api/nudges", headers=h).json()
    missed = next(n for n in ns if n["kind"] == "sip_missed")
    assert "₹5,000 SIP in Test Flexi Cap Fund" in missed["body"]
    assert client.post("/api/nudges/dismiss", json={"id": missed["id"]}, headers=h).json()["ok"]
    assert not any(n["kind"] == "sip_missed" for n in client.get("/api/nudges", headers=h).json())
    assert client.post("/api/nudges/dismiss", json={"id": "made_up:1"}, headers=h).status_code == 422

    assert client.patch(f"/api/sips/{sip['id']}", json={"active": False}, headers=h).json()["ok"]
    off = client.get("/api/sips", headers=h).json()
    assert off["items"][0]["status"] == "off" and off["monthly_total"] == 0
    assert client.get("/api/home", headers=h).json()["cash_flow"]["sips"] == 0
    assert client.patch("/api/sips/nope", json={"active": True}, headers=h).status_code == 404


def test_step_due_nudge_follows_the_plan_and_the_settings_switch(client):
    h = login(client)
    client.put("/api/profile", json={"data": PROFILE}, headers=h)
    assert client.get("/api/nudges", headers=h).json() == []
    chat = client.post("/api/chats", json={}, headers=h).json()
    events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Make me a plan for my money"}, headers=h))
    due = client.get("/api/nudges", headers=h).json()
    assert [n["kind"] for n in due] == ["step_due"] and due[0]["title"].startswith("This month:")
    me = client.get("/api/me", headers=h).json()
    client.put("/api/settings", json={"notifications": {**me["settings"]["notifications"], "plan_reminders": False}}, headers=h)
    assert client.get("/api/nudges", headers=h).json() == []
