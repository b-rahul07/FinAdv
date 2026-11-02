"""XIRR: annualised return for dated cash flows (investments negative, withdrawals/current value positive)."""

from __future__ import annotations

from datetime import date


def _npv(rate: float, flows: list[tuple[date, float]]) -> float:
    t0 = flows[0][0]
    return sum(cf / (1 + rate) ** ((d - t0).days / 365.0) for d, cf in flows)


def _dnpv(rate: float, flows: list[tuple[date, float]]) -> float:
    t0 = flows[0][0]
    total = 0.0
    for d, cf in flows:
        t = (d - t0).days / 365.0
        total -= t * cf / (1 + rate) ** (t + 1)
    return total


def xirr(flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Return XIRR as a fraction (0.12 = 12%), or None when it is undefined.

    Undefined when flows don't contain both signs or no root exists in (-99.99%, 1,00,000%).
    Uses Newton's method, falling back to bisection.
    """
    flows = sorted(((d, float(cf)) for d, cf in flows if cf != 0), key=lambda x: x[0])
    if len(flows) < 2 or not (any(cf < 0 for _, cf in flows) and any(cf > 0 for _, cf in flows)):
        return None
    if flows[0][0] == flows[-1][0]:
        return None

    rate = guess
    for _ in range(100):
        f = _npv(rate, flows)
        df = _dnpv(rate, flows)
        if df == 0:
            break
        new = rate - f / df
        if new <= -0.9999:
            break
        if abs(new - rate) < 1e-10:
            return new
        rate = new

    lo, hi = -0.9999, 1000.0
    f_lo, f_hi = _npv(lo, flows), _npv(hi, flows)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, flows)
        if abs(f_mid) < 1e-9 or (hi - lo) < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def is_annualisable(start: date, end: date) -> bool:
    """Brief §4.4: returns over less than a year are never shown annualised."""
    return (end - start).days >= 365
