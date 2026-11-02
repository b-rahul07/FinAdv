"""Loan arithmetic."""

from __future__ import annotations

import math


def emi(principal: float, annual_pct: float, months: int) -> float:
    """Standard reducing-balance EMI."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_pct / 1200
    if r == 0:
        return principal / months
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def months_to_repay(principal: float, annual_pct: float, payment: float) -> int | None:
    """Months to clear a loan with a fixed monthly payment; None if the payment never clears it."""
    if principal <= 0:
        return 0
    r = annual_pct / 1200
    if r == 0:
        return math.ceil(principal / payment - 1e-9)
    if payment <= principal * r:
        return None
    n = -math.log(1 - principal * r / payment) / math.log(1 + r)
    return math.ceil(n - 1e-9)


def emi_ratio(total_emi: float, take_home: float) -> float:
    if take_home <= 0:
        return math.inf if total_emi > 0 else 0.0
    return total_emi / take_home
