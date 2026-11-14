"""Contract tests: each market parser against an excerpt of a real file as its source publishes it.

The other parser tests use short hand-made strings. Those keep passing when a source changes its format, the same way
the CAS tests kept passing while casparser 1.x broke real uploads (14 Nov 2026). The fixtures in tests/fixtures/market/
are the first rows of files downloaded from NSE, BSE and AMFI, cut down. Each test pins one known row to its published
values. When a source changes its format, refresh the fixture from a new download and update the pinned row.
"""

from datetime import date
from pathlib import Path

import pytest

from finadvisor.market import parse

FIX = Path(__file__).parent / "fixtures" / "market"


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name,exchange,day,symbol,isin,close", [
    ("nse_bhav_2026-11-12.csv", "NSE", date(2026, 11, 12), "RELIANCE", "INE002A01018", 1339.7),
    ("nse_bhav_2026-11-12.csv", "NSE", date(2026, 11, 12), "NIFTYBEES", "INF204KB14I2", 288.22),
    ("bse_bhav_2026-10-30.csv", "BSE", date(2026, 10, 30), "RELIANCE", "INE002A01018", 1163.55),
])
def test_bhavcopy_udiff_real_files(name, exchange, day, symbol, isin, close):
    rows = parse.parse_bhav_udiff(read(name))
    assert len(rows) > 50
    assert all(r.exchange == exchange and r.trade_date == day for r in rows)
    assert all(r.isin and len(r.isin) == 12 and r.close and r.close > 0 for r in rows)
    row = next(r for r in rows if r.symbol == symbol)
    assert (row.isin, row.close) == (isin, close)
    assert row.low <= row.close <= row.high


def test_amfi_navall_real_file():
    rows = parse.parse_amfi_navall(read("amfi_navall_2026-11-08.txt"))
    assert len(rows) > 15
    assert all(r.code.isdigit() and r.nav and r.nav > 0 and r.nav_date for r in rows)
    pp = next(r for r in rows if r.code == "122639")
    assert (pp.isin_growth, pp.amc, pp.category, pp.plan, pp.option) == (
        "INF879O01027", "PPFAS Mutual Fund", "Equity Scheme - Flexi Cap Fund", "Direct", "Growth")
    assert (pp.nav, pp.nav_date) == (93.9483, date(2026, 11, 6))


def test_nse_index_close_real_file():
    rows = parse.parse_index_close(read("nse_indices_2026-11-08.csv"))
    assert len(rows) > 30
    nifty = next(r for r in rows if r.name == "Nifty 50")
    assert (nifty.trade_date, nifty.close) == (date(2026, 11, 8), 24986.4)


def test_nse_52_week_real_file():
    rows = parse.parse_nse_52w(read("nse_52w_2026-10-30.csv"))
    assert len(rows) > 50
    assert rows[0].symbol == "1STCUS$" and rows[0].high is None      # "-" in the file means no value
    priced = [r for r in rows if r.high is not None]
    assert priced and all(r.low is None or r.low <= r.high for r in priced)
