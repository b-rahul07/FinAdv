"""Valuation of deposits, retirement and small savings, cash, physical/digital gold and silver, property and other
assets, plus liabilities. Each value carries its source and as-of date (brief §2.7)."""

from __future__ import annotations

from datetime import date
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from finadvisor.calc.deposits import fd_value, rd_value
from finadvisor.db.models import Instrument, InsurancePolicy, Liability, OtherAsset, PriceDaily

KIND_CLASS = {
    "fd": "deposits", "rd": "deposits",
    "epf": "retirement", "ppf": "retirement", "nps": "retirement", "ssy": "retirement",
    "savings": "cash", "cash": "cash",
    "gold_physical": "gold", "gold_digital": "gold",
    "silver_physical": "silver",
    "property": "other", "vehicle": "other", "other": "other",
}
LIQUID_KINDS = {"savings", "cash", "fd"}           # counted towards emergency savings on the profile proposal
SELF_REPORTED = {"property", "vehicle", "other", "silver_physical"}
GOLD_REF_KEY = "GOLD_REF_999"
GOLD_REF_SOURCE = "Reference: median NSE close of Sovereign Gold Bonds (1 unit = 1 g of 999 gold; SGBs can trade at a premium or discount)"


def gold_reference_from_bhav(rows) -> float | None:
    """Median close of SGB series with trades that day. Each SGB unit is one gram of 999 gold."""
    closes = [r.close for r in rows if r.series == "GB" and (r.volume or 0) > 0 and r.close > 0]
    return median(closes) if len(closes) >= 3 else None


def gold_reference(s: Session, as_of: date) -> tuple[float, date, str] | None:
    inst = s.scalar(select(Instrument).where(Instrument.kind == "index", Instrument.key == GOLD_REF_KEY))
    if inst is None:
        return None
    p = s.scalar(select(PriceDaily).where(PriceDaily.instrument_id == inst.id, PriceDaily.date <= as_of)
                 .order_by(PriceDaily.date.desc()).limit(1))
    return (p.close, p.date, p.source) if p else None


def _date(x) -> date | None:
    return date.fromisoformat(x) if isinstance(x, str) and x else (x if isinstance(x, date) else None)


def value_asset(a: OtherAsset, as_of: date, gold: tuple[float, date, str] | None) -> dict:
    d = a.data or {}
    out = {"id": a.id, "kind": a.kind, "name": a.name, "asset_class": KIND_CLASS.get(a.kind, "other"),
           "account_last4": a.account_last4, "data": d, "value": None, "source": None, "as_of": None,
           "self_reported": a.kind in SELF_REPORTED, "note": None}
    if a.kind in ("fd", "rd"):
        start, maturity = _date(d.get("start")), _date(d.get("maturity"))
        if not (start and maturity and d.get("rate_pa") is not None):
            out["note"] = "Missing start, maturity or rate."
            return out
        if a.kind == "fd":
            v = fd_value(float(d["principal"]), float(d["rate_pa"]), start, as_of, maturity, d.get("compounding", "quarterly"))
        else:
            v = rd_value(float(d["instalment"]), float(d["rate_pa"]), start, as_of, maturity)
        out.update(value=v, source="Computed from your deposit's terms (accrued value, before TDS)",
                   as_of=min(as_of, maturity).isoformat(), matured=as_of >= maturity)
    elif a.kind in ("gold_physical", "gold_digital"):
        grams = float(d.get("grams") or 0)
        purity = float(d.get("purity") or 999) if a.kind == "gold_physical" else 999.0
        if gold is None:
            out["note"] = "No gold reference rate yet."
            return out
        rate, rdate, src = gold
        out.update(value=grams * purity / 999 * rate, source=src, as_of=rdate.isoformat(), rate_per_gram_999=rate)
    elif a.kind == "silver_physical":
        grams, rate = float(d.get("grams") or 0), d.get("rate_per_gram")
        purity = float(d.get("purity") or 999)
        if rate:
            out.update(value=grams * purity / 999 * float(rate), source="Rate entered by you (no free silver reference)",
                       as_of=d.get("rate_date") or a.created_at.date().isoformat())
        else:
            out["note"] = "Enter a rate per gram to value this."
    else:
        out.update(value=float(d.get("balance") or 0), source="Entered by you" + (" (self-reported)" if a.kind in SELF_REPORTED else ""),
                   as_of=d.get("as_of") or a.created_at.date().isoformat())
    return out


def others(s: Session, user_id: str, as_of: date) -> dict:
    gold = gold_reference(s, as_of)
    assets = [value_asset(a, as_of, gold) for a in s.scalars(select(OtherAsset).where(OtherAsset.user_id == user_id)
                                                              .order_by(OtherAsset.created_at))]
    loans = [{"id": l.id, "kind": l.kind, "lender": l.lender, "outstanding": l.outstanding, "rate_pa": l.rate_pa,
              "emi_monthly": l.emi_monthly, "end_date": l.end_date.isoformat() if l.end_date else None,
              "as_of": l.as_of.isoformat(), "account_last4": l.account_last4, "source": "Entered by you"}
             for l in s.scalars(select(Liability).where(Liability.user_id == user_id).order_by(Liability.created_at))]
    cover = [{"id": c.id, "kind": c.kind, "insurer": c.insurer, "sum_assured": c.sum_assured, "premium_yearly": c.premium_yearly,
              "renewal_date": c.renewal_date.isoformat() if c.renewal_date else None, "employer_provided": c.employer_provided}
             for c in s.scalars(select(InsurancePolicy).where(InsurancePolicy.user_id == user_id))]
    return {"assets": assets, "liabilities": loans, "insurance": cover,
            "gold_reference": {"rate_per_gram_999": gold[0], "as_of": gold[1].isoformat(), "source": gold[2]} if gold else None}


def profile_proposal(current: dict, other: dict, holdings_items: list[dict]) -> tuple[dict, list[str]]:
    """Facts implied by tracked holdings. Returned as a proposal for the profile card, never applied directly."""
    liquid = sum(a["value"] or 0 for a in other["assets"] if a["kind"] in LIQUID_KINDS)
    liquid += sum(h["value"] or 0 for h in holdings_items
                  if h["instrument"]["kind"] == "mf" and any(w in (h["instrument"]["category"] or "") for w in ("Liquid", "Overnight", "Money Market")))
    proposed = dict(current)
    changed = []

    def put(k, v):
        if v is not None and round(float(v), 2) != round(float(current.get(k) or 0), 2):
            proposed[k] = v
            changed.append(k)
    put("liquid_savings", round(liquid, 2))
    put("life_cover", sum(c["sum_assured"] for c in other["insurance"] if c["kind"] == "term"))
    put("health_cover", sum(c["sum_assured"] for c in other["insurance"] if c["kind"] == "health" and not c["employer_provided"]))
    debts = [{"kind": l["kind"], "label": l["lender"], "outstanding": l["outstanding"], "rate_pa": l["rate_pa"],
              "emi_monthly": l["emi_monthly"]} for l in other["liabilities"]]
    if debts and debts != current.get("debts"):
        proposed["debts"] = debts
        changed.append("debts")
    return proposed, changed
