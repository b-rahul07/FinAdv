"""Income tax on salary under both regimes (estimated, not tax advice). Rules live in configs/income_tax/*.yaml.

Scope: a resident individual below 60 with salary income. Left out and said so with every answer: other income,
home-loan interest, parents' health cover, employer NPS, marginal relief on surcharge.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs" / "income_tax"
DEDUCTION_FIELDS = ("deductions_80c", "deductions_80d", "nps_80ccd1b", "hra_exemption_annual")


@lru_cache(maxsize=4)
def rules(stem: str = "fy2026_27") -> dict:
    return yaml.safe_load((CONFIG_DIR / f"{stem}.yaml").read_text(encoding="utf-8"))


def slab_tax(taxable: float, slabs: list) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        if upper is None or taxable <= upper:
            return tax + max(0.0, taxable - lower) * rate
        tax += (upper - lower) * rate
        lower = upper
    return tax


def slab_rate(taxable: float, slabs: list) -> float:
    """The rate on the next rupee of taxable income."""
    for upper, rate in slabs:
        if upper is None or taxable < upper:
            return rate
    return slabs[-1][1]


def regime_tax(gross: float, deductions: dict[str, float], regime: dict, cess: float) -> dict:
    """Tax for one regime. `deductions` maps the person's fields to the amounts they claim; each is capped as the
    regime allows, and a regime that does not allow a deduction ignores it."""
    allowed = {}
    for field, cap in (regime.get("deductions") or {}).items():
        amount = max(0.0, float(deductions.get(field) or 0))
        allowed[field] = amount if cap is None else min(amount, cap)
    std = min(regime["standard_deduction"], gross)
    taxable = max(0.0, gross - std - sum(allowed.values()))
    before = slab_tax(taxable, regime["slabs"])
    reb = regime["rebate"]
    if taxable <= reb["income_up_to"]:
        rebate = min(before, reb["max"])
    elif reb.get("marginal_relief"):
        rebate = max(0.0, before - (taxable - reb["income_up_to"]))     # tax cannot exceed the income above the limit
    else:
        rebate = 0.0
    after = before - rebate
    rate = 0.0
    for above, r in regime.get("surcharge") or []:
        if taxable > above:
            rate = r
    surcharge = after * rate
    cess_amt = (after + surcharge) * cess
    total = after + surcharge + cess_amt
    return {"label": regime["label"], "gross": gross, "standard_deduction": std, "deductions": allowed,
            "deductions_total": sum(allowed.values()), "taxable": taxable, "tax_before_rebate": before, "rebate": rebate,
            "surcharge": surcharge, "cess": cess_amt, "total": total,
            # the rate the next rupee of income bears: nil while the rebate wipes the tax out
            "marginal_rate": 0.0 if after == 0 else slab_rate(taxable, regime["slabs"]) * (1 + rate) * (1 + cess)}


def compare(gross: float, deductions: dict[str, float] | None = None, cfg: dict | None = None) -> dict:
    """Both regimes for a gross salary, the cheaper one, and the rupee difference."""
    cfg = cfg or rules()
    deductions = deductions or {}
    new = regime_tax(gross, deductions, cfg["new"], cfg["cess"])
    old = regime_tax(gross, deductions, cfg["old"], cfg["cess"])
    diff = old["total"] - new["total"]
    better = "same" if abs(diff) < 1 else ("new" if diff > 0 else "old")
    return {"financial_year": cfg["financial_year"], "as_of": str(cfg["as_of"]), "version": cfg["version"],
            "new": new, "old": old, "better": better, "saving": abs(diff),
            "not_modelled": cfg["not_modelled"]}


def room(deductions: dict[str, float], cfg: dict | None = None) -> dict[str, float]:
    """Unused room under each capped old-regime deduction."""
    cfg = cfg or rules()
    return {f: max(0.0, cap - float(deductions.get(f) or 0))
            for f, cap in cfg["old"]["deductions"].items() if cap is not None}


def with_full_deductions(gross: float, deductions: dict[str, float] | None = None, cfg: dict | None = None) -> dict:
    """The same comparison if the person used all of 80C and the extra NPS deduction: what investing in ELSS, PPF or
    NPS would do to the tax under each regime (nothing under the new regime)."""
    cfg = cfg or rules()
    deductions = dict(deductions or {})
    base = compare(gross, deductions, cfg)
    caps = cfg["old"]["deductions"]
    filled = {**deductions, "deductions_80c": caps["deductions_80c"], "nps_80ccd1b": caps["nps_80ccd1b"]}
    full = compare(gross, filled, cfg)
    extra = (filled["deductions_80c"] - min(float(deductions.get("deductions_80c") or 0), caps["deductions_80c"])
             + filled["nps_80ccd1b"] - min(float(deductions.get("nps_80ccd1b") or 0), caps["nps_80ccd1b"]))
    return {"extra_invested": extra, "old_tax_now": base["old"]["total"], "old_tax_full": full["old"]["total"],
            "old_saving": base["old"]["total"] - full["old"]["total"], "new_tax": base["new"]["total"],
            "better_after": full["better"], "saving_after": full["saving"]}


def fd_vs_debt_fund(amount: float, years: int, fd_rate_pct: float, fund_rate_pct: float, marginal_rate: float) -> dict:
    """What `amount` becomes after tax in a bank FD and in a debt fund. Both are taxed at the person's slab rate; the
    FD's interest is taxed every year as it accrues, the fund's gain once, when it is sold (funds bought after
    1 Apr 2023). Rates are planning assumptions, not promises."""
    fd = amount * (1 + fd_rate_pct / 100 * (1 - marginal_rate)) ** years
    grown = amount * (1 + fund_rate_pct / 100) ** years
    fund = grown - (grown - amount) * marginal_rate
    return {"amount": amount, "years": years, "fd_rate_pct": fd_rate_pct, "fund_rate_pct": fund_rate_pct,
            "marginal_rate": marginal_rate, "fd_after_tax": fd, "debt_fund_after_tax": fund,
            "difference": fund - fd}
