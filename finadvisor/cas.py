"""Consolidated Account Statement import (casparser). Brief §5.5.

- The PDF is parsed in memory and never written to disk or the database; the password is used once and dropped.
- Only PII-free fields are kept: no names, PAN, email, address, mobile; folio/account numbers reduced to last 4.
- CAMS/KFintech detailed CAS -> mutual fund transactions. Summary and demat (NSDL/CDSL) CAS -> holdings only,
  so the user supplies cost and date before import (a CAS is a month-end snapshot, not a price source).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

BUY_TYPES = {"PURCHASE", "PURCHASE_SIP", "SWITCH_IN", "SWITCH_IN_MERGER", "DIVIDEND_REINVEST", "GIFT_IN"}
SELL_TYPES = {"REDEMPTION", "SWITCH_OUT", "SWITCH_OUT_MERGER", "GIFT_OUT"}
CHARGE_TYPES = {"STAMP_DUTY_TAX", "STT_TAX"}


class CasError(Exception):
    pass


def last4(x: str | None) -> str | None:
    digits = "".join(ch for ch in (x or "") if ch.isalnum())
    return digits[-4:] if digits else None


def _d(x) -> date | None:
    if isinstance(x, date):
        return x
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(x), fmt).date()
        except ValueError:
            continue
    return None


def _f(x) -> float | None:
    if x is None:
        return None
    return float(x) if isinstance(x, (int, float, Decimal)) else float(str(x).replace(",", ""))


def read(pdf: bytes, password: str) -> dict:
    """Parse with casparser. Raises CasError with a user-safe message."""
    import casparser  # heavy import, only when needed
    try:
        return casparser.read_cas_pdf(io.BytesIO(pdf), password, output="dict")
    except Exception as e:  # noqa: BLE001 - casparser raises several types; never echo the password
        msg = str(e).lower()
        if "password" in msg or "decrypt" in msg:
            raise CasError("The password did not open this statement. CAS passwords are usually your PAN (CAMS/KFintech) "
                           "or as set when you requested the statement.") from None
        raise CasError("This file could not be read as a CAS. Only original PDFs from CAMS, KFintech, NSDL or CDSL work; "
                       "'printed to PDF' copies do not.") from None


@dataclass
class Item:
    key: str                      # stable id inside the preview
    kind: str                     # mf | stock | etf
    name: str
    isin: str | None
    amfi: str | None
    folio_last4: str | None
    units: float                  # closing balance per the statement
    value: float | None
    nav_or_price: float | None
    valuation_date: str | None
    cost: float | None            # statement's cost value, when given
    transactions: list[dict]      # [{date, kind, units, price, charges}]
    needs_cost: bool              # no transactions: user must give cost and date


def normalise(data: dict) -> dict:
    """casparser dict -> PII-free preview."""
    ftype = str(data.get("file_type") or "UNKNOWN").split(".")[-1]
    period = data.get("statement_period") or {}
    items: list[Item] = []
    warnings = [str(w) for w in data.get("parse_warnings", [])][:20]
    if "folios" in data:
        cas_type = str(data.get("cas_type") or "UNKNOWN").split(".")[-1]
        for fo in data["folios"]:
            for sch in fo.get("schemes", []):
                val = sch.get("valuation") or {}
                txs, pending_charges = [], {}
                for t in sch.get("transactions", []):
                    ttype = str(t.get("type") or "").split(".")[-1]
                    d = _d(t.get("date"))
                    units = _f(t.get("units"))
                    nav = _f(t.get("nav"))
                    if ttype in CHARGE_TYPES and d:
                        pending_charges[d] = pending_charges.get(d, 0.0) + abs(_f(t.get("amount")) or 0.0)
                        continue
                    if not d or not units or not nav:
                        continue
                    kind = "buy" if ttype in BUY_TYPES or (ttype in ("REVERSAL", "MISC") and units > 0) else (
                        "sell" if ttype in SELL_TYPES or units < 0 else None)
                    if kind:
                        txs.append({"date": d.isoformat(), "kind": kind, "units": abs(units), "price": nav, "charges": 0.0,
                                    "type": ttype})
                for t in txs:   # stamp duty is charged on the purchase date
                    if t["kind"] == "buy" and _d(t["date"]) in pending_charges:
                        t["charges"] = round(pending_charges.pop(_d(t["date"])), 2)
                close = _f(sch.get("close")) or 0.0
                items.append(Item(
                    key=f"mf:{sch.get('amfi') or sch.get('isin')}:{last4(fo.get('folio'))}", kind="mf",
                    name=sch.get("scheme", ""), isin=sch.get("isin"), amfi=str(sch.get("amfi") or "") or None,
                    folio_last4=last4(fo.get("folio")), units=close, value=_f(val.get("value")), nav_or_price=_f(val.get("nav")),
                    valuation_date=str(val.get("date")) if val.get("date") else None, cost=_f(val.get("cost")),
                    transactions=txs, needs_cost=not txs and close > 0))
    else:
        cas_type = "DEMAT"
        for acc in data.get("accounts", []):
            acct = last4(acc.get("client_id") or acc.get("dp_id"))
            for eq in acc.get("equities", []):
                items.append(Item(key=f"eq:{eq.get('isin')}:{acct}", kind="stock", name=eq.get("name") or eq.get("isin"),
                                  isin=eq.get("isin"), amfi=None, folio_last4=acct, units=_f(eq.get("num_shares")) or 0.0,
                                  value=_f(eq.get("value")), nav_or_price=_f(eq.get("price")), valuation_date=period.get("to"),
                                  cost=None, transactions=[], needs_cost=True))
            for mf in acc.get("mutual_funds", []):
                items.append(Item(key=f"mf:{mf.get('amfi') or mf.get('isin')}:{acct}", kind="mf", name=mf.get("name") or "",
                                  isin=mf.get("isin"), amfi=mf.get("amfi"), folio_last4=last4(mf.get("folio")) or acct,
                                  units=_f(mf.get("balance")) or 0.0, value=_f(mf.get("value")), nav_or_price=_f(mf.get("nav")),
                                  valuation_date=period.get("to"), cost=_f(mf.get("total_cost")), transactions=[],
                                  needs_cost=True))
    return {
        "file_type": ftype, "cas_type": cas_type,
        "period_from": period.get("from") or period.get("from_"), "period_to": period.get("to"),
        "items": [i.__dict__ for i in items if i.units > 0 or i.transactions],
        "warnings": warnings,
    }


def transactions_for(item: dict, choice: dict) -> list[dict]:
    """What to import for one item. Detailed CAS: its transactions. Snapshot: one opening entry from the user's cost/date."""
    if item["transactions"] and not item["needs_cost"]:
        return item["transactions"]
    cost_per_unit = choice.get("avg_price")
    if cost_per_unit is None and item.get("cost") and item["units"]:
        cost_per_unit = item["cost"] / item["units"]
    when = choice.get("date")
    if not cost_per_unit or not when:
        raise CasError(f"Enter the average cost and purchase date for {item['name']}.")
    return [{"date": when, "kind": "buy", "units": item["units"], "price": float(cost_per_unit), "charges": 0.0,
             "type": "OPENING_BALANCE"}]
