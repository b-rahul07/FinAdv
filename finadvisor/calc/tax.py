"""Capital-gains classification and estimates (estimated, not tax advice)."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta


def is_long_term_equity(bought: date, sold_or_today: date, tax_cfg: dict) -> bool:
    """Long-term when held MORE than N months (N = 12 for listed equity and equity funds)."""
    months = tax_cfg["equity"]["long_term_after_months"]
    return sold_or_today > bought + relativedelta(months=months)


def equity_tax_estimate(ltcg: float, stcg: float, tax_cfg: dict, ltcg_exemption_used: float = 0.0) -> dict:
    e = tax_cfg["equity"]
    exemption_left = max(0.0, e["ltcg_annual_exemption_inr"] - ltcg_exemption_used)
    taxable_lt = max(0.0, ltcg - exemption_left)
    lt_tax = taxable_lt * e["ltcg_rate"]
    st_tax = max(0.0, stcg) * e["stcg_rate"]
    return {
        "taxable_ltcg": taxable_lt,
        "ltcg_tax": lt_tax,
        "stcg_tax": st_tax,
        "total": lt_tax + st_tax,
        "financial_year": tax_cfg["financial_year"],
        "note": "Estimated, not tax advice. Excludes cess, surcharge and set-off of losses.",
    }
