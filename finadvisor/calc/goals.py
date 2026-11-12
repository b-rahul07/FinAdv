"""Goal and SIP arithmetic. SIPs are monthly instalments paid at the start of each month."""

from __future__ import annotations

import math


def monthly_rate(annual_pct: float) -> float:
    """Effective monthly rate equivalent to an annual compounded rate."""
    return (1 + annual_pct / 100) ** (1 / 12) - 1


def inflate(amount_today: float, inflation_pct: float, years: float) -> float:
    return amount_today * (1 + inflation_pct / 100) ** years


def fv_lump(amount: float, annual_pct: float, years: float) -> float:
    return amount * (1 + annual_pct / 100) ** years


def fv_sip(monthly: float, annual_pct: float, months: int) -> float:
    i = monthly_rate(annual_pct)
    if i == 0:
        return monthly * months
    return monthly * ((1 + i) ** months - 1) / i * (1 + i)


def sip_needed(target_fv: float, annual_pct: float, months: int, already_saved: float = 0.0) -> float:
    """Monthly SIP that reaches target_fv in `months`, counting growth on money already saved."""
    if months <= 0:
        raise ValueError("months must be positive")
    gap = target_fv - fv_lump(already_saved, annual_pct, months / 12)
    if gap <= 0:
        return 0.0
    i = monthly_rate(annual_pct)
    if i == 0:
        return gap / months
    return gap / (((1 + i) ** months - 1) / i * (1 + i))


def months_to_target(monthly: float, annual_pct: float, target_today: float, inflation_pct: float,
                     already_saved: float = 0.0, start_month: int = 1, max_months: int = 720) -> int | None:
    """Months from now until savings reach a target that grows with inflation, investing `monthly` from
    `start_month`. None if it isn't reached within `max_months` (60 years)."""
    for n in range(1, max_months + 1):
        paid = max(0, n - (start_month - 1))
        have = fv_sip(monthly, annual_pct, paid) + fv_lump(already_saved, annual_pct, n / 12)
        if have >= inflate(target_today, inflation_pct, n / 12):
            return n
    return None


def months_to_save(gap: float, monthly: float) -> int:
    """Months of a fixed monthly amount needed to cover a gap, without growth (used for priority steps)."""
    if gap <= 0:
        return 0
    if monthly <= 0:
        raise ValueError("monthly must be positive to close a gap")
    return math.ceil(gap / monthly - 1e-9)


def retirement_corpus_today(spend_monthly: float, years: int, return_pct: float, inflation_pct: float) -> float:
    """Corpus, in today's rupees, that pays `spend_monthly` (today's money, rising with inflation) at the start of every
    month for `years`, while what remains earns `return_pct` a year. Worked in real terms, so the result can be used
    as a goal's cost today."""
    real = (1 + return_pct / 100) / (1 + inflation_pct / 100) - 1
    i = (1 + real) ** (1 / 12) - 1
    n = years * 12
    if abs(i) < 1e-12:
        return spend_monthly * n
    return spend_monthly * (1 - (1 + i) ** -n) / i * (1 + i)
