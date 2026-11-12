"""Realised capital gains for a financial year (1 April to 31 March), sale by sale, with an estimated tax.

First-in first-out on prices adjusted for splits and bonuses, the same engine the holdings page uses. Listed shares,
ETFs and equity-oriented funds get the equity rates in configs/tax; other funds are taxed at the person's slab rate
and are listed without an estimate. Estimated, not tax advice.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy.orm import Session

from finadvisor.calc.tax import equity_tax_estimate
from finadvisor.db.models import Instrument
from finadvisor.portfolio import engine as E
from finadvisor.portfolio import service as P

EQUITY_FUND_WORDS = ("equity scheme", "elss", "index fund", "equity")


def fy_of(d: date) -> str:
    """'2026-27' for any date from 1 Apr 2026 to 31 Mar 2027."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def fy_bounds(fy: str) -> tuple[date, date]:
    start = int(fy[:4])
    if fy != f"{start}-{str(start + 1)[-2:]}":
        raise ValueError("Financial year must look like 2026-27")
    return date(start, 4, 1), date(start + 1, 3, 31)


def tax_class(inst: Instrument) -> str:
    """equity: the equity capital-gains rates apply. slab: taxed at the person's income-tax rate."""
    if inst.kind in ("stock", "etf"):
        return "equity"
    if inst.kind == "mf":
        cat = (inst.category or "").lower()
        if "debt" in cat or "liquid" in cat or "money market" in cat or "gilt" in cat:
            return "slab"
        return "equity" if any(w in cat for w in EQUITY_FUND_WORDS) else "slab"
    return "slab"


def statement(s: Session, user_id: str, fy: str, tax_cfg: dict) -> dict:
    start, end = fy_bounds(fy)
    months = tax_cfg["equity"]["long_term_after_months"]
    rows, years = [], set()
    for iid, (inst, txs) in P.holdings_raw(s, user_id).items():
        acts = P.actions_for(s, iid)
        _, realised = E.fifo([E.adjust_tx(P._tx(t), acts) for t in txs], months)
        cls = tax_class(inst)
        for r in realised:
            years.add(fy_of(r.sell_date))
            if not start <= r.sell_date <= end:
                continue
            rows.append({"instrument_id": iid, "name": inst.name if inst.kind == "mf" else (inst.symbol or inst.name),
                         "kind": inst.kind, "tax_class": cls, "buy_date": r.buy_date.isoformat(),
                         "sell_date": r.sell_date.isoformat(), "quantity": r.qty, "buy_price": r.buy_price,
                         "sell_price": r.sell_price, "cost": r.qty * r.buy_price, "proceeds": r.qty * r.sell_price,
                         "gain": r.gain, "term": "long" if r.long_term else "short"})
    rows.sort(key=lambda x: (x["sell_date"], x["name"], x["buy_date"]))

    def total(cls: str, term: str) -> float:
        return sum(x["gain"] for x in rows if x["tax_class"] == cls and x["term"] == term)
    ltcg, stcg = total("equity", "long"), total("equity", "short")
    # a loss in one equity bucket is not set off against the other here; each bucket is floored at zero for the estimate
    est = equity_tax_estimate(max(0.0, ltcg), max(0.0, stcg), tax_cfg)
    return {
        "financial_year": fy, "from": start.isoformat(), "to": end.isoformat(),
        "years": sorted(years | {fy}, reverse=True),
        "rows": rows,
        "equity": {"long_term": ltcg, "short_term": stcg, "exemption": tax_cfg["equity"]["ltcg_annual_exemption_inr"],
                   "taxable_long_term": est["taxable_ltcg"], "long_term_tax": est["ltcg_tax"],
                   "short_term_tax": est["stcg_tax"], "tax": est["total"],
                   "long_term_rate": tax_cfg["equity"]["ltcg_rate"], "short_term_rate": tax_cfg["equity"]["stcg_rate"]},
        "slab": {"gain": total("slab", "long") + total("slab", "short")},
        "rates_of": tax_cfg["financial_year"],
        "note": ("Estimated, not tax advice. First-in first-out. Excludes cess, surcharge, set-off and carry-forward of "
                 "losses. Gains on debt and other non-equity funds are taxed at your slab rate and are not estimated here."
                 + ("" if tax_cfg["financial_year"] == fy else f" Rates of FY {tax_cfg['financial_year']} are applied.")),
    }


def to_csv(st: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([f"Capital gains, FY {st['financial_year']} ({st['from']} to {st['to']})"])
    w.writerow(["Name", "Type", "Taxed as", "Bought", "Sold", "Quantity", "Buy price", "Sell price", "Cost", "Proceeds", "Gain", "Term"])
    for r in st["rows"]:
        w.writerow([r["name"], r["kind"], r["tax_class"], r["buy_date"], r["sell_date"], f"{r['quantity']:.4f}",
                    f"{r['buy_price']:.4f}", f"{r['sell_price']:.4f}", f"{r['cost']:.2f}", f"{r['proceeds']:.2f}",
                    f"{r['gain']:.2f}", r["term"]])
    e = st["equity"]
    w.writerow([])
    w.writerow(["Equity: long-term gain", f"{e['long_term']:.2f}"])
    w.writerow(["Equity: short-term gain", f"{e['short_term']:.2f}"])
    w.writerow(["Equity: estimated tax", f"{e['tax']:.2f}"])
    w.writerow(["Taxed at slab rate: gain", f"{st['slab']['gain']:.2f}"])
    w.writerow([st["note"]])
    return out.getvalue()
