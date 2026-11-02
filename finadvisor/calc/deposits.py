"""Fixed and recurring deposit values."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

COMPOUNDING_PER_YEAR = {"monthly": 12, "quarterly": 4, "half_yearly": 2, "yearly": 1, "simple": 0}


def _years(start: date, end: date) -> float:
    return max(0, (end - start).days) / 365.0


def fd_value(principal: float, rate_pa: float, start: date, as_of: date, maturity: date,
             compounding: str = "quarterly") -> float:
    """Accrued FD value on `as_of` (capped at maturity). Uses fractional periods for partial quarters."""
    end = min(as_of, maturity)
    t = _years(start, end)
    n = COMPOUNDING_PER_YEAR[compounding]
    if n == 0:
        return principal * (1 + rate_pa / 100 * t)
    return principal * (1 + rate_pa / 100 / n) ** (n * t)


def rd_value(instalment: float, rate_pa: float, start: date, as_of: date, maturity: date) -> float:
    """Accrued RD value: monthly instalments on the start day, each compounded quarterly (Indian bank convention)."""
    end = min(as_of, maturity)
    total = 0.0
    k = 0
    while True:
        paid_on = start + relativedelta(months=k)
        if paid_on > end or paid_on >= maturity:
            break
        total += instalment * (1 + rate_pa / 400) ** (4 * _years(paid_on, end))
        k += 1
    return total


def rd_instalments_paid(start: date, as_of: date, maturity: date) -> int:
    k = 0
    while start + relativedelta(months=k) <= min(as_of, maturity) and start + relativedelta(months=k) < maturity:
        k += 1
    return k
