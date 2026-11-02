"""Portfolio engine and official-file parsers, with hand-checked values."""

from datetime import date

import pytest

from finadvisor.calc.xirr import xirr
from finadvisor.market import parse
from finadvisor.portfolio import engine as E

D = date


def test_fifo_and_realised_long_short():
    txs = [E.Tx(D(2024, 1, 10), "buy", 10, 100), E.Tx(D(2025, 6, 1), "buy", 10, 150),
           E.Tx(D(2025, 2, 1), "sell", 5, 130)]
    lots, real = E.fifo(txs)
    assert [(l.qty, l.price) for l in lots] == [(5, 100), (10, 150)]
    assert real[0].gain == pytest.approx(150) and real[0].long_term  # held > 12 months


def test_exactly_twelve_months_is_short_term():
    assert not E.is_long_term(D(2025, 10, 31), D(2026, 10, 31))
    assert E.is_long_term(D(2025, 10, 31), D(2026, 11, 1))


def test_selling_more_than_held_raises():
    with pytest.raises(ValueError):
        E.fifo([E.Tx(D(2025, 1, 1), "buy", 1, 10), E.Tx(D(2025, 2, 1), "sell", 2, 10)])


def test_charges_go_into_cost():
    lots, _ = E.fifo([E.Tx(D(2025, 1, 1), "buy", 10, 100, charges=20)])
    assert lots[0].price == 102


def test_bonus_adjusts_quantity_and_price():
    # 1:1 bonus on 1 Jul 2025 -> factor 0.5
    a = [E.Action(D(2025, 7, 1), 0.5)]
    t = E.adjust_tx(E.Tx(D(2025, 1, 1), "buy", 10, 200), a)
    assert (t.qty, t.price) == (20, 100)
    t2 = E.adjust_tx(E.Tx(D(2025, 8, 1), "buy", 10, 120), a)
    assert (t2.qty, t2.price) == (10, 120)


def test_derive_actions_from_prev_close():
    rows = [(D(2025, 6, 27), 400.0, 398.0), (D(2025, 6, 30), 402.0, 400.0), (D(2025, 7, 1), 205.0, 201.0),
            (D(2025, 7, 2), 207.0, 205.0)]
    acts = E.derive_actions(rows)
    assert len(acts) == 1 and acts[0].ex_date == D(2025, 7, 1) and acts[0].factor == pytest.approx(0.5)
    assert E.classify(acts[0].factor) == "split_or_bonus"
    assert E.classify(0.97) == "other_adjustment"


def test_derive_split_from_price_gap_when_prev_close_unadjusted():
    # NSE publishes the unadjusted previous close on split dates (WEBELSOLAR 1:10, Nov 2025)
    rows = [(D(2025, 11, 13), 1352.8, 1340.0), (D(2025, 11, 14), 132.1, 1352.8), (D(2025, 11, 17), 134.0, 132.1)]
    acts = E.derive_actions(rows)
    assert acts == [E.Action(D(2025, 11, 14), 0.1)]


def test_dividend_and_missed_session_are_not_splits():
    # prev close 9% below the last close we have (a missed special session or a dividend): ignored
    rows = [(D(2026, 1, 30), 151.4, 150.0), (D(2026, 2, 2), 136.07, 137.5)]
    assert E.derive_actions(rows) == []
    # a 25% crash is not a 3:4 split
    assert E.derive_actions([(D(2026, 3, 1), 100.0, 99.0), (D(2026, 3, 2), 75.0, 100.0)]) == []


def test_position_values_and_day_change():
    txs = [E.Tx(D(2025, 1, 1), "buy", 10, 100), E.Tx(D(2026, 3, 1), "buy", 10, 120)]
    p = E.position(txs, price=130, price_date=D(2026, 10, 30), prev_price=125, as_of=D(2026, 10, 31))
    assert p.qty == 20 and p.invested == 2200 and p.avg_price == 110
    assert p.value == 2600 and p.unrealised == 400 and p.unrealised_pct == pytest.approx(400 / 2200)
    assert p.day_change == 100 and p.day_change_pct == pytest.approx(0.04)
    assert p.long_term_qty == 10 and p.short_term_qty == 10
    assert p.holding_days == (D(2026, 10, 31) - D(2025, 1, 1)).days


def test_position_without_price_is_honest():
    p = E.position([E.Tx(D(2025, 1, 1), "buy", 1, 100)], None, None, None, D(2026, 1, 1))
    assert p.value is None and p.unrealised is None and p.day_change is None


def test_xirr_of_position():
    flows = E.xirr_flows([E.Tx(D(2025, 1, 1), "buy", 10, 100)], 1100, D(2026, 1, 1))
    assert xirr(flows) == pytest.approx(0.10, abs=1e-9)


def test_week52_uses_adjusted_highs_lows():
    a = [E.Action(D(2026, 7, 1), 0.5)]
    rows = [(D(2026, 1, 5), 410.0, 380.0, 400.0), (D(2026, 8, 5), 230.0, 195.0, 220.0)]
    lo, hi = E.week52(rows, a, D(2026, 10, 30))
    assert lo == 190 and hi == 230   # 380 × 0.5 = 190, 410 × 0.5 = 205 < 230


def test_value_series():
    h = {"a": [E.Tx(D(2026, 1, 2), "buy", 10, 100)]}
    prices = {"a": [(D(2026, 1, 2), 100.0), (D(2026, 1, 5), 110.0)]}
    s = E.value_series(h, prices, [D(2026, 1, 1), D(2026, 1, 2), D(2026, 1, 3), D(2026, 1, 5)])
    assert [x["value"] for x in s] == [0, 1000, 1000, 1100]
    assert s[-1]["net_invested"] == 1000


# ---------------------------------------------------------------- parsers (real file formats)

BHAV = """TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4
2026-10-30,2026-10-30,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES LTD,1400.00,1412.50,1395.10,1408.20,1408.00,1401.30,,1408.20,,,5000000,7040000000.00,150000,F1,1,,,,,
2026-10-30,2026-10-30,CM,NSE,FUT,1,INE002A01018,RELIANCE,,2026-11-27,,,,RELIANCE FUT,1,1,1,1,1,1,,1,,,1,1,1,F1,1,,,,,
"""

NAV = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

PPFAS Mutual Fund

122639;INF879O01027;-;Parag Parikh Flexi Cap Fund;Direct Plan;Growth Option;92.1234;30-Oct-2026
122640;INF879O01019;-;Parag Parikh Flexi Cap Fund;Regular Plan;Growth Option;85.4321;30-Oct-2026
"""


def test_parse_bhav():
    rows = parse.parse_bhav_udiff(BHAV)
    assert len(rows) == 1
    r = rows[0]
    assert (r.symbol, r.isin, r.close, r.prev_close, r.trade_date) == ("RELIANCE", "INE002A01018", 1408.20, 1401.30, D(2026, 10, 30))


def test_parse_amfi():
    s = parse.parse_amfi_navall(NAV)
    assert len(s) == 2
    assert (s[0].code, s[0].amc, s[0].category, s[0].plan, s[0].option, s[0].nav, s[0].nav_date) == (
        "122639", "PPFAS Mutual Fund", "Equity Scheme - Flexi Cap Fund", "Direct", "Growth", 92.1234, D(2026, 10, 30))


def test_parse_52w_and_index():
    t = ('"Disclaimer"\n"Effective for 30-Oct-2026"\n"SYMBOL","SERIES","Adjusted_52_Week_High","52_Week_High_Date",'
         '"Adjusted_52_Week_Low","52_Week_Low_DT"\n"20MICRONS","EQ","    237.40","26-DEC-2025","    129.61","30-MAR-2026"\n')
    w = parse.parse_nse_52w(t)[0]
    assert (w.symbol, w.high, w.low, w.low_date) == ("20MICRONS", 237.40, 129.61, D(2026, 3, 30))
    idx = parse.parse_index_close("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value\n"
                                  "Nifty 50,30-10-2026,1,2,3,23053.1\n")
    assert idx[0].close == 23053.1 and idx[0].trade_date == D(2026, 10, 30)


def test_bhav_rows_match_by_symbol_after_isin_change():
    from types import SimpleNamespace
    from finadvisor.market import jobs, sources
    old_isin = BHAV.replace("INE002A01018", "INE002A01999")   # pre-split ISIN
    stored = []
    inst = SimpleNamespace(id="i1", isin="INE002A01018", symbol="RELIANCE", exchange="NSE")
    f = SimpleNamespace(text=old_isin, source=sources.Source("x", "NSE bhavcopy", ""), fetched_at=None)
    orig = jobs._upsert_price
    jobs._upsert_price = lambda s, iid, d, close, *a, **k: stored.append((iid, d, close))
    try:
        jobs.store_bhav_day(None, f, {inst.isin: inst})
    finally:
        jobs._upsert_price = orig
    assert stored == [("i1", D(2026, 10, 30), 1408.20)]
