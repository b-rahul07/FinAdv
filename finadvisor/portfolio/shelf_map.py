"""Map what someone already holds onto the advisor's product types, so a reply can start from their portfolio.

Mutual funds use AMFI's scheme category ("Equity Scheme - Small Cap Fund", "Debt Scheme - Liquid Fund", ...); listed
securities use their kind and name. Used only for the reply text ("What you already have"); plans are unchanged.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

MF_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"index|etf", re.I), "large_cap_index_fund"),
    (re.compile(r"elss|tax saver", re.I), "elss"),
    (re.compile(r"small cap|mid cap", re.I), "mid_small_cap_fund"),
    (re.compile(r"liquid|overnight|money market", re.I), "liquid_fund"),
    (re.compile(r"gold|silver", re.I), "gold_etf_fund"),
    (re.compile(r"hybrid|balanced|arbitrage|asset allocation", re.I), "hybrid_baf"),
    (re.compile(r"debt|gilt|bond|duration|credit|banking and psu|floater", re.I), "short_duration_debt_fund"),
    (re.compile(r"equity|large|flexi|multi|focused|value|contra|sectoral|thematic|dividend", re.I), "flexi_cap_fund"),
]


def product_of(inst: dict) -> str | None:
    kind, name = inst.get("kind"), (inst.get("name") or "")
    if kind == "stock":
        return "direct_equity"
    if kind == "sgb" or (kind == "etf" and re.search(r"gold|silver", name, re.I)):
        return "gold_etf_fund"
    if kind == "etf":
        return "large_cap_index_fund"
    if kind == "mf":
        text = f"{inst.get('category') or ''} {name}"
        for pat, pid in MF_RULES:
            if pat.search(text):
                return pid
    return None


def existing(s: Session, user_id: str, tax_cfg: dict) -> list[dict]:
    """Current market value per product type: [{"product_id", "value"}], largest first."""
    from finadvisor.portfolio.service import holdings
    totals: dict[str, float] = {}
    for h in holdings(s, user_id, tax_cfg)["items"]:
        pid = product_of(h["instrument"])
        if pid and h.get("value"):
            totals[pid] = totals.get(pid, 0) + h["value"]
    return [{"product_id": k, "value": round(v, 2)} for k, v in sorted(totals.items(), key=lambda x: -x[1])]
