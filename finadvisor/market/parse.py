"""Parsers for the official files. Pure functions over text, tested with real-format fixtures."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if s in ("", "-", "N.A.", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class BhavRow:
    exchange: str
    trade_date: date
    symbol: str
    isin: str
    series: str
    name: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    prev_close: float | None
    volume: float | None
    instrument_type: str


def parse_bhav_udiff(text: str) -> list[BhavRow]:
    """NSE and BSE share the UDiFF common bhavcopy format (one row per security per day)."""
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("FinInstrmTp") not in ("STK", "ETF") and not (r.get("SctySrs") in ("GB",)):
            continue
        close = _num(r.get("ClsPric"))
        if close is None:
            continue
        out.append(BhavRow(
            exchange=r.get("Src", "").strip() or "NSE",
            trade_date=datetime.strptime(r["TradDt"], "%Y-%m-%d").date(),
            symbol=(r.get("TckrSymb") or "").strip(),
            isin=(r.get("ISIN") or "").strip(),
            series=(r.get("SctySrs") or "").strip(),
            name=(r.get("FinInstrmNm") or "").strip(),
            open=_num(r.get("OpnPric")), high=_num(r.get("HghPric")), low=_num(r.get("LwPric")), close=close,
            prev_close=_num(r.get("PrvsClsgPric")), volume=_num(r.get("TtlTradgVol")),
            instrument_type=r.get("FinInstrmTp", ""),
        ))
    return out


NSE_EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST", "GB"}


@dataclass
class Scheme:
    code: str
    isin_growth: str | None
    isin_reinvest: str | None
    name: str
    amc: str
    category: str
    plan: str | None          # Direct / Regular
    option: str | None        # Growth / IDCW
    nav: float | None
    nav_date: date | None


_CATEGORY = re.compile(r"^(Open|Close|Interval) Ended Schemes\s*\((.*)\)\s*$")


def parse_amfi_navall(text: str) -> list[Scheme]:
    """AMFI NAVAll.txt: category header lines, AMC lines, then 'code;isin1;isin2;name;plan;option;nav;date' rows.
    Older files have 6 columns (no plan/option); both are handled."""
    out: list[Scheme] = []
    category = amc = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("Scheme Code"):
            continue
        m = _CATEGORY.match(line)
        if m:
            category = m.group(2).strip()
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
            if ";" not in line:
                amc = line
            continue
        if len(parts) >= 8:
            code, i1, i2, name, plan, option, nav, d = parts[:8]
        else:
            code, i1, i2, name, nav, d = parts[:6]
            plan = "Direct" if "direct" in name.lower() else ("Regular" if "regular" in name.lower() else None)
            option = "Growth" if "growth" in name.lower() else ("IDCW" if re.search(r"idcw|dividend", name, re.I) else None)
        try:
            nav_date = datetime.strptime(d, "%d-%b-%Y").date()
        except ValueError:
            nav_date = None
        out.append(Scheme(code, None if i1 in ("-", "") else i1, None if i2 in ("-", "") else i2, name, amc, category,
                          (plan or "").replace(" Plan", "") or None, (option or "").replace(" Option", "") or None,
                          _num(nav), nav_date))
    return out


@dataclass
class IndexRow:
    name: str
    trade_date: date
    close: float


def parse_index_close(text: str) -> list[IndexRow]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        v = _num(r.get("Closing Index Value"))
        if v is None:
            continue
        out.append(IndexRow(r["Index Name"].strip(), datetime.strptime(r["Index Date"].strip(), "%d-%m-%Y").date(), v))
    return out


@dataclass
class Week52:
    symbol: str
    series: str
    high: float | None
    high_date: date | None
    low: float | None
    low_date: date | None


def parse_nse_52w(text: str) -> list[Week52]:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('"SYMBOL"'))
    out = []

    def dt(s):
        try:
            return datetime.strptime(s.strip(), "%d-%b-%Y").date()
        except ValueError:
            return None
    for r in csv.reader(lines[start + 1:]):
        if len(r) < 6:
            continue
        out.append(Week52(r[0].strip(), r[1].strip(), _num(r[2]), dt(r[3]), _num(r[4]), dt(r[5])))
    return out
