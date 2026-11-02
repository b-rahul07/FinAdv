"""Lots, corporate-action adjustment, valuation, XIRR flows, 52-week range and value series.

Conventions
- A corporate action with `factor` f on ex-date E means: prices before E are multiplied by f to be comparable
  with prices from E on (a 1:1 bonus or 2-for-1 split has f = 0.5). Quantities held before E are divided by f.
- All comparisons across dates (P&L, 52-week range, charts, change since added) use adjusted values.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


@dataclass(frozen=True)
class Tx:
    date: date
    kind: str            # buy | sell
    qty: float
    price: float
    charges: float = 0.0


@dataclass(frozen=True)
class Action:
    ex_date: date
    factor: float


@dataclass
class Lot:
    date: date
    qty: float
    price: float         # adjusted cost per unit, charges included

    @property
    def cost(self) -> float:
        return self.qty * self.price


@dataclass
class Realised:
    buy_date: date
    sell_date: date
    qty: float
    buy_price: float
    sell_price: float
    long_term: bool

    @property
    def gain(self) -> float:
        return self.qty * (self.sell_price - self.buy_price)


# --------------------------------------------------------------------------- adjustments

def factor_after(d: date, actions: list[Action]) -> float:
    """Product of factors for actions whose ex-date is after d (i.e. that d's prices still need)."""
    f = 1.0
    for a in actions:
        if a.ex_date > d:
            f *= a.factor
    return f


def adjust_tx(t: Tx, actions: list[Action]) -> Tx:
    f = factor_after(t.date, actions)
    return Tx(t.date, t.kind, t.qty / f, t.price * f, t.charges)


def classify(factor: float) -> str:
    """Splits and bonuses have simple ratios (2:1, 1:1, 1:10 -> factor 10/11) and cut prices by at least ~9%."""
    if factor > 0.92:
        return "other_adjustment"
    inv = 1 / factor
    for n in range(1, 11):
        if abs(inv * n - round(inv * n)) < 0.02:
            return "split_or_bonus"
    return "other_adjustment"


def _simple_fraction(r: float, tol: float = 0.04) -> float | None:
    """Nearest split/bonus ratio p/q (q <= 10, or 1/k up to 1/100) within a relative tolerance."""
    best = None
    for q in range(2, 101):
        for p in ([1] if q > 10 else range(1, q)):
            f = p / q
            if abs(r / f - 1) <= tol and (best is None or abs(r / f - 1) < abs(r / best - 1)):
                best = f
    return best


def derive_actions(rows: list[tuple[date, float, float | None]], max_ratio: float = 0.7) -> list[Action]:
    """Find splits and bonuses from consecutive end-of-day rows (date, close, prev_close).

    Two signals, both requiring a simple ratio (1:2, 1:5, 1:10, 2:3, 1:100 ...) and a fall beyond any normal
    circuit limit (ratio <= 0.7):
      1. the exchange published the previous close already adjusted: prev_close(t) / close(t-1) ~ p/q;
      2. the previous close is unadjusted (as NSE does on split dates) and the close itself gaps: close(t) / close(t-1) ~ p/q.
    Small adjustments (dividends) and gaps from a missed session are ignored: dividends are income, not a
    change in units, and NSE's adjusted 52-week figures exclude them."""
    out = []
    rows = sorted(rows)
    for (d0, c0, _), (d1, c1, p1) in zip(rows, rows[1:]):
        if c0 <= 0:
            continue
        f = None
        if p1 is not None and p1 / c0 <= max_ratio:
            f = _simple_fraction(p1 / c0)
        elif (p1 is None or abs(p1 / c0 - 1) < 0.01) and c1 / c0 <= max_ratio:
            f = _simple_fraction(c1 / c0)
        if f:
            out.append(Action(d1, f))
    return out


def adjusted_prices(prices: list[tuple[date, float]], actions: list[Action]) -> list[tuple[date, float]]:
    return [(d, p * factor_after(d, actions)) for d, p in prices]


# --------------------------------------------------------------------------- lots and realised gains

def is_long_term(buy: date, sell: date, months: int = 12) -> bool:
    return sell > buy + relativedelta(months=months)


def fifo(txs: list[Tx], long_term_months: int = 12) -> tuple[list[Lot], list[Realised]]:
    """Open lots and realised gains, first-in first-out. Inputs must already be adjusted."""
    lots: list[Lot] = []
    realised: list[Realised] = []
    for t in sorted(txs, key=lambda t: (t.date, 0 if t.kind == "buy" else 1)):
        if t.kind == "buy":
            lots.append(Lot(t.date, t.qty, (t.qty * t.price + t.charges) / t.qty))
            continue
        left = t.qty
        sell_price = (t.qty * t.price - t.charges) / t.qty
        while left > 1e-9:
            if not lots:
                raise ValueError(f"sell on {t.date} exceeds holdings by {left:g}")
            lot = lots[0]
            take = min(lot.qty, left)
            realised.append(Realised(lot.date, t.date, take, lot.price, sell_price,
                                     is_long_term(lot.date, t.date, long_term_months)))
            lot.qty -= take
            left -= take
            if lot.qty <= 1e-9:
                lots.pop(0)
    return lots, realised


# --------------------------------------------------------------------------- valuation

@dataclass
class Position:
    qty: float
    avg_price: float
    invested: float
    price: float | None
    price_date: date | None
    prev_price: float | None
    value: float | None
    day_change: float | None
    day_change_pct: float | None
    unrealised: float | None
    unrealised_pct: float | None
    first_buy: date | None
    holding_days: int | None
    long_term_qty: float
    short_term_qty: float
    realised: float = 0.0
    lots: list[Lot] = field(default_factory=list)


def position(txs_adjusted: list[Tx], price: float | None, price_date: date | None, prev_price: float | None,
             as_of: date, long_term_months: int = 12) -> Position:
    lots, realised = fifo(txs_adjusted, long_term_months)
    qty = sum(l.qty for l in lots)
    invested = sum(l.cost for l in lots)
    avg = invested / qty if qty > 1e-9 else 0.0
    value = qty * price if price is not None else None
    day = qty * (price - prev_price) if price is not None and prev_price is not None else None
    day_pct = (price / prev_price - 1) if price is not None and prev_price else None
    unr = value - invested if value is not None else None
    unr_pct = unr / invested if unr is not None and invested > 0 else None
    first = min((l.date for l in lots), default=None)
    lt = sum(l.qty for l in lots if is_long_term(l.date, as_of, long_term_months))
    return Position(qty, avg, invested, price, price_date, prev_price, value, day, day_pct, unr, unr_pct, first,
                    (as_of - first).days if first else None, lt, qty - lt, sum(r.gain for r in realised), lots)


def xirr_flows(txs: list[Tx], value_now: float | None, as_of: date) -> list[tuple[date, float]]:
    flows = [(t.date, -(t.qty * t.price + t.charges) if t.kind == "buy" else (t.qty * t.price - t.charges)) for t in txs]
    if value_now:
        flows.append((as_of, value_now))
    return flows


def week52(rows: list[tuple[date, float | None, float | None, float]], actions: list[Action], as_of: date) -> tuple[float, float] | None:
    """(low, high) over the 52 weeks to as_of, from adjusted daily highs/lows (close when high/low missing)."""
    start = as_of - relativedelta(years=1)   # NSE's window includes the same date one year earlier
    lows, highs = [], []
    for d, hi, lo, cl in rows:
        if start <= d <= as_of:
            f = factor_after(d, actions)
            highs.append((hi if hi is not None else cl) * f)
            lows.append((lo if lo is not None else cl) * f)
    if not highs:
        return None
    return min(lows), max(highs)


def last_on_or_before(series: list[tuple[date, float]], d: date) -> tuple[date, float] | None:
    """series sorted by date."""
    i = bisect.bisect_right(series, (d, float("inf"))) - 1
    return series[i] if i >= 0 else None


def value_series(holdings: dict[str, list[Tx]], prices: dict[str, list[tuple[date, float]]], dates: list[date]) -> list[dict]:
    """Daily value and net money put in, for each date. Inputs adjusted; prices sorted by date.
    A day where an instrument has no price yet uses its last known price; before its first price it is left out
    and counted in `missing` so the chart can say so."""
    out = []
    for d in dates:
        value = 0.0
        net_in = 0.0
        missing = 0
        for iid, txs in holdings.items():
            q = 0.0
            for t in txs:
                if t.date <= d:
                    q += t.qty if t.kind == "buy" else -t.qty
                    net_in += (t.qty * t.price + t.charges) if t.kind == "buy" else -(t.qty * t.price - t.charges)
            if q <= 1e-9:
                continue
            p = last_on_or_before(prices.get(iid, []), d)
            if p is None:
                missing += 1
                continue
            value += q * p[1]
        out.append({"date": d, "value": value, "net_invested": net_in, "missing": missing})
    return out
