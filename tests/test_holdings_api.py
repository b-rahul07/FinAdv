"""Holdings API on seeded prices: values reconcile between pages, adjustments apply, oversells are refused."""

from datetime import timedelta

import pytest

from finadvisor.api import runtime as rt_mod
from finadvisor.db.models import CorporateAction, Instrument, PriceDaily
from finadvisor.market import jobs
from test_api import client, login  # noqa: F401  (fixture)

TODAY = jobs.today_ist()


def seed(client):
    with rt_mod.get_runtime().Session() as s:
        stock = Instrument(kind="stock", key="INE000TEST01", isin="INE000TEST01", symbol="TESTCO", exchange="NSE", name="Test Co Ltd",
                           tracked=True)
        fund = Instrument(kind="mf", key="999001", name="Test Flexi Cap Fund - Direct Plan - Growth", amc="Test MF",
                          category="Equity Scheme - Flexi Cap Fund", plan="Direct", option="Growth", tracked=True)
        bench = Instrument(kind="index", key="NIFTY 50", name="Nifty 50", symbol="NIFTY 50", tracked=True)
        s.add_all([stock, fund, bench])
        s.flush()
        # 300 trading-ish days of prices; a 1:1 bonus 100 days ago halves the price
        bonus_day = TODAY - timedelta(days=100)
        for k in range(300, -1, -1):
            d = TODAY - timedelta(days=k)
            if d.weekday() >= 5:
                continue
            raw = 200.0 + (300 - k) * 0.1
            close = raw / 2 if d >= bonus_day else raw
            prev = None
            s.add(PriceDaily(instrument_id=stock.id, date=d, close=close, high=close * 1.01, low=close * 0.99, prev_close=prev,
                             source="NSE bhavcopy"))
            s.add(PriceDaily(instrument_id=fund.id, date=d, close=50 + (300 - k) * 0.02, source="AMFI daily NAV"))
            s.add(PriceDaily(instrument_id=bench.id, date=d, close=20000 + (300 - k), source="NSE Indices daily close (price index)"))
        s.add(CorporateAction(instrument_id=stock.id, ex_date=bonus_day, kind="split_or_bonus", factor=0.5, source="test"))
        s.commit()
        return stock.id, fund.id, bonus_day


def last_weekday(d):
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def test_holdings_dashboard_reconcile_and_adjust(client):
    sid, fid, bonus_day = seed(client)
    h = login(client)
    buy_day = last_weekday(TODAY - timedelta(days=200))
    assert client.post("/api/transactions", json={"instrument_id": sid, "kind": "buy", "trade_date": buy_day.isoformat(),
                                                  "quantity": 10, "price": 210, "charges": 0}, headers=h).status_code == 200
    assert client.post("/api/transactions", json={"instrument_id": fid, "kind": "buy", "trade_date": buy_day.isoformat(),
                                                  "quantity": 100, "price": 52, "charges": 0}, headers=h).status_code == 200
    hold = client.get("/api/holdings", headers=h).json()
    stock = next(x for x in hold["items"] if x["instrument"]["id"] == sid)
    # bonus: 10 shares at 210 become 20 at 105
    assert stock["qty"] == pytest.approx(20) and stock["avg_price"] == pytest.approx(105)
    assert stock["invested"] == pytest.approx(2100)
    assert stock["value"] == pytest.approx(20 * stock["price"])
    assert stock["price_source"] == "NSE bhavcopy" and stock["price_date"]
    # 52-week low is the adjusted pre-bonus low, not the raw one
    assert stock["week52"]["low"] < stock["price"] and stock["week52"]["high"] >= stock["price"]
    assert stock["week52"]["low"] == pytest.approx(min(
        (200 + (300 - k) * 0.1) * 0.5 * 0.99 for k in range(300, -1, -1)
        if (TODAY - timedelta(days=k)).weekday() < 5 and TODAY - timedelta(days=k) >= TODAY - timedelta(days=364)), rel=1e-6)
    dash = client.get("/api/dashboard?range=1Y", headers=h).json()
    total = sum(x["value"] for x in hold["items"])
    assert dash["net_worth"]["value"] == pytest.approx(total)
    assert dash["returns"]["invested"] == pytest.approx(sum(x["invested"] for x in hold["items"]))
    assert sum(a["share"] for a in dash["allocation"]) == pytest.approx(1)
    assert dash["returns"]["xirr"] is None and dash["returns"]["note"]   # under a year: not annualised
    pts = dash["series"]["points"]
    assert pts and pts[-1]["value"] == pytest.approx(total)
    assert pts[-1]["benchmark"] is not None and dash["series"]["benchmark_label"].startswith("Nifty 50")


def test_oversell_refused_and_sell_ok(client):
    sid, _, _ = seed(client)
    h = login(client)
    d0 = last_weekday(TODAY - timedelta(days=50)).isoformat()
    client.post("/api/transactions", json={"instrument_id": sid, "kind": "buy", "trade_date": d0, "quantity": 5, "price": 100}, headers=h)
    r = client.post("/api/transactions", json={"instrument_id": sid, "kind": "sell", "trade_date": d0, "quantity": 6, "price": 100}, headers=h)
    assert r.status_code == 422
    assert client.post("/api/transactions", json={"instrument_id": sid, "kind": "sell", "trade_date": d0, "quantity": 2, "price": 120},
                       headers=h).status_code == 200
    hold = client.get("/api/holdings", headers=h).json()
    assert hold["items"][0]["qty"] == 3 and hold["items"][0]["realised"] == pytest.approx(40)
    future = (TODAY + timedelta(days=3)).isoformat()
    assert client.post("/api/transactions", json={"instrument_id": sid, "kind": "buy", "trade_date": future, "quantity": 1, "price": 1},
                       headers=h).status_code == 422


def test_watchlist_change_since_added(client):
    sid, _, bonus_day = seed(client)
    h = login(client)
    added = last_weekday(TODAY - timedelta(days=150))
    assert client.post("/api/watchlist", json={"instrument_id": sid, "added_on": added.isoformat()}, headers=h).json()["ok"]
    w = client.get("/api/watchlist", headers=h).json()[0]
    # price when added is adjusted for the later bonus, so the change is a real move, not -50%
    assert w["change_since_added"] == pytest.approx(w["current_price"] / w["price_when_added"] - 1)
    assert -0.2 < w["change_since_added"] < 0.2
    assert client.post("/api/watchlist", json={"instrument_id": sid}, headers=h).status_code == 409


def test_search_and_instrument_detail(client):
    sid, fid, _ = seed(client)
    h = login(client)
    assert client.get("/api/instruments/search?q=TESTCO", headers=h).json()[0]["id"] == sid
    assert client.get("/api/instruments/search?q=flexi&kind=mf", headers=h).json()[0]["id"] == fid
    d = client.get(f"/api/instruments/{sid}?range=1Y", headers=h).json()
    assert d["points"] and d["corporate_actions"][0]["factor"] == 0.5
    closes = [p["close"] for p in d["points"]]
    assert max(closes) / min(closes) < 1.5   # adjusted series has no 50% cliff
    assert client.put(f"/api/instruments/{sid}/note", json={"text": "watch margins"}, headers=h).json()["ok"]
    assert client.get(f"/api/instruments/{sid}", headers=h).json()["note"] == "watch margins"
