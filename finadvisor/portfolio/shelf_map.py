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
    from finadvisor.portfolio.service import holdings
    return summarise(holdings(s, user_id, tax_cfg)["items"])


def summarise(items: list[dict]) -> list[dict]:
    """Per product type, largest first: [{"product_id", "value", "invested", "funds", "regular"}]. `funds` counts the
    mutual funds; `regular` lists those held in a Regular plan ({"name", "value", "code"}), which the same scheme's
    Direct plan would cost less."""
    out: dict[str, dict] = {}
    for h in items:
        pid = product_of(h["instrument"])
        if not pid or not h.get("value"):
            continue
        p = out.setdefault(pid, {"product_id": pid, "value": 0.0, "invested": 0.0, "funds": 0, "regular": []})
        p["value"] += h["value"]
        p["invested"] += h.get("invested") or 0
        inst = h["instrument"]
        if inst.get("kind") == "mf":
            p["funds"] += 1
            if (inst.get("plan") or "").lower() == "regular":
                p["regular"].append({"name": inst["name"], "value": round(h["value"], 2), "code": inst.get("scheme_code")})
    for p in out.values():
        p["value"], p["invested"] = round(p["value"], 2), round(p["invested"], 2)
    return sorted(out.values(), key=lambda p: -p["value"])
