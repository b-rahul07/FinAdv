"""Point-to-point fund returns from a NAV history, as AMFI and fund factsheets report them."""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from dateutil.relativedelta import relativedelta

# A NAV this many days before the anniversary still counts (weekends, holidays); an older one means no data.
MAX_GAP_DAYS = 7


def nav_on_or_before(navs: list[tuple[date, float]], d: date) -> tuple[date, float] | None:
    """`navs` sorted by date. The last NAV published on or before `d`, if it is at most MAX_GAP_DAYS old."""
    i = bisect_right([x[0] for x in navs], d)
    if i == 0:
        return None
    nd, nav = navs[i - 1]
    return (nd, nav) if (d - nd).days <= MAX_GAP_DAYS else None


def annualised_return(navs: list[tuple[date, float]], years: int) -> float | None:
    """Return over the last `years` years as a fraction a year (CAGR; 0.12 = 12%), ending at the latest NAV.
    None when the fund is younger than that or the history has a gap at the start date."""
    if not navs or years < 1:
        return None
    end_d, end_nav = navs[-1]
    start = nav_on_or_before(navs, end_d - relativedelta(years=years))
    if start is None or start[1] <= 0:
        return None
    return (end_nav / start[1]) ** (1 / years) - 1
